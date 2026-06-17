from __future__ import annotations

import atexit
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from contextlib import suppress, closing
from pathlib import Path
from typing import Optional, List, Dict

os.environ.setdefault("SKIP_SCHEMA_INIT", "1")
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.runtime_config import load_runtime_env

load_runtime_env()

from core.comm_service import send_scheduled_report_email, send_scheduled_report_telegram
from core.database import get_connection
from core.report_builder import (
    build_management_report,
    get_period_window_for_schedule,
    schedule_is_due,
)
from core.tenant_context import TenantContext, platform_context, tenant_context


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


def update_scheduler_status(status: str, details: Optional[str] = None):
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


def _load_enabled_schedules(
    conn,
    *,
    tenant_id: Optional[int] = None,
    report_type: Optional[str] = None,
    schedule_id: Optional[int] = None,
) -> List[Dict]:
    clauses = ["rs.enabled = TRUE"]
    params: List = []
    if tenant_id is not None:
        clauses.append("rs.tenant_id = %s")
        params.append(int(tenant_id))
    if report_type:
        clauses.append("rs.report_type = %s")
        params.append(report_type)
    if schedule_id is not None:
        clauses.append("rs.id = %s")
        params.append(int(schedule_id))

    rows = conn.execute(
        """
        SELECT
            rs.id,
            rs.tenant_id,
            rs.name,
            rs.report_type,
            rs.scope_type,
            rs.send_time,
            rs.timezone,
            rs.weekly_day,
            rs.monthly_day,
            rs.use_last_day,
            rs.channels_json
        FROM report_schedules rs
        WHERE """ + " AND ".join(clauses) + """
        ORDER BY rs.tenant_id, rs.report_type, rs.scope_type, rs.id
        """
        ,
        tuple(params),
    ).fetchall()
    schedules = []
    for row in rows:
        channels = row[10] or []
        if isinstance(channels, str):
            try:
                channels = json.loads(channels)
            except Exception:
                channels = [channels]
        schedules.append(
            {
                "schedule_id": row[0],
                "tenant_id": row[1],
                "name": row[2],
                "report_type": row[3],
                "scope_type": row[4],
                "send_time": row[5],
                "timezone": row[6],
                "weekly_day": row[7],
                "monthly_day": row[8],
                "use_last_day": bool(row[9]),
                "channels": [str(channel) for channel in channels if str(channel).strip()],
            }
        )
    return schedules


def load_report_schedules(
    conn,
    *,
    tenant_id: Optional[int] = None,
    report_type: Optional[str] = None,
    schedule_id: Optional[int] = None,
) -> List[Dict]:
    return _load_enabled_schedules(
        conn,
        tenant_id=tenant_id,
        report_type=report_type,
        schedule_id=schedule_id,
    )


def _resolve_schedule_recipients(conn, schedule: dict) -> List[Dict]:
    rows = conn.execute(
        """
        SELECT
            sub.id,
            sub.tenant_id,
            sub.schedule_id,
            sub.recipient_user_id,
            sub.recipient_role,
            sub.scope_type,
            sub.scope_id,
            sub.delivery_channels_json,
            u.id AS user_id,
            u.email,
            u.telegram_chat_id,
            COALESCE(NULLIF(TRIM(COALESCE(u.name,'') || ' ' || COALESCE(u.surname,'')), ''), u.email, u.username) AS full_name,
            u.role,
            u.station_id,
            u.region_id
        FROM report_subscriptions sub
        LEFT JOIN users u
          ON u.tenant_id = sub.tenant_id
         AND (
              (sub.recipient_user_id IS NOT NULL AND u.id = sub.recipient_user_id)
              OR (
                  sub.recipient_user_id IS NULL
                  AND sub.recipient_role IS NOT NULL
                  AND u.role = sub.recipient_role
                  AND u.is_active = TRUE
              )
         )
        WHERE sub.tenant_id = %s
          AND sub.schedule_id = %s
          AND sub.enabled = TRUE
        ORDER BY sub.id, u.id
        """,
        (schedule["tenant_id"], schedule["schedule_id"]),
    ).fetchall()

    recipients: List[Dict] = []
    for row in rows:
        subscription_channels = row[7] or schedule.get("channels") or []
        if isinstance(subscription_channels, str):
            try:
                subscription_channels = json.loads(subscription_channels)
            except Exception:
                subscription_channels = [subscription_channels]

        user_id = row[8]
        if user_id is None:
            continue

        scope_type = row[5] or schedule["scope_type"]
        scope_id = row[6]
        if scope_type == "employee":
            scope_id = user_id
        elif scope_type == "station" and not scope_id:
            scope_id = row[13]
        elif scope_type == "region" and not scope_id:
            scope_id = row[14]
        elif scope_type == "company":
            scope_id = None

        recipients.append(
            {
                "subscription_id": row[0],
                "tenant_id": row[1],
                "schedule_id": row[2],
                "recipient_user_id": user_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "email": row[9],
                "telegram_chat_id": row[10],
                "full_name": row[11],
                "role": row[12],
                "report_type": schedule["report_type"],
                "channels": [str(channel) for channel in subscription_channels if str(channel).strip()],
            }
        )
    return recipients


