from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_landing_page_sections_are_present() -> None:
    app_text = (REPO_ROOT / "app.py").read_text()

    for needle in (
        "Operational AI for modern fuel retail networks.",
        "The problem",
        "Three solution pillars",
        "Tier comparison",
        "Benefits for pilot rollouts",
        "Trust &amp; privacy",
        "Secure workspace login",
        'href="#login-access"',
    ):
        assert needle in app_text


def test_public_landing_page_does_not_render_internal_status_blocks() -> None:
    app_text = (REPO_ROOT / "app.py").read_text()

    assert "System status: Operational" not in app_text
    assert "System Readiness" not in app_text
    assert "Latest startup verification" not in app_text
    assert "def render_login_readiness_panel" not in app_text
