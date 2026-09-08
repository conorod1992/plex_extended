"""Real Home Assistant config-flow tests for Plex Extended."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from plexapi.exceptions import Unauthorized

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.plex_extended.const import (
    CONF_ALLOW_LLM_MUTATIONS,
    CONF_ALLOW_LLM_PLAYLIST_MUTATIONS,
    CONF_ALLOW_LLM_WATCHLIST_MUTATIONS,
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_DEFAULT_USER_ID,
    CONF_ENABLE_LLM_TOOLS,
    CONF_MACHINE_IDENTIFIER,
    CONF_SERVER_NAME,
    CONF_SERVER_TOKEN,
    DOMAIN,
)


def _server_data(
    *,
    token: str = "server-token-a",
    machine_identifier: str = "machine-a",
    name: str = "Plex A",
) -> dict[str, str]:
    return {
        CONF_BASE_URL: "http://plex-a.example:32400",
        CONF_SERVER_TOKEN: token,
        CONF_MACHINE_IDENTIFIER: machine_identifier,
        CONF_SERVER_NAME: name,
    }


async def _open_manual_form(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "manual_setup"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual_setup"
    return result


async def test_manual_setup_and_error_recovery(
    hass: HomeAssistant,
    mock_connect,
) -> None:
    """Manual setup should recover from bad credentials and create a config entry."""
    result = await _open_manual_form(hass)

    with patch(
        "custom_components.plex_extended.config_flow._connect_manual",
        side_effect=Unauthorized("bad token"),
    ) as connect_manual:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_BASE_URL: "http://plex-a.example:32400",
                CONF_TOKEN: "bad-token",
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

        connect_manual.side_effect = None
        connect_manual.return_value = _server_data()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_BASE_URL: "http://plex-a.example:32400",
                CONF_TOKEN: "good-token",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Plex A"
    assert result["data"] == _server_data()
    await hass.async_block_till_done()
    mock_connect.assert_awaited_once()


async def test_website_auth_creates_selected_server_entry(
    hass: HomeAssistant,
    current_request_with_host,
    mock_connect,
) -> None:
    """The Plex-hosted external flow should resume and create the discovered server."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU

    auth = MagicMock()
    auth.initiate_auth = AsyncMock()
    auth.auth_url.return_value = "https://app.plex.tv/auth"
    auth.token = AsyncMock(return_value="account-token")
    auth.client_identifier = "ha-client-id"
    resource = SimpleNamespace(
        clientIdentifier="machine-a",
        name="Plex A",
        sourceTitle=None,
    )

    with (
        patch("custom_components.plex_extended.config_flow.PlexAuth", return_value=auth),
        patch(
            "custom_components.plex_extended.config_flow._discover_servers",
            return_value=[resource],
        ),
        patch(
            "custom_components.plex_extended.config_flow._connect_resource",
            return_value=_server_data(),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"next_step_id": "website_auth"}
        )
        assert result["type"] is FlowResultType.EXTERNAL_STEP
        assert result["step_id"] == "obtain_token"

        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["type"] is FlowResultType.EXTERNAL_STEP_DONE
        assert result["next_step_id"] == "discover_servers"

        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SERVER_TOKEN] == "server-token-a"
    assert result["data"][CONF_CLIENT_ID] == "ha-client-id"
    await hass.async_block_till_done()
    mock_connect.assert_awaited_once()


async def test_reauthentication_updates_credentials(
    hass: HomeAssistant,
    current_request_with_host,
    entry_factory,
    mock_connect,
) -> None:
    """A Home Assistant reauth flow should preserve the server identity and replace data."""
    entry = entry_factory(token="old-token")

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    auth = MagicMock()
    auth.initiate_auth = AsyncMock()
    auth.auth_url.return_value = "https://app.plex.tv/auth"
    auth.token = AsyncMock(return_value="new-account-token")
    auth.client_identifier = "new-ha-client-id"
    resource = SimpleNamespace(
        clientIdentifier="machine-a",
        name="Plex A",
        sourceTitle=None,
    )
    new_data = _server_data(token="new-server-token")

    with (
        patch("custom_components.plex_extended.config_flow.PlexAuth", return_value=auth),
        patch(
            "custom_components.plex_extended.config_flow._discover_servers",
            return_value=[resource],
        ),
        patch(
            "custom_components.plex_extended.config_flow._connect_resource",
            return_value=new_data,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        assert result["type"] is FlowResultType.EXTERNAL_STEP

        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["type"] is FlowResultType.EXTERNAL_STEP_DONE

        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_SERVER_TOKEN] == "new-server-token"
    assert entry.data[CONF_CLIENT_ID] == "new-ha-client-id"
    await hass.async_block_till_done()


async def test_options_flow_uses_loaded_runtime_client(
    hass: HomeAssistant,
    entry_factory,
    mock_connect,
) -> None:
    """Options should load through HA and persist user/Assist policy settings."""
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with (
        patch.object(
            entry.runtime_data,
            "async_list_users",
            new=AsyncMock(
                return_value={
                    "users": [
                        {"id": 1, "name": "Owner"},
                        {"id": 7, "name": "Guest"},
                    ]
                }
            ),
        ),
        patch(
            "custom_components.plex_extended.config_flow.async_validate_user_context",
            new_callable=AsyncMock,
        ) as validate_user,
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEFAULT_USER_ID: "7",
                CONF_ENABLE_LLM_TOOLS: True,
                CONF_ALLOW_LLM_MUTATIONS: True,
                CONF_ALLOW_LLM_WATCHLIST_MUTATIONS: False,
                CONF_ALLOW_LLM_PLAYLIST_MUTATIONS: True,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEFAULT_USER_ID] == "7"
    assert result["data"][CONF_ALLOW_LLM_MUTATIONS] is True
    assert result["data"][CONF_ALLOW_LLM_PLAYLIST_MUTATIONS] is True
    validate_user.assert_awaited_once_with(entry.runtime_data, "7")
