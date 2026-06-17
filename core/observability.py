from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Iterable

from core.database import get_pool_stats, test_redis_connection

logger = logging.getLogger("gentstation.observability")

WORKER_HEARTBEAT_KEYS = (
    ("AI Worker", "ai_processing_status"),
    ("Bot Worker", "telegram_bot_status"),
    ("Report Scheduler", "report_scheduler_status"),
    ("CCTV Worker", "cctv_worker_status"),
)


def structured_log(event: str, **fields: Any) -> str:
    payload = {"event": event, **fields}
    message = json.dumps(payload, default=str, sort_keys=True)
    logger.info(message)
    return message


def get_disk_health(path: str | os.PathLike[str] = ".") -> Dict[str, Any]:
    usage = shutil.disk_usage(Path(path))
    total_bytes = int(usage.total)
    used_bytes = int(usage.used)
    free_bytes = int(usage.free)
    used_pct = round((used_bytes / total_bytes) * 100, 2) if total_bytes else 0.0
    return {
        "path": str(path),
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "used_pct": used_pct,
    }


def _load_worker_status_payload(conn, setting_key: str) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT value FROM system_settings WHERE key = %s",
        (setting_key,),
    ).fetchone()
    if not row or not row[0]:
        return {}
    try:
        return json.loads(row[0])
    except Exception:
        return {}


def get_worker_health_summary(
    conn,
    *,
    stale_after_seconds: int = 120,
) -> list[Dict[str, Any]]:
    now_ts = time.time()
    summaries: list[Dict[str, Any]] = []
    for worker_name, setting_key in WORKER_HEARTBEAT_KEYS:
        payload = _load_worker_status_payload(conn, setting_key)
        last_update_ts = float(payload.get("last_update_ts") or 0)
        age_seconds = max(0, int(now_ts - last_update_ts)) if last_update_ts else None
        raw_status = str(payload.get("status") or "offline").lower()
        if not payload:
            effective_status = "offline"
        elif age_seconds is not None and age_seconds > stale_after_seconds:
            effective_status = "stale"
        else:
            effective_status = raw_status
        summaries.append(
            {
                "worker_name": worker_name,
                "setting_key": setting_key,
                "status": effective_status,
                "raw_status": raw_status,
                "age_seconds": age_seconds,
                "details": payload.get("details"),
                "metrics": payload.get("metrics") or {},
            }
        )
    return summaries


def get_queue_health_summary(conn) -> Dict[str, Any]:
    pending_submissions = int(
        conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE status = 'pending'"
        ).fetchone()[0]
        or 0
    )
    processing_submissions = int(
        conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE status = 'processing'"
        ).fetchone()[0]
        or 0
    )
    failed_submissions = int(
        conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE processed = -1 OR status = 'failed'"
        ).fetchone()[0]
        or 0
    )
    pending_cctv_jobs = int(
        conn.execute(
            "SELECT COUNT(*) FROM cctv_analysis_jobs WHERE status = 'pending'"
        ).fetchone()[0]
        or 0
    )
    processing_cctv_jobs = int(
        conn.execute(
            "SELECT COUNT(*) FROM cctv_analysis_jobs WHERE status = 'processing'"
        ).fetchone()[0]
        or 0
    )
    new_alerts = int(
        conn.execute(
            "SELECT COUNT(*) FROM ai_alerts WHERE status = 'new'"
        ).fetchone()[0]
        or 0
    )
    return {
        "pending_submissions": pending_submissions,
        "processing_submissions": processing_submissions,
        "failed_submissions": failed_submissions,
        "pending_cctv_jobs": pending_cctv_jobs,
        "processing_cctv_jobs": processing_cctv_jobs,
        "new_alerts": new_alerts,
    }


def get_worker_resource_rows(conn, *, limit: int = 20) -> list[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT worker_name, cpu_percent, memory_mb, timestamp
        FROM worker_health_logs
        ORDER BY timestamp DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "worker_name": row[0],
            "cpu_percent": float(row[1] or 0),
            "memory_mb": float(row[2] or 0),
            "timestamp": row[3],
        }
        for row in rows
    ]


def get_recent_operational_failures(conn, *, limit: int = 20) -> Iterable[tuple]:
    return conn.execute(
        """
        SELECT timestamp, user_name, action, details
        FROM activity_logs
        WHERE action LIKE '%ERROR%' OR action LIKE '%FAIL%'
        ORDER BY timestamp DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()


def get_observability_snapshot(conn) -> Dict[str, Any]:
    queue = get_queue_health_summary(conn)
    workers = get_worker_health_summary(conn)
    disk = get_disk_health()
    pool = get_pool_stats() or {}
    redis_online = test_redis_connection()
    return {
        "queue": queue,
        "workers": workers,
        "disk": disk,
        "pool": pool,
        "redis_online": redis_online,
    }
