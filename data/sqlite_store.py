"""SQLite setup and query helpers for telemetry demo."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from data.seed_data import load_seed_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "telemetry.db"


def get_db_path() -> Path:
    raw = os.getenv("TELEMETRY_DB_PATH")
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_DB_PATH


def init_db(db_path: Path | None = None) -> Path:
    db_file = db_path or get_db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    seed = load_seed_bundle()
    con = sqlite3.connect(db_file)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS dbql_query_log (
            query_id TEXT PRIMARY KEY,
            job_name TEXT,
            run_time TEXT,
            cpu_sec INTEGER,
            io_mb INTEGER,
            spool_mb INTEGER,
            amp_skew_pct INTEGER
        );
        CREATE TABLE IF NOT EXISTS table_stats (
            job_name TEXT PRIMARY KEY,
            stats_age_days INTEGER,
            has_index INTEGER,
            pi_health TEXT
        );
        CREATE TABLE IF NOT EXISTS job_deps (
            parent_job TEXT,
            child_job TEXT
        );
        CREATE TABLE IF NOT EXISTS actions_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT,
            details TEXT,
            outcome TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cur.execute("DELETE FROM dbql_query_log")
    cur.execute("DELETE FROM table_stats")
    cur.execute("DELETE FROM job_deps")
    cur.executemany(
        "INSERT INTO dbql_query_log(query_id, job_name, run_time, cpu_sec, io_mb, spool_mb, amp_skew_pct) VALUES (:query_id,:job_name,:run_time,:cpu_sec,:io_mb,:spool_mb,:amp_skew_pct)",
        seed["dbql_query_log"],
    )
    cur.executemany(
        "INSERT INTO table_stats(job_name, stats_age_days, has_index, pi_health) VALUES (?,?,?,?)",
        [(name, v["stats_age_days"], int(v["has_index"]), v["pi_health"]) for name, v in seed["table_stats"].items()],
    )
    cur.executemany(
        "INSERT INTO job_deps(parent_job, child_job) VALUES (:parent_job,:child_job)",
        seed["job_deps"],
    )
    con.commit()
    con.close()
    return db_file


def fetch_all(db_path: Path, sql: str, params: tuple = ()) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(sql, params).fetchall()]
    con.close()
    return rows


def execute_sql(db_path: Path, sql: str, params: tuple = ()) -> int:
    con = sqlite3.connect(db_path)
    cur = con.execute(sql, params)
    con.commit()
    count = cur.rowcount
    con.close()
    return count
