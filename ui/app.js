const { useEffect, useState } = React;

function App() {
  const [state, setState] = useState({ agent_log: [], chat: [], latest_findings: [], proposed_actions: [] });
  const [wlm, setWlm] = useState([]);
  const [runTime, setRunTime] = useState("20:00");
  const [message, setMessage] = useState("");
  const [audit, setAudit] = useState([]);
  const [dbPath, setDbPath] = useState("");
  const [runId, setRunId] = useState("");
  const [pending, setPending] = useState(null);
  const [streaming, setStreaming] = useState(false);

  const refresh = () => fetch("/api/state").then((r) => r.json()).then((d) => {
    setState(d.state); setWlm(d.wlm_rules); setAudit(d.audit || []); setDbPath(d.db_path || "");
  });
  useEffect(() => { refresh(); }, []);

  const sendChat = async () => {
    if (!message.trim()) return;
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
    setState((await r.json()).state);
    setMessage("");
  };

  const startRun = async () => {
    const r = await fetch("/api/chat/start_run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_time: runTime }) });
    const d = await r.json();
    setRunId(d.run_id);
    setState(d.state);
    setStreaming(true);
  };

  const streamNext = async () => {
    if (!runId || pending) return;
    const r = await fetch("/api/chat/stream_next", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: runId }) });
    const d = await r.json();
    setState(d.state);
    if (d.event?.requires_approval) setPending(d.event);
    if (d.event?.done) setStreaming(false);
  };

  const decision = async (approve) => {
    const r = await fetch("/api/chat/decision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: runId, approve }) });
    const d = await r.json();
    setState(d.state);
    setAudit(d.audit || []);
    setPending(null);
    if (d.event?.done) setStreaming(false);
  };

  useEffect(() => {
    if (!streaming || pending) return;
    const t = setTimeout(() => { streamNext(); }, 900);
    return () => clearTimeout(t);
  }, [streaming, pending, runId, state.chat.length]);

  return (
    <div className="wrap">
      <h2>Teradata Batch Optimization Accelerator (React Demo)</h2>
      <div><small>SQLite: {dbPath}</small></div>
      <div className="grid">
        <div className="pane">
          <h3>1) Data Source</h3>
          <label>Batch Window: </label>
          <select value={runTime} onChange={(e) => setRunTime(e.target.value)}><option>20:00</option><option>19:00</option></select>
          <div><button onClick={refresh}>Reload State</button></div>
          <h4>WLM Rules</h4><pre>{JSON.stringify(wlm, null, 2)}</pre>
        </div>

        <div className="pane">
          <h3>2) Agent State + Synthesis</h3>
          <button onClick={startRun}>Start Agentic Run</button>
          <button onClick={() => setStreaming((v) => !v)}>{streaming ? "Pause Stream" : "Resume Stream"}</button>
          <h4>Findings</h4><pre>{JSON.stringify(state.latest_findings || [], null, 2)}</pre>
          <h4>Proposed Actions</h4><pre>{JSON.stringify(state.proposed_actions || [], null, 2)}</pre>
        </div>

        <div className="pane">
          <h3>3) User Chat (Streaming + HITL)</h3>
          <input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Ask the agent" style={{ width: "70%" }} />
          <button onClick={sendChat}>Send</button>
          {(state.chat || []).map((m, i) => <div key={i} className={`chat ${m.role}`}>{m.role}: {m.content}</div>)}
          {pending && (
            <div className="chat assistant">
              <div><b>Approval needed:</b> {pending.tool?.name}</div>
              <button style={{fontSize: "12px", padding: "2px 8px"}} onClick={() => decision(true)}>Approve</button>
              <button style={{fontSize: "12px", padding: "2px 8px"}} onClick={() => decision(false)}>Reject</button>
            </div>
          )}
        </div>
      </div>
      <h3>Agent Activity Log</h3>
      {(state.agent_log || []).map((l, i) => <pre key={i}>{l}</pre>)}
      <h3>Execution Audit</h3>
      <pre>{JSON.stringify(audit, null, 2)}</pre>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
