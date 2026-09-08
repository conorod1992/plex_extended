"""Contract checks for TV catch-up exposure and documentation."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def test_tv_catch_up_action_is_registered_as_response_only() -> None:
    const = (COMPONENT / "const.py").read_text()
    adapter = (COMPONENT / "tv_catch_up_service.py").read_text()
    setup = (COMPONENT / "__init__.py").read_text()

    assert 'SERVICE_TV_CATCH_UP: Final = "tv_catch_up"' in const
    assert "async_setup_tv_catch_up_service" in setup
    assert "SERVICE_TV_CATCH_UP" in adapter
    assert "supports_response=SupportsResponse.ONLY" in adapter


def test_action_and_llm_share_window_and_user_controls() -> None:
    adapter = (COMPONENT / "tv_catch_up_service.py").read_text()
    tool = (COMPONENT / "tv_catch_up_llm.py").read_text()

    assert '"user"' in adapter
    assert '"user_id"' in adapter
    assert "self._user_fields()" in tool

    for field in (
        '"library"',
        '"library_id"',
        '"since"',
        '"before"',
        '"within_days"',
        '"include_specials"',
        '"include_in_progress"',
        '"limit"',
        '"episode_limit"',
        '"include_summary"',
    ):
        assert field in adapter
        assert field in tool


def test_native_assist_exposes_read_only_tv_catch_up_tool() -> None:
    provider = (COMPONENT / "llm.py").read_text()
    tool = (COMPONENT / "tv_catch_up_llm.py").read_text()

    assert 'name = "plex_extended__tv_catch_up"' in tool
    assert "TvCatchUpPlexTool(clients)" in provider
    assert "_TV_CATCH_UP_PROMPT" in provider
    assert "watch_status instead" in provider
    assert "CONF_ALLOW_LLM" not in tool


def test_docs_metadata_and_diagnostics_advertise_tv_catch_up() -> None:
    yaml = (COMPONENT / "services.yaml").read_text()
    diagnostics = (COMPONENT / "diagnostics.py").read_text()
    readme = (ROOT / "README.md").read_text()

    assert "\ntv_catch_up:\n" in yaml
    assert '"tv_catch_up"' in diagnostics
    assert "plex_extended.tv_catch_up" in readme
    assert "plex_extended__tv_catch_up" in readme
    assert "candidate_scan_truncated" in readme


def test_temporary_tv_catch_up_helpers_are_not_retained() -> None:
    assert not (ROOT / ".github" / "workflows" / "tv-catch-up-docs.yml").exists()
    assert not (ROOT / ".github" / "scripts" / "tv_catch_up_docs.py").exists()
