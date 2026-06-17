from __future__ import annotations

from unittest.mock import patch

import pytest
import streamlit as st

from core.report_scope import get_station_manager_options, get_user_scope
from core.subscription import RESOURCE_EMPLOYEES, RESOURCE_STATIONS, load_usage_counts
from core.tenant_context import (
    TenantContext,
    TenantContextError,
    clear_current_tenant_context,
    current_tenant_id,
    require_current_tenant_context,
    tenant_context,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        self.calls.append((normalized, params))
        if "COUNT(*) FROM stations" in normalized:
            return _FakeResult([(4,)])
        if "COUNT(*) FROM users" in normalized:
            return _FakeResult([(9,)])
        if "COUNT(*) FROM cctv_cameras" in normalized:
            return _FakeResult([(0,)])
        if "FROM users" in normalized and "role = 'Gas Station Manager'" in normalized:
            return _FakeResult([(12, "Manager One", 44)])
        if "FROM users" in normalized and "WHERE id = %s AND tenant_id = %s" in normalized:
            return _FakeResult([(77, "General Manager", 2, 3, None, "gm@example.com", None, "GM")])
        raise AssertionError(f"Unexpected query: {query}")


def test_tenant_context_can_fall_back_to_streamlit_session_state() -> None:
    with patch.object(
        st,
        "session_state",
        {
            "tenant_id": 42,
            "user_id": 9,
            "user_role": "General Manager",
            "username": "gm",
            "user_station_id": 7,
            "user_region_id": 5,
        },
        create=True,
    ):
        context = require_current_tenant_context()
        assert context.tenant_id == 42
        assert current_tenant_id() == 42
    clear_current_tenant_context()


def test_missing_tenant_context_still_fails_closed() -> None:
    clear_current_tenant_context()
    with patch.object(st, "session_state", {}, create=True):
        with pytest.raises(TenantContextError):
            current_tenant_id()


def test_subscription_usage_counts_are_tenant_scoped() -> None:
    conn = _RecordingConnection()
    with tenant_context(TenantContext(tenant_id=7, role="General Manager")):
        usage = load_usage_counts(conn)

    assert usage[RESOURCE_STATIONS] == 4
    assert usage[RESOURCE_EMPLOYEES] == 9
    assert usage["cameras"] == 0
    assert any("stations WHERE tenant_id = %s" in call[0] for call in conn.calls)
    assert any("users WHERE tenant_id = %s" in call[0] for call in conn.calls)


def test_report_scope_helpers_filter_by_tenant() -> None:
    conn = _RecordingConnection()
    with tenant_context(TenantContext(tenant_id=7, role="General Manager")):
        options = get_station_manager_options(conn)
        scope = get_user_scope(conn, 77)

    assert options == [{"id": 12, "label": "Manager One", "station_id": 44}]
    assert scope is not None
    assert scope["user_id"] == 77
    assert any("tenant_id = %s" in call[0] for call in conn.calls)
