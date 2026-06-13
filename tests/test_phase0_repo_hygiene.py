from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
SAFE_ENV_EXAMPLES = [
    REPO_ROOT / ".env.example",
    REPO_ROOT / "deployment-handoff/vm/.env.vm.example",
    REPO_ROOT / "deployment-handoff/vm/.env.production.example",
]
PROHIBITED_TRACKED_FILES = {
    ".env",
    "deployment-handoff/gentstation_backup.dump",
    "deployment-handoff/vm/.env.production.actual",
}


def tracked_files() -> set[str]:
    output = subprocess.check_output(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        text=True,
    )
    return set(output.splitlines())


def test_sensitive_runtime_artifacts_are_not_tracked() -> None:
    assert PROHIBITED_TRACKED_FILES.isdisjoint(tracked_files())


def test_only_sanitized_env_examples_are_tracked() -> None:
    tracked = tracked_files()
    for path in SAFE_ENV_EXAMPLES:
        assert path.relative_to(REPO_ROOT).as_posix() in tracked


def test_env_examples_use_placeholders_for_secret_values() -> None:
    secret_keys = {
        "DB_PASSWORD",
        "INITIAL_ADMIN_PASSWORD",
        "TELEGRAM_BOT_TOKEN",
        "SMTP_PASS",
    }
    allowed_markers = ("", "change_me", "replace_", "your_")

    for path in SAFE_ENV_EXAMPLES:
        parsed = {}
        for line in path.read_text().splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key] = value.strip()

        for key in secret_keys.intersection(parsed):
            value = parsed[key]
            assert any(marker in value for marker in allowed_markers)
