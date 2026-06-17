from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_files_exist() -> None:
    assert (REPO_ROOT / "alembic.ini").exists()
    assert (REPO_ROOT / "migrations/env.py").exists()
    assert (REPO_ROOT / "migrations/script.py.mako").exists()


def test_phase_two_migrations_exist() -> None:
    versions_dir = REPO_ROOT / "migrations/versions"
    files = {path.name for path in versions_dir.iterdir() if path.is_file()}

    assert "89a5e1d5e3c2_baseline.py" in files
    assert "92b6f2e6f4d3_multi_tenant_core.py" in files
    assert "20260617_0011_reporting_foundation.py" in files
    assert "20260617_0012_reporting_schedule_hierarchy.py" in files
    assert "20260617_0013_user_management_hardening.py" in files


def test_baseline_migration_mentions_core_pre_tenant_tables() -> None:
    migration_text = (REPO_ROOT / "migrations/versions/89a5e1d5e3c2_baseline.py").read_text()

    for needle in (
        "system_settings",
        "worker_health_logs",
        "redis_health_logs",
        "scheduled_reports",
        "ai_jobs",
        "ai_reports",
    ):
        assert needle in migration_text


def test_multitenant_migration_mentions_tenant_core() -> None:
    migration_text = (
        REPO_ROOT / "migrations/versions/92b6f2e6f4d3_multi_tenant_core.py"
    ).read_text()

    for needle in (
        "tenants",
        "tenant_subscriptions",
        "tenant_settings",
        "tenant_feature_flags",
        "tenant_id",
        "uq_station_categories_tenant_name",
        "Default Tenant",
    ):
        assert needle in migration_text
