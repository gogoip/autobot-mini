# Init Guide: Teradata Agentic Demo (React + Python)

## 1) Create a Python environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2) Install dependencies
```bash
pip install -r requirements.txt
```

## 3) Start the demo
```bash
python3 ui/server.py
```

Open: `http://localhost:8000`

---

## What you should see
A 3-pane UI:
1. **Data Source**: batch window + sample telemetry/WLM preview
2. **Agent State + Synthesis**: run autonomous analysis + approve actions
3. **User Chat**: send chat prompts to simulate coordinator interactions

---

## Suggested demo flow
1. Click **Load Sample Telemetry**
2. Keep batch window at `20:00`
3. Click **Run Autonomous Analysis**
4. Review findings + proposed actions
5. Click **Approve + Execute Pending Actions**
6. Check **Agent Activity Log** for handoffs and execution status

---

## API endpoints (if you want to test directly)
- `GET /api/state`
- `POST /api/run` with `{ "run_time": "20:00" }`
- `POST /api/approve`
- `POST /api/chat` with `{ "message": "optimize 8PM batch" }`

Example:
```bash
curl -s http://127.0.0.1:8000/api/state
curl -s -X POST http://127.0.0.1:8000/api/run -H 'Content-Type: application/json' -d '{"run_time":"20:00"}'
```

---

## Notes
- React frontend is intentionally lightweight and loaded from CDN (no build step).
- Seed data is deterministic (`data/seed_data.py`) for repeatable demos.
- If `langchain` is unavailable, agent creation falls back to stubs, but the autonomous tool-routing demo still works.
