from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_database_layer_mentions_row_level_tenant_enforcement() -> None:
    database_text = (REPO_ROOT / "core/database.py").read_text()

    for needle in (
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
        "gsai_assign_tenant_id",
        "gsai_current_tenant_id",
        "app.current_tenant_id",
        "app.platform_access",
    ):
        assert needle in database_text


def test_tenant_owned_table_list_covers_cross_tenant_assets() -> None:
    database_text = (REPO_ROOT / "core/database.py").read_text()

    for table_name in (
        "users",
        "sessions",
        "submissions",
        "ai_alerts",
        "scheduled_reports",
        "ai_reports",
    ):
        assert f'"{table_name}"' in database_text or f"'{table_name}'" in database_text
