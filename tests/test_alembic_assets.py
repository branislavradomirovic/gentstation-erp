from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_files_exist() -> None:
    assert (REPO_ROOT / "alembic.ini").exists()
    assert (REPO_ROOT / "migrations/env.py").exists()
    assert (REPO_ROOT / "migrations/script.py.mako").exists()


def test_phase_two_migrations_exist() -> None:
    versions_dir = REPO_ROOT / "migrations/versions"
    files = {path.name for path in versions_dir.iterdir() if path.is_file()}

    assert "20260613_0001_baseline_schema.py" in files
    assert "20260613_0002_multitenant_core.py" in files


def test_multitenant_migration_mentions_tenant_core() -> None:
    migration_text = (
        REPO_ROOT / "migrations/versions/20260613_0002_multitenant_core.py"
    ).read_text()

    for needle in (
        "tenants",
        "tenant_subscriptions",
        "tenant_settings",
        "tenant_feature_flags",
        "tenant_id",
    ):
        assert needle in migration_text
