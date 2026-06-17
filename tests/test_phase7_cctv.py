from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import core.storage as storage
from core.cctv_review import apply_review_transition, allowed_review_actions


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


class FakeConn:
    def __init__(self):
        self.calls = []
        self.job_row = [None]
        self.job_tenant_id = None
        self.job_id = None
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        self.calls.append((normalized, params))
        if normalized.startswith("UPDATE cctv_analysis_jobs"):
            self.job_tenant_id = params[5]
            self.job_id = params[6]
            self.job_row = [params[4]]
            return SimpleNamespace(fetchone=lambda: None)
        if normalized.startswith("SELECT evidence_blob FROM cctv_analysis_jobs"):
            tenant_id, job_id = params
            if tenant_id != self.job_tenant_id or job_id != self.job_id:
                return SimpleNamespace(fetchone=lambda: None)
            return SimpleNamespace(fetchone=lambda: (self.job_row[0],))
        raise AssertionError(normalized)

    def commit(self):
        self.commits += 1


def test_database_evidence_storage_round_trip(monkeypatch, tmp_path) -> None:
    fake_conn = FakeConn()

    monkeypatch.setattr(storage, "get_connection", lambda platform_access=False: fake_conn)
    monkeypatch.setattr(storage, "require_current_tenant_context", lambda: SimpleNamespace(tenant_id=7))

    source = tmp_path / "clip.mp4"
    payload = b"demo-video-bytes"
    source.write_bytes(payload)

    ref = storage.save_event_evidence(str(source), 12)
    assert ref == "db://cctv_analysis_jobs/12"
    assert not source.exists()

    restored = storage.get_evidence_url(ref)
    assert restored == payload


def test_review_transition_records_audit_metadata() -> None:
    session = FakeSession()
    event = SimpleNamespace(id=44, tenant_id=9, status="new")

    result = apply_review_transition(
        session,
        event=event,
        tenant_id=9,
        reviewer_user_id=101,
        new_status="acknowledged",
        comment="Reviewed by duty manager",
    )

    assert event.status == "acknowledged"
    assert result.previous_status == "new"
    assert result.new_status == "acknowledged"
    assert session.added[0].from_status == "new"
    assert session.added[0].to_status == "acknowledged"
    assert "acknowledged" in allowed_review_actions("new")


def test_review_transition_rejects_cross_tenant_event() -> None:
    session = FakeSession()
    event = SimpleNamespace(id=44, tenant_id=9, status="new")

    try:
        apply_review_transition(
            session,
            event=event,
            tenant_id=10,
            reviewer_user_id=101,
            new_status="acknowledged",
        )
        raise AssertionError("Expected a ValueError")
    except ValueError:
        pass


def test_database_storage_rejects_wrong_tenant(monkeypatch, tmp_path) -> None:
    fake_conn = FakeConn()
    monkeypatch.setattr(storage, "get_connection", lambda platform_access=False: fake_conn)
    monkeypatch.setattr(storage, "require_current_tenant_context", lambda: SimpleNamespace(tenant_id=7))

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"demo")
    ref = storage.save_event_evidence(str(source), 12)

    monkeypatch.setattr(storage, "require_current_tenant_context", lambda: SimpleNamespace(tenant_id=8))
    assert storage.get_evidence_url(ref) is None
