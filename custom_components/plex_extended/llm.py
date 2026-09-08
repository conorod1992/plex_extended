"""Native Home Assistant LLM tool provider for Plex Extended."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.llm import LLMContext

from .active_streams_llm import ActiveStreamsPlexTool
from .client import PlexExtendedClient
from .const import (
    CONF_ALLOW_LLM_MUTATIONS,
    CONF_ALLOW_LLM_PLAYLIST_MUTATIONS,
    CONF_ALLOW_LLM_WATCHLIST_MUTATIONS,
)
from .discover_watchlist_llm import (
    AddToWatchlistPlexTool,
    DiscoverSearchPlexTool,
    RemoveFromWatchlistPlexTool,
)
from .library_summary_llm import LibrarySummaryPlexTool
from .llm_policy import enabled_llm_clients
from .playlist_mutations_llm import (
    AddToPlaylistPlexTool,
    CreatePlaylistPlexTool,
    RemoveFromPlaylistPlexTool,
)
from .llm_tools import (
    MarkUnwatchedPlexTool,
    MarkWatchedPlexTool,
    _loaded_clients,
    async_get_tools as _async_get_tools,
)
from .related_media_llm import RelatedMediaPlexTool
from .tv_catch_up_llm import TvCatchUpPlexTool

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
_TV_CATCH_UP_PROMPT = (
    " Use tv_catch_up for cross-show questions about unwatched or in-progress TV episodes, "
    "new episodes the user has not finished, or what they have to catch up on. Use its "
    "within_days/since/before fields when the user specifies a recent time period. Use "
    "watch_status instead when the question is about progress or the next episode in one "
    "specific show."
)
_RELATED_MEDIA_PROMPT = (
    " Use related_media when the user asks for local Plex movies or shows related/similar "
    "to a particular local title. Resolve the seed title to an exact local rating_key with "
    "search or query_library first. Preserve Plex's returned hub categories as explanation "
    "of why items are related; do not invent a ranking across different hubs."
)
_DISCOVER_PROMPT = (
    " Use discover_search for movies/shows in Plex Discover, especially titles that may "
    "not exist on the local server. Discover and Watchlist are scoped to the configured "
    "plex.tv account rather than the household default Plex user."
)
_WATCHLIST_MUTATION_PROMPT = (
    " add_to_watchlist and remove_from_watchlist change the configured plex.tv account: "
    "use them only for an explicit user request and only with the exact guid and title "
    "returned by discover_search or other Plex Extended Watchlist data. Never invent or "
    "modify a Discover guid."
)
_PLAYLIST_MUTATION_PROMPT = (
    " create_playlist, add_to_playlist, and remove_from_playlist change regular Plex "
    "playlists for the selected/default Plex user. Use them only for an explicit user "
    "request. Resolve exact local media rating_key values with read tools, and resolve "
    "an existing playlist_rating_key with list_playlists before add/remove. Never invent "
    "identifiers. Smart and radio playlists are read-only for these tools."
)
_LIBRARY_SUMMARY_PROMPT = (
    " Use library_summary instead of query_library when the user wants an exact count, "
    "a grouped breakdown/facet, or total runtime rather than a list of matching media. "
    "Request only the facets needed for the answer to keep responses compact."
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

    clients = enabled_llm_clients(_loaded_clients(hass))
    if not clients:
        return None

    mutation_clients = {
        label: client
        for label, client in clients.items()
        if bool(client.entry.options.get(CONF_ALLOW_LLM_MUTATIONS, False))
    }
    watchlist_mutation_clients = {
        label: client
        for label, client in clients.items()
        if bool(
            client.entry.options.get(CONF_ALLOW_LLM_WATCHLIST_MUTATIONS, False)
        )
    }
    playlist_mutation_clients = {
        label: client
        for label, client in clients.items()
        if bool(
            client.entry.options.get(CONF_ALLOW_LLM_PLAYLIST_MUTATIONS, False)
        )
    }

    tools = [
        type(tool)(clients)
        for tool in result.tools
        if tool.name not in _MUTATION_TOOL_NAMES
    ]
    tools.extend(
        [
            ActiveStreamsPlexTool(clients),
            LibrarySummaryPlexTool(clients),
            TvCatchUpPlexTool(clients),
            RelatedMediaPlexTool(clients),
            DiscoverSearchPlexTool(clients),
        ]
    )
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

    if watchlist_mutation_clients:
        force_server_selector = len(clients) > 1
        tools.extend(
            [
                AddToWatchlistPlexTool(
                    watchlist_mutation_clients,
                    force_server_selector=force_server_selector,
                ),
                RemoveFromWatchlistPlexTool(
                    watchlist_mutation_clients,
                    force_server_selector=force_server_selector,
                ),
            ]
        )

    if playlist_mutation_clients:
        force_server_selector = len(clients) > 1
        tools.extend(
            [
                CreatePlaylistPlexTool(
                    playlist_mutation_clients,
                    force_server_selector=force_server_selector,
                ),
                AddToPlaylistPlexTool(
                    playlist_mutation_clients,
                    force_server_selector=force_server_selector,
                ),
                RemoveFromPlaylistPlexTool(
                    playlist_mutation_clients,
                    force_server_selector=force_server_selector,
                ),
            ]
        )

    prompt = result.prompt
    if not mutation_clients and prompt:
        prompt = prompt.replace(_MUTATION_PROMPT, "")
    prompt = (
        f"{prompt or ''}{_ACTIVE_STREAMS_PROMPT}{_TV_CATCH_UP_PROMPT}"
        f"{_RELATED_MEDIA_PROMPT}{_LIBRARY_SUMMARY_PROMPT}{_DISCOVER_PROMPT}"
        f"{_WATCHLIST_MUTATION_PROMPT if watchlist_mutation_clients else ''}"
        f"{_PLAYLIST_MUTATION_PROMPT if playlist_mutation_clients else ''}"
    )

    return LLMTools(tools=tools, prompt=prompt)
