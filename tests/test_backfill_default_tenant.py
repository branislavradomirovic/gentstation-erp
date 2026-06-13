from scripts.backfill_default_tenant import DEFAULT_TENANT_ID, TENANT_TABLES


def test_backfill_targets_expected_tables() -> None:
    assert DEFAULT_TENANT_ID == 1
    assert "users" in TENANT_TABLES
    assert "submissions" in TENANT_TABLES
    assert "scheduled_reports" in TENANT_TABLES


def test_backfill_table_list_excludes_global_tables() -> None:
    assert "system_settings" not in TENANT_TABLES
    assert "worker_health_logs" not in TENANT_TABLES
    assert "redis_health_logs" not in TENANT_TABLES
