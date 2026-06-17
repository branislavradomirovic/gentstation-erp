from __future__ import annotations

import json

from core import observability


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        self.calls.append((normalized, params))
        if "FROM system_settings" in normalized:
            key = params[0]
            mapping = {
                "ai_processing_status": json.dumps({"status": "running", "last_update_ts": 10_000_000_000}),
                "telegram_bot_status": json.dumps({"status": "online", "last_update_ts": 10_000_000_000}),
                "report_scheduler_status": json.dumps({"status": "idle", "last_update_ts": 10_000_000_000}),
                "cctv_worker_status": json.dumps({"status": "processing", "last_update_ts": 10_000_000_000}),
            }
            return _FakeResult([(mapping.get(key),)])
        if "COUNT(*) FROM submissions WHERE status = 'pending'" in normalized:
            return _FakeResult([(3,)])
        if "COUNT(*) FROM submissions WHERE status = 'processing'" in normalized:
            return _FakeResult([(1,)])
        if "COUNT(*) FROM submissions WHERE processed = -1 OR status = 'failed'" in normalized:
            return _FakeResult([(2,)])
        if "COUNT(*) FROM cctv_analysis_jobs WHERE status = 'pending'" in normalized:
            return _FakeResult([(4,)])
        if "COUNT(*) FROM cctv_analysis_jobs WHERE status = 'processing'" in normalized:
            return _FakeResult([(1,)])
        if "COUNT(*) FROM ai_alerts WHERE status = 'new'" in normalized:
            return _FakeResult([(5,)])
        if "FROM worker_health_logs" in normalized:
            return _FakeResult([("ai_worker", 12.5, 256.0, "2026-06-17T11:00:00")])
        if "FROM activity_logs" in normalized:
            return _FakeResult([("2026-06-17", "System", "AI_FAIL", "Queue stalled")])
        raise AssertionError(normalized)


def test_structured_log_returns_json_message():
    message = observability.structured_log("unit_test", detail="ok", count=2)
    payload = json.loads(message)
    assert payload["event"] == "unit_test"
    assert payload["detail"] == "ok"
    assert payload["count"] == 2


def test_queue_and_worker_health_helpers_collect_expected_metrics(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(observability.time, "time", lambda: 9_999_999_950)

    queue = observability.get_queue_health_summary(conn)
    workers = observability.get_worker_health_summary(conn)
    resources = observability.get_worker_resource_rows(conn)
    failures = list(observability.get_recent_operational_failures(conn))

    assert queue["pending_submissions"] == 3
    assert queue["pending_cctv_jobs"] == 4
    assert workers[0]["worker_name"] == "AI Worker"
    assert workers[0]["status"] == "running"
    assert resources[0]["worker_name"] == "ai_worker"
    assert failures[0][2] == "AI_FAIL"
