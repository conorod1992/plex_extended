"""Contract checks for related-media exposure and documentation."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def test_related_media_action_is_registered_response_only() -> None:
    const = (COMPONENT / "const.py").read_text()
    adapter = (COMPONENT / "related_media_service.py").read_text()
    setup = (COMPONENT / "__init__.py").read_text()

    assert 'SERVICE_RELATED_MEDIA: Final = "related_media"' in const
    assert "async_setup_related_media_service" in setup
    assert "SERVICE_RELATED_MEDIA" in adapter
    assert "supports_response=SupportsResponse.ONLY" in adapter


def test_related_media_requires_exact_rating_key_and_shared_context() -> None:
    adapter = (COMPONENT / "related_media_service.py").read_text()
    tool = (COMPONENT / "related_media_llm.py").read_text()

    assert 'vol.Required("rating_key")' in adapter
    assert 'vol.Required("rating_key")' in tool
    assert '"library"' in adapter and '"library_id"' in adapter
    assert '"user"' in adapter and '"user_id"' in adapter
    assert "self._library_fields()" in tool
    assert "self._user_fields()" in tool


def test_native_assist_exposes_read_only_related_media_tool() -> None:
    provider = (COMPONENT / "llm.py").read_text()
    tool = (COMPONENT / "related_media_llm.py").read_text()

    assert 'name = "plex_extended__related_media"' in tool
    assert "RelatedMediaPlexTool(clients)" in provider
    assert "_RELATED_MEDIA_PROMPT" in provider
    assert "do not invent a ranking across different hubs" in provider
    assert "CONF_ALLOW_LLM" not in tool


def test_docs_metadata_and_diagnostics_advertise_related_media() -> None:
    yaml = (COMPONENT / "services.yaml").read_text()
    diagnostics = (COMPONENT / "diagnostics.py").read_text()
    readme = (ROOT / "README.md").read_text()

    assert "\nrelated_media:\n" in yaml
    assert '"related_media"' in diagnostics
    assert "plex_extended.related_media" in readme
    assert "plex_extended__related_media" in readme
    assert "more_available_from_plex" in readme
    assert "Provider/online objects" in readme


def test_related_backend_stays_local_and_plex_native() -> None:
    backend = (COMPONENT / "related_media.py").read_text()

    assert "source.hubs()" in backend
    assert 'librarySectionID' in backend
    assert "ratingKey" in backend
    assert "score" not in backend.casefold()
    assert "similarity" not in backend.casefold()


def test_temporary_related_media_helpers_are_not_retained() -> None:
    assert not (ROOT / ".github" / "workflows" / "related-media-docs.yml").exists()
    assert not (ROOT / ".github" / "scripts" / "related_media_docs.py").exists()
