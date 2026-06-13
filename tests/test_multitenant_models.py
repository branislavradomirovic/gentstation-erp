from core.models import Base


def test_tenant_core_tables_exist_in_metadata() -> None:
    for table_name in (
        "tenants",
        "tenant_subscriptions",
        "tenant_settings",
        "tenant_feature_flags",
    ):
        assert table_name in Base.metadata.tables


def test_tenant_owned_tables_expose_tenant_id_columns() -> None:
    for table_name in (
        "regions",
        "station_categories",
        "stations",
        "users",
        "sessions",
        "activity_logs",
        "submissions",
        "ai_alerts",
        "ai_inference_latency",
        "scheduled_reports",
        "ai_jobs",
        "ai_reports",
    ):
        assert "tenant_id" in Base.metadata.tables[table_name].c


def test_station_categories_are_unique_per_tenant() -> None:
    constraints = Base.metadata.tables["station_categories"].constraints
    names = {constraint.name for constraint in constraints if constraint.name}
    assert "uq_station_categories_tenant_name" in names
