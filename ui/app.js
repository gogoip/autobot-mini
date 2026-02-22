const root = document.getElementById("root");

const model = {
  state: { agent_log: [], chat: [], latest_findings: [], proposed_actions: [] },
  wlm: [],
  runTime: "20:00",
  message: "",
  audit: [],
  dbPath: "",
  conn: { host: "localhost", port: "1025", user: "demo_user", db_path: "" },
  tables: {},
  runId: "",
  qnaRunId: "",
  pending: null,
  streaming: false,
  qnaStreaming: false,
};

const toAssistantMessages = (chat = []) =>
  chat.map((entry, idx) => ({
    id: `msg-${idx}`,
    role: entry.role === "assistant" ? "assistant" : "user",
    content: [{ type: "text", text: entry.content || "" }],
  }));

const fetchJson = async (url, options = {}) => {
  const response = await fetch(url, options);
  return response.json();
};

const refresh = async () => {
  const data = await fetchJson("/api/state");
  model.state = data.state;
  model.wlm = data.wlm_rules || [];
  model.audit = data.audit || [];
  model.dbPath = data.db_path || "";
  model.tables = data.tables || {};
  render();
};

const connectDb = async () => {
  const data = await fetchJson("/api/connect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ db_path: model.conn.db_path }),
  });
  model.dbPath = data.db_path;
  model.tables = data.tables || {};
  render();
};

const sendChat = async () => {
  if (!model.message.trim()) return;
  const data = await fetchJson("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: model.message }),
  });
  model.state = data.state;
  model.message = "";
  render();
};

const startQna = async () => {
  const data = await fetchJson("/api/chat/start_qna", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: model.message || "what does my telemetry contain?" }),
  });
  model.qnaRunId = data.run_id;
  model.qnaStreaming = true;
  render();
};

const streamQnaNext = async () => {
  if (!model.qnaRunId || model.pending) return;
  const data = await fetchJson("/api/chat/stream_qna_next", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: model.qnaRunId }),
  });
  model.state = data.state;
  if (data.event?.requires_approval) model.pending = { ...data.event, mode: "qna" };
  if (data.event?.done) model.qnaStreaming = false;
  render();
};

const qnaDecision = async (approve) => {
  const data = await fetchJson("/api/chat/qna_decision", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: model.qnaRunId, approve }),
  });
  model.state = data.state;
  model.pending = null;
  if (data.event?.done) model.qnaStreaming = false;
  render();
};

const startRun = async () => {
  const data = await fetchJson("/api/chat/start_run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_time: model.runTime }),
  });
  model.runId = data.run_id;
  model.state = data.state;
  model.streaming = true;
  render();
};

const streamNext = async () => {
  if (!model.runId || model.pending) return;
  const data = await fetchJson("/api/chat/stream_next", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: model.runId }),
  });
  model.state = data.state;
  if (data.event?.requires_approval) model.pending = { ...data.event, mode: "opt" };
  if (data.event?.done) model.streaming = false;
  render();
};

const decision = async (approve) => {
  if (model.pending?.mode === "qna") {
    await qnaDecision(approve);
    return;
  }
  const data = await fetchJson("/api/chat/decision", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: model.runId, approve }),
  });
  model.state = data.state;
  model.audit = data.audit || [];
  model.pending = null;
  if (data.event?.done) model.streaming = false;
  render();
};

const paneTablePreview = () => {
  const tables = Object.entries(model.tables)
    .map(([name, rows]) => {
      const head = rows.length
        ? `<tr>${Object.keys(rows[0]).map((c) => `<th>${c}</th>`).join("")}</tr>`
        : "";
      const body = rows
        .map((row) => `<tr>${Object.keys(row).map((c) => `<td>${String(row[c])}</td>`).join("")}</tr>`)
        .join("");
      return `<section><h5>${name}</h5>${rows.length ? `<table><thead>${head}</thead><tbody>${body}</tbody></table>` : "<small>No rows</small>"}</section>`;
    })
    .join("");

  return `
    <section class="pane">
      <h3>Connection + Data Preview</h3>
      <div class="controls">
        <input data-model="host" placeholder="Host" value="${model.conn.host}" />
        <input data-model="port" placeholder="Port" value="${model.conn.port}" />
        <input data-model="user" placeholder="User" value="${model.conn.user}" />
        <input data-model="db_path" placeholder="Telemetry DB path (optional)" value="${model.conn.db_path}" style="min-width:250px;" />
        <button data-action="connect">Connect + Fetch Tables</button>
      </div>
      <h4>Tables + Sample Rows</h4>
      ${tables}
    </section>
  `;
};

