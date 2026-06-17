from __future__ import annotations

import core.user_admin as user_admin


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, handlers=None):
        self.handlers = handlers or []
        self.calls = []
        self.commits = 0

    def execute(self, query, params=()):
        compact = " ".join(query.split())
        self.calls.append((compact, params))
        for needle, rows in self.handlers:
            if needle in compact:
                if callable(rows):
                    rows = rows(params)
                return _Result(rows)
        return _Result([])

    def commit(self):
        self.commits += 1


def test_validate_user_assignment_blocks_cross_scope_employee_manager():
    conn = FakeConn(
        [
            ("FROM stations", [(10, 50, "Station 10")]),
            ("FROM users", [(200, "Gas Station Manager", 11, 50, "manager@example.com")]),
        ]
    )

    try:
        user_admin.validate_user_assignment(
            conn,
            tenant_id=7,
            role="Employee",
            station_id=10,
            manager_user_id=200,
        )
    except ValueError as exc:
        assert "employee station" in str(exc).lower()
    else:
        raise AssertionError("Expected employee manager mismatch to be rejected.")


def test_validate_user_assignment_normalizes_station_region_for_manager():
    conn = FakeConn(
        [
            ("FROM stations", [(10, 50, "Station 10")]),
            ("FROM users", [(300, "Region Manager", None, 50, "rm@example.com")]),
        ]
    )

    normalized = user_admin.validate_user_assignment(
        conn,
        tenant_id=7,
        role="Gas Station Manager",
        station_id=10,
        manager_user_id=300,
    )

    assert normalized == {
        "station_id": 10,
        "region_id": 50,
        "manager_user_id": 300,
    }


def test_preview_user_import_reports_invalid_rows_before_commit():
    csv_bytes = (
        "first_name,surname,email,role,station_name,region_name,manager_email,phone,telegram_chat_id\n"
        "Ana,Markovic,ana@example.com,Employee,Station 10,,manager@example.com,+381600000001,\n"
        "Milan,Petrovic,milan@example.com,Region Manager,,North Region,bad-manager@example.com,+381600000002,\n"
    ).encode("utf-8")

    conn = FakeConn(
        [
            ("SELECT id FROM stations", [(10,)]),
            ("SELECT id FROM regions", [(77,)]),
            (
                "SELECT id FROM users WHERE tenant_id = %s AND LOWER(email) = LOWER(%s)",
                lambda params: [(200,)] if params[1] == "manager@example.com" else [],
            ),
            ("FROM stations", [(10, 50, "Station 10")]),
            ("FROM users WHERE tenant_id = %s AND id = %s", [(200, "Gas Station Manager", 10, 50, "manager@example.com")]),
        ]
    )

    preview = user_admin.preview_user_import(conn, tenant_id=9, content_bytes=csv_bytes)

    assert len(preview.preview_rows) == 2
    assert len(preview.valid_rows) == 1
    assert preview.error_count == 1
    assert preview.preview_rows[0]["status"] == "valid"
    assert preview.preview_rows[1]["status"] == "error"


def test_set_user_lifecycle_state_updates_force_password_change_and_active_flags():
    conn = FakeConn()

    user_admin.set_user_lifecycle_state(
        conn,
        tenant_id=4,
        user_id=22,
        lifecycle_state="offboarded",
    )

    assert conn.commits == 1
    update_query, params = conn.calls[0]
    assert "UPDATE users" in update_query
    assert params[0] == "offboarded"
    assert params[1] is False
    assert params[2] is False
