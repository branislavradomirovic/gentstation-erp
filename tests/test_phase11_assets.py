from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_phase11_observability_assets_exist() -> None:
    for rel_path in (
        "core/observability.py",
        "pages/platform_health.py",
        "deploy/scripts/backup.sh",
        "deploy/scripts/restore.sh",
        "deploy/scripts/RUNBOOKS.md",
        "deploy/scripts/healthcheck.sh",
    ):
        assert (REPO_ROOT / rel_path).exists()


def test_phase11_assets_reference_disk_queue_worker_health() -> None:
    healthcheck_text = (REPO_ROOT / "deploy/scripts/healthcheck.sh").read_text()
    runbook_text = (REPO_ROOT / "deploy/scripts/RUNBOOKS.md").read_text()
    observability_text = (REPO_ROOT / "core/observability.py").read_text()

    assert "check_disk" in healthcheck_text
    assert "check_queue_health" in healthcheck_text
    assert "check_worker_heartbeats" in healthcheck_text
    assert "Queue Backlog Growth" in runbook_text
    assert "structured_log" in observability_text
