"""Agentic multi-agent orchestration with tool routing + handoffs."""

from __future__ import annotations

from dataclasses import dataclass

from langchain.agents import create_react_agent


@dataclass
class ToolCall:
    name: str
    args: dict


def _log(state: dict, text: str) -> None:
    state.setdefault("agent_log", []).append(text)


def _transfer(state: dict, frm: str, to: str, reason: str) -> None:
    _log(state, f"handoff: {frm} -> {to} ({reason})")


def _query_jobs(seed: dict, run_time: str) -> list:
    return [j for j in seed["dbql_query_log"] if j["run_time"] == run_time]


def _query_table_stats(seed: dict, jobs: list[str]) -> dict:
    return {name: seed["table_stats"].get(name, {}) for name in jobs}


def _query_dependencies(seed: dict, jobs: list[str]) -> list:
    related = set(jobs)
    return [d for d in seed["job_deps"] if d["child_job"] in related or d["parent_job"] in related]


def _propose_actions(findings: list) -> list:
    actions = []
    if findings:
        actions.append(
            {
                "action_type": "collect_stats",
                "details": "Collect stats for stale tables in 8PM critical jobs",
                "expected_impact": "Lower spool and CPU by 10-20%",
                "status": "pending_user_approval",
            }
        )
        actions.append(
            {
                "action_type": "wlm_throttle",
                "details": "Set heavy_batch throttle from 5 to 3 during 20:00 peak",
                "expected_impact": "Reduce contention and peak skew",
                "status": "pending_user_approval",
            }
        )
    return actions


def _execute_actions(seed: dict, actions: list[dict]) -> None:
    for action in actions:
        seed["actions_audit"].append({"action": action["details"], "outcome": "executed"})
        action["status"] = "executed"


def build_agents(llm):
    prompts = {
        "coordinator": "Route tasks to specialized agents and keep shared state coherent.",
        "telemetry": "Use telemetry tools to find job runtime, spool, skew hotspots.",
        "dependency": "Analyze DAG and detect artificial serialization and bottlenecks.",
        "optimizer": "Generate ranked actions with impact and risk.",
        "executor": "Execute only approved actions and update audit trail.",
    }
    return {k: create_react_agent(llm=llm, tools=[], prompt=v) for k, v in prompts.items()}


def run_autonomous_cycle(state: dict, seed: dict, run_time: str = "20:00") -> dict:
    tools = {
        "query_jobs": lambda args: _query_jobs(seed, args["run_time"]),
        "query_table_stats": lambda args: _query_table_stats(seed, args["jobs"]),
        "query_dependencies": lambda args: _query_dependencies(seed, args["jobs"]),
        "propose_actions": lambda args: _propose_actions(args["findings"]),
    }
    queue = [
        ("coordinator", ToolCall("query_jobs", {"run_time": run_time})),
    ]
    findings = []

    _log(state, f"coordinator: starting autonomous optimization for {run_time} batch")
    while queue:
        agent, call = queue.pop(0)
        _log(state, f"{agent}: executing tool {call.name} with {call.args}")
        result = tools[call.name](call.args)

        if call.name == "query_jobs":
            rows = result
            _log(state, f"telemetry: found {len(rows)} jobs for {run_time}")
            jobs = [r["job_name"] for r in rows]
            _transfer(state, "coordinator", "telemetry", "need table stats")
            queue.append(("telemetry", ToolCall("query_table_stats", {"jobs": jobs})))
            _transfer(state, "telemetry", "dependency", "need dependency graph")
            queue.append(("dependency", ToolCall("query_dependencies", {"jobs": jobs})))
            state["_rows"] = rows

        elif call.name == "query_table_stats":
            rows = state.get("_rows", [])
            stats = result
            for row in rows:
                st = stats.get(row["job_name"], {})
                is_hot = row["spool_mb"] > 10000 or row["amp_skew_pct"] > 20 or st.get("stats_age_days", 0) > 30
                if is_hot:
                    findings.append(
                        {
                            "job_name": row["job_name"],
                            "reason": f"spool={row['spool_mb']} skew={row['amp_skew_pct']} stats_age={st.get('stats_age_days', 'n/a')}",
                        }
                    )
            _log(state, f"telemetry: shortlisted {len(findings)} issue jobs")

        elif call.name == "query_dependencies":
            dep_edges = result
            _log(state, f"dependency: inspected {len(dep_edges)} edges")
            _transfer(state, "dependency", "optimizer", "ready to synthesize")
            queue.append(("optimizer", ToolCall("propose_actions", {"findings": findings})))

        elif call.name == "propose_actions":
            actions = result
            state["latest_findings"] = findings
            state["proposed_actions"] = actions
            state["proposed_action"] = actions[0] if actions else {}
            _log(state, "optimizer: created action plan")
            _log(state, "coordinator: waiting user approval")

    state.pop("_rows", None)
    return state


def apply_approved_action(state: dict, seed: dict) -> dict:
    actions = [a for a in state.get("proposed_actions", []) if a.get("status") == "pending_user_approval"]
    if not actions:
        _log(state, "executor: no pending actions")
        return state
    _log(state, "executor: executing approved actions")
    _execute_actions(seed, actions)
    _log(state, "executor: actions applied; waiting for next execution")
    return state
