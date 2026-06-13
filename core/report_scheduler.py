from __future__ import annotations

import atexit
import json
import logging
import os
import random
import sys
import time
from contextlib import suppress, closing
from pathlib import Path

os.environ.setdefault("SKIP_SCHEMA_INIT", "1")
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.runtime_config import load_runtime_env

load_runtime_env()

from core.comm_service import send_scheduled_report_email, send_scheduled_report_telegram
from core.database import get_connection
from core.report_builder import cadence_is_due, get_period_window, build_management_report


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("gentstation.report_scheduler")

LOCK_FILE = Path("/tmp/gentstationai_report_scheduler.lock")
POLL_INTERVAL_SECONDS = int(os.getenv("REPORT_SCHEDULER_POLL_INTERVAL_SECONDS", "60"))
REPORT_TYPES = ("daily", "weekly", "monthly")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


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
        LOCK_FILE.unlink(missing_ok=True)


atexit.register(release_lock)


def update_scheduler_status(status: str, details: str = None):
    payload = {
        "status": status,
        "details": details,
        "last_update_ts": time.time(),
    }
    with closing(get_connection()) as conn:
        conn.execute(
            """
            INSERT INTO system_settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            ("report_scheduler_status", json.dumps(payload)),
        )
        conn.commit()


def _recipients_for_report(conn, report_type: str):
    station_rows = conn.execute(
        """
        SELECT id, station_id, region_id, email, telegram_chat_id,
               COALESCE(NULLIF(TRIM(COALESCE(name,'') || ' ' || COALESCE(surname,'')), ''), email, username) AS full_name,
               role
        FROM users
        WHERE role = 'Gas Station Manager' AND station_id IS NOT NULL AND is_active = TRUE
        """
    ).fetchall()
    region_rows = conn.execute(
        """
        SELECT id, region_id, email, telegram_chat_id,
               COALESCE(NULLIF(TRIM(COALESCE(name,'') || ' ' || COALESCE(surname,'')), ''), email, username) AS full_name,
               role
        FROM users
        WHERE role = 'Region Manager' AND region_id IS NOT NULL AND is_active = TRUE
        """
    ).fetchall()
    gm_rows = conn.execute(
        """
        SELECT id, email, telegram_chat_id,
               COALESCE(NULLIF(TRIM(COALESCE(name,'') || ' ' || COALESCE(surname,'')), ''), email, username) AS full_name,
               role
        FROM users
        WHERE role = 'General Manager' AND is_active = TRUE
        """
    ).fetchall()

    recipients = []
    for row in station_rows:
        recipients.append(
            {
                "recipient_user_id": row[0],
                "scope_type": "station",
                "scope_id": row[1],
                "region_id": row[2],
                "email": row[3],
                "telegram_chat_id": row[4],
                "full_name": row[5],
                "role": row[6],
                "report_type": report_type,
            }
        )
    for row in region_rows:
        recipients.append(
            {
                "recipient_user_id": row[0],
                "scope_type": "region",
                "scope_id": row[1],
                "email": row[2],
                "telegram_chat_id": row[3],
                "full_name": row[4],
                "role": row[5],
                "report_type": report_type,
            }
        )
    for row in gm_rows:
        recipients.append(
            {
                "recipient_user_id": row[0],
                "scope_type": "company",
                "scope_id": None,
                "email": row[1],
                "telegram_chat_id": row[2],
                "full_name": row[3],
                "role": row[4],
                "report_type": report_type,
            }
        )
    return recipients


def _upsert_pending_report(conn, recipient: dict, period_start, period_end, scheduled_for):
    existing = conn.execute(
        """
        SELECT id, status
        FROM scheduled_reports
        WHERE report_type = %s
          AND scope_type = %s
          AND COALESCE(scope_id, -1) = COALESCE(%s, -1)
          AND recipient_user_id = %s
          AND period_start = %s
          AND period_end = %s
        """,
        (
            recipient["report_type"],
            recipient["scope_type"],
            recipient["scope_id"],
            recipient["recipient_user_id"],
            period_start,
            period_end,
        ),
    ).fetchone()
    if existing:
        return existing[0], existing[1]

    row = conn.execute(
        """
        INSERT INTO scheduled_reports (
            report_type, scope_type, scope_id, recipient_user_id,
            period_start, period_end, scheduled_for, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
        RETURNING id
        """,
        (
            recipient["report_type"],
            recipient["scope_type"],
            recipient["scope_id"],
            recipient["recipient_user_id"],
            period_start,
            period_end,
            scheduled_for,
        ),
    ).fetchone()
    conn.commit()
    return row[0], "pending"


def _deliver_report(conn, report_id: int, recipient: dict, payload: dict):
    channels = []
    success = False
    if recipient.get("email"):
        email_ok = send_scheduled_report_email(recipient["email"], payload)
        channels.append("email")
        success = success or email_ok
    if recipient.get("telegram_chat_id"):
        telegram_ok = send_scheduled_report_telegram(recipient["telegram_chat_id"], payload)
        channels.append("telegram")
        success = success or telegram_ok

    status = "sent" if success else "failed"
    error_message = None if success else "No delivery channel succeeded."
    conn.execute(
        """
        UPDATE scheduled_reports
        SET status = %s,
            delivery_channel = %s,
            payload_json = %s,
            error_message = %s,
            sent_at = CASE WHEN %s = 'sent' THEN NOW() ELSE sent_at END,
            updated_at = NOW()
        WHERE id = %s
        """,
        (
            status,
            ",".join(channels) if channels else None,
            json.dumps(payload),
            error_message,
            status,
            report_id,
        ),
    )
    conn.commit()


def process_due_reports():
    with closing(get_connection()) as conn:
        sent_count = 0
        for report_type in REPORT_TYPES:
            if not cadence_is_due(report_type):
                continue

            period_start, period_end, scheduled_for = get_period_window(report_type)
            recipients = _recipients_for_report(conn, report_type)
            for recipient in recipients:
                report_id, current_status = _upsert_pending_report(
                    conn, recipient, period_start, period_end, scheduled_for
                )
                if current_status in {"sent", "failed"}:
                    continue

                payload = build_management_report(
                    conn=conn,
                    report_type=report_type,
                    scope_type=recipient["scope_type"],
                    scope_id=recipient["scope_id"],
                    role=recipient["role"],
                    recipient_name=recipient["full_name"],
                    period_start=period_start,
                    period_end=period_end,
                )
                _deliver_report(conn, report_id, recipient, payload)
                sent_count += 1
        return sent_count


def main():
    if not acquire_lock():
        logger.error("Report scheduler already running")
        return

    while True:
        try:
            update_scheduler_status("running")
            sent_count = process_due_reports()
            update_scheduler_status("idle", details=f"Processed {sent_count} report deliveries.")
            time.sleep(POLL_INTERVAL_SECONDS + random.uniform(0, 3))
        except Exception as e:
            logger.exception("Report scheduler loop error: %s", e)
            update_scheduler_status("error", details=str(e))
            time.sleep(10)


if __name__ == "__main__":
    main()
