import importlib


def reload_runtime_config():
    import core.runtime_config as runtime_config

    return importlib.reload(runtime_config)


def test_production_env_disables_embedded_workers(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    runtime_config = reload_runtime_config()

    assert runtime_config.is_production_env() is True
    assert runtime_config.should_spawn_embedded_workers() is False


def test_local_env_allows_embedded_workers(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    runtime_config = reload_runtime_config()

    assert runtime_config.is_production_env() is False
    assert runtime_config.should_spawn_embedded_workers() is True


def test_background_worker_env_flags_detect_enabled_worker(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTO_START_BACKGROUND_WORKERS", "0")
    monkeypatch.setenv("AUTO_START_TELEGRAM_BOT", "1")
    monkeypatch.setenv("AUTO_START_AI_WORKER", "0")
    monkeypatch.setenv("AUTO_START_REPORT_SCHEDULER", "0")
    runtime_config = reload_runtime_config()

    assert runtime_config.background_workers_enabled_by_env() is True
