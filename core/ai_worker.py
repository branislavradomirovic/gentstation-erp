from __future__ import annotations

import atexit
import json
import logging
import os
import subprocess
import sys
import random
import time
import psycopg2

try:
    import psutil
except ImportError:
    psutil = None
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from contextlib import suppress, closing

import redis
from dotenv import load_dotenv

os.environ.setdefault("SKIP_SCHEMA_INIT", "1")

sys.path.append(str(Path(__file__).resolve().parents[1]))
load_dotenv()

from core.database import get_connection, test_redis_connection
from core.video_processor import parse_station_video
from core.comm_service import send_ai_report_email, send_submission_result_telegram


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("gentstation.ai_worker")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOCK_FILE = Path("/tmp/gentstationai_ai_worker.lock")
POLL_INTERVAL_SECONDS = int(os.getenv("AI_WORKER_POLL_INTERVAL_SECONDS", "10"))
EMPTY_BACKOFF_MAX_SECONDS = int(os.getenv("AI_WORKER_EMPTY_BACKOFF_MAX_SECONDS", "60"))
AI_MAX_RETRIES = int(os.getenv("AI_WORKER_MAX_RETRIES", "3"))
AI_MEMORY_LIMIT_MB = int(os.getenv("AI_WORKER_MEMORY_LIMIT_MB", "2048"))
STUCK_PROCESSING_TIMEOUT_SECONDS = int(
    os.getenv("AI_WORKER_STUCK_TIMEOUT_SECONDS", "600")
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEDUPE_KEY_PREFIX = "gsai:dedupe:"


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
        stat = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "stat="], text=True
        ).strip()
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
    with suppress(Exception):
        conn.rollback()
    conn.autocommit = False
    # Log the backend PID for database session troubleshooting
    try:
        logger.debug("Database connection acquired (PID: %s)", conn.get_backend_pid())
    except Exception:
        pass
    return conn


def _status_conn():
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if database_url:
        conn = psycopg2.connect(database_url, connect_timeout=5)
    else:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "gentstation"),
            user=os.getenv("DB_USER", "gentstation_user"),
            password=os.getenv("DB_PASSWORD", "change_me_for_local_dev"),
            connect_timeout=5,
        )
    conn.autocommit = True
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
    file_unique_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Redis client for AI worker (synchronous)
# ---------------------------------------------------------------------------
_sync_redis_client: Optional[redis.Redis] = None


def get_sync_redis() -> redis.Redis:
    global _sync_redis_client
    if _sync_redis_client is None:
        _sync_redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _sync_redis_client


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def update_ai_status(
    status: str, total: int = 0, current: int = 0, details: str = None
):
    """
    Consolidated status update:
    1. Updates ai_processing_status in system_settings
    2. Records CPU/Memory metrics in worker_health_logs
    3. Enforces memory safety limits
    """
    now_ts = time.time()
    payload = {
        "status": status,
        "total": total,
        "current": current,
        "last_update_ts": now_ts,
        "details": details,
    }
    if status == "idle":
        payload["last_run_ts"] = now_ts

    # Collect metrics
    cpu, mem = 0.0, 0.0
    if psutil:
        with suppress(Exception):
            process = psutil.Process(os.getpid())
            cpu = process.cpu_percent(interval=None)
            mem = process.memory_info().rss / (1024 * 1024)
            payload["metrics"] = {"cpu": cpu, "mem": mem}

    with closing(_status_conn()) as conn:
        try:
            cur = conn.cursor()

            # 1. Update Status
            cur.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("ai_processing_status", json.dumps(payload)),
            )

            # 2. Record Health
            cur.execute(
                "INSERT INTO worker_health_logs (worker_name, cpu_percent, memory_mb) VALUES (%s, %s, %s)",
                ("ai_worker", cpu, mem),
            )

            # 3. Check Limits
            cur.execute(
                "SELECT value FROM system_settings WHERE key='ai_worker_memory_limit'"
            )
            row = cur.fetchone()
            limit = int(row[0]) if row and row[0] else AI_MEMORY_LIMIT_MB
            if mem > limit:
                logger.error(
                    "FATAL: Memory limit exceeded (Current: %.1f MB | Limit: %d MB). Terminating for auto-restart.",
                    mem,
                    limit,
                )
                release_lock()
                os._exit(1)

        except Exception as e:
            logger.error("Failed to update AI status: %s", e)


