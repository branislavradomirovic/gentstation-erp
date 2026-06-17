from __future__ import annotations

import json
from datetime import time
from typing import Dict, List, Optional

from core.report_scheduler import retry_delivery_attempt, run_reports_manually


def _parse_json_list(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except Exception:
            return [value]
    return [str(value)]


def _format_send_time(value) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value or "20:00")[:5]


def list_report_schedules(conn, tenant_id: int) -> List[Dict]:
    rows = conn.execute(
        """
        SELECT
            rs.id,
            rs.name,
            rs.report_type,
            rs.scope_type,
            rs.enabled,
            rs.send_time,
            rs.timezone,
            rs.weekly_day,
            rs.monthly_day,
            rs.use_last_day,
            rs.channels_json,
            base_sub.id,
            base_sub.enabled,
            base_sub.recipient_role,
            base_sub.delivery_channels_json
        FROM report_schedules rs
        LEFT JOIN report_subscriptions base_sub
          ON base_sub.tenant_id = rs.tenant_id
         AND base_sub.schedule_id = rs.id
         AND base_sub.recipient_user_id IS NULL
        WHERE rs.tenant_id = %s
        ORDER BY
            CASE rs.scope_type
                WHEN 'employee' THEN 1
                WHEN 'station' THEN 2
                WHEN 'region' THEN 3
                ELSE 4
            END,
            CASE rs.report_type
                WHEN 'daily' THEN 1
                WHEN 'weekly' THEN 2
                ELSE 3
            END,
            rs.id
        """,
        (tenant_id,),
    ).fetchall()
    schedules: List[Dict] = []
    for row in rows:
        schedules.append(
            {
                "schedule_id": row[0],
                "name": row[1],
                "report_type": row[2],
                "scope_type": row[3],
                "enabled": bool(row[4]),
                "send_time": _format_send_time(row[5]),
                "timezone": row[6] or "UTC",
                "weekly_day": row[7],
                "monthly_day": row[8],
                "use_last_day": bool(row[9]),
                "channels": _parse_json_list(row[10]),
                "default_subscription_id": row[11],
                "default_subscription_enabled": bool(row[12]) if row[11] is not None else True,
                "default_recipient_role": row[13],
                "default_channels": _parse_json_list(row[14]) or _parse_json_list(row[10]),
            }
        )
    return schedules


def get_schedule_user_overrides(conn, tenant_id: int, schedule_id: int) -> List[Dict]:
    rows = conn.execute(
        """
        SELECT
            sub.id,
            sub.recipient_user_id,
            sub.enabled,
            sub.delivery_channels_json,
            COALESCE(NULLIF(TRIM(COALESCE(u.name,'') || ' ' || COALESCE(u.surname,'')), ''), u.email, u.username) AS full_name,
            u.role
        FROM report_subscriptions sub
        JOIN users u ON u.tenant_id = sub.tenant_id AND u.id = sub.recipient_user_id
        WHERE sub.tenant_id = %s
          AND sub.schedule_id = %s
          AND sub.recipient_user_id IS NOT NULL
        ORDER BY full_name
        """,
        (tenant_id, schedule_id),
    ).fetchall()
    return [
        {
            "subscription_id": row[0],
            "user_id": row[1],
            "enabled": bool(row[2]),
            "channels": _parse_json_list(row[3]),
            "full_name": row[4],
            "role": row[5],
        }
        for row in rows
    ]


def get_recipient_candidates(
    conn,
    tenant_id: int,
    *,
    recipient_role: Optional[str] = None,
) -> List[Dict]:
    clauses = ["tenant_id = %s", "is_active = TRUE"]
    params: List = [tenant_id]
    if recipient_role:
        clauses.append("role = %s")
        params.append(recipient_role)

    rows = conn.execute(
        """
        SELECT
            id,
            COALESCE(NULLIF(TRIM(COALESCE(name,'') || ' ' || COALESCE(surname,'')), ''), email, username) AS full_name,
            role,
            email,
            telegram_chat_id
        FROM users
        WHERE """
        + " AND ".join(clauses)
        + """
        ORDER BY full_name
        """,
        tuple(params),
    ).fetchall()
    return [
        {
            "user_id": row[0],
            "full_name": row[1],
            "role": row[2],
            "email": row[3],
            "telegram_chat_id": row[4],
        }
        for row in rows
    ]


