from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_tenant_plan_page_is_registered_in_app_shell() -> None:
    app_text = (REPO_ROOT / "app.py").read_text()

    assert 'import pages.tenant_plan as tenant_plan' in app_text
    assert 'import pages.cctv_intelligence as cctv_intelligence' in app_text
    assert '"Tenant Plan": tenant_plan.render' in app_text
    assert '"CCTV Intelligence": cctv_intelligence.render' in app_text


def test_sidebar_and_access_control_expose_tenant_plan() -> None:
    sidebar_text = (REPO_ROOT / "ui/sidebar.py").read_text()
    access_control_text = (REPO_ROOT / "core/access_control.py").read_text()

    assert '("Tenant Plan", "Tenant Plan", "tenant_plan")' in sidebar_text
    assert '("CCTV Intelligence", "CCTV Intelligence", "cctv_intelligence")' in sidebar_text
    assert '"Tenant Plan"' in access_control_text
    assert '"CCTV Intelligence"' in access_control_text


def test_subscription_module_defines_tier_and_feature_gate_constants() -> None:
    subscription_text = (REPO_ROOT / "core/subscription.py").read_text()

    for needle in (
        "TIER_1_AI_DAILY_OPERATIONS",
        "TIER_2_CCTV_INTELLIGENCE",
        "FEATURE_CCTV_INTELLIGENCE",
        "require_feature",
        "require_usage_capacity",
    ):
        assert needle in subscription_text
