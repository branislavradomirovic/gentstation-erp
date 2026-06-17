from core.access_control import is_platform_superadmin
from core.platform_admin import (
    TIER_1_AI_DAILY_OPERATIONS,
    TIER_2_CCTV_INTELLIGENCE,
    default_limits_for_tier,
    feature_flags_for_tier,
    slugify_tenant_name,
)


def test_slugify_tenant_name_creates_stable_slug() -> None:
    assert slugify_tenant_name("Summit CCTV Demo") == "summit-cctv-demo"
    assert slugify_tenant_name("  Aurora Fuel  ") == "aurora-fuel"


def test_feature_flags_follow_tier_capabilities() -> None:
    tier_1_flags = feature_flags_for_tier(TIER_1_AI_DAILY_OPERATIONS)
    tier_2_flags = feature_flags_for_tier(TIER_2_CCTV_INTELLIGENCE)

    assert tier_1_flags[TIER_1_AI_DAILY_OPERATIONS] is True
    assert tier_1_flags[TIER_2_CCTV_INTELLIGENCE] is False
    assert tier_2_flags[TIER_2_CCTV_INTELLIGENCE] is True


def test_default_limits_match_tier_expectations() -> None:
    assert default_limits_for_tier(TIER_1_AI_DAILY_OPERATIONS)["camera_limit"] == 0
    assert default_limits_for_tier(TIER_2_CCTV_INTELLIGENCE)["camera_limit"] is None


def test_platform_superadmin_helper_uses_username_allowlist() -> None:
    assert is_platform_superadmin("admin") is True
    assert is_platform_superadmin("ordinary-user") is False