def update_report_schedule(
    conn,
    *,
    tenant_id: int,
    schedule_id: int,
    enabled: bool,
    send_time: str,
    timezone: str,
    weekly_day: Optional[int],
    monthly_day: Optional[int],
    use_last_day: bool,
    channels: List[str],
    default_subscription_enabled: bool,
) -> None:
    conn.execute(
        """
        UPDATE report_schedules
        SET enabled = %s,
            send_time = %s::time,
            timezone = %s,
            weekly_day = %s,
            monthly_day = %s,
            use_last_day = %s,
            channels_json = %s,
            updated_at = NOW()
        WHERE tenant_id = %s AND id = %s
        """,
        (
            enabled,
            send_time,
            (timezone or "UTC").strip() or "UTC",
            weekly_day,
            monthly_day,
            use_last_day,
            json.dumps(channels),
            tenant_id,
            schedule_id,
        ),
    )
    conn.execute(
        """
        UPDATE report_subscriptions
        SET enabled = %s,
            delivery_channels_json = %s,
            updated_at = NOW()
        WHERE tenant_id = %s
          AND schedule_id = %s
          AND recipient_user_id IS NULL
        """,
        (
            default_subscription_enabled,
            json.dumps(channels),
            tenant_id,
            schedule_id,
        ),
    )
    conn.commit()


def replace_schedule_user_overrides(
    conn,
    *,
    tenant_id: int,
    schedule_id: int,
    user_ids: List[int],
    channels: List[str],
) -> None:
    schedule_row = conn.execute(
        """
        SELECT scope_type
        FROM report_schedules
        WHERE tenant_id = %s AND id = %s
        """,
        (tenant_id, schedule_id),
    ).fetchone()
    if not schedule_row:
        raise ValueError("Report schedule not found.")

    scope_type = schedule_row[0]
    conn.execute(
        """
        DELETE FROM report_subscriptions
        WHERE tenant_id = %s
          AND schedule_id = %s
          AND recipient_user_id IS NOT NULL
        """,
        (tenant_id, schedule_id),
    )
    for user_id in user_ids:
        conn.execute(
            """
            INSERT INTO report_subscriptions (
                tenant_id,
                schedule_id,
                recipient_user_id,
                recipient_role,
                scope_type,
                scope_id,
                enabled,
                delivery_channels_json
            )
            VALUES (%s, %s, %s, NULL, %s, 0, TRUE, %s)
            """,
            (
                tenant_id,
                schedule_id,
                int(user_id),
                scope_type,
                json.dumps(channels),
            ),
        )
    conn.commit()


def list_delivery_attempts(
    conn,
    tenant_id: int,
    *,
    status: Optional[str] = None,
    limit: int = 200,
) -> List[Dict]:
    clauses = ["a.tenant_id = %s"]
    params: List = [tenant_id]
    if status:
        clauses.append("a.status = %s")
        params.append(status)
    params.append(int(limit))
    rows = conn.execute(
        """
        SELECT
            a.id,
            a.report_type,
            a.scope_type,
            a.channel,
            a.status,
            a.error_message,
            a.attempted_at,
            a.delivered_at,
            a.recipient_user_id,
            COALESCE(NULLIF(TRIM(COALESCE(u.name,'') || ' ' || COALESCE(u.surname,'')), ''), u.email, u.username) AS full_name,
            rs.name
        FROM report_delivery_attempts a
        LEFT JOIN users u ON u.tenant_id = a.tenant_id AND u.id = a.recipient_user_id
        LEFT JOIN report_schedules rs ON rs.tenant_id = a.tenant_id AND rs.id = a.report_schedule_id
        WHERE """
        + " AND ".join(clauses)
        + """
        ORDER BY a.attempted_at DESC, a.id DESC
        LIMIT %s
        """,
        tuple(params),
    ).fetchall()
    return [
        {
            "attempt_id": row[0],
            "report_type": row[1],
            "scope_type": row[2],
            "channel": row[3],
            "status": row[4],
            "error_message": row[5],
            "attempted_at": row[6],
            "delivered_at": row[7],
            "recipient_user_id": row[8],
            "recipient_name": row[9],
            "schedule_name": row[10],
        }
        for row in rows
    ]


def send_test_report(
    *,
    tenant_id: int,
    schedule_id: int,
) -> int:
    return run_reports_manually(tenant_id=tenant_id, schedule_id=schedule_id)


def retry_failed_report_attempt(
    *,
    tenant_id: int,
    attempt_id: int,
) -> bool:
    return retry_delivery_attempt(tenant_id=tenant_id, attempt_id=attempt_id)
