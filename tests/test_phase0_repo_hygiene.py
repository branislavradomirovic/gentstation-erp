from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
SAFE_ENV_EXAMPLES = [
    REPO_ROOT / ".env.example",
    REPO_ROOT / "deployment-handoff/vm/.env.vm.example",
    REPO_ROOT / "deployment-handoff/vm/.env.production.example",
    REPO_ROOT / "deploy/env/.env.production.example",
]
PROHIBITED_TRACKED_FILES = {
    ".env",
    "deployment-handoff/gentstation_backup.dump",
    "deployment-handoff/vm/.env.production.actual",
    ".gitignore.bak",
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
    for path in SAFE_ENV_EXAMPLES:
        parsed = {}
        for line in path.read_text().splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key] = value.strip()

        for key, value in parsed.items():
            if "PASSWORD" in key or "TOKEN" in key or key.endswith("_PASS"):
                assert value
                assert not value.startswith(("postgresql://", "postgres://"))
                assert any(
                    marker in value.lower()
                    for marker in ("change_me", "replace_", "your_", "example")
                )


def test_phase_zero_production_readme_exists() -> None:
    readme = REPO_ROOT / "docs/production/README.md"
    assert readme.exists()
    text = readme.read_text()
    for needle in (
        "dedicated Ubuntu",
        "web",
        "ai-worker",
        "telegram-worker",
        "report-scheduler",
        "Render",
    ):
        assert needle in text


def test_phase_zero_ignore_rules_cover_mac_artifacts_and_backups() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    dockerignore = (REPO_ROOT / ".dockerignore").read_text()

    for needle in (
        ".DS_Store",
        ".AppleDouble",
        ".Spotlight-V100",
        ".Trashes",
        "*.bak",
    ):
        assert needle in gitignore
        assert needle in dockerignore
