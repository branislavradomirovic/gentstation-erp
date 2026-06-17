from __future__ import annotations

from types import SimpleNamespace

import core.submission_storage as submission_storage


class FakeConn:
    def __init__(self):
        self.calls = []
        self.row = [None]
        self.tenant_id = None
        self.submission_id = None
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        self.calls.append((normalized, params))
        if normalized.startswith("UPDATE submissions SET video_filename"):
            self.tenant_id = params[5]
            self.submission_id = params[6]
            self.row = [params[4]]
            return SimpleNamespace(fetchone=lambda: None)
        if normalized.startswith("SELECT video_blob FROM submissions"):
            tenant_id, submission_id = params
            if tenant_id != self.tenant_id or submission_id != self.submission_id:
                return SimpleNamespace(fetchone=lambda: None)
            return SimpleNamespace(fetchone=lambda: (self.row[0],))
        raise AssertionError(normalized)

    def commit(self):
        self.commits += 1


def test_submission_video_storage_round_trip(monkeypatch) -> None:
    fake_conn = FakeConn()
    monkeypatch.setattr(
        submission_storage,
        "get_connection",
        lambda platform_access=False: fake_conn,
    )
    monkeypatch.setattr(
        submission_storage,
        "require_current_tenant_context",
        lambda: SimpleNamespace(tenant_id=4),
    )

    payload = b"demo-submission-video"
    submission_storage.save_submission_video(
        55,
        payload,
        filename="demo.mp4",
        mime_type="video/mp4",
    )
    restored = submission_storage.get_submission_video_bytes(55)
    assert restored == payload


def test_submission_video_storage_rejects_wrong_tenant(monkeypatch) -> None:
    fake_conn = FakeConn()
    monkeypatch.setattr(
        submission_storage,
        "get_connection",
        lambda platform_access=False: fake_conn,
    )
    monkeypatch.setattr(
        submission_storage,
        "require_current_tenant_context",
        lambda: SimpleNamespace(tenant_id=4),
    )

    submission_storage.save_submission_video(55, b"demo", filename="demo.mp4")
    monkeypatch.setattr(
        submission_storage,
        "require_current_tenant_context",
        lambda: SimpleNamespace(tenant_id=5),
    )
    assert submission_storage.get_submission_video_bytes(55) is None
