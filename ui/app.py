"""Simple 3-pane agentic UI for Teradata optimization demo."""

from __future__ import annotations

import streamlit as st

from agents.react_agents import apply_approved_action, run_autonomous_cycle
from data.seed_data import load_seed_bundle

st.set_page_config(layout="wide")
st.title("Teradata Batch Optimization Accelerator (Agentic Demo)")

if "seed" not in st.session_state:
    st.session_state.seed = load_seed_bundle()
if "state" not in st.session_state:
    st.session_state.state = {"agent_log": [], "chat": []}

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("1) Data Source")
    run_time = st.selectbox("Batch window", ["20:00", "19:00"], index=0)
    st.text_input("Source", value="demo_dbql_query_log", disabled=True)
    if st.button("Load Sample Telemetry"):
        st.success("Sample telemetry loaded")
    st.write("WLM rules")
    st.json(st.session_state.seed["wlm_rules"])

with col2:
    st.subheader("2) Agent State + Synthesis")
    st.text_area("Summarize prompt", value="Summarize top cost drivers and safe actions.")
    if st.button("Run Autonomous Analysis"):
        run_autonomous_cycle(st.session_state.state, st.session_state.seed, run_time=run_time)
    if st.button("Approve + Execute Pending Actions"):
        apply_approved_action(st.session_state.state, st.session_state.seed)
    st.write("Findings", st.session_state.state.get("latest_findings", []))
    st.write("Proposed Actions", st.session_state.state.get("proposed_actions", []))

with col3:
    st.subheader("3) User Chat")
    msg = st.chat_input("Ask the agent")
    if msg:
        st.session_state.state["chat"].append({"role": "user", "content": msg})
        st.session_state.state["chat"].append(
            {
                "role": "assistant",
                "content": "Acknowledged. Coordinator agent will route telemetry, dependency, optimizer, and executor agents autonomously.",
            }
        )
    for m in st.session_state.state["chat"]:
        with st.chat_message(m["role"]):
            st.write(m["content"])

st.divider()
st.subheader("Agent activity log")
for line in st.session_state.state.get("agent_log", []):
    st.code(line)
