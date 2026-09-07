"""Regression checks for the Plex external-auth callback page."""

from pathlib import Path


CONFIG_FLOW = (
    Path(__file__).parents[1]
    / "custom_components"
    / "plex_extended"
    / "config_flow.py"
)


def test_auth_callback_closes_or_returns_to_home_assistant() -> None:
    """Successful Plex auth must not leave users on a dead-end callback page."""
    source = CONFIG_FLOW.read_text(encoding="utf-8")

    assert "<script>window.close();</script>" in source
    assert '<a href="/">Return to Home Assistant</a>' in source
    assert "Returning to Home Assistant" in source
    assert 'headers={"Cache-Control": "no-store"}' in source
