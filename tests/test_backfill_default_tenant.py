from scripts.backfill_default_tenant import (
    DEFAULT_TENANT_ID,
    DEFAULT_TENANT_SLUG,
    TENANT_TABLES,
)


def test_backfill_targets_expected_tables() -> None:
    assert DEFAULT_TENANT_ID == 1
    assert DEFAULT_TENANT_SLUG == "default"
    assert "users" in TENANT_TABLES
    assert "submissions" in TENANT_TABLES
    assert "scheduled_reports" in TENANT_TABLES
    assert "report_schedules" in TENANT_TABLES
    assert "report_subscriptions" in TENANT_TABLES
    assert "report_delivery_attempts" in TENANT_TABLES
    assert "ai_reports" in TENANT_TABLES


def test_backfill_table_list_excludes_global_tables() -> None:
    assert "system_settings" not in TENANT_TABLES
    assert "worker_health_logs" not in TENANT_TABLES
    assert "redis_health_logs" not in TENANT_TABLES


def test_backfill_mentions_tenant_seed_tables() -> None:
    from pathlib import Path

    script_text = Path("scripts/backfill_default_tenant.py").read_text()

    for needle in (
        "tenant_subscriptions",
        "tenant_settings",
        "tenant_feature_flags",
        "Default Tenant",
    ):
        assert needle in script_text
