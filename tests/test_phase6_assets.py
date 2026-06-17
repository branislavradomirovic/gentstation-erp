from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_platform_admin_page_is_registered() -> None:
    app_text = (REPO_ROOT / "app.py").read_text()
    sidebar_text = (REPO_ROOT / "ui/sidebar.py").read_text()
    access_control_text = (REPO_ROOT / "core/access_control.py").read_text()

    assert 'import pages.platform_admin as platform_admin' in app_text
    assert '"Platform Admin": platform_admin.render' in app_text
    assert '("Platform Admin", "Platform Admin", "platform_admin")' in sidebar_text
    assert '"Platform Admin"' in access_control_text
    assert "platform_superadmin_only" in access_control_text


def test_phase6_service_and_seed_assets_exist() -> None:
    assert (REPO_ROOT / "core/platform_admin.py").exists()
    assert (REPO_ROOT / "pages/platform_admin.py").exists()
    assert (REPO_ROOT / "scripts/seed_demo_tenants.py").exists()


def test_database_session_builder_mentions_tenant_scoped_sqlalchemy_settings() -> None:
    database_text = (REPO_ROOT / "core/database.py").read_text()

    assert "_apply_tenant_settings_to_sqla_connection" in database_text
    assert "app.current_tenant_id" in database_text
    assert "app.platform_access" in database_text
