from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_phase12_launch_artifacts_exist() -> None:
    for rel_path in (
        "docs/production/LAUNCH_CHECKLIST.md",
        "docs/production/SMOKE_TEST_CHECKLIST.md",
        "deploy/PILOT_ONBOARDING.md",
        "RELEASE_NOTES.md",
    ):
        assert (REPO_ROOT / rel_path).exists()


def test_phase12_prod_bundle_mentions_limits_and_checklists() -> None:
    compose_text = (REPO_ROOT / "deploy/docker-compose.prod.yml").read_text()
    env_text = (REPO_ROOT / "deploy/env/.env.production.example").read_text()
    release_notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text()

    assert "WEB_CPU_LIMIT" in compose_text
    assert "AI_WORKER_CONTAINER_MEMORY_LIMIT" in compose_text
    assert "OMP_NUM_THREADS" in env_text
    assert "WORKER_STALE_SECONDS" in env_text
    assert "Remaining risks" in release_notes


def test_phase12_checklists_cover_launch_smoke_and_pilot() -> None:
    launch_text = (REPO_ROOT / "docs/production/LAUNCH_CHECKLIST.md").read_text()
    smoke_text = (REPO_ROOT / "docs/production/SMOKE_TEST_CHECKLIST.md").read_text()
    pilot_text = (REPO_ROOT / "deploy/PILOT_ONBOARDING.md").read_text()

    assert "Platform Health" in launch_text
    assert "Cross-tenant DB isolation tests pass" in launch_text
    assert "landing page" in smoke_text.lower()
    assert "Platform Health loads for a Platform Superadmin only" in smoke_text
    assert "Pilot acceptance checks" in pilot_text
