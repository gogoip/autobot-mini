"""Small demo API + static server for React frontend."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.react_agents import apply_approved_action, run_autonomous_cycle
from data.seed_data import load_seed_bundle

STATE = {"agent_log": [], "chat": [], "latest_findings": [], "proposed_actions": []}
SEED = load_seed_bundle()


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
            self._json(200, {"state": STATE, "wlm_rules": SEED["wlm_rules"]})
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        if self.path == "/api/run":
            payload = self._read_json()
            run_time = payload.get("run_time", "20:00")
            run_autonomous_cycle(STATE, SEED, run_time=run_time)
            self._json(200, {"state": STATE})
            return
        if self.path == "/api/approve":
            apply_approved_action(STATE, SEED)
            self._json(200, {"state": STATE, "audit": SEED["actions_audit"]})
            return
        if self.path == "/api/chat":
            payload = self._read_json()
            msg = payload.get("message", "")
            if msg:
                STATE["chat"].append({"role": "user", "content": msg})
                STATE["chat"].append(
                    {
                        "role": "assistant",
                        "content": "Acknowledged. Coordinator is routing telemetry, dependency, optimizer, and executor agents.",
                    }
                )
            self._json(200, {"state": STATE})
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    print("Serving React demo at http://localhost:8000")
    server.serve_forever()
