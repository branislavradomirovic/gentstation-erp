from __future__ import annotations

import atexit
import json
import logging
import os
import subprocess
import sys
import time
try:
    import psutil
except ImportError:
    psutil = None
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from contextlib import suppress, closing

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.database import get_connection
from core.video_processor import parse_station_video
from core.comm_service import send_ai_report_email


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("gentstation.ai_worker")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOCK_FILE = Path("/tmp/gentstationai_ai_worker.lock")
POLL_INTERVAL_SECONDS = int(os.getenv("AI_WORKER_POLL_INTERVAL_SECONDS", "10"))
EMPTY_BACKOFF_MAX_SECONDS = int(os.getenv("AI_WORKER_EMPTY_BACKOFF_MAX_SECONDS", "60"))
AI_MAX_RETRIES = int(os.getenv("AI_WORKER_MAX_RETRIES", "3"))
AI_MEMORY_LIMIT_MB = int(os.getenv("AI_WORKER_MEMORY_LIMIT_MB", "2048"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now():
    return time.time()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False

    try:
        stat = subprocess.check_output(["ps", "-p", str(pid), "-o", "stat="], text=True).strip()
        if not stat or stat.startswith("Z"):
            return False
    except Exception:
        pass

    return True


def acquire_lock():
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as fh:
            fh.write(str(os.getpid()))
        return True
    except FileExistsError:
        try:
            existing_pid = int(LOCK_FILE.read_text().strip())
            if _pid_alive(existing_pid):
                return False
        except Exception:
            pass

        with suppress(Exception):
            LOCK_FILE.unlink(missing_ok=True)

        return acquire_lock()


def release_lock():
    with suppress(Exception):
        if LOCK_FILE.exists():
            LOCK_FILE.unlink(missing_ok=True)


atexit.register(release_lock)


def _get_connection():
    conn = get_connection()
    conn.autocommit = False
    # Log the backend PID for database session troubleshooting
    try:
        logger.debug("Database connection acquired (PID: %s)", conn.get_backend_pid())
    except Exception:
        pass
    return conn


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass
class SubmissionJob:
    sub_id: int
    video_path: str
    station_id: int
    retry_count: int = 0


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def record_worker_health(worker_name: str):
    """Captures CPU and Memory usage for the current process and saves to DB."""
    if psutil is None:
        logger.debug("psutil not installed; skipping health recording.")
        return
    try:
        process = psutil.Process(os.getpid())
        cpu = process.cpu_percent(interval=None)
        mem = process.memory_info().rss / (1024 * 1024)  # Convert to MB
        
        with closing(_get_connection()) as conn:
            cur = conn.cursor()
            
            # Fetch override from DB if exists
            cur.execute("SELECT value FROM system_settings WHERE key='ai_worker_memory_limit'")
            row = cur.fetchone()
            limit = int(row[0]) if row and row[0] else AI_MEMORY_LIMIT_MB

            cur.execute(
                "INSERT INTO worker_health_logs (worker_name, cpu_percent, memory_mb) VALUES (%s, %s, %s)",
                (worker_name, cpu, mem)
            )
            conn.commit()

            # Safety check: Auto-restart if threshold exceeded
            if mem > limit:
                logger.error("FATAL: Memory limit exceeded (Current: %.1f MB | Limit: %d MB). Terminating for auto-restart.", mem, limit)
                release_lock()
                os._exit(1) # Immediate exit to trigger restart via app.py

    except Exception as e:
        logger.debug("Failed to record worker health: %s", e)

def update_ai_status(status: str, total: int = 0, current: int = 0):
    """Updates the AI status JSON in system_settings for the Monitoring UI."""
    payload = {
        "status": status,
        "total": total,
        "current": current,
        "last_update_ts": time.time()
    }
    if status == "idle":
        payload["last_run_ts"] = time.time()
    record_worker_health("ai_worker")

    with closing(_get_connection()) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            ("ai_processing_status", json.dumps(payload))
        )
        conn.commit()

def get_force_run_flag() -> bool:
    try:
        with closing(_get_connection()) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM system_settings WHERE key=%s", ("force_ai_processing",))
            row = cur.fetchone()

            if row and str(row[0]).strip() == "1":
                cur.execute(
                    """
                    INSERT INTO system_settings (key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """,
                    ("force_ai_processing", "0"),
                )
                conn.commit()
                return True
            return False
    except Exception as e:
        logger.warning("Force run check failed: %s", e)
        return False


def get_pending_count():
    try:
        with closing(_get_connection()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM submissions
                WHERE status='pending'
                """
            )
            row = cur.fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


def claim_job() -> Optional[SubmissionJob]:
    conn = None
    try:
        conn = _get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, video_path, station_id, retry_count
            FROM submissions
            WHERE status='pending'
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        )

        row = cur.fetchone()
        if not row:
            conn.rollback()
            return None

        sub_id, path, station_id, retries = row
        backend_pid = conn.get_backend_pid()

        logger.info("Claiming job %s (Station: %s) [Attempt %s/%s] [DB PID: %s]", sub_id, station_id, retries + 1, AI_MAX_RETRIES, backend_pid)
        cur.execute(
            """
            UPDATE submissions
            SET status='processing',
                processing_started_ts = NOW()
            WHERE id=%s
            """,
            (sub_id,),
        )

        conn.commit()
        return SubmissionJob(sub_id, path, station_id, retries)

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Claim failed: %s", e)
        return None
    finally:
        if conn:
            conn.close()


def mark_done(sub_id, result):
    with closing(_get_connection()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE submissions
            SET data_json=%s,
                status='done',
                processed=1,
                processed_ts=NOW()
            WHERE id=%s
            """,
            (json.dumps(result), sub_id),
        )
        conn.commit()


def mark_failed(sub_id, error):
    with closing(_get_connection()) as conn:
        db_pid = conn.get_backend_pid()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE submissions
            SET retry_count = retry_count + 1,
                error_message = %s,
                status = CASE WHEN retry_count + 1 >= %s THEN 'failed' ELSE 'pending' END,
                processed = CASE WHEN retry_count + 1 >= %s THEN -1 ELSE 0 END,
                processed_ts = CASE WHEN retry_count + 1 >= %s THEN NOW() ELSE processed_ts END
            WHERE id=%s
            RETURNING retry_count, status
            """,
            (error, AI_MAX_RETRIES, AI_MAX_RETRIES, AI_MAX_RETRIES, sub_id),
        )
        res = cur.fetchone()
        new_count, new_status = res if res else (0, 'unknown')
        conn.commit()
        
        level = logging.ERROR if new_status == 'failed' else logging.WARNING
        logger.log(level, "Job %s failed (Attempt %s/%s). Status moved to: %s [DB PID: %s]. Error: %s", 
                   sub_id, new_count, AI_MAX_RETRIES, new_status, db_pid, error)


def reset_stuck_jobs(timeout=1800):
    cutoff = _now() - timeout
    with closing(_get_connection()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE submissions
            SET status='pending'
            WHERE status='processing'
              AND processing_started_ts IS NOT NULL
              AND processing_started_ts < to_timestamp(%s)
            RETURNING id
            """,
            (cutoff,),
        )
        rows = cur.fetchall()
        conn.commit()
        if rows:
            logger.warning("Recovered %s stuck jobs", len(rows))


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
def record_inference_latency(sub_id: int, model: str, latency: float):
    try:
        with closing(_get_connection()) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ai_inference_latency (submission_id, model_name, latency_seconds) VALUES (%s, %s, %s)",
                (sub_id, model, latency)
            )
            conn.commit()
    except Exception as e:
        logger.warning("Could not record latency: %s", e)

