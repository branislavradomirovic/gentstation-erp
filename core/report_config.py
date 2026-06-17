from __future__ import annotations

import json


DEFAULT_REPORT_SCHEDULES = (
    {
        "key": "employee_daily",
        "name": "Employee Daily Report",
        "report_type": "daily",
        "scope_type": "employee",
        "send_time": "20:00",
        "weekly_day": None,
        "monthly_day": None,
        "use_last_day": False,
        "channels": ["email", "telegram"],
        "recipient_role": "Employee",
    },
    {
        "key": "employee_weekly",
        "name": "Employee Weekly Summary",
        "report_type": "weekly",
        "scope_type": "employee",
        "send_time": "20:00",
        "weekly_day": 4,
        "monthly_day": None,
        "use_last_day": False,
        "channels": ["email", "telegram"],
        "recipient_role": "Employee",
    },
    {
        "key": "employee_monthly",
        "name": "Employee Monthly Summary",
        "report_type": "monthly",
        "scope_type": "employee",
        "send_time": "20:00",
        "weekly_day": None,
        "monthly_day": 1,
        "use_last_day": True,
        "channels": ["email", "telegram"],
        "recipient_role": "Employee",
    },
    {
        "key": "station_daily",
        "name": "Station Daily Report",
        "report_type": "daily",
        "scope_type": "station",
        "send_time": "20:15",
        "weekly_day": None,
        "monthly_day": None,
        "use_last_day": False,
        "channels": ["email", "telegram"],
        "recipient_role": "Gas Station Manager",
    },
    {
        "key": "station_weekly",
        "name": "Station Weekly Summary",
        "report_type": "weekly",
        "scope_type": "station",
        "send_time": "20:15",
        "weekly_day": 4,
        "monthly_day": None,
        "use_last_day": False,
        "channels": ["email", "telegram"],
        "recipient_role": "Gas Station Manager",
    },
    {
        "key": "station_monthly",
        "name": "Station Monthly Summary",
        "report_type": "monthly",
        "scope_type": "station",
        "send_time": "20:15",
        "weekly_day": None,
        "monthly_day": 1,
        "use_last_day": True,
        "channels": ["email", "telegram"],
        "recipient_role": "Gas Station Manager",
    },
    {
        "key": "region_daily",
        "name": "Region Daily Report",
        "report_type": "daily",
        "scope_type": "region",
        "send_time": "20:30",
        "weekly_day": None,
        "monthly_day": None,
        "use_last_day": False,
        "channels": ["email", "telegram"],
        "recipient_role": "Region Manager",
    },
    {
        "key": "region_weekly",
        "name": "Region Weekly Summary",
        "report_type": "weekly",
        "scope_type": "region",
        "send_time": "20:30",
        "weekly_day": 4,
        "monthly_day": None,
        "use_last_day": False,
        "channels": ["email", "telegram"],
        "recipient_role": "Region Manager",
    },
    {
        "key": "region_monthly",
        "name": "Region Monthly Summary",
        "report_type": "monthly",
        "scope_type": "region",
        "send_time": "20:30",
        "weekly_day": None,
        "monthly_day": 1,
        "use_last_day": True,
        "channels": ["email", "telegram"],
        "recipient_role": "Region Manager",
    },
    {
        "key": "company_daily",
        "name": "Company Daily Report",
        "report_type": "daily",
        "scope_type": "company",
        "send_time": "21:00",
        "weekly_day": None,
        "monthly_day": None,
        "use_last_day": False,
        "channels": ["email", "telegram"],
        "recipient_role": "General Manager",
    },
    {
        "key": "company_weekly",
        "name": "Company Weekly Summary",
        "report_type": "weekly",
        "scope_type": "company",
        "send_time": "21:15",
        "weekly_day": 4,
        "monthly_day": None,
        "use_last_day": False,
        "channels": ["email", "telegram"],
        "recipient_role": "General Manager",
    },
    {
        "key": "company_monthly",
        "name": "Company Monthly Summary",
        "report_type": "monthly",
        "scope_type": "company",
        "send_time": "21:30",
        "weekly_day": None,
        "monthly_day": 1,
        "use_last_day": True,
        "channels": ["email", "telegram"],
        "recipient_role": "General Manager",
    },
)


def seed_default_report_configuration(
    conn,
    *,
    tenant_id: int,
    timezone: str = "UTC",
) -> None:
    for schedule in DEFAULT_REPORT_SCHEDULES:
        schedule_row = conn.execute(
            """
            INSERT INTO report_schedules (
                tenant_id,
                name,
                report_type,
                scope_type,
                enabled,
                send_time,
                timezone,
                weekly_day,
                monthly_day,
                use_last_day,
                channels_json,
                config_json
            )
            VALUES (%s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, report_type, scope_type) DO UPDATE SET
                name = EXCLUDED.name,
                timezone = COALESCE(report_schedules.timezone, EXCLUDED.timezone)
            RETURNING id
            """,
            (
                tenant_id,
                schedule["name"],
                schedule["report_type"],
                schedule["scope_type"],
                schedule["send_time"],
                (timezone or "UTC").strip() or "UTC",
                schedule["weekly_day"],
                schedule["monthly_day"],
                schedule["use_last_day"],
                json.dumps(schedule["channels"]),
                json.dumps({"seed_key": schedule["key"]}),
            ),
        ).fetchone()

        schedule_id = int(schedule_row[0])
        conn.execute(
            """
            INSERT INTO report_subscriptions (
                tenant_id,
                schedule_id,
                recipient_role,
                scope_type,
                scope_id,
                enabled,
                delivery_channels_json
            )
            VALUES (%s, %s, %s, %s, %s, TRUE, %s)
            ON CONFLICT (tenant_id, schedule_id, recipient_role, scope_type, scope_id)
            DO NOTHING
            """,
            (
                tenant_id,
                schedule_id,
                schedule["recipient_role"],
                schedule["scope_type"],
                0,
                json.dumps(schedule["channels"]),
            ),
        )
