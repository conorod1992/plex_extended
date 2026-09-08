"""Static contract checks for native Assist exposure configuration."""

from pathlib import Path

ROOT = Path(__file__).parents[1]

def test_options_and_provider_share_native_tool_setting() -> None:
    const = (ROOT / "custom_components/plex_extended/const.py").read_text()
    flow = (ROOT / "custom_components/plex_extended/config_flow.py").read_text()
    provider = (ROOT / "custom_components/plex_extended/llm.py").read_text()
    assert 'CONF_ENABLE_LLM_TOOLS: Final = "enable_llm_tools"' in const
    assert "CONF_ENABLE_LLM_TOOLS" in flow
    assert "enabled_llm_clients(_loaded_clients(hass))" in provider
    assert "type(tool)(clients)" in provider

def test_ui_docs_and_diagnostics_expose_policy() -> None:
    strings = (ROOT / "custom_components/plex_extended/strings.json").read_text()
    translation = (ROOT / "custom_components/plex_extended/translations/en.json").read_text()
    diagnostics = (ROOT / "custom_components/plex_extended/diagnostics.py").read_text()
    readme = (ROOT / "README.md").read_text()
    for text in (strings, translation):
        assert '"enable_llm_tools": "Enable native Assist tools"' in text
    assert '"native_assist_tools_enabled"' in diagnostics
    assert "### Native Assist tool exposure" in readme

def test_temporary_workflow_is_removed() -> None:
    assert not (ROOT / ".github/workflows/configuration-polish.yml").exists()
