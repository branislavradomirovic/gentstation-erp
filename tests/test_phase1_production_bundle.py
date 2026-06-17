from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_app_has_hard_production_worker_guard() -> None:
    app_text = (REPO_ROOT / "app.py").read_text()

    assert "if is_production_env():" in app_text
    assert "Use dedicated worker services" in app_text


def test_production_config_centralizes_environment_defaults() -> None:
    config_text = (REPO_ROOT / "core/deployment_config.py").read_text()

    for needle in (
        "PRODUCTION_ENV_VALUES",
        "PRODUCTION_SERVICE_NAMES",
        "PRODUCTION_COMPOSE_FILE",
        "production_environment_defaults",
    ):
        assert needle in config_text


def test_production_compose_targets_ubuntu_services() -> None:
    compose_text = (REPO_ROOT / "deploy/docker-compose.prod.yml").read_text()

    for needle in (
        "reverse-proxy:",
        "ports:",
        '"80:80"',
        '"443:443"',
        "OLLAMA_HOST: 0.0.0.0:11434",
    ):
        assert needle in compose_text


def test_healthcheck_scripts_exist_and_are_referenced() -> None:
    for rel in (
        "deploy/scripts/healthcheck.sh",
        "deploy/scripts/healthcheck_web.sh",
        "deploy/scripts/healthcheck_worker.sh",
    ):
        assert (REPO_ROOT / rel).exists()
