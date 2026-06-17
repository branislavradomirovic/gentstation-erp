from types import SimpleNamespace

import core.auth as auth
import scripts.seed_demo_tenants as seed_demo_tenants


class FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0
        self.next_row = None
        self.platform_access_flags = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self

    def execute(self, query, params=()):
        self.executed.append((query, params))
        normalized = " ".join(query.split())
        if "SELECT region_id FROM stations" in normalized:
            self.next_row = (77,)
            return FakeResult(self.next_row)
        if "INSERT INTO users" in normalized:
            self.next_row = (4242,)
            return FakeResult(self.next_row)
        if "SELECT id FROM tenants WHERE slug = %s" in normalized:
            self.next_row = None
            return FakeResult(None)
        if "SELECT id FROM stations WHERE tenant_id = %s AND name = %s" in normalized:
            self.next_row = (99,)
            return FakeResult(self.next_row)
        self.next_row = None
        return FakeResult(None)

    def fetchone(self):
        return self.next_row

    def commit(self):
        self.commits += 1


def test_create_user_supports_platform_onboarding_without_tenant_context(monkeypatch):
    fake_conn = FakeConnection()
    captured = {}

    def fake_get_connection(*, platform_access=False):
        fake_conn.platform_access_flags.append(platform_access)
        return fake_conn

    def fake_require_usage_capacity(conn, resource, tenant_context=None):
        captured["conn"] = conn
        captured["resource"] = resource
        captured["tenant_context"] = tenant_context

    monkeypatch.setattr(auth, "get_connection", fake_get_connection)
    monkeypatch.setattr(auth, "get_current_tenant_context", lambda: None)
    monkeypatch.setattr(auth, "require_usage_capacity", fake_require_usage_capacity)

    user = auth.create_user(
        username="company.admin",
        password="secret123",  # pragma: allowlist secret
        email="admin@example.com",
        role="General Manager",
        name="Company",
        surname="Admin",
        tenant_id=17,
    )

    assert user["id"] == 4242
    assert user["tenant_id"] == 17
    assert fake_conn.platform_access_flags == [True]
    assert captured["tenant_context"].tenant_id == 17
    insert_query, insert_params = fake_conn.executed[-1]
    assert "INSERT INTO users" in insert_query
    assert insert_params[0] == 17


def test_seed_demo_tenant_uses_returned_tenant_id(monkeypatch):
    fake_conn = FakeConnection()
    created = []
    seeded = []

    def fake_create_tenant_with_company_admin(conn, **kwargs):
        created.append(kwargs)
        return SimpleNamespace(
            tenant_id=17,
            tenant_slug=kwargs["tenant_slug"],
            tenant_name=kwargs["tenant_name"],
            tier_code=kwargs["tier_code"],
            admin_user_id=101,
            admin_username=kwargs["admin_username"],
            admin_email=kwargs["admin_email"],
        )

    def fake_seed_demo_hierarchy(conn, **kwargs):
        seeded.append(kwargs)

    monkeypatch.setattr(seed_demo_tenants, "create_tenant_with_company_admin", fake_create_tenant_with_company_admin)
    monkeypatch.setattr(seed_demo_tenants, "seed_demo_hierarchy", fake_seed_demo_hierarchy)

    payload = seed_demo_tenants.DEMO_TENANTS[1]
    seed_demo_tenants._seed_demo_tenant(fake_conn, payload)

    assert created and created[0]["tenant_slug"] == payload["tenant_slug"]
    assert seeded and seeded[0]["tenant_id"] == 17
    assert seeded[0]["tenant_name"] == payload["tenant_name"]
    assert any("INSERT INTO cctv_cameras" in q for q, _ in fake_conn.executed)
    assert any(params[0] == 17 for q, params in fake_conn.executed if "INSERT INTO cctv_cameras" in q)
