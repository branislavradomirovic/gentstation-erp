import pytest

from core.subscription import (
    FEATURE_AI_DAILY_OPERATIONS,
    FEATURE_CCTV_INTELLIGENCE,
    RESOURCE_CAMERAS,
    RESOURCE_EMPLOYEES,
    RESOURCE_STATIONS,
    TIER_1_AI_DAILY_OPERATIONS,
    TIER_2_CCTV_INTELLIGENCE,
    FeatureGateError,
    SubscriptionSnapshot,
    build_plan_summary,
    enforce_limit_for_snapshot,
    feature_enabled_for_snapshot,
    require_usage_capacity,
    require_feature,
    UsageLimitError,
)
from core.tenant_context import TenantContext, tenant_context


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConnection:
    def __init__(self, subscription_row, feature_rows, usage_rows):
        self.subscription_row = subscription_row
        self.feature_rows = feature_rows
        self.usage_rows = usage_rows

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        if "FROM tenant_subscriptions" in normalized:
            return FakeResult([self.subscription_row] if self.subscription_row else [])
        if "FROM tenant_feature_flags" in normalized:
            return FakeResult(self.feature_rows)
        if "COUNT(*) FROM stations" in normalized:
            return FakeResult([(self.usage_rows[RESOURCE_STATIONS],)])
        if "COUNT(*) FROM users" in normalized:
            return FakeResult([(self.usage_rows[RESOURCE_EMPLOYEES],)])
        if "COUNT(*) FROM cctv_cameras" in normalized:
            return FakeResult([(self.usage_rows[RESOURCE_CAMERAS],)])
        raise AssertionError(f"Unexpected query: {query}")


def test_tier_1_enables_daily_operations_but_not_cctv() -> None:
    snapshot = SubscriptionSnapshot(
        tenant_id=1,
        tier_code=TIER_1_AI_DAILY_OPERATIONS,
        status="active",
        billing_cycle="monthly",
        billing_currency="EUR",
        limits={RESOURCE_STATIONS: None, RESOURCE_EMPLOYEES: None, RESOURCE_CAMERAS: 0},
        feature_overrides={},
    )

    assert feature_enabled_for_snapshot(snapshot, FEATURE_AI_DAILY_OPERATIONS) is True
    assert feature_enabled_for_snapshot(snapshot, FEATURE_CCTV_INTELLIGENCE) is False


def test_tier_2_enables_cctv_features() -> None:
    snapshot = SubscriptionSnapshot(
        tenant_id=1,
        tier_code=TIER_2_CCTV_INTELLIGENCE,
        status="active",
        billing_cycle="monthly",
        billing_currency="EUR",
        limits={RESOURCE_STATIONS: None, RESOURCE_EMPLOYEES: None, RESOURCE_CAMERAS: None},
        feature_overrides={},
    )

    assert feature_enabled_for_snapshot(snapshot, FEATURE_CCTV_INTELLIGENCE) is True


def test_feature_override_cannot_bypass_tier_minimum() -> None:
    snapshot = SubscriptionSnapshot(
        tenant_id=1,
        tier_code=TIER_1_AI_DAILY_OPERATIONS,
        status="active",
        billing_cycle="monthly",
        billing_currency="EUR",
        limits={RESOURCE_STATIONS: None, RESOURCE_EMPLOYEES: None, RESOURCE_CAMERAS: 0},
        feature_overrides={FEATURE_CCTV_INTELLIGENCE: True},
    )

    assert feature_enabled_for_snapshot(snapshot, FEATURE_CCTV_INTELLIGENCE) is False


def test_usage_limit_enforcement_blocks_overages() -> None:
    snapshot = SubscriptionSnapshot(
        tenant_id=1,
        tier_code=TIER_1_AI_DAILY_OPERATIONS,
        status="active",
        billing_cycle="monthly",
        billing_currency="EUR",
        limits={RESOURCE_STATIONS: 2, RESOURCE_EMPLOYEES: 5, RESOURCE_CAMERAS: 0},
        feature_overrides={},
    )

    with pytest.raises(RuntimeError):
        enforce_limit_for_snapshot(
            snapshot,
            {RESOURCE_STATIONS: 2, RESOURCE_EMPLOYEES: 1},
            RESOURCE_STATIONS,
        )


def test_require_usage_capacity_blocks_tier_1_camera_overages() -> None:
    conn = FakeConnection(
        subscription_row=(
            TIER_1_AI_DAILY_OPERATIONS,
            "active",
            "monthly",
            "EUR",
            10,
            10,
            0,
        ),
        feature_rows=[],
        usage_rows={RESOURCE_STATIONS: 1, RESOURCE_EMPLOYEES: 2, RESOURCE_CAMERAS: 1},
    )

    with tenant_context(TenantContext(tenant_id=11, role="General Manager")):
        with pytest.raises(UsageLimitError):
            require_usage_capacity(conn, RESOURCE_CAMERAS)


def test_require_feature_fails_closed_without_tier_access() -> None:
    conn = FakeConnection(
        subscription_row=(
            TIER_1_AI_DAILY_OPERATIONS,
            "active",
            "monthly",
            "EUR",
            None,
            None,
            0,
        ),
        feature_rows=[],
        usage_rows={RESOURCE_STATIONS: 1, RESOURCE_EMPLOYEES: 2},
    )

    with tenant_context(TenantContext(tenant_id=7, role="General Manager")):
        with pytest.raises(FeatureGateError):
            require_feature(conn, FEATURE_CCTV_INTELLIGENCE)


def test_build_plan_summary_includes_usage_and_feature_matrix() -> None:
    conn = FakeConnection(
        subscription_row=(
            TIER_2_CCTV_INTELLIGENCE,
            "active",
            "monthly",
            "EUR",
            12,
            50,
            24,
        ),
        feature_rows=[(FEATURE_CCTV_INTELLIGENCE, True)],
        usage_rows={RESOURCE_STATIONS: 3, RESOURCE_EMPLOYEES: 11, RESOURCE_CAMERAS: 0},
    )

    with tenant_context(TenantContext(tenant_id=8, role="General Manager")):
        summary = build_plan_summary(conn)

    assert summary["tier"].code == TIER_2_CCTV_INTELLIGENCE
    assert summary["usage"][RESOURCE_STATIONS] == 3
    assert summary["limits"][RESOURCE_EMPLOYEES] == 50
    assert summary["features"][FEATURE_CCTV_INTELLIGENCE]["enabled"] is True
