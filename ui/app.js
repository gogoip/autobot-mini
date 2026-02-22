const { useEffect, useState } = React;

function TablePreview({ name, rows }) {
  if (!rows || !rows.length) return <div><h5>{name}</h5><small>No rows</small></div>;
  const cols = Object.keys(rows[0]);
  return (
    <div style={{ marginBottom: "10px" }}>
      <h5>{name}</h5>
      <div style={{ overflowX: "auto", border: "1px solid #e5e7eb", borderRadius: "6px" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "12px" }}>
          <thead><tr>{cols.map((c) => <th key={c} style={{ borderBottom: "1px solid #ddd", textAlign: "left", padding: "4px" }}>{c}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c} style={{ borderBottom: "1px solid #f1f5f9", padding: "4px" }}>{String(r[c])}</td>)}</tr>)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function App() {
  const [state, setState] = useState({ agent_log: [], chat: [], latest_findings: [], proposed_actions: [] });
  const [wlm, setWlm] = useState([]);
  const [runTime, setRunTime] = useState("20:00");
  const [message, setMessage] = useState("");
  const [audit, setAudit] = useState([]);
  const [dbPath, setDbPath] = useState("");
  const [conn, setConn] = useState({ host: "localhost", port: "1025", user: "demo_user", db_path: "" });
  const [tables, setTables] = useState({});
  const [runId, setRunId] = useState("");
  const [qnaRunId, setQnaRunId] = useState("");
  const [pending, setPending] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [qnaStreaming, setQnaStreaming] = useState(false);

  const refresh = () => fetch("/api/state").then((r) => r.json()).then((d) => {
    setState(d.state); setWlm(d.wlm_rules); setAudit(d.audit || []); setDbPath(d.db_path || ""); setTables(d.tables || {});
  });
  useEffect(() => { refresh(); }, []);

  const connectDb = async () => {
    const r = await fetch("/api/connect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ db_path: conn.db_path }) });
    const d = await r.json();
    setDbPath(d.db_path); setTables(d.tables || {});
  };

  const sendChat = async () => {
    if (!message.trim()) return;
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
    const d = await r.json();
    setState(d.state); setMessage("");
  };

  const startQna = async () => {
    const query = message || "what does my telemetry contain?";
    const r = await fetch("/api/chat/start_qna", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query }) });
    const d = await r.json();
    setQnaRunId(d.run_id); setQnaStreaming(true);
  };

  const streamQnaNext = async () => {
    if (!qnaRunId || pending) return;
    const r = await fetch("/api/chat/stream_qna_next", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: qnaRunId }) });
    const d = await r.json();
    setState(d.state);
    if (d.event?.requires_approval) setPending({ ...d.event, mode: "qna" });
    if (d.event?.done) setQnaStreaming(false);
  };

  const qnaDecision = async (approve) => {
    const r = await fetch("/api/chat/qna_decision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: qnaRunId, approve }) });
    const d = await r.json();
    setState(d.state); setPending(null);
    if (d.event?.done) setQnaStreaming(false);
  };

  const startRun = async () => {
    const r = await fetch("/api/chat/start_run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_time: runTime }) });
    const d = await r.json();
    setRunId(d.run_id); setState(d.state); setStreaming(true);
  };

  const streamNext = async () => {
    if (!runId || pending) return;
    const r = await fetch("/api/chat/stream_next", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: runId }) });
    const d = await r.json();
    setState(d.state);
    if (d.event?.requires_approval) setPending({ ...d.event, mode: "opt" });
    if (d.event?.done) setStreaming(false);
  };

  const decision = async (approve) => {
    if (pending?.mode === "qna") return qnaDecision(approve);
    const r = await fetch("/api/chat/decision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: runId, approve }) });
    const d = await r.json();
    setState(d.state); setAudit(d.audit || []); setPending(null);
    if (d.event?.done) setStreaming(false);
  };

  useEffect(() => {
    if (!streaming || pending) return;
    const t = setTimeout(() => { streamNext(); }, 1100);
    return () => clearTimeout(t);
  }, [streaming, pending, runId, state.chat.length]);

  useEffect(() => {
    if (!qnaStreaming || pending) return;
    const t = setTimeout(() => { streamQnaNext(); }, 1200);
    return () => clearTimeout(t);
  }, [qnaStreaming, pending, qnaRunId, state.chat.length]);

  return (
    <div className="wrap">
      <h2>Teradata Batch Optimization Accelerator (React Demo)</h2>
      <div><small>Connected DB: {dbPath}</small></div>
      <div className="grid">
        <div className="pane">
          <h3>1) Connection + Data Preview</h3>
          <input placeholder="Host" value={conn.host} onChange={(e) => setConn({ ...conn, host: e.target.value })} />
          <input placeholder="Port" value={conn.port} onChange={(e) => setConn({ ...conn, port: e.target.value })} />
          <input placeholder="User" value={conn.user} onChange={(e) => setConn({ ...conn, user: e.target.value })} />
          <input placeholder="Telemetry DB path (optional)" value={conn.db_path} onChange={(e) => setConn({ ...conn, db_path: e.target.value })} style={{ width: "95%" }} />
          <div><button onClick={connectDb}>Connect + Fetch Tables</button></div>
          <h4>Tables + Sample Rows</h4>
          {Object.entries(tables).map(([name, rows]) => <TablePreview key={name} name={name} rows={rows} />)}
          <h4>WLM Rules</h4><pre>{JSON.stringify(wlm, null, 2)}</pre>
        </div>

        <div className="pane">
          <h3>2) Optimization Agents (HITL)</h3>
          <label>Batch Window: </label>
          <select value={runTime} onChange={(e) => setRunTime(e.target.value)}><option>20:00</option><option>19:00</option></select>
          <button onClick={startRun}>Start Optimization Run</button>
          <button onClick={() => setStreaming((v) => !v)}>{streaming ? "Pause Stream" : "Resume Stream"}</button>
          <h4>Findings</h4><pre>{JSON.stringify(state.latest_findings || [], null, 2)}</pre>
          <h4>Proposed Actions</h4><pre>{JSON.stringify(state.proposed_actions || [], null, 2)}</pre>
        </div>

        <div className="pane">
          <h3>3) Chat QnA (Streaming + ReAct Feel)</h3>
          <input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Ask: what does my telemetry contain?" style={{ width: "72%" }} />
          <button onClick={sendChat}>Send</button>
          <button onClick={startQna}>Run QnA Agent</button>
          {(state.chat || []).map((m, i) => <div key={i} className={`chat ${m.role.includes("assistant") ? "assistant" : "user"}`}>{m.role}: {m.content}</div>)}
          {pending && (
            <div className="chat assistant">
              <div><b>Approval needed:</b> {pending.tool?.name}</div>
              <button style={{ fontSize: "12px", padding: "2px 8px" }} onClick={() => decision(true)}>Approve</button>
              <button style={{ fontSize: "12px", padding: "2px 8px" }} onClick={() => decision(false)}>Reject</button>
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
