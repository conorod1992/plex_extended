"""Contract tests for Plex Extended aggregate library summaries."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def test_library_summary_reuses_structured_query_contract() -> None:
    """Summary filters should evolve with query_library rather than fork from it."""
    service = (COMPONENT / "library_summary_service.py").read_text()
    tool = (COMPONENT / "library_summary_llm.py").read_text()

    assert "QUERY_LIBRARY_SCHEMA" in service
    assert "class LibrarySummaryPlexTool(QueryLibraryPlexTool)" in tool
    assert 'name = "plex_extended__library_summary"' in tool


def test_library_summary_count_path_is_not_limited_to_returned_items() -> None:
    """Exact counts must use PMS totalSize or the full materialized match set."""
    backend = (COMPONENT / "library_summary.py").read_text()

    assert 'data.attrib.get("totalSize")' in backend
    assert '"X-Plex-Container-Size": "1"' in backend
    assert "maxresults=" not in backend
    assert "_DETAIL_BATCH_SIZE = 100" in backend


def test_watched_and_metadata_facets_use_bounded_hydration() -> None:
    """Facets requiring complete Plex rows must not depend on implicit N+1 reloads."""
    backend = (COMPONENT / "library_summary.py").read_text()

    assert '"watched_state"' in backend.split("_HYDRATED_FACETS", 1)[1].split("}", 1)[0]
    watched = backend.split("def _watched_state", 1)[1].split("def _facet_values", 1)[0]
    assert 'getattr(item, "isPlayed")' not in watched
    assert "server.fetchItems(chunk)" in backend


def test_library_summary_is_exposed_in_developer_tools_and_readme() -> None:
    """The public action and native LLM tool should be discoverable/documented."""
    services = (COMPONENT / "services.yaml").read_text()
    readme = (ROOT / "README.md").read_text()
    setup = (COMPONENT / "__init__.py").read_text()

    assert "\nlibrary_summary:\n" in services
    for facet in (
        "genre",
        "year",
        "decade",
        "resolution",
        "watched_state",
        "content_rating",
        "studio",
        "collection",
    ):
        assert f"            - {facet}\n" in services
    assert "async_setup_library_summary_service" in setup
    assert "plex_extended.library_summary" in readme
    assert "plex_extended__library_summary" in readme


def test_library_summary_is_read_only_response_data() -> None:
    """Aggregate analysis must remain a response-only query action."""
    service = (COMPONENT / "library_summary_service.py").read_text()

    assert "supports_response=SupportsResponse.ONLY" in service
    assert "markPlayed" not in service
    assert "markUnplayed" not in service


def test_temporary_pr11_helper_is_not_retained() -> None:
    """The one-shot branch helper must delete itself before review."""
    assert not (ROOT / ".github" / "workflows" / "pr11-polish.yml").exists()
