# Teradata Batch Optimization Demo Scenarios (Agentic)

These scenarios are designed to mimic the real user ask:
- optimize Teradata compute cost
- handle large batch ecosystems (30K+ jobs in production; demo uses small representative set)
- show autonomous analysis + action proposals + user approval + execution + re-check loop

## Scenario 1: 8PM Peak Batch Cost Spike (CPU/Spool/Skew)

**User problem statement:** “Optimize job performance for 8PM batch and reduce compute cost.”

**Demo flow:**
1. Agent receives goal for 8PM optimization.
2. Telemetry agent pulls 8PM jobs from DBQL-like telemetry.
3. Agent identifies top offenders (high CPU, spool, skew).
4. Agent checks table stats freshness and PI/index hints.
5. Optimizer agent proposes actions:
   - collect stale stats
   - reduce heavy-batch concurrency during peak
   - shift one non-critical heavy job out of peak
6. Agent asks for user approval.
7. Executor agent applies approved actions.
8. Agent reports before/after impact.

**KPIs to show:** peak CPU, spool hotspots, batch window, estimated compute savings.

---

## Scenario 2: Artificial Serialization in Batch DAG

**User problem statement:** “Can we run many jobs in the most optimal way?”

**Demo flow:**
1. Dependency agent reads scheduler-like dependency graph.
2. Finds unnecessary sequential chains and idle gaps.
3. Simulates “current vs parallelized” execution windows.
4. Optimizer agent proposes:
   - remove one non-essential dependency edge
   - enable safe parallel runs for independent jobs
   - cap concurrency for heavy class to avoid contention
5. User approves.
6. Executor applies changes in simulator/demo state.
7. Agent reports critical path and runtime reduction.

**KPIs to show:** critical path length, parallelization %, idle time reduction, SLA adherence.

---

## Scenario 3: Autonomous Iterative Optimization Loop (Human-in-the-Loop)

**User problem statement:** “Can it analyze, act after confirmation, evaluate intermediate output, and act again?”

**Demo flow:**
1. Coordinator agent routes work to telemetry/dependency/optimizer agents.
2. Produces ranked actions with impact + risk.
3. User approves only low-risk actions (phase 1).
4. Executor applies and writes audit entry.
5. Agent re-checks telemetry and compares baseline vs current.
6. If targets not met, proposes phase 2 actions.
7. Stops when KPI target reached or user halts.

**KPIs to show:** number of cycles, approvals vs rejects, cumulative savings, complete audit trail.

---

## Keep It Simple: Do We Need More Files?

Not strictly required for a demo, but these **small optional files** will improve clarity:

1. `docs/demo_script.md`
   - 10-minute presenter script (what to click, what to say, expected output).
2. `docs/agent_contracts.md`
   - tiny spec for each agent: responsibility, allowed tools, handoff conditions.
3. `data/scenario_overrides.py`
   - small per-scenario data tweaks (e.g., forced 8PM hotspot, forced DAG bottleneck).

If you want minimum footprint, keep only the current 3 code files + this document.

## Keep It Simple: Do We Need More Libraries?

For this demo, **no must-have new libraries** beyond what is already implied:
- Streamlit (UI)
- LangChain (agent scaffolding)

Optional only if you want richer visualization:
- `networkx` for DAG visualization (not mandatory)

## Grounding the Agents: Do We Need RAG/Knowledge Base?

For this demo, **RAG is not mandatory**.

Use lightweight grounding instead:
1. Ground agents to deterministic seed telemetry (`data/seed_data.py`).
2. Add strict tool contracts (query jobs, stats, dependencies, propose actions, execute actions).
3. Add guardrails:
   - only approved actions execute
   - all actions logged to audit
   - no external side effects in demo mode

Only add RAG if you must support questions like:
- “Have we done similar engagements for specific clients?”
- “Show prior project patterns/case studies from internal docs.”

If needed later, start with a tiny read-only knowledge file (Markdown/JSON) instead of full vector DB.

## Recommendation (for this demo)

- Keep architecture simple and deterministic.
- Show autonomous handoffs + tool calls + approval gating.
- Prioritize believable metrics and repeatable outcomes over model complexity.
