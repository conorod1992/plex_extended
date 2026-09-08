"""Contract tests for Discover/Watchlist public exposure."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components/plex_extended"


def _documentation() -> str:
    return "\n".join(
        path.read_text()
        for path in (
            ROOT / "README.md",
            ROOT / "docs" / "action-reference.md",
            ROOT / "docs" / "assist-reference.md",
        )
    )


def test_actions_use_correct_response_contracts() -> None:
    source = (COMPONENT / "discover_watchlist_service.py").read_text()
    assert "SERVICE_DISCOVER_SEARCH" in source
    assert source.count("supports_response=SupportsResponse.OPTIONAL") == 2
    assert "supports_response=SupportsResponse.ONLY" in source
    assert 'vol.Required("guid")' in source
    assert 'vol.Required("title")' in source


def test_watchlist_assist_write_permission_is_separate_and_default_off() -> None:
    const = (COMPONENT / "const.py").read_text()
    flow = (COMPONENT / "config_flow.py").read_text()
    provider = (COMPONENT / "llm.py").read_text()
    assert 'CONF_ALLOW_LLM_WATCHLIST_MUTATIONS: Final = "allow_llm_watchlist_mutations"' in const
    assert "CONF_ALLOW_LLM_WATCHLIST_MUTATIONS, False" in flow
    assert "watchlist_mutation_clients" in provider
    assert "AddToWatchlistPlexTool" in provider
    assert "RemoveFromWatchlistPlexTool" in provider


def test_discover_read_tool_is_not_gated_by_write_permission() -> None:
    provider = (COMPONENT / "llm.py").read_text()
    assert "DiscoverSearchPlexTool(clients)" in provider


def test_developer_tools_docs_and_diagnostics_are_present() -> None:
    services = (COMPONENT / "services.yaml").read_text()
    diagnostics = (COMPONENT / "diagnostics.py").read_text()
    docs = _documentation()
    for name in ("discover_search", "add_to_watchlist", "remove_from_watchlist"):
        assert f"\n{name}:\n" in services
        assert name in diagnostics
    assert "plex_extended.discover_search" in docs
    assert "plex_extended.add_to_watchlist" in docs
    assert "plex_extended__discover_search" in docs


def test_temporary_pr13_helpers_are_removed() -> None:
    assert not (ROOT / ".github/workflows/pr13-wire.yml").exists()
    assert not (ROOT / ".github/scripts/pr13_patch.py").exists()
