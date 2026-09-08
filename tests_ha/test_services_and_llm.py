"""Real Home Assistant service and native-LLM contract tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.llm import async_get_tools
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.llm import LLM_API_ASSIST, LLMContext
from homeassistant.setup import async_setup_component

from custom_components.plex_extended.const import (
    CONF_CONFIG_ENTRY_ID,
    DOMAIN,
    SERVICE_MARK_WATCHED,
    SERVICE_SEARCH,
)


async def _setup_entry(hass: HomeAssistant, entry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_services_require_server_selection_with_multiple_entries(
    hass: HomeAssistant,
    entry_factory,
    mock_connect,
) -> None:
    """HA service dispatch should be unambiguous and respect config_entry_id."""
    first = entry_factory(title="Plex A", machine_identifier="machine-a")
    second = entry_factory(title="Plex B", machine_identifier="machine-b")
    await _setup_entry(hass, first)
    await _setup_entry(hass, second)

    with patch(
        "custom_components.plex_extended.services.async_search_for_context",
        new=AsyncMock(
            side_effect=lambda client, criteria: {
                "success": True,
                "server": client.server_name,
                "query": criteria["query"],
            }
        ),
    ):
        with pytest.raises(HomeAssistantError, match="Multiple Plex Extended servers"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SEARCH,
                {"query": "Alien"},
                blocking=True,
                return_response=True,
            )

        result = await hass.services.async_call(
            DOMAIN,
            SERVICE_SEARCH,
            {
                CONF_CONFIG_ENTRY_ID: second.entry_id,
                "query": "Alien",
            },
            blocking=True,
            return_response=True,
        )

    assert result["server"] == "Plex B"
    assert result["query"] == "Alien"


async def test_optional_mutation_response_contract(
    hass: HomeAssistant,
    entry_factory,
    mock_connect,
) -> None:
    """Mutation actions should work both fire-and-forget and with response data."""
    entry = entry_factory()
    await _setup_entry(hass, entry)

    backend = AsyncMock(
        return_value={
            "success": True,
            "rating_key": "10",
            "watched": True,
        }
    )
    with patch(
        "custom_components.plex_extended.services.async_mark_watched",
        new=backend,
    ):
        no_response = await hass.services.async_call(
            DOMAIN,
            SERVICE_MARK_WATCHED,
            {"rating_key": "10"},
            blocking=True,
        )
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_MARK_WATCHED,
            {"rating_key": "10"},
            blocking=True,
            return_response=True,
        )

    assert no_response is None
    assert response == {"success": True, "rating_key": "10", "watched": True}
    assert backend.await_count == 2


async def test_native_llm_platform_is_discovered_by_home_assistant(
    hass: HomeAssistant,
    entry_factory,
    mock_connect,
) -> None:
    """HA's real LazyIntegrationPlatforms path should discover Plex Extended tools."""
    assert await async_setup_component(hass, "llm", {})

    entry = entry_factory()
    await _setup_entry(hass, entry)

    result = await async_get_tools(
        hass,
        LLMContext(
            platform="test",
            context=None,
            language="en",
            assistant="conversation",
            device_id=None,
        ),
        LLM_API_ASSIST,
    )

    names = {tool.name for tool in result.tools}
    assert "plex_extended__search" in names
    assert "plex_extended__library_summary" in names
    assert "plex_extended__related_media" in names
    assert "plex_extended__mark_watched" not in names
