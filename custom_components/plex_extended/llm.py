"""Native Home Assistant LLM tools for Plex Extended."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant.components.llm import LLMTools
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLM_API_ASSIST, LLMContext, Tool, ToolInput
from homeassistant.util.json import JsonObjectType

from .client import PlexExtendedAuthenticationError, PlexExtendedClient, PlexExtendedError
from .const import (
    COLLECTION_MEDIA_TYPES,
    DEFAULT_LLM_INCLUDE_SUMMARY,
    DEFAULT_SEARCH_TYPES,
    DOMAIN,
    PLAYLIST_TYPES,
    QUERY_HDR_STATES,
    QUERY_MEDIA_TYPES,
    QUERY_SORT_FIELDS,
    QUERY_SORT_ORDERS,
    QUERY_WATCH_STATES,
    RECENT_TV_GROUPINGS,
    SEARCH_TYPES,
    WATCHLIST_FILTERS,
    WATCHLIST_MEDIA_TYPES,
    WATCHLIST_SORT_FIELDS,
)
from .library_lists import (
    async_collection_items,
    async_list_collections,
    async_list_playlists,
    async_playlist_items,
    async_watchlist,
)
from .library_query import async_query_library
from .recent_media import async_recently_added, async_recently_watched
from .user_context import (
    async_continue_watching_for_context,
    async_media_details_for_context,
    async_on_deck_for_context,
    async_search_for_context,
)
from .viewing_progress import async_watch_status

LLM_LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=25))
LLM_TYPES = vol.All(cv.ensure_list, [vol.In(SEARCH_TYPES)])
LLM_TEXT_LIST = vol.All(
    cv.ensure_list,
    [vol.All(cv.string, vol.Length(min=1))],
)
LLM_YEAR = vol.All(vol.Coerce(int), vol.Range(min=0, max=9999))
LLM_RATING = vol.All(vol.Coerce(float), vol.Range(min=0, max=10))
LLM_DURATION = vol.All(vol.Coerce(float), vol.Range(min=0))
LLM_WINDOW_DAYS = vol.All(vol.Coerce(int), vol.Range(min=1, max=3650))


class PlexTool(Tool):
    """Base class for Plex Extended LLM tools."""

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        """Initialize a Plex tool."""
        self._clients = clients

    def _server_fields(self) -> dict[Any, Any]:
        """Return a server selector only when multiple servers are loaded."""
        if len(self._clients) <= 1:
            return {}
        return {vol.Required("server"): vol.In(list(self._clients))}

    @staticmethod
    def _library_fields() -> dict[Any, Any]:
        """Return stable and human-friendly library selectors."""
        return {
            vol.Optional("library"): cv.string,
            vol.Optional("library_id"): cv.string,
        }

    @staticmethod
    def _user_fields() -> dict[Any, Any]:
        """Return optional Plex user selectors for viewing-state queries."""
        return {
            vol.Optional("user"): cv.string,
            vol.Optional("user_id"): cv.string,
        }

    @staticmethod
    def _window_fields() -> dict[Any, Any]:
        """Return recent-media time-window selectors."""
        return {
            vol.Optional("since"): cv.string,
            vol.Optional("before"): cv.string,
            vol.Optional("within_days"): LLM_WINDOW_DAYS,
        }

    def _client(self, data: dict[str, Any]) -> PlexExtendedClient:
        """Resolve the client selected by the LLM."""
        if len(self._clients) == 1:
            return next(iter(self._clients.values()))
        server = data.get("server")
        if not server or server not in self._clients:
            raise HomeAssistantError("A Plex server must be selected")
        return self._clients[server]

    @staticmethod
    def _criteria(data: dict[str, Any]) -> dict[str, Any]:
        """Return tool arguments without the Home Assistant server selector."""
        criteria = dict(data)
        criteria.pop("server", None)
        return criteria

    async def _call(self, awaitable: Any) -> JsonObjectType:
        """Translate client errors to Home Assistant tool errors."""
        try:
            return await awaitable
        except PlexExtendedAuthenticationError as err:
            raise HomeAssistantError(
                "Plex authorization failed; Home Assistant has requested reauthentication"
            ) from err
        except PlexExtendedError as err:
            raise HomeAssistantError(str(err)) from err


class SearchPlexTool(PlexTool):
    """Search Plex libraries."""

    name = "plex_extended__search"
    description = (
        "Search Plex libraries for media titles. Viewing-state fields in results use the "
        "configured default Plex user unless user or user_id explicitly overrides it. "
        "Results are compact by default; use media_details for full details."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._library_fields(),
                **self._user_fields(),
                vol.Required("query"): vol.All(cv.string, vol.Length(min=1)),
                vol.Optional("search_types", default=DEFAULT_SEARCH_TYPES): LLM_TYPES,
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        criteria = self._criteria(data)
        criteria["include_technical"] = False
        return await self._call(
            async_search_for_context(self._client(data), criteria)
        )


class QueryLibraryPlexTool(PlexTool):
    """Run a filtered Plex library query."""

    name = "plex_extended__query_library"
    description = (
        "Find Plex media by structured criteria rather than title similarity. Use this "
        "for genre, people, year, collections, watched state, runtime, resolution/HDR, "
        "ratings, dates, or sorting. Viewing-state filters use the configured default "
        "Plex user unless user or user_id explicitly overrides it."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._library_fields(),
                **self._user_fields(),
                vol.Required("media_type"): vol.In(QUERY_MEDIA_TYPES),
                vol.Optional("title"): vol.All(cv.string, vol.Length(min=1)),
                vol.Optional("genres"): LLM_TEXT_LIST,
                vol.Optional("genres_all"): LLM_TEXT_LIST,
                vol.Optional("actors"): LLM_TEXT_LIST,
                vol.Optional("directors"): LLM_TEXT_LIST,
                vol.Optional("collections"): LLM_TEXT_LIST,
                vol.Optional("content_ratings"): LLM_TEXT_LIST,
                vol.Optional("studios"): LLM_TEXT_LIST,
                vol.Optional("year"): LLM_YEAR,
                vol.Optional("year_min"): LLM_YEAR,
                vol.Optional("year_max"): LLM_YEAR,
                vol.Optional("decade"): LLM_YEAR,
                vol.Optional("watched_state", default="any"): vol.In(
                    QUERY_WATCH_STATES
                ),
                vol.Optional("resolutions"): LLM_TEXT_LIST,
                vol.Optional("hdr", default="any"): vol.In(QUERY_HDR_STATES),
                vol.Optional("critic_rating_min"): LLM_RATING,
                vol.Optional("critic_rating_max"): LLM_RATING,
                vol.Optional("audience_rating_min"): LLM_RATING,
                vol.Optional("audience_rating_max"): LLM_RATING,
                vol.Optional("user_rating_min"): LLM_RATING,
                vol.Optional("user_rating_max"): LLM_RATING,
                vol.Optional("duration_min_minutes"): LLM_DURATION,
                vol.Optional("duration_max_minutes"): LLM_DURATION,
                vol.Optional("added_after"): cv.string,
                vol.Optional("added_before"): cv.string,
                vol.Optional("last_viewed_after"): cv.string,
                vol.Optional("last_viewed_before"): cv.string,
                vol.Optional("sort_by"): vol.In(QUERY_SORT_FIELDS),
                vol.Optional("sort_order"): vol.In(QUERY_SORT_ORDERS),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        client = self._client(data)
        criteria = self._criteria(data)
        criteria["include_technical"] = False
        return await self._call(async_query_library(client, criteria))


class WatchStatusPlexTool(PlexTool):
    """Return episode-level viewing progress for one TV show."""

    name = "plex_extended__watch_status"
    description = (
        "Get TV-show viewing progress: completion, watched/unwatched episode counts, "
        "the last watched/current episode, and the next episode to watch. The configured "
        "default Plex user is used unless user or user_id explicitly overrides it. Use a "
        "known show rating_key when available; title and optional year can also resolve it."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._library_fields(),
                **self._user_fields(),
                vol.Optional("rating_key"): vol.All(cv.string, vol.Length(min=1)),
                vol.Optional("title"): vol.All(cv.string, vol.Length(min=1)),
                vol.Optional("year"): LLM_YEAR,
                vol.Optional("include_specials", default=False): cv.boolean,
                vol.Optional("include_seasons", default=False): cv.boolean,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_watch_status(self._client(data), self._criteria(data))
        )


class RecentlyAddedPlexTool(PlexTool):
    """Return recently added Plex media."""

    name = "plex_extended__recently_added"
    description = (
        "Return recently added Plex items, optionally bounded by since/before or "
        "within_days. TV episode additions can be grouped by show or season to avoid "
        "large episode-by-episode responses. Viewing-state fields use the configured "
        "default Plex user unless user or user_id explicitly overrides it."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._library_fields(),
                **self._user_fields(),
                **self._window_fields(),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional("media_types"): LLM_TYPES,
                vol.Optional("group_tv_by", default="none"): vol.In(
                    RECENT_TV_GROUPINGS
                ),
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_recently_added(self._client(data), self._criteria(data))
        )


class RecentlyWatchedPlexTool(PlexTool):
    """Return Plex watch history."""

    name = "plex_extended__recently_watched"
    description = (
        "Return Plex watch history, optionally filtered by library, media type, and an "
        "exact since/before or within_days time window. The configured default Plex user "
        "is used when present; user or user_id can explicitly override it."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._library_fields(),
                **self._user_fields(),
                **self._window_fields(),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional("media_types"): LLM_TYPES,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_recently_watched(self._client(data), self._criteria(data))
        )


class ContinueWatchingPlexTool(PlexTool):
    """Return Continue Watching items."""

    name = "plex_extended__continue_watching"
    description = (
        "Return personalized Plex Continue Watching items. The configured default Plex "
        "user is used unless user or user_id explicitly overrides it."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._library_fields(),
                **self._user_fields(),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_continue_watching_for_context(
                self._client(data), self._criteria(data)
            )
        )


class OnDeckPlexTool(PlexTool):
    """Return Plex On Deck items."""

    name = "plex_extended__on_deck"
    description = (
        "Return personalized Plex On Deck items. The configured default Plex user is "
        "used unless user or user_id explicitly overrides it."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._library_fields(),
                **self._user_fields(),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_on_deck_for_context(self._client(data), self._criteria(data))
        )


class MediaDetailsPlexTool(PlexTool):
    """Return metadata for a known Plex item."""

    name = "plex_extended__media_details"
    description = (
        "Get detailed metadata for a Plex item using a rating_key returned by another "
        "Plex tool. Viewing-state/progress fields use the configured default Plex user "
        "unless user or user_id explicitly overrides it."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._user_fields(),
                vol.Required("rating_key"): cv.string,
                vol.Optional("include_technical", default=False): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_media_details_for_context(
                self._client(data), self._criteria(data)
            )
        )


class ListCollectionsPlexTool(PlexTool):
    """List Plex collections."""

    name = "plex_extended__list_collections"
    description = (
        "List Plex collections visible to the configured/default Plex user. Use this to "
        "discover a collection rating_key before calling collection_items."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._library_fields(),
                **self._user_fields(),
                vol.Optional("media_type"): vol.In(COLLECTION_MEDIA_TYPES),
                vol.Optional("title"): cv.string,
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_list_collections(self._client(data), self._criteria(data))
        )


class CollectionItemsPlexTool(PlexTool):
    """Return items from one Plex collection."""

    name = "plex_extended__collection_items"
    description = (
        "Return items in a Plex collection. Prefer a collection rating_key from "
        "list_collections; an exact collection title can also be used when unambiguous."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._library_fields(),
                **self._user_fields(),
                vol.Optional("rating_key"): cv.string,
                vol.Optional("title"): cv.string,
                vol.Optional("media_types"): LLM_TYPES,
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_collection_items(self._client(data), self._criteria(data))
        )


class ListPlaylistsPlexTool(PlexTool):
    """List Plex playlists."""

    name = "plex_extended__list_playlists"
    description = (
        "List Plex video/audio/photo playlists visible to the configured/default Plex "
        "user. Use the returned rating_key for playlist_items when possible."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._user_fields(),
                vol.Optional("playlist_type"): vol.In(PLAYLIST_TYPES),
                vol.Optional("title"): cv.string,
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_list_playlists(self._client(data), self._criteria(data))
        )


class PlaylistItemsPlexTool(PlexTool):
    """Return items from one Plex playlist."""

    name = "plex_extended__playlist_items"
    description = (
        "Return items in one Plex playlist. Prefer a playlist rating_key from "
        "list_playlists; an exact title is accepted when unambiguous."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                **self._user_fields(),
                vol.Optional("rating_key"): cv.string,
                vol.Optional("title"): cv.string,
                vol.Optional("media_types"): LLM_TYPES,
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(
            async_playlist_items(self._client(data), self._criteria(data))
        )


class WatchlistPlexTool(PlexTool):
    """Return the configured Plex account's plex.tv Watchlist."""

    name = "plex_extended__watchlist"
    description = (
        "Return the configured Plex account's plex.tv Watchlist and optionally match each "
        "movie/show to local server media by Plex GUID. This account-level Watchlist is "
        "not changed by the integration's default household Plex user setting."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema(
            {
                **self._server_fields(),
                vol.Optional("filter", default="all"): vol.In(WATCHLIST_FILTERS),
                vol.Optional("media_type"): vol.In(WATCHLIST_MEDIA_TYPES),
                vol.Optional("sort_by", default="watchlisted_at"): vol.In(
                    WATCHLIST_SORT_FIELDS
                ),
                vol.Optional("sort_order", default="desc"): vol.In(
                    QUERY_SORT_ORDERS
                ),
                vol.Optional("limit", default=10): LLM_LIMIT,
                vol.Optional("match_local", default=True): cv.boolean,
                vol.Optional(
                    "include_summary", default=DEFAULT_LLM_INCLUDE_SUMMARY
                ): cv.boolean,
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(async_watchlist(self._client(data), self._criteria(data)))


class ListLibrariesPlexTool(PlexTool):
    """List Plex libraries."""

    name = "plex_extended__list_libraries"
    description = (
        "List available Plex libraries including stable library IDs and media types."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema({**self._server_fields()})

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(self._client(data).async_list_libraries())


class ListUsersPlexTool(PlexTool):
    """List Plex users."""

    name = "plex_extended__list_users"
    description = (
        "List Plex users including stable user IDs for exact viewing-state queries."
    )

    def __init__(self, clients: dict[str, PlexExtendedClient]) -> None:
        super().__init__(clients)
        self.parameters = vol.Schema({**self._server_fields()})

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        data = self.parameters(tool_input.tool_args)
        return await self._call(self._client(data).async_list_users())


def _loaded_clients(hass: HomeAssistant) -> dict[str, PlexExtendedClient]:
    """Return loaded Plex clients with unambiguous display names."""
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and isinstance(entry.runtime_data, PlexExtendedClient)
    ]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.title] = counts.get(entry.title, 0) + 1

    result: dict[str, PlexExtendedClient] = {}
    for entry in entries:
        label = (
            entry.title
            if counts[entry.title] == 1
            else f"{entry.title} ({entry.entry_id[:8]})"
        )
        result[label] = entry.runtime_data
    return result


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Contribute Plex tools to Home Assistant's built-in Assist LLM API."""
    if api_id != LLM_API_ASSIST:
        return None

    clients = _loaded_clients(hass)
    if not clients:
        return None

    return LLMTools(
        tools=[
            SearchPlexTool(clients),
            QueryLibraryPlexTool(clients),
            WatchStatusPlexTool(clients),
            RecentlyAddedPlexTool(clients),
            RecentlyWatchedPlexTool(clients),
            ContinueWatchingPlexTool(clients),
            OnDeckPlexTool(clients),
            MediaDetailsPlexTool(clients),
            ListCollectionsPlexTool(clients),
            CollectionItemsPlexTool(clients),
            ListPlaylistsPlexTool(clients),
            PlaylistItemsPlexTool(clients),
            WatchlistPlexTool(clients),
            ListLibrariesPlexTool(clients),
            ListUsersPlexTool(clients),
        ],
        prompt=(
            "Use Plex Extended tools for questions about the user's Plex library, watch "
            "history, recently added media, Continue Watching, On Deck, TV viewing "
            "progress, collections, playlists, or Plex Watchlist. Media/viewing-state "
            "tools use the Plex user configured as the integration default; do not supply "
            "user/user_id unless the request clearly asks about a different Plex user. "
            "The plex.tv Watchlist is account-level and belongs to the configured Plex "
            "account, so the default household user does not apply to watchlist. Use "
            "search for title/name lookup and query_library for structured media discovery "
            "or recommendations involving genres, people, years, watched state, runtime, "
            "quality, ratings, dates, or sorting. Use list_collections/list_playlists to "
            "resolve stable rating keys before collection_items/playlist_items. Watchlist "
            "can match online entries to local Plex media by GUID, which is useful for "
            "questions about which Watchlist items are already on the server. For recent "
            "media questions, use within_days for relative windows or since/before for "
            "explicit ranges. For broad recently-added TV questions, group_tv_by=show or "
            "season can avoid returning many individual episodes. Use watch_status for "
            "questions such as where the user is up to in a TV show, whether it is "
            "complete, or which episode should be watched next. Search/list results are "
            "intentionally compact and omit summaries by default; call media_details for "
            "a selected local item when detailed metadata or its summary is needed."
        ),
    )
