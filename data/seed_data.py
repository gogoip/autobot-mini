"""Seed telemetry for a Teradata batch-optimization demo."""

from __future__ import annotations


def load_seed_bundle() -> dict:
    dbql_query_log = [
        {"query_id": "q101", "job_name": "TRN_BIG_JOIN", "run_time": "20:00", "cpu_sec": 910, "io_mb": 1200, "spool_mb": 19000, "amp_skew_pct": 31},
        {"query_id": "q102", "job_name": "TRN_DIM_REFRESH", "run_time": "20:00", "cpu_sec": 340, "io_mb": 690, "spool_mb": 5200, "amp_skew_pct": 12},
        {"query_id": "q103", "job_name": "PUB_AGG_LOAD", "run_time": "20:00", "cpu_sec": 610, "io_mb": 980, "spool_mb": 13200, "amp_skew_pct": 24},
        {"query_id": "q104", "job_name": "ING_CRM", "run_time": "19:00", "cpu_sec": 180, "io_mb": 320, "spool_mb": 1600, "amp_skew_pct": 7},
        {"query_id": "q105", "job_name": "TRN_CUSTOMER_ENRICH", "run_time": "20:00", "cpu_sec": 520, "io_mb": 840, "spool_mb": 9800, "amp_skew_pct": 19},
    ]
    table_stats = {
        "TRN_BIG_JOIN": {"stats_age_days": 45, "has_index": False, "pi_health": "poor"},
        "TRN_DIM_REFRESH": {"stats_age_days": 8, "has_index": True, "pi_health": "good"},
        "PUB_AGG_LOAD": {"stats_age_days": 39, "has_index": False, "pi_health": "fair"},
        "TRN_CUSTOMER_ENRICH": {"stats_age_days": 21, "has_index": True, "pi_health": "fair"},
    }
    job_runs = [
        {"job_name": "TRN_BIG_JOIN", "duration_min": 62, "upstream_wait_sec": 210},
        {"job_name": "TRN_DIM_REFRESH", "duration_min": 24, "upstream_wait_sec": 80},
        {"job_name": "PUB_AGG_LOAD", "duration_min": 47, "upstream_wait_sec": 95},
    ]
    job_deps = [
        {"parent_job": "ING_CRM", "child_job": "TRN_BIG_JOIN"},
        {"parent_job": "TRN_BIG_JOIN", "child_job": "TRN_DIM_REFRESH"},
        {"parent_job": "TRN_BIG_JOIN", "child_job": "PUB_AGG_LOAD"},
        {"parent_job": "TRN_DIM_REFRESH", "child_job": "PUB_AGG_LOAD"},
    ]
    wlm_rules = [
        {"class": "heavy_batch", "throttle": 5, "active_window": "19:30-22:00"},
        {"class": "standard", "throttle": 12, "active_window": "all"},
    ]
    return {
        "dbql_query_log": dbql_query_log,
        "table_stats": table_stats,
        "job_runs": job_runs,
        "job_deps": job_deps,
        "wlm_rules": wlm_rules,
        "actions_audit": [],
    }