const paneRulesFindingsAudit = () => `
  <section class="pane">
    <h3>WLM rules / findings / audit</h3>
    <h4>WLM Rules</h4><pre>${JSON.stringify(model.wlm, null, 2)}</pre>
    <h4>Findings</h4><pre>${JSON.stringify(model.state.latest_findings || [], null, 2)}</pre>
    <h4>Proposed Actions</h4><pre>${JSON.stringify(model.state.proposed_actions || [], null, 2)}</pre>
    <h4>Execution Audit</h4><pre>${JSON.stringify(model.audit || [], null, 2)}</pre>
  </section>
`;

const paneOptimizationControls = () => `
  <section class="pane">
    <h3>Optimization stream controls</h3>
    <div class="controls">
      <label>Batch Window</label>
      <select data-model="runTime"><option ${model.runTime === "20:00" ? "selected" : ""}>20:00</option><option ${model.runTime === "19:00" ? "selected" : ""}>19:00</option></select>
      <button data-action="start-run">Start Optimization Run</button>
      <button data-action="toggle-run">${model.streaming ? "Pause Stream" : "Resume Stream"}</button>
    </div>
  </section>
`;

const assistantThreadPane = () => {
  const messages = toAssistantMessages(model.state.chat || []);
  const rendered = messages
    .map((m) => `<article class="msg msg-${m.role}"><b>${m.role}</b><div>${m.content.map((chunk) => chunk.text).join("\n")}</div></article>`)
    .join("");

  return `
    <section class="pane">
      <h3>Assistant UI Thread</h3>
      <small>Mapped from STATE["chat"] to assistant-ui message shape (id, role, content[]).</small>
      <div class="thread">${rendered || "<small>No chat yet.</small>"}</div>
      <div class="controls">
        <input data-model="message" placeholder="Ask: what does my telemetry contain?" value="${model.message}" style="min-width:300px;" />
        <button data-action="send-chat">Send</button>
        <button data-action="start-qna">Run QnA Agent</button>
      </div>
      ${model.pending ? `<div class="toolcard"><b>Approval needed:</b> ${model.pending.tool?.name || "tool"}<br/><small>${JSON.stringify(model.pending.tool?.args || {})}</small><div class="controls"><button data-action="approve">Approve</button><button data-action="reject">Reject</button></div></div>` : ""}
    </section>
  `;
};

const paneAgentLog = () => `
  <section class="pane">
    <h3>Agent Activity Log</h3>
    ${(model.state.agent_log || []).map((l) => `<pre>${l}</pre>`).join("")}
  </section>
`;

const bindEvents = () => {
  root.querySelectorAll("input[data-model],select[data-model]").forEach((el) => {
    el.addEventListener("input", (event) => {
      const key = event.target.dataset.model;
      if (["host", "port", "user", "db_path"].includes(key)) model.conn[key] = event.target.value;
      else model[key] = event.target.value;
    });
  });

  root.querySelector("[data-action='connect']")?.addEventListener("click", connectDb);
  root.querySelector("[data-action='send-chat']")?.addEventListener("click", sendChat);
  root.querySelector("[data-action='start-qna']")?.addEventListener("click", startQna);
  root.querySelector("[data-action='start-run']")?.addEventListener("click", startRun);
  root.querySelector("[data-action='toggle-run']")?.addEventListener("click", () => {
    model.streaming = !model.streaming;
    render();
  });
  root.querySelector("[data-action='approve']")?.addEventListener("click", () => decision(true));
  root.querySelector("[data-action='reject']")?.addEventListener("click", () => decision(false));
};

const scheduleStreaming = () => {
  clearTimeout(window.__optTick);
  clearTimeout(window.__qnaTick);
  if (model.streaming && !model.pending) window.__optTick = setTimeout(streamNext, 1100);
  if (model.qnaStreaming && !model.pending) window.__qnaTick = setTimeout(streamQnaNext, 1200);
};

const render = () => {
  root.innerHTML = `
    <h2>Teradata Batch Optimization Accelerator</h2>
    <small>Connected DB: ${model.dbPath}</small>
    <div class="layout">
      <div class="stack">
        ${assistantThreadPane()}
        ${paneAgentLog()}
      </div>
      <div class="stack">
        ${paneOptimizationControls()}
        ${paneRulesFindingsAudit()}
        ${paneTablePreview()}
      </div>
    </div>
  `;
  bindEvents();
  scheduleStreaming();
};

refresh();