def get_force_run_flag() -> bool:
    try:
        with closing(_get_connection()) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT value FROM system_settings WHERE key=%s",
                ("force_ai_processing",),
            )
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
    try:
        conn = _get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, video_path, station_id, retry_count, file_unique_id
            FROM submissions
            WHERE status='pending'
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        )

        row = cur.fetchone()
        if not row:
            logger.debug("No pending jobs found in submissions table.")
            conn.rollback()
            return None

        sub_id, path, station_id, retries, file_unique_id = row
        backend_pid = conn.get_backend_pid()

        logger.info(
            "Claiming job %s (Station: %s) [Attempt %s/%s] [DB PID: %s]",
            sub_id,
            station_id,
            retries + 1,
            AI_MAX_RETRIES,
            backend_pid,
        )
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
        job = SubmissionJob(sub_id, path, station_id, retries, file_unique_id)

        # Do not skip by Redis dedupe key here: the bot sets dedupe on enqueue.
        # Skipping in AI worker would prevent legitimate queued jobs from being processed.
        return job

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
        new_count, new_status = res if res else (0, "unknown")
        conn.commit()

        level = logging.ERROR if new_status == "failed" else logging.WARNING
        logger.log(
            level,
            "Job %s failed (Attempt %s/%s). Status moved to: %s [DB PID: %s]. Error: %s",
            sub_id,
            new_count,
            AI_MAX_RETRIES,
            new_status,
            db_pid,
            error,
        )
        return new_status


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
                (sub_id, model, latency),
            )
            conn.commit()
    except Exception as e:
        logger.warning("Could not record latency: %s", e)


def cleanup_processed_media(sub_id: int, video_path: Optional[str]) -> None:
    """
    Delete processed media from local storage and clear the stored path so the
    platform does not retain uploaded videos after successful analysis.
    """
    if not video_path:
        return

    with suppress(Exception):
        path = Path(video_path)
        if path.exists():
            path.unlink()

    try:
        with closing(_get_connection()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE submissions
                SET video_path = NULL,
                    audio_path = NULL
                WHERE id = %s
                """,
                (sub_id,),
            )
            conn.commit()
    except Exception as e:
        logger.warning("Could not clear stored media path for submission %s: %s", sub_id, e)


def process_job(job: SubmissionJob):
    start = time.time()
    db_pid = "unknown"

    # Help debug path issues by logging the absolute path being checked
    if not os.path.exists(job.video_path):
        abs_path = os.path.abspath(job.video_path)
        raise FileNotFoundError(
            f"Video not found at: {job.video_path} (Resolved to: {abs_path})"
        )

    result = parse_station_video(job.video_path)
    latency = time.time() - start

    mark_done(job.sub_id, result)
    record_inference_latency(job.sub_id, result.get("_model_used", "unknown"), latency)
    cleanup_processed_media(job.sub_id, job.video_path)

    try:
        with closing(_get_connection()) as conn:
            db_pid = conn.get_backend_pid()
            try:
                send_ai_report_email(conn, job.station_id, result)
            except Exception as e:
                logger.warning("AI report email failed for job %s: %s", job.sub_id, e)

            try:
                send_submission_result_telegram(conn, job.sub_id, report_data=result)
            except Exception as e:
                logger.warning(
                    "Telegram completion notification failed for job %s: %s",
                    job.sub_id,
                    e,
                )
    except Exception as e:
        logger.warning("Completion notification connection failed: %s", e)

    logger.info(
        "Processed job %s in %.2fs [Final DB PID: %s]",
        job.sub_id,
        time.time() - start,
        db_pid,
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    if not acquire_lock():
        logger.error("Worker already running")
        return

    update_ai_status("starting", 0, 0)

    backoff = POLL_INTERVAL_SECONDS
    redis_fail_count = 0

    while True:
        try:
            reset_stuck_jobs(STUCK_PROCESSING_TIMEOUT_SECONDS)

            # Check Redis before proceeding (Backoff if offline)
            # Increased timeout to 5 seconds to be more lenient during network blips
            if not test_redis_connection(timeout=5):
                redis_fail_count += 1
                if redis_fail_count >= 5:
                    logger.error(
                        "Redis connection failed 5 times. Terminating for auto-restart."
                    )
                    release_lock()
                    os._exit(1)

                logger.warning(
                    "Redis is offline (%d/5). Background workers require Redis for coordination. Backing off for 60s...",
                    redis_fail_count,
                )
                time.sleep(60)
                continue

            redis_fail_count = 0

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
                update_ai_status(
                    "processing", total=total_in_batch, current=processed_count
                )

                try:
                    process_job(job)
                except Exception as e:
                    logger.error("Job %s failed: %s", job.sub_id, e)
                    final_status = mark_failed(job.sub_id, str(e))
                    if final_status == "failed":
                        try:
                            with closing(_get_connection()) as conn:
                                send_submission_result_telegram(
                                    conn,
                                    job.sub_id,
                                    error_message=str(e),
                                )
                        except Exception as notify_err:
                            logger.warning(
                                "Telegram failure notification failed for job %s: %s",
                                job.sub_id,
                                notify_err,
                            )

            update_ai_status("idle")

        except Exception as e:
            logger.exception("Worker loop error: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