def process_job(job: SubmissionJob):
    start = time.time()
    db_pid = "unknown"

    if not os.path.exists(job.video_path):
        raise FileNotFoundError(job.video_path)

    result = parse_station_video(job.video_path)
    latency = time.time() - start

    # async-safe side effects
    try:
        with closing(_get_connection()) as conn:
            db_pid = conn.get_backend_pid()
            mark_done(job.sub_id, result) # Moved inside to reuse/log pid context if desired
            record_inference_latency(job.sub_id, result.get("_model_used", "unknown"), latency)
            send_ai_report_email(conn, job.station_id, result)
    except Exception as e:
        logger.warning("Email failed: %s", e)

    logger.info("Processed job %s in %.2fs [Final DB PID: %s]", job.sub_id, time.time() - start, db_pid)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    if not acquire_lock():
        logger.error("Worker already running")
        return

    backoff = POLL_INTERVAL_SECONDS

    while True:
        try:
            reset_stuck_jobs()

            pending_count = get_pending_count()
            force_run = get_force_run_flag()

            if pending_count == 0 and not force_run:
                update_ai_status("idle")
                backoff = min(EMPTY_BACKOFF_MAX_SECONDS, backoff * 2)
                time.sleep(backoff + random.uniform(0, 2))
                continue

            # Start batch processing
            total_in_batch = pending_count
            processed_count = 0
            
            while True:
                job = claim_job()
                if not job:
                    break
                
                processed_count += 1
                backoff = POLL_INTERVAL_SECONDS
                update_ai_status("processing", total=total_in_batch, current=processed_count)

                try:
                    process_job(job)
                except Exception as e:
                    logger.error("Job %s failed: %s", job.sub_id, e)
                    mark_failed(job.sub_id, str(e))

            update_ai_status("idle")

        except Exception as e:
            logger.exception("Worker loop error: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    main()