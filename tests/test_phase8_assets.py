from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_phase8_cctv_pipeline_assets_exist() -> None:
    for rel_path in (
        "core/cctv_analysis.py",
        "core/cctv_worker.py",
        "migrations/versions/20260617_0007_cctv_analysis_versions.py",
    ):
        assert (REPO_ROOT / rel_path).exists()


def test_phase8_cctv_migration_mentions_provenance_columns() -> None:
    migration_text = (REPO_ROOT / "migrations/versions/20260617_0007_cctv_analysis_versions.py").read_text()
    for needle in (
        "provider_name",
        "model_version",
        "prompt_version",
        "confidence",
    ):
        assert needle in migration_text
