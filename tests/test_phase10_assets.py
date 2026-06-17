from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_phase10_integration_assets_exist() -> None:
    for rel_path in (
        "core/integration_service.py",
        "pages/integrations.py",
        "migrations/versions/20260617_0010_integration_framework_expansion.py",
    ):
        assert (REPO_ROOT / rel_path).exists()


def test_phase10_migration_mentions_mapping_and_import_tables() -> None:
    migration_text = (
        REPO_ROOT / "migrations/versions/20260617_0010_integration_framework_expansion.py"
    ).read_text()
    for needle in (
        "integration_station_mappings",
        "integration_import_batches",
        "secret_refs_json",
        "external_station_id",
        "source_blob",
    ):
        assert needle in migration_text