def _upsert_pending_report(conn, recipient: dict, period_start, period_end, scheduled_for):
    existing = conn.execute(
        """
        SELECT id, status
        FROM scheduled_reports
        WHERE tenant_id = %s
          AND report_type = %s
          AND scope_type = %s
          AND COALESCE(scope_id, -1) = COALESCE(%s, -1)
          AND recipient_user_id = %s
          AND period_start = %s
          AND period_end = %s
        """,
        (
            recipient["tenant_id"],
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
            tenant_id, report_type, scope_type, scope_id, recipient_user_id,
            period_start, period_end, scheduled_for, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        RETURNING id
        """,
        (
            recipient["tenant_id"],
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


def _record_delivery_attempt(
    conn,
    *,
    report_id: int,
    recipient: dict,
    payload: dict,
    channel: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO report_delivery_attempts (
            tenant_id,
            scheduled_report_id,
            report_schedule_id,
            report_subscription_id,
            report_type,
            scope_type,
            scope_id,
            recipient_user_id,
            channel,
            status,
            error_message,
            payload_json,
            delivered_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s = 'sent' THEN NOW() ELSE NULL END)
        """,
        (
            recipient["tenant_id"],
            report_id,
            recipient.get("schedule_id"),
            recipient.get("subscription_id"),
            recipient["report_type"],
            recipient["scope_type"],
            recipient["scope_id"],
            recipient["recipient_user_id"],
            channel,
            status,
            error_message,
            json.dumps(payload),
            status,
        ),
    )


def _deliver_report(conn, report_id: int, recipient: dict, payload: dict):
    channels = []
    success = False
    last_error = None
    configured_channels = recipient.get("channels") or ["email", "telegram"]

    for channel in configured_channels:
        if channel == "email":
            if not recipient.get("email"):
                continue
            email_ok = send_scheduled_report_email(recipient["email"], payload)
            channels.append("email")
            success = success or email_ok
            if email_ok:
                _record_delivery_attempt(
                    conn, report_id=report_id, recipient=recipient, payload=payload, channel="email", status="sent"
                )
            else:
                last_error = "Email delivery failed."
                _record_delivery_attempt(
                    conn,
                    report_id=report_id,
                    recipient=recipient,
                    payload=payload,
                    channel="email",
                    status="failed",
                    error_message=last_error,
                )
        elif channel == "telegram":
            if not recipient.get("telegram_chat_id"):
                continue
            telegram_ok = send_scheduled_report_telegram(recipient["telegram_chat_id"], payload)
            channels.append("telegram")
            success = success or telegram_ok
            if telegram_ok:
                _record_delivery_attempt(
                    conn, report_id=report_id, recipient=recipient, payload=payload, channel="telegram", status="sent"
                )
            else:
                last_error = "Telegram delivery failed."
                _record_delivery_attempt(
                    conn,
                    report_id=report_id,
                    recipient=recipient,
                    payload=payload,
                    channel="telegram",
                    status="failed",
                    error_message=last_error,
                )

    status = "sent" if success else "failed"
    error_message = None if success else (last_error or "No delivery channel succeeded.")
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


def process_due_reports(
    *,
    now_utc: Optional[datetime] = None,
    force_run: bool = False,
    tenant_id: Optional[int] = None,
    report_type: Optional[str] = None,
    schedule_id: Optional[int] = None,
):
    with platform_context():
        with closing(get_connection(platform_access=True)) as conn:
            sent_count = 0
            schedules = _load_enabled_schedules(
                conn,
                tenant_id=tenant_id,
                report_type=report_type,
                schedule_id=schedule_id,
            )
            for schedule in schedules:
                if not force_run and not schedule_is_due(schedule, now_utc=now_utc):
                    continue
                period_start, period_end, scheduled_for = get_period_window_for_schedule(
                    schedule,
                    now_utc=now_utc,
                )
                recipients = _resolve_schedule_recipients(conn, schedule)
                for recipient in recipients:
                    with tenant_context(TenantContext(tenant_id=recipient["tenant_id"])):
                        with closing(get_connection()) as scoped_conn:
                            report_id, current_status = _upsert_pending_report(
                                scoped_conn,
                                recipient,
                                period_start,
                                period_end,
                                scheduled_for,
                            )
                            if current_status in {"sent", "failed"}:
                                continue

                            payload = build_management_report(
                                conn=scoped_conn,
                                tenant_id=recipient["tenant_id"],
                                report_type=recipient["report_type"],
                                scope_type=recipient["scope_type"],
                                scope_id=recipient["scope_id"],
                                role=recipient["role"],
                                recipient_name=recipient["full_name"],
                                period_start=period_start,
                                period_end=period_end,
                            )
                            _deliver_report(scoped_conn, report_id, recipient, payload)
                            sent_count += 1
            return sent_count


def run_reports_manually(
    *,
    tenant_id: Optional[int] = None,
    report_type: Optional[str] = None,
    schedule_id: Optional[int] = None,
    now_utc: Optional[datetime] = None,
) -> int:
    return process_due_reports(
        now_utc=now_utc or datetime.now(timezone.utc),
        force_run=True,
        tenant_id=tenant_id,
        report_type=report_type,
        schedule_id=schedule_id,
    )


def retry_delivery_attempt(*, tenant_id: int, attempt_id: int) -> bool:
    with platform_context():
        with closing(get_connection(platform_access=True)) as conn:
            row = conn.execute(
                """
                SELECT
                    a.scheduled_report_id,
                    a.report_schedule_id,
                    a.report_type,
                    a.scope_type,
                    a.scope_id,
                    a.recipient_user_id,
                    a.channel,
                    sr.period_start,
                    sr.period_end,
                    sr.payload_json,
                    COALESCE(NULLIF(TRIM(COALESCE(u.name,'') || ' ' || COALESCE(u.surname,'')), ''), u.email, u.username) AS full_name,
                    u.role,
                    u.email,
                    u.telegram_chat_id
                FROM report_delivery_attempts a
                JOIN scheduled_reports sr
                  ON sr.tenant_id = a.tenant_id
                 AND sr.id = a.scheduled_report_id
                JOIN users u
                  ON u.tenant_id = a.tenant_id
                 AND u.id = a.recipient_user_id
                WHERE a.tenant_id = %s
                  AND a.id = %s
                  AND a.status = 'failed'
                """,
                (tenant_id, attempt_id),
            ).fetchone()
            if not row:
                return False

            (
                report_id,
                schedule_id,
                report_type,
                scope_type,
                scope_id,
                recipient_user_id,
                channel,
                period_start,
                period_end,
                payload_json,
                full_name,
                role,
                email,
                telegram_chat_id,
            ) = row

            payload = payload_json
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = None

            with tenant_context(TenantContext(tenant_id=tenant_id)):
                with closing(get_connection()) as scoped_conn:
                    if not payload:
                        payload = build_management_report(
                            conn=scoped_conn,
                            tenant_id=tenant_id,
                            report_type=report_type,
                            scope_type=scope_type,
                            scope_id=scope_id,
                            role=role,
                            recipient_name=full_name,
                            period_start=period_start,
                            period_end=period_end,
                        )

                    recipient = {
                        "tenant_id": tenant_id,
                        "schedule_id": schedule_id,
                        "subscription_id": None,
                        "recipient_user_id": recipient_user_id,
                        "scope_type": scope_type,
                        "scope_id": scope_id,
                        "email": email,
                        "telegram_chat_id": telegram_chat_id,
                        "full_name": full_name,
                        "role": role,
                        "report_type": report_type,
                        "channels": [channel],
                    }
                    _deliver_report(scoped_conn, report_id, recipient, payload)
                    return True


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
