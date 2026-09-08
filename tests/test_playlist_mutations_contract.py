"""Contract checks for safe playlist mutation exposure."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def test_manual_playlist_mutations_are_optional_response_actions() -> None:
    adapter = (COMPONENT / "playlist_mutations_service.py").read_text()
    setup = (COMPONENT / "__init__.py").read_text()
    for name in ("SERVICE_CREATE_PLAYLIST", "SERVICE_ADD_TO_PLAYLIST", "SERVICE_REMOVE_FROM_PLAYLIST"):
        assert name in adapter
    assert "supports_response=SupportsResponse.OPTIONAL" in adapter
    assert "async_setup_playlist_mutation_services" in setup


def test_existing_playlist_writes_require_exact_playlist_id() -> None:
    backend = (COMPONENT / "playlist_mutations.py").read_text()
    adapter = (COMPONENT / "playlist_mutations_service.py").read_text()
    tool = (COMPONENT / "playlist_mutations_llm.py").read_text()
    assert 'vol.Required("playlist_rating_key")' in adapter
    assert 'vol.Required("playlist_rating_key")' in tool
    assert "_playlist_by_rating_key" in backend
    assert 'criteria.get("title")' not in backend.split("def _add_to_playlist", 1)[1]
    assert 'criteria.get("title")' not in backend.split("def _remove_from_playlist", 1)[1]


def test_playlist_assist_writes_have_separate_default_off_permission() -> None:
    const = (COMPONENT / "const.py").read_text()
    flow = (COMPONENT / "config_flow.py").read_text()
    provider = (COMPONENT / "llm.py").read_text()
    strings = (COMPONENT / "strings.json").read_text()
    assert 'CONF_ALLOW_LLM_PLAYLIST_MUTATIONS: Final = "allow_llm_playlist_mutations"' in const
    assert "CONF_ALLOW_LLM_PLAYLIST_MUTATIONS, False" in flow
    assert "playlist_mutation_clients" in provider
    assert "CONF_ALLOW_LLM_PLAYLIST_MUTATIONS, False" in provider
    assert '"allow_llm_playlist_mutations": "Allow Assist to change Plex playlists"' in strings


def test_docs_diagnostics_and_metadata_expose_all_three_mutations() -> None:
    yaml = (COMPONENT / "services.yaml").read_text()
    diagnostics = (COMPONENT / "diagnostics.py").read_text()
    readme = (ROOT / "README.md").read_text()
    for name in ("create_playlist", "add_to_playlist", "remove_from_playlist"):
        assert f"\n{name}:\n" in yaml
        assert f'"{name}"' in diagnostics
        assert f"plex_extended.{name}" in readme
        assert f"plex_extended__{name}" in readme
    assert '"assist_playlist_mutations_enabled"' in diagnostics


def test_playlist_mutation_backend_has_no_title_fallback_for_existing_writes() -> None:
    backend = (COMPONENT / "playlist_mutations.py").read_text()
    assert "server.createPlaylist" in backend
    assert "playlist.addItems" in backend
    assert "playlist.removeItems" in backend
    assert "Smart Plex playlists cannot be edited item-by-item" in backend
    assert "Plex radio playlists cannot be edited item-by-item" in backend


def test_temporary_pr15_helpers_are_not_retained() -> None:
    assert not (ROOT / ".github" / "scripts" / "pr15_patch.py").exists()
    assert not (ROOT / ".github" / "workflows" / "pr15-wire.yml").exists()
