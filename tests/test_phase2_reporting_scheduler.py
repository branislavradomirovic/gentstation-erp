from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import core.report_scheduler as report_scheduler
from core.report_builder import get_period_window_for_schedule, schedule_is_due


def test_schedule_is_due_respects_timezone_and_weekly_day():
    schedule = {
        "report_type": "weekly",
        "timezone": "Europe/Belgrade",
        "send_time": time(20, 15),
        "weekly_day": 4,
        "monthly_day": None,
        "use_last_day": False,
    }

    due_now = datetime(2026, 6, 19, 18, 20, tzinfo=timezone.utc)
    not_due_yet = datetime(2026, 6, 19, 17, 59, tzinfo=timezone.utc)

    assert schedule_is_due(schedule, now_utc=due_now) is True
    assert schedule_is_due(schedule, now_utc=not_due_yet) is False


def test_get_period_window_for_monthly_last_day_schedule():
    schedule = {
        "report_type": "monthly",
        "timezone": "Europe/Belgrade",
        "send_time": time(21, 30),
        "weekly_day": None,
        "monthly_day": 1,
        "use_last_day": True,
    }

    period_start, period_end, scheduled_for = get_period_window_for_schedule(
        schedule,
        now_utc=datetime(2026, 6, 30, 19, 40, tzinfo=timezone.utc),
    )

    local_tz = ZoneInfo("Europe/Belgrade")
    local_start = period_start.replace(tzinfo=timezone.utc).astimezone(local_tz)
    local_end = period_end.replace(tzinfo=timezone.utc).astimezone(local_tz)
    assert local_start.month == 6
    assert local_start.day == 1
    assert local_end.month == 6
    assert local_end.day == 30
    assert scheduled_for == period_end


def test_run_reports_manually_forces_processing(monkeypatch):
    captured = {}

    def fake_process_due_reports(**kwargs):
        captured.update(kwargs)
        return 3

    monkeypatch.setattr(report_scheduler, "process_due_reports", fake_process_due_reports)

    result = report_scheduler.run_reports_manually(tenant_id=8, report_type="daily", schedule_id=12)

    assert result == 3
    assert captured["force_run"] is True
    assert captured["tenant_id"] == 8
    assert captured["report_type"] == "daily"
    assert captured["schedule_id"] == 12


def test_deliver_report_records_attempts_per_channel(monkeypatch):
    calls = []

    class FakeConn:
        def execute(self, query, params=()):
            calls.append((" ".join(query.split()), params))
            class _Result:
                def fetchone(self):
                    return None
            return _Result()

        def commit(self):
            calls.append(("COMMIT", ()))

    monkeypatch.setattr(report_scheduler, "send_scheduled_report_email", lambda email, payload: True)
    monkeypatch.setattr(report_scheduler, "send_scheduled_report_telegram", lambda chat_id, payload: False)

    report_scheduler._deliver_report(
        FakeConn(),
        99,
        {
            "tenant_id": 7,
            "schedule_id": 12,
            "subscription_id": 18,
            "report_type": "daily",
            "scope_type": "station",
            "scope_id": 44,
            "recipient_user_id": 55,
            "email": "station@example.com",
            "telegram_chat_id": "12345",
            "channels": ["email", "telegram"],
        },
        {"title": "Report"},
    )

    insert_calls = [item for item in calls if "INSERT INTO report_delivery_attempts" in item[0]]
    update_calls = [item for item in calls if "UPDATE scheduled_reports" in item[0]]
    assert len(insert_calls) == 2
    assert insert_calls[0][1][8] == "email"
    assert insert_calls[0][1][9] == "sent"
    assert insert_calls[1][1][8] == "telegram"
    assert insert_calls[1][1][9] == "failed"
    assert update_calls[0][1][0] == "sent"
