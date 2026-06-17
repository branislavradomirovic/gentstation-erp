from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_phase7_cctv_pages_are_registered() -> None:
    app_text = (REPO_ROOT / "app.py").read_text()
    sidebar_text = (REPO_ROOT / "ui/sidebar.py").read_text()
    access_control_text = (REPO_ROOT / "core/access_control.py").read_text()

    assert 'import pages.cctv_cameras as cctv_cameras' in app_text
    assert '"Camera Registry": cctv_cameras.render' in app_text
    assert '("Camera Registry", "Camera Registry", "cctv_cameras")' in sidebar_text
    assert '"Camera Registry"' in access_control_text


def test_phase7_cctv_migration_mentions_review_audit_columns() -> None:
    migration_text = (REPO_ROOT / "migrations/versions/20260617_0006_cctv_review_audit.py").read_text()

    assert "from_status" in migration_text
    assert "to_status" in migration_text
    assert "cctv_review_actions" in migration_text


def test_phase7_cctv_support_files_exist() -> None:
    for rel_path in (
        "core/cctv_review.py",
        "pages/cctv_cameras.py",
        "pages/review_center.py",
    ):
        assert (REPO_ROOT / rel_path).exists()
