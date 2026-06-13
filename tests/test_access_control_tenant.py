import pytest

from core.access_control import can_manage_region, can_manage_station, has_access, require_page_access
from core.tenant_context import TenantContext, TenantContextError


class FakeConn:
    def __init__(self, subscription_row, feature_rows):
        self.subscription_row = subscription_row
        self.feature_rows = feature_rows

    def execute(self, query, params=()):
        del params
        if "FROM tenant_subscriptions" in query:
            return _FakeResult([self.subscription_row])
        if "FROM tenant_feature_flags" in query:
            return _FakeResult(self.feature_rows)
        raise AssertionError(query)


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


def test_require_page_access_needs_tenant_context() -> None:
    with pytest.raises(TenantContextError):
        require_page_access("Dashboard", None, "General Manager", "admin")


def test_require_page_access_allows_authorized_role() -> None:
    context = TenantContext(tenant_id=1, user_id=1, role="General Manager", username="admin")
    require_page_access("Dashboard", context, "General Manager", "admin")


def test_station_and_region_management_checks_use_central_context() -> None:
    gm_context = TenantContext(tenant_id=1, role="General Manager")
    station_context = TenantContext(tenant_id=1, role="Gas Station Manager", station_id=44)
    region_context = TenantContext(tenant_id=1, role="Region Manager", region_id=12)

    assert can_manage_station(gm_context, 99) is True
    assert can_manage_station(station_context, 44) is True
    assert can_manage_station(station_context, 45) is False
    assert can_manage_region(gm_context, 5) is True
    assert can_manage_region(region_context, 12) is True
    assert can_manage_region(region_context, 13) is False


def test_has_access_hides_feature_gated_pages_without_connection() -> None:
    context = TenantContext(tenant_id=1, role="General Manager", username="admin")

    assert has_access(
        "Tenant Plan",
        "General Manager",
        "admin",
        tenant_context=context,
    ) is True


def test_has_access_blocks_cctv_page_for_tier_1() -> None:
    context = TenantContext(tenant_id=1, role="General Manager", username="gm-user")
    conn = FakeConn(
        (
            "tier_1_ai_daily_operations",
            "active",
            "monthly",
            "EUR",
            None,
            None,
            0,
        ),
        [],
    )

    assert has_access(
        "CCTV Intelligence",
        "General Manager",
        "gm-user",
        tenant_context=context,
        conn=conn,
    ) is False


def test_has_access_allows_cctv_page_for_tier_2() -> None:
    context = TenantContext(tenant_id=1, role="General Manager", username="gm-user")
    conn = FakeConn(
        (
            "tier_2_cctv_intelligence",
            "active",
            "monthly",
            "EUR",
            None,
            None,
            None,
        ),
        [("tier_2_cctv_intelligence", True)],
    )

    assert has_access(
        "CCTV Intelligence",
        "General Manager",
        "gm-user",
        tenant_context=context,
        conn=conn,
    ) is True
