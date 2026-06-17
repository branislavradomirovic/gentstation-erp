from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_landing_page_sections_are_present() -> None:
    landing_text = (REPO_ROOT / "ui/landing.py").read_text()

    for needle in (
        "Operational AI for modern fuel retail networks.",
        "The problem",
        "Tier comparison",
        "Trust &amp; privacy",
        "Secure application login",
        "Open Application",
        "render_public_site",
        "render_login_page",
    ):
        assert needle in landing_text


def test_public_landing_page_does_not_render_internal_status_blocks() -> None:
    landing_text = (REPO_ROOT / "ui/landing.py").read_text()

    assert "System status: Operational" not in landing_text
    assert "System Readiness" not in landing_text
    assert "Latest startup verification" not in landing_text
    assert "def render_login_readiness_panel" not in landing_text
