from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_prod_compose_separates_web_and_workers() -> None:
    compose_text = (REPO_ROOT / "deploy/docker-compose.prod.yml").read_text()

    for service_name in (
        "web:",
        "ai-worker:",
        "telegram-worker:",
        "report-scheduler:",
        "postgres:",
        "redis:",
        "reverse-proxy:",
    ):
        assert service_name in compose_text

    assert 'AUTO_START_BACKGROUND_WORKERS: "0"' in compose_text
    assert 'AUTO_START_TELEGRAM_BOT: "0"' in compose_text
    assert 'AUTO_START_AI_WORKER: "0"' in compose_text
    assert 'AUTO_START_REPORT_SCHEDULER: "0"' in compose_text
    assert "cctv-worker:" not in compose_text
    assert "env_file: ./env/.env.production" in compose_text


def test_prod_compose_uses_healthcheck_scripts() -> None:
    compose_text = (REPO_ROOT / "deploy/docker-compose.prod.yml").read_text()

    assert "deploy/scripts/healthcheck_web.sh" in compose_text
    assert "deploy/scripts/healthcheck_worker.sh" in compose_text
    assert "caddy:2.8-alpine" in compose_text


def test_prod_deploy_script_uses_env_file() -> None:
    deploy_script = (REPO_ROOT / "deploy/scripts/deploy.sh").read_text()

    assert "--env-file" in deploy_script
    assert "deploy/env/.env.production" in deploy_script


def test_production_env_example_stays_sanitized() -> None:
    env_text = (REPO_ROOT / "deploy/env/.env.production.example").read_text()

    assert "replace_with_strong_database_password" in env_text
    assert "replace_with_strong_admin_password" in env_text
    assert "replace_if_telegram_enabled" in env_text
    assert "replace_with_smtp_password" in env_text
