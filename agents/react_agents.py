"""Agentic multi-agent orchestration with SQLite tools and HITL tool approvals."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from data.sqlite_store import execute_sql, fetch_all

try:
    from langchain_groq import ChatGroq
except ImportError:  # pragma: no cover
    ChatGroq = None

try:
    from langchain.agents import AgentState, create_agent
    from langchain.agents.middleware import HumanInTheLoopMiddleware
    from langgraph.checkpoint.memory import InMemorySaver
except ImportError:  # pragma: no cover
    AgentState = None
    HumanInTheLoopMiddleware = None
    InMemorySaver = None
    create_agent = None


@dataclass
class ToolCall:
    name: str
    args: dict
    agent: str


@dataclass
class RunContext:
    run_time: str
    queue: list[ToolCall] = field(default_factory=list)
    pending_call: ToolCall | None = None
    data: dict = field(default_factory=dict)
    done: bool = False


def _log(state: dict, text: str) -> None:
    state.setdefault("agent_log", []).append(text)


def _transfer(state: dict, frm: str, to: str, reason: str) -> None:
    _log(state, f"handoff: {frm} -> {to} ({reason})")


def get_llm():
    if ChatGroq is None or not os.getenv("GROQ_API_KEY"):
        return None
    return ChatGroq(model="llama-3.3-70b-versatile", temperature=1)


def _run_sql_tool(db_path: Path, sql: str, params: tuple = ()) -> list[dict]:
    return fetch_all(db_path, sql, params)


def _get_jobs_for_window(db_path: Path, run_time: str) -> list[dict]:
    return _run_sql_tool(
        db_path,
        "SELECT query_id, job_name, run_time, cpu_sec, io_mb, spool_mb, amp_skew_pct FROM dbql_query_log WHERE run_time = ?",
        (run_time,),
    )


def _get_stats_for_jobs(db_path: Path, jobs: list[str]) -> list[dict]:
    if not jobs:
        return []
    placeholders = ",".join(["?"] * len(jobs))
    return _run_sql_tool(
        db_path,
        f"SELECT job_name, stats_age_days, has_index, pi_health FROM table_stats WHERE job_name IN ({placeholders})",
        tuple(jobs),
    )


def _get_dependencies(db_path: Path, jobs: list[str]) -> list[dict]:
    if not jobs:
        return []
    placeholders = ",".join(["?"] * len(jobs))
    args = tuple(jobs + jobs)
    return _run_sql_tool(
        db_path,
        f"SELECT parent_job, child_job FROM job_deps WHERE parent_job IN ({placeholders}) OR child_job IN ({placeholders})",
        args,
    )


def _propose_dynamic_actions(findings: list[dict], dep_edges: list[dict], run_time: str) -> list[dict]:
    actions = []
    for finding in findings:
        reason = finding["reason"]
        if "stats_age=" in reason and "n/a" not in reason:
            actions.append({"action_type": "collect_stats", "details": f"Collect stats for {finding['job_name']} before {run_time}"})
        if "skew=" in reason:
            actions.append({"action_type": "pi_review", "details": f"Review PI/index strategy for {finding['job_name']}"})
    if dep_edges:
        actions.append({"action_type": "dag_parallelization", "details": f"Evaluate {len(dep_edges)} dependency edges for parallelization"})
    dedup = {(a["action_type"], a["details"]): a for a in actions}
    return list(dedup.values())


def _execute_action(db_path: Path, action: dict) -> None:
    execute_sql(
        db_path,
        "INSERT INTO actions_audit(action_type, details, outcome) VALUES (?, ?, ?)",
        (action["action_type"], action["details"], "executed"),
    )



def create_hitl_agent(tools: list):
    """Optional LangChain HITL agent factory when dependencies are available."""
    if create_agent is None or HumanInTheLoopMiddleware is None or InMemorySaver is None:
        return None

    class DemoState(AgentState):
        prompt: str

    return create_agent(
        model="gpt-5-nano",
        tools=tools,
        state_schema=DemoState,
        checkpointer=InMemorySaver(),
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={name: True for name in [t.__name__ for t in tools]},
                description_prefix="Tool execution requires approval",
            )
        ],
    )

def start_run(state: dict, run_time: str = "20:00") -> RunContext:
    _log(state, f"coordinator: starting optimization for {run_time} batch")
    return RunContext(run_time=run_time, queue=[ToolCall("get_jobs_for_window", {"run_time": run_time}, "coordinator")])


def _execute_tool(db_path: Path, call: ToolCall):
    if call.name == "get_jobs_for_window":
        return _get_jobs_for_window(db_path, call.args["run_time"])
    if call.name == "get_stats_for_jobs":
        return _get_stats_for_jobs(db_path, call.args["jobs"])
    if call.name == "get_dependencies":
        return _get_dependencies(db_path, call.args["jobs"])
    if call.name == "execute_action":
        _execute_action(db_path, call.args["action"])
        return {"status": "executed"}
    return None


def next_event(state: dict, db_path: Path, ctx: RunContext, approval: bool | None = None) -> dict:
    if ctx.done:
        return {"message": "run already completed", "done": True}

    if ctx.pending_call is not None:
        call = ctx.pending_call
        if approval is None:
            return {
                "message": f"{call.agent}: request approval to run tool `{call.name}` with args {call.args}",
                "requires_approval": True,
                "tool": {"name": call.name, "args": call.args},
            }
        if approval is False:
            _log(state, f"{call.agent}: tool {call.name} rejected by user")
            ctx.pending_call = None
            if not ctx.queue:
                ctx.done = True
                return {"message": "No more steps after rejection.", "done": True}
            return {"message": f"Skipped tool `{call.name}` by user decision.", "requires_approval": False}

        result = _execute_tool(db_path, call)
        ctx.pending_call = None
        return _after_tool(state, ctx, call, result)

    if not ctx.queue:
        ctx.done = True
        _log(state, "coordinator: completed run")
        return {"message": "Run complete.", "done": True}

    call = ctx.queue.pop(0)
    ctx.pending_call = call
    return {
        "message": f"{call.agent}: prepared tool `{call.name}`. Awaiting your approval.",
        "requires_approval": True,
        "tool": {"name": call.name, "args": call.args},
    }


def _after_tool(state: dict, ctx: RunContext, call: ToolCall, result) -> dict:
    if call.name == "get_jobs_for_window":
        jobs = result or []
        ctx.data["jobs"] = jobs
        names = [j["job_name"] for j in jobs]
        _transfer(state, "coordinator", "telemetry", "inspect table stats")
        ctx.queue.append(ToolCall("get_stats_for_jobs", {"jobs": names}, "telemetry"))
        _transfer(state, "coordinator", "dependency", "inspect dependencies")
        ctx.queue.append(ToolCall("get_dependencies", {"jobs": names}, "dependency"))
        return {"message": f"telemetry: found {len(jobs)} jobs for {ctx.run_time}", "requires_approval": False}

    if call.name == "get_stats_for_jobs":
        rows = ctx.data.get("jobs", [])
        stats_map = {r["job_name"]: r for r in (result or [])}
        findings = []
        for row in rows:
            st = stats_map.get(row["job_name"], {})
            if row["spool_mb"] > 10000 or row["amp_skew_pct"] > 20 or st.get("stats_age_days", 0) > 30:
                findings.append({"job_name": row["job_name"], "reason": f"spool={row['spool_mb']} skew={row['amp_skew_pct']} stats_age={st.get('stats_age_days', 'n/a')}"})
        ctx.data["findings"] = findings
        return {"message": f"telemetry: identified {len(findings)} hotspot jobs", "requires_approval": False}

    if call.name == "get_dependencies":
        dep_edges = result or []
        ctx.data["dep_edges"] = dep_edges
        findings = ctx.data.get("findings", [])
        actions = _propose_dynamic_actions(findings, dep_edges, ctx.run_time)
        for action in actions:
            ctx.queue.append(ToolCall("execute_action", {"action": action}, "executor"))
        state["latest_findings"] = findings
        state["proposed_actions"] = [{**a, "status": "pending_user_approval"} for a in actions]
        _transfer(state, "dependency", "optimizer", "prepare action plan")
        return {"message": f"optimizer: proposed {len(actions)} actions; each execution requires approval", "requires_approval": False}

    if call.name == "execute_action":
        action = call.args["action"]
        for item in state.get("proposed_actions", []):
            if item["action_type"] == action["action_type"] and item["details"] == action["details"]:
                item["status"] = "executed"
        return {"message": f"executor: executed {action['action_type']}", "requires_approval": False}

    return {"message": f"completed {call.name}", "requires_approval": False}
