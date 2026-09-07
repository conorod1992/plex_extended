"""Native Home Assistant LLM tool provider for Plex Extended."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.llm import LLMContext

from .active_streams_llm import ActiveStreamsPlexTool
from .client import PlexExtendedClient
from .const import CONF_ALLOW_LLM_MUTATIONS
from .llm_tools import (
    MarkUnwatchedPlexTool,
    MarkWatchedPlexTool,
    _loaded_clients,
    async_get_tools as _async_get_tools,
)

_MUTATION_TOOL_NAMES = {
    "plex_extended__mark_watched",
    "plex_extended__mark_unwatched",
}
_MUTATION_PROMPT = (
    " mark_watched and mark_unwatched change Plex data: use them only when the user "
    "explicitly asks to change watch state, first resolve an exact local rating_key with "
    "a read tool, and never invent a rating_key. A show/season mutation also affects its "
    "child episodes."
)
_ACTIVE_STREAMS_PROMPT = (
    " Use active_streams for questions about what is playing on Plex right now, who is "
    "currently using Plex, player/playback state, progress, local versus remote playback, "
    "or whether a current session is direct play, direct stream, or transcoding."
)


class _RestrictedMarkWatchedPlexTool(MarkWatchedPlexTool):
    """Mark-watched tool restricted to entries that explicitly allow LLM writes."""

    def __init__(
        self,
        clients: dict[str, PlexExtendedClient],
        *,
        force_server_selector: bool,
    ) -> None:
        self._force_server_selector = force_server_selector
        super().__init__(clients)

    @override
    def _server_fields(self) -> dict[Any, Any]:
        if self._force_server_selector:
            return {vol.Required("server"): vol.In(list(self._clients))}
        return super()._server_fields()


class _RestrictedMarkUnwatchedPlexTool(MarkUnwatchedPlexTool):
    """Mark-unwatched tool restricted to entries that explicitly allow LLM writes."""

    def __init__(
        self,
        clients: dict[str, PlexExtendedClient],
        *,
        force_server_selector: bool,
    ) -> None:
        self._force_server_selector = force_server_selector
        super().__init__(clients)

    @override
    def _server_fields(self) -> dict[Any, Any]:
        if self._force_server_selector:
            return {vol.Required("server"): vol.In(list(self._clients))}
        return super()._server_fields()


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Return Plex tools, exposing write tools only for explicitly enabled entries."""
    result = _async_get_tools(hass, llm_context, api_id)
    if result is None:
        return None

    clients = _loaded_clients(hass)
    mutation_clients = {
        label: client
        for label, client in clients.items()
        if bool(client.entry.options.get(CONF_ALLOW_LLM_MUTATIONS, False))
    }

    tools = [tool for tool in result.tools if tool.name not in _MUTATION_TOOL_NAMES]
    tools.append(ActiveStreamsPlexTool(clients))
    if mutation_clients:
        force_server_selector = len(clients) > 1
        tools.extend(
            [
                _RestrictedMarkWatchedPlexTool(
                    mutation_clients,
                    force_server_selector=force_server_selector,
                ),
                _RestrictedMarkUnwatchedPlexTool(
                    mutation_clients,
                    force_server_selector=force_server_selector,
                ),
            ]
        )

    prompt = result.prompt
    if not mutation_clients and prompt:
        prompt = prompt.replace(_MUTATION_PROMPT, "")
    prompt = f"{prompt or ''}{_ACTIVE_STREAMS_PROMPT}"

    return LLMTools(tools=tools, prompt=prompt)
