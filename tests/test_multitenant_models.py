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
        "report_schedules",
        "report_subscriptions",
        "report_delivery_attempts",
        "ai_jobs",
        "ai_reports",
        "cctv_cameras",
        "cctv_zones",
        "cctv_events",
        "cctv_review_actions",
        "cctv_analysis_jobs",
        "cctv_metrics_hourly",
        "integrations",
        "integration_station_mappings",
        "integration_events",
        "integration_import_batches",
    ):
        assert "tenant_id" in Base.metadata.tables[table_name].c


def test_station_categories_are_unique_per_tenant() -> None:
    constraints = Base.metadata.tables["station_categories"].constraints
    names = {constraint.name for constraint in constraints if constraint.name}
    assert "uq_station_categories_tenant_name" in names


def test_reporting_foundation_tables_exist_in_metadata() -> None:
    for table_name in (
        "report_schedules",
        "report_subscriptions",
        "report_delivery_attempts",
    ):
        assert table_name in Base.metadata.tables


def test_cctv_review_actions_store_transition_metadata() -> None:
    table = Base.metadata.tables["cctv_review_actions"]
    assert "from_status" in table.c
    assert "to_status" in table.c


def test_cctv_pipeline_tables_store_analysis_provenance() -> None:
    for table_name in ("cctv_events", "cctv_analysis_jobs", "cctv_metrics_hourly"):
        table = Base.metadata.tables[table_name]
        for column_name in ("provider_name", "model_version", "prompt_version"):
            assert column_name in table.c
    assert "confidence" in Base.metadata.tables["cctv_events"].c
    assert "confidence" in Base.metadata.tables["cctv_metrics_hourly"].c
    assert "job_id" in Base.metadata.tables["cctv_events"].c
    for column_name in (
        "evidence_filename",
        "evidence_mime_type",
        "evidence_size_bytes",
        "evidence_checksum",
        "evidence_blob",
    ):
        assert column_name in Base.metadata.tables["cctv_analysis_jobs"].c


def test_integration_framework_tables_store_mapping_and_secret_metadata() -> None:
    integrations_table = Base.metadata.tables["integrations"]
    mapping_table = Base.metadata.tables["integration_station_mappings"]
    import_table = Base.metadata.tables["integration_import_batches"]

    for column_name in ("display_name", "metadata_json", "secret_ref", "secret_refs_json"):
        assert column_name in integrations_table.c

    for column_name in ("integration_id", "station_id", "external_station_id", "external_location_id", "metadata_json"):
        assert column_name in mapping_table.c

    for column_name in ("integration_id", "import_type", "source_filename", "source_blob", "result_json"):
        assert column_name in import_table.c
