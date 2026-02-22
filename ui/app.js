const { useEffect, useState } = React;

function App() {
  const [state, setState] = useState({ agent_log: [], chat: [], latest_findings: [], proposed_actions: [] });
  const [wlm, setWlm] = useState([]);
  const [runTime, setRunTime] = useState("20:00");
  const [message, setMessage] = useState("");

  const refresh = () => fetch("/api/state").then((r) => r.json()).then((d) => { setState(d.state); setWlm(d.wlm_rules); });
  useEffect(() => { refresh(); }, []);

  const runAnalysis = async () => {
    const r = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_time: runTime }) });
    setState((await r.json()).state);
  };

  const approve = async () => {
    const r = await fetch("/api/approve", { method: "POST" });
    setState((await r.json()).state);
  };

  const sendChat = async () => {
    if (!message.trim()) return;
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
    setState((await r.json()).state);
    setMessage("");
  };

  return (
    <div className="wrap">
      <h2>Teradata Batch Optimization Accelerator (React Demo)</h2>
      <div className="grid">
        <div className="pane">
          <h3>1) Data Source</h3>
          <label>Batch Window: </label>
          <select value={runTime} onChange={(e) => setRunTime(e.target.value)}><option>20:00</option><option>19:00</option></select>
          <div><button onClick={refresh}>Load Sample Telemetry</button></div>
          <h4>WLM Rules</h4><pre>{JSON.stringify(wlm, null, 2)}</pre>
        </div>
        <div className="pane">
          <h3>2) Agent State + Synthesis</h3>
          <button onClick={runAnalysis}>Run Autonomous Analysis</button>
          <button onClick={approve}>Approve + Execute Pending Actions</button>
          <h4>Findings</h4><pre>{JSON.stringify(state.latest_findings || [], null, 2)}</pre>
          <h4>Proposed Actions</h4><pre>{JSON.stringify(state.proposed_actions || [], null, 2)}</pre>
        </div>
        <div className="pane">
          <h3>3) User Chat</h3>
          <input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Ask the agent" style={{ width: "70%" }} />
          <button onClick={sendChat}>Send</button>
          {(state.chat || []).map((m, i) => <div key={i} className={`chat ${m.role}`}>{m.role}: {m.content}</div>)}
        </div>
      </div>
      <h3>Agent Activity Log</h3>
      {(state.agent_log || []).map((l, i) => <pre key={i}>{l}</pre>)}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
