from __future__ import annotations

import json

import core.report_admin as report_admin


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    def __init__(self, rows_by_snippet=None):
        self.rows_by_snippet = rows_by_snippet or {}
        self.calls = []
        self.commits = 0

    def execute(self, query, params=()):
        compact_query = " ".join(query.split())
        self.calls.append((compact_query, params))
        for snippet, rows in self.rows_by_snippet.items():
            if snippet in compact_query:
                return _Result(rows)
        return _Result([])

    def commit(self):
        self.commits += 1


def test_list_report_schedules_parses_channels_and_defaults():
    conn = FakeConn(
        {
            "FROM report_schedules rs": [
                (
                    12,
                    "Station Daily Summary",
                    "daily",
                    "station",
                    True,
                    "20:30:00",
                    "Europe/Belgrade",
                    None,
                    None,
                    False,
                    json.dumps(["email", "telegram"]),
                    44,
                    True,
                    "Gas Station Manager",
                    None,
                )
            ]
        }
    )

    schedules = report_admin.list_report_schedules(conn, tenant_id=7)

    assert schedules == [
        {
            "schedule_id": 12,
            "name": "Station Daily Summary",
            "report_type": "daily",
            "scope_type": "station",
            "enabled": True,
            "send_time": "20:30",
            "timezone": "Europe/Belgrade",
            "weekly_day": None,
            "monthly_day": None,
            "use_last_day": False,
            "channels": ["email", "telegram"],
            "default_subscription_id": 44,
            "default_subscription_enabled": True,
            "default_recipient_role": "Gas Station Manager",
            "default_channels": ["email", "telegram"],
        }
    ]


def test_update_report_schedule_updates_schedule_and_default_subscription():
    conn = FakeConn()

    report_admin.update_report_schedule(
        conn,
        tenant_id=8,
        schedule_id=15,
        enabled=False,
        send_time="21:45",
        timezone="UTC",
        weekly_day=2,
        monthly_day=10,
        use_last_day=True,
        channels=["telegram"],
        default_subscription_enabled=False,
    )

    assert conn.commits == 1
    assert len(conn.calls) == 2
    assert "UPDATE report_schedules" in conn.calls[0][0]
    assert conn.calls[0][1][0] is False
    assert conn.calls[0][1][5] is True
    assert conn.calls[0][1][6] == json.dumps(["telegram"])
    assert "UPDATE report_subscriptions" in conn.calls[1][0]
    assert conn.calls[1][1][0] is False
    assert conn.calls[1][1][1] == json.dumps(["telegram"])


def test_replace_schedule_user_overrides_recreates_user_specific_subscriptions():
    conn = FakeConn(
        {
            "SELECT scope_type FROM report_schedules": [("region",)],
        }
    )

    report_admin.replace_schedule_user_overrides(
        conn,
        tenant_id=4,
        schedule_id=21,
        user_ids=[100, 101],
        channels=["email"],
    )

    assert conn.commits == 1
    assert any("DELETE FROM report_subscriptions" in query for query, _ in conn.calls)
    insert_calls = [call for call in conn.calls if "INSERT INTO report_subscriptions" in call[0]]
    assert len(insert_calls) == 2
    assert insert_calls[0][1][2] == 100
    assert insert_calls[0][1][3] == "region"
    assert insert_calls[1][1][2] == 101


def test_retry_failed_report_attempt_delegates_to_scheduler(monkeypatch):
    captured = {}

    def fake_retry_delivery_attempt(*, tenant_id, attempt_id):
        captured["tenant_id"] = tenant_id
        captured["attempt_id"] = attempt_id
        return True

    monkeypatch.setattr(report_admin, "retry_delivery_attempt", fake_retry_delivery_attempt)

    result = report_admin.retry_failed_report_attempt(tenant_id=9, attempt_id=222)

    assert result is True
    assert captured == {"tenant_id": 9, "attempt_id": 222}
