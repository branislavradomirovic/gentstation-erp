from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_phase9_reporting_assets_exist() -> None:
    for rel_path in (
        "core/cctv_reports.py",
        "core/report_builder.py",
        "pages/benchmarking.py",
        "pages/dashboard.py",
    ):
        assert (REPO_ROOT / rel_path).exists()


def test_phase9_reporting_mentions_cctv_merge_points() -> None:
    report_builder_text = (REPO_ROOT / "core/report_builder.py").read_text()
    dashboard_text = (REPO_ROOT / "pages/dashboard.py").read_text()
    benchmarking_text = (REPO_ROOT / "pages/benchmarking.py").read_text()

    assert "cctv_intelligence" in report_builder_text
    assert "get_cctv_summary_for_scope" in report_builder_text
    assert "CCTV Intelligence Snapshot" in dashboard_text
    assert "get_station_benchmark_rows" in benchmarking_text
