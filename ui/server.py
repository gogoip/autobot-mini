"""Small demo API + static server for React frontend with streaming HITL."""

from __future__ import annotations

import json
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.react_agents import (
    get_llm,
    list_tables_with_samples,
    next_chat_event,
    next_event,
    start_chat_qna,
    start_run,
)
from data.seed_data import load_seed_bundle
from data.sqlite_store import fetch_all, get_db_path, init_db

STATE = {"agent_log": [], "chat": [], "latest_findings": [], "proposed_actions": []}
SEED = load_seed_bundle()
DB_PATH = init_db(get_db_path())
LLM = get_llm()
RUNS: dict[str, object] = {}
CHAT_RUNS: dict[str, object] = {}
TABLE_PREVIEW = list_tables_with_samples(DB_PATH)


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(body)

    def _serve_file(self, file_name: str, content_type: str):
        file_path = ROOT / file_name
        if not file_path.exists():
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def do_GET(self):  # noqa: N802
        if self.path in ["/", "/index.html"]:
            self._serve_file("index.html", "text/html")
            return
        if self.path == "/app.js":
            self._serve_file("app.js", "application/javascript")
            return
        if self.path == "/api/state":
            audit = fetch_all(DB_PATH, "SELECT action_type, details, outcome, created_at FROM actions_audit ORDER BY id DESC LIMIT 20")
            self._json(
                200,
                {
                    "state": STATE,
                    "wlm_rules": SEED["wlm_rules"],
                    "audit": audit,
                    "db_path": str(DB_PATH),
                    "llm_enabled": LLM is not None,
                    "tables": TABLE_PREVIEW,
                },
            )
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        global DB_PATH, TABLE_PREVIEW
        payload = self._read_json()

        if self.path == "/api/connect":
            custom_path = payload.get("db_path")
            DB_PATH = init_db(Path(custom_path).expanduser().resolve()) if custom_path else init_db(get_db_path())
            TABLE_PREVIEW = list_tables_with_samples(DB_PATH)
            self._json(200, {"connected": True, "db_path": str(DB_PATH), "tables": TABLE_PREVIEW})
            return

        if self.path == "/api/chat":
            msg = payload.get("message", "")
            if msg:
                STATE["chat"].append({"role": "user", "content": msg})
                if LLM is not None:
                    answer = LLM.invoke(
                        "You are a Teradata batch optimization coordinator. "
                        "Provide verbose but safe reasoning summaries only. "
                        "Always mention HITL approvals before tool execution.\n"
                        f"User: {msg}"
                    ).content
                else:
                    answer = "Understood. I will stream intent detection, SQL generation, SQL execution, optimization analysis, and optional web research."
                STATE["chat"].append({"role": "assistant", "content": answer})
            self._json(200, {"state": STATE})
            return

        if self.path == "/api/chat/start_qna":
            query = payload.get("query", "what does my telemetry contain?")
            run_id = str(uuid.uuid4())
            CHAT_RUNS[run_id] = start_chat_qna(STATE, user_query=query)
            self._json(200, {"run_id": run_id, "state": STATE})
            return

        if self.path == "/api/chat/stream_qna_next":
            run_id = payload.get("run_id")
            ctx = CHAT_RUNS.get(run_id)
            if ctx is None:
                self._json(404, {"error": "invalid run_id"})
                return
            time.sleep(0.7)
            event = next_chat_event(STATE, DB_PATH, ctx, approval=None)
            STATE["chat"].append({"role": "assistant", "content": event["message"]})
            self._json(200, {"event": event, "state": STATE})
            return

        if self.path == "/api/chat/qna_decision":
            run_id = payload.get("run_id")
            approve = bool(payload.get("approve"))
            ctx = CHAT_RUNS.get(run_id)
            if ctx is None:
                self._json(404, {"error": "invalid run_id"})
                return
            event = next_chat_event(STATE, DB_PATH, ctx, approval=approve)
            STATE["chat"].append({"role": "assistant", "content": event["message"]})
            self._json(200, {"event": event, "state": STATE})
            return

        if self.path == "/api/chat/start_run":
            run_time = payload.get("run_time", "20:00")
            run_id = str(uuid.uuid4())
            RUNS[run_id] = start_run(STATE, run_time=run_time)
            self._json(200, {"run_id": run_id, "state": STATE})
            return

        if self.path == "/api/chat/stream_next":
            run_id = payload.get("run_id")
            ctx = RUNS.get(run_id)
            if ctx is None:
                self._json(404, {"error": "invalid run_id"})
                return
            time.sleep(0.6)
            event = next_event(STATE, DB_PATH, ctx, approval=None)
            STATE["chat"].append({"role": "assistant", "content": event["message"]})
            self._json(200, {"event": event, "state": STATE})
            return

        if self.path == "/api/chat/decision":
            run_id = payload.get("run_id")
            approve = bool(payload.get("approve"))
            ctx = RUNS.get(run_id)
            if ctx is None:
                self._json(404, {"error": "invalid run_id"})
                return
            event = next_event(STATE, DB_PATH, ctx, approval=approve)
            STATE["chat"].append({"role": "assistant", "content": event["message"]})
            audit = fetch_all(DB_PATH, "SELECT action_type, details, outcome, created_at FROM actions_audit ORDER BY id DESC LIMIT 20")
            self._json(200, {"event": event, "state": STATE, "audit": audit})
            return

        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    print(f"Serving React demo at http://localhost:8000 using db={DB_PATH}")
    server.serve_forever()
