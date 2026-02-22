"""Agentic orchestration with dynamic QnA routing and HITL tool approvals."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data.sqlite_store import execute_sql, fetch_all

try:
    from langchain_groq import ChatGroq
except ImportError:  # pragma: no cover
    ChatGroq = None

try:
    from tavily import TavilyClient
except ImportError:  # pragma: no cover
    TavilyClient = None


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


@dataclass
class ChatContext:
    user_query: str
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


def list_tables_with_samples(db_path: Path, limit: int = 3) -> dict[str, list[dict]]:
    tables = _run_sql_tool(db_path, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    out: dict[str, list[dict]] = {}
    for t in tables:
        name = t["name"]
        out[name] = _run_sql_tool(db_path, f"SELECT * FROM {name} LIMIT {int(limit)}")
    return out


def _get_jobs_for_window(db_path: Path, run_time: str) -> list[dict]:
    return _run_sql_tool(db_path, "SELECT * FROM dbql_query_log WHERE run_time = ?", (run_time,))


def _get_stats_for_jobs(db_path: Path, jobs: list[str]) -> list[dict]:
    if not jobs:
        return []
    placeholders = ",".join(["?"] * len(jobs))
    return _run_sql_tool(db_path, f"SELECT * FROM table_stats WHERE job_name IN ({placeholders})", tuple(jobs))


def _get_dependencies(db_path: Path, jobs: list[str]) -> list[dict]:
    if not jobs:
        return []
    placeholders = ",".join(["?"] * len(jobs))
    args = tuple(jobs + jobs)
    return _run_sql_tool(db_path, f"SELECT parent_job, child_job FROM job_deps WHERE parent_job IN ({placeholders}) OR child_job IN ({placeholders})", args)


def _tavily_search(query: str) -> list[dict]:
    if TavilyClient is None or not os.getenv("TAVILY_API_KEY"):
        return [{"title": "Tavily unavailable", "url": "", "content": "Set TAVILY_API_KEY and install tavily-python."}]
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    result = client.search(query=query, max_results=3)
    return result.get("results", [])


def _build_sql_from_query(user_query: str) -> str:
    q = user_query.lower()
    if any(k in q for k in ["contain", "schema", "table"]):
        return "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    if any(k in q for k in ["relation", "dependency"]):
        return "SELECT parent_job, child_job FROM job_deps LIMIT 20"
    if "8pm" in q or "20:00" in q:
        return "SELECT job_name, cpu_sec, spool_mb, amp_skew_pct FROM dbql_query_log WHERE run_time='20:00' ORDER BY spool_mb DESC"
    if "skew" in q:
        return "SELECT job_name, amp_skew_pct FROM dbql_query_log ORDER BY amp_skew_pct DESC LIMIT 10"
    if "spool" in q:
        return "SELECT job_name, spool_mb FROM dbql_query_log ORDER BY spool_mb DESC LIMIT 10"
    return "SELECT job_name, run_time, cpu_sec, spool_mb FROM dbql_query_log LIMIT 10"


def _plan_qna_tools(user_query: str, llm=None) -> list[ToolCall]:
    base = [ToolCall("intent_understanding", {"query": user_query}, "qna-coordinator")]
    dynamic: list[str] = []
    if llm is not None:
        try:
            prompt = (
                "Return ONLY a JSON array of tool names from: "
                "build_sql, execute_sql, optimize_analysis, tavily_search, final_answer. "
                f"Question: {user_query}"
            )
            content = llm.invoke(prompt).content
            names = json.loads(content)
            dynamic = [n for n in names if n in {"build_sql", "execute_sql", "optimize_analysis", "tavily_search", "final_answer"}]
        except Exception:
            dynamic = []
    if not dynamic:
        q = user_query.lower()
        dynamic = ["build_sql", "execute_sql"]
        if any(k in q for k in ["optimize", "improve", "cost", "skew", "spool"]):
            dynamic.append("optimize_analysis")
        if any(k in q for k in ["online", "reference", "best practice", "industry"]):
            dynamic.append("tavily_search")
        dynamic.append("final_answer")
    if dynamic[-1] != "final_answer":
        dynamic.append("final_answer")
    mapping = {
        "build_sql": ToolCall("build_sql", {"query": user_query}, "sql-agent"),
        "execute_sql": ToolCall("execute_sql", {}, "sql-agent"),
        "optimize_analysis": ToolCall("optimize_analysis", {}, "optimizer-agent"),
        "tavily_search": ToolCall("tavily_search", {"query": f"Teradata optimization patterns for: {user_query}"}, "research-agent"),
        "final_answer": ToolCall("final_answer", {"query": user_query}, "qna-coordinator"),
    }
    return base + [mapping[n] for n in dynamic]


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
    return list({(a["action_type"], a["details"]): a for a in actions}.values())


def _execute_action(db_path: Path, action: dict) -> None:
    execute_sql(db_path, "INSERT INTO actions_audit(action_type, details, outcome) VALUES (?, ?, ?)", (action["action_type"], action["details"], "executed"))


def start_run(state: dict, run_time: str = "20:00") -> RunContext:
    _log(state, f"coordinator: starting optimization for {run_time} batch")
    return RunContext(run_time=run_time, queue=[ToolCall("get_jobs_for_window", {"run_time": run_time}, "coordinator")])


def start_chat_qna(state: dict, user_query: str, llm=None) -> ChatContext:
    _log(state, f"qna-coordinator: received query: {user_query}")
    queue = _plan_qna_tools(user_query, llm=llm)
    _log(state, f"qna-coordinator: dynamic plan -> {[c.name for c in queue]}")
    return ChatContext(user_query=user_query, queue=queue)


def _execute_tool(db_path: Path, call: ToolCall, ctx: Any):
    if call.name == "get_jobs_for_window":
        return _get_jobs_for_window(db_path, call.args["run_time"])
    if call.name == "get_stats_for_jobs":
        return _get_stats_for_jobs(db_path, call.args["jobs"])
    if call.name == "get_dependencies":
        return _get_dependencies(db_path, call.args["jobs"])
    if call.name == "execute_action":
        _execute_action(db_path, call.args["action"])
        return {"status": "executed"}
    if call.name == "intent_understanding":
        q = call.args["query"].lower()
        intent = "metadata" if any(k in q for k in ["contain", "schema", "table"]) else "analysis"
        ctx.data["intent"] = intent
        return {"intent": intent}
    if call.name == "build_sql":
        sql = _build_sql_from_query(call.args["query"])
        ctx.data["generated_sql"] = sql
        return {"sql": sql}
    if call.name == "execute_sql":
        sql = ctx.data.get("generated_sql")
        if not sql:
            return {"rows": [], "sql": "<none>"}
        rows = _run_sql_tool(db_path, sql)
        ctx.data["sql_rows"] = rows
        return {"rows": rows, "sql": sql}
    if call.name == "optimize_analysis":
        rows = ctx.data.get("sql_rows", [])
        observations = []
        for r in rows[:10]:
            if isinstance(r, dict) and r.get("spool_mb", 0) > 10000:
                observations.append(f"High spool: {r.get('job_name')} ({r.get('spool_mb')} MB)")
            if isinstance(r, dict) and r.get("amp_skew_pct", 0) > 20:
                observations.append(f"High skew: {r.get('job_name')} ({r.get('amp_skew_pct')}%)")
        ctx.data["observations"] = observations
        return {"observations": observations}
    if call.name == "tavily_search":
        results = _tavily_search(call.args["query"])[:2]
        ctx.data["web_results"] = results
        return {"results": results}
    if call.name == "final_answer":
        rows = ctx.data.get("sql_rows", [])
        obs = ctx.data.get("observations", [])
        refs = [f"{r.get('title','')} ({r.get('url','')})" for r in ctx.data.get("web_results", [])]
        return {"answer": f"Answer: Retrieved {len(rows)} row(s). Observations: {obs if obs else ['none']}. References: {refs if refs else ['none']}"}
    return None


def next_chat_event(state: dict, db_path: Path, ctx: ChatContext, approval: bool | None = None) -> dict:
    if ctx.done:
        return {"message": "chat run completed", "done": True}

    if ctx.pending_call is not None:
        call = ctx.pending_call
        if approval is None:
            return {"message": f"{call.agent}: Ready to run `{call.name}` with {call.args}", "requires_approval": True, "tool": {"name": call.name, "args": call.args}}
        if approval is False:
            ctx.pending_call = None
            if call.name in {"build_sql", "execute_sql"}:
                ctx.done = True
                return {"message": f"{call.agent}: `{call.name}` rejected. QnA run stopped because SQL stage is required.", "done": True}
            return {"message": f"{call.agent}: rejected `{call.name}`; continuing.", "requires_approval": False}

        result = _execute_tool(db_path, call, ctx)
        ctx.pending_call = None
        if call.name == "build_sql":
            return {"message": f"sql-agent: built SQL -> {result['sql']}", "requires_approval": False}
        if call.name == "execute_sql":
            sample = result["rows"][:3]
            return {"message": f"sql-agent: executed SQL ({result['sql']}) and fetched {len(result['rows'])} row(s). Sample: {sample}", "requires_approval": False}
        if call.name == "optimize_analysis":
            msg = result.get("observations", []) or ["No major optimization red flags in this result set."]
            return {"message": f"optimizer-agent: {msg}", "requires_approval": False}
        if call.name == "tavily_search":
            refs = [f"{r.get('title','n/a')} ({r.get('url','')})" for r in result.get("results", [])]
            return {"message": f"research-agent: references -> {refs}", "requires_approval": False}
        if call.name == "final_answer":
            ctx.done = True
            return {"message": result["answer"], "done": True}
        return {"message": f"{call.agent}: completed `{call.name}`", "requires_approval": False}

    if not ctx.queue:
        ctx.done = True
        return {"message": "chat run completed", "done": True}

    call = ctx.queue.pop(0)
    ctx.pending_call = call
    hints = {
        "intent_understanding": "I’ll classify your intent and decide which tools are needed.",
        "build_sql": "I’ll compose SQL tailored to your question and telemetry schema.",
        "execute_sql": "I’ll execute SQL and show real sample rows.",
        "optimize_analysis": "I’ll derive optimization signals from returned metrics.",
        "tavily_search": "I’ll fetch external references for complementary context.",
        "final_answer": "I’ll synthesize a direct answer using all collected evidence.",
    }
    return {"message": f"{call.agent}: {hints.get(call.name, 'Preparing tool step')}", "requires_approval": True, "tool": {"name": call.name, "args": call.args}}


def next_event(state: dict, db_path: Path, ctx: RunContext, approval: bool | None = None) -> dict:
    if ctx.done:
        return {"message": "run already completed", "done": True}

    if ctx.pending_call is not None:
        call = ctx.pending_call
        if approval is None:
            return {"message": f"{call.agent}: request approval to run tool `{call.name}` with args {call.args}", "requires_approval": True, "tool": {"name": call.name, "args": call.args}}
        if approval is False:
            _log(state, f"{call.agent}: tool {call.name} rejected by user")
            ctx.pending_call = None
            if not ctx.queue:
                ctx.done = True
                return {"message": "No more steps after rejection.", "done": True}
            return {"message": f"Skipped tool `{call.name}` by user decision.", "requires_approval": False}

        result = _execute_tool(db_path, call, ctx)
        ctx.pending_call = None
        return _after_tool(state, ctx, call, result)

    if not ctx.queue:
        ctx.done = True
        _log(state, "coordinator: completed run")
        return {"message": "Run complete.", "done": True}

    call = ctx.queue.pop(0)
    ctx.pending_call = call
    return {"message": f"{call.agent}: prepared tool `{call.name}`. Awaiting your approval.", "requires_approval": True, "tool": {"name": call.name, "args": call.args}}


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
            if row.get("spool_mb", 0) > 10000 or row.get("amp_skew_pct", 0) > 20 or st.get("stats_age_days", 0) > 30:
                findings.append({"job_name": row["job_name"], "reason": f"spool={row.get('spool_mb')} skew={row.get('amp_skew_pct')} stats_age={st.get('stats_age_days', 'n/a')}"})
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
