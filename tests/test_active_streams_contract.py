"""Contract tests for Plex Extended active-stream exposure."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def _documentation() -> str:
    """Return the public documentation corpus."""
    return "\n".join(
        path.read_text()
        for path in (
            ROOT / "README.md",
            ROOT / "docs" / "action-reference.md",
            ROOT / "docs" / "assist-reference.md",
        )
    )


def test_active_streams_action_is_read_only_response_data() -> None:
    """The action must stay a response-only query rather than playback control."""
    adapter = (COMPONENT / "active_streams_service.py").read_text()
    setup = (COMPONENT / "__init__.py").read_text()

    assert "SERVICE_ACTIVE_STREAMS" in adapter
    assert "supports_response=SupportsResponse.ONLY" in adapter
    assert "async_setup_active_streams_service" in setup
    assert ".stop(" not in adapter


def test_active_streams_llm_tool_is_always_read_only() -> None:
    """Active streams should be a normal read tool, independent of mutation opt-in."""
    provider = (COMPONENT / "llm.py").read_text()
    tool = (COMPONENT / "active_streams_llm.py").read_text()

    assert "ActiveStreamsPlexTool(clients)" in provider
    assert "plex_extended__active_streams" in tool
    assert "what is playing" in tool
    assert "CONF_ALLOW_LLM_MUTATIONS" not in tool


def test_active_stream_serializer_does_not_expose_network_or_device_ids() -> None:
    """Session output should exclude addresses and stable device/session identifiers."""
    source = (COMPONENT / "active_streams.py").read_text()

    forbidden_output_keys = (
        '"address":',
        '"remote_public_address":',
        '"machine_identifier":',
        '"session_id":',
        '"file":',
        '"token":',
    )
    for key in forbidden_output_keys:
        assert key not in source


def test_active_streams_does_not_add_playback_control() -> None:
    """PR10 should query /status/sessions only, not terminate/control sessions."""
    backend = (COMPONENT / "active_streams.py").read_text()
    tool = (COMPONENT / "active_streams_llm.py").read_text()

    assert "server.sessions()" in backend
    assert ".stop(" not in backend
    assert "terminate" not in backend.casefold()
    assert ".stop(" not in tool


def test_active_streams_public_metadata_and_docs_are_present() -> None:
    """Developer Tools and public docs should expose and explain the query."""
    services = (COMPONENT / "services.yaml").read_text()
    docs = _documentation()

    assert "\nactive_streams:\n" in services
    assert "name: Active streams" in services
    assert "plex_extended.active_streams" in docs
    assert "plex_extended__active_streams" in docs
    assert "direct_play" in docs
    assert "direct_stream" in docs
    assert "transcode" in docs


def test_temporary_doc_helper_is_not_retained() -> None:
    """PR-only helper workflow must not remain in the final branch diff."""
    assert not (ROOT / ".github" / "workflows" / "pr10-doc-patch.yml").exists()
