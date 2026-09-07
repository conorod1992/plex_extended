"""Contract tests for Plex Extended watched-state exposure."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def test_mutation_actions_use_optional_responses() -> None:
    """Side-effecting HA actions must not masquerade as read-only response actions."""
    source = (COMPONENT / "services.py").read_text()

    assert "SERVICE_MARK_WATCHED" in source
    assert "SERVICE_MARK_UNWATCHED" in source
    assert "supports_response=SupportsResponse.OPTIONAL" in source
    assert "result if call.return_response else None" in source


def test_assist_mutations_are_opt_in_and_default_off() -> None:
    """Assist must not receive write tools unless an entry explicitly enables them."""
    provider = (COMPONENT / "llm.py").read_text()
    flow = (COMPONENT / "config_flow.py").read_text()

    assert "client.entry.options.get(CONF_ALLOW_LLM_MUTATIONS, False)" in provider
    assert "tool.name not in _MUTATION_TOOL_NAMES" in provider
    assert "if mutation_clients:" in provider
    assert "self.config_entry.options.get(CONF_ALLOW_LLM_MUTATIONS, False)" in flow


def test_mutation_tool_descriptions_require_explicit_exact_ids() -> None:
    """LLM write tools must clearly require an explicit request and local rating key."""
    source = (COMPONENT / "llm_tools.py").read_text()

    assert source.count("SIDE EFFECT:") >= 2
    assert source.count("Use only when the user explicitly asks to change watch state") >= 2
    assert source.count("never infer a rating_key from a title") >= 2


def test_services_yaml_exposes_both_mutation_actions_with_valid_selectors() -> None:
    """Developer Tools metadata should expose both actions without flattened YAML."""
    source = (COMPONENT / "services.yaml").read_text()

    assert "\nmark_watched:\n" in source
    assert "\nmark_unwatched:\n" in source
    assert source.count("Stable local Plex rating key returned by another Plex Extended action.") == 2
    assert "config_entry:\nintegration: plex_extended" not in source
    assert source.count("        config_entry:\n          integration: plex_extended") >= 2


def test_no_temporary_patch_workflows_remain() -> None:
    """One-off branch patch helpers must not become part of the PR."""
    workflows = ROOT / ".github" / "workflows"

    assert not (workflows / "pr9-doc-patch.yml").exists()
    assert not (workflows / "pr9-yaml-fix.yml").exists()
