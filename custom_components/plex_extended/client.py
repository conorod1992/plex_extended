"""Plex client and query helpers for Plex Extended."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from functools import partial
from typing import Any, TypeVar
from urllib.parse import urlencode

from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from plexapi.server import PlexServer
from requests.exceptions import RequestException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BASE_URL,
    CONF_SERVER_TOKEN,
    DEFAULT_LIMIT,
    DEFAULT_SEARCH_TYPES,
    HISTORY_PAGE_SIZE,
    MAX_LIMIT,
)

_T = TypeVar("_T")


class PlexExtendedError(Exception):
    """Base Plex Extended error."""


class PlexExtendedAuthenticationError(PlexExtendedError):
    """Raised when Plex rejects the configured token."""


class PlexExtendedConnectionError(PlexExtendedError):
    """Raised when Plex cannot be reached."""


def _iso(value: Any) -> str | None:
    """Convert a Plex date/datetime to an ISO string."""
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


def _tag_names(values: Iterable[Any] | None) -> list[str]:
    """Return tag names from Plex tag objects."""
    if not values:
        return []
    result: list[str] = []
    for value in values:
        name = getattr(value, "tag", None) or getattr(value, "title", None)
        if name:
            result.append(str(name))
    return result


class PlexExtendedClient:
    """Thread-safe async wrapper around the synchronous PlexAPI client."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the client."""
        self.hass = hass
        self.entry = entry
        self._server: PlexServer | None = None
        self._lock = asyncio.Lock()

    @property
    def server_name(self) -> str:
        """Return the configured server name."""
        return self.entry.title

    async def async_connect(self) -> None:
        """Connect and validate the configured Plex server."""
        try:
            async with self._lock:
                self._server = await self.hass.async_add_executor_job(
                    PlexServer,
                    self.entry.data[CONF_BASE_URL],
                    self.entry.data[CONF_SERVER_TOKEN],
                )
        except Unauthorized as err:
            raise PlexExtendedAuthenticationError(
                "Plex rejected the configured token"
            ) from err
        except RequestException as err:
            raise PlexExtendedConnectionError(
                f"Unable to connect to Plex: {err}"
            ) from err
        except Exception as err:
            raise PlexExtendedConnectionError(
                f"Unable to connect to Plex: {err}"
            ) from err

    async def async_close(self) -> None:
        """Release the connected Plex server object."""
        async with self._lock:
            self._server = None

    async def _async_run(
        self,
        func: Callable[..., _T],
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        """Run a PlexAPI operation in the executor and serialize access."""
        try:
            async with self._lock:
                return await self.hass.async_add_executor_job(
                    partial(func, *args, **kwargs)
                )
        except Unauthorized as err:
            self.entry.async_start_reauth(self.hass)
            raise PlexExtendedAuthenticationError(
                "Plex authorization is no longer valid"
            ) from err
        except RequestException as err:
            raise PlexExtendedConnectionError(
                f"Unable to communicate with Plex: {err}"
            ) from err
        except (BadRequest, NotFound) as err:
            raise PlexExtendedError(str(err)) from err
        except PlexExtendedError:
            raise
        except Exception as err:
            raise PlexExtendedError(str(err)) from err

    def _require_server(self) -> PlexServer:
        """Return the connected server."""
        if self._server is None:
            raise PlexExtendedConnectionError("Plex client is not connected")
        return self._server

    def _section(
        self,
        library: str | None = None,
        library_id: str | int | None = None,
        server: PlexServer | None = None,
    ) -> Any | None:
        """Resolve a library by exact ID or unambiguous case-insensitive name."""
        if not library and library_id is None:
            return None

        target_server = server or self._require_server()
        sections = target_server.library.sections()

        if library_id is not None:
            wanted_id = str(library_id)
            matches = [section for section in sections if str(section.key) == wanted_id]
            if not matches:
                raise PlexExtendedError(f"Plex library ID not found: {library_id}")
            section = matches[0]
            if library and section.title.casefold() != library.casefold():
                raise PlexExtendedError(
                    f"Plex library ID {library_id} is '{section.title}', not '{library}'"
                )
            return section

        assert library is not None
        wanted = library.casefold()
        matches = [
            section for section in sections if section.title.casefold() == wanted
        ]
        if not matches:
            raise PlexExtendedError(f"Plex library not found: {library}")
        if len(matches) > 1:
            ids = ", ".join(str(section.key) for section in matches)
            raise PlexExtendedError(
                f"Multiple Plex libraries are named '{library}'. Use library_id instead "
                f"(matching IDs: {ids})"
            )
        return matches[0]

    @staticmethod
    def _normalize_types(
        search_types: list[str] | tuple[str, ...] | None,
    ) -> list[str]:
        """Normalize requested media types."""
        values = list(search_types or DEFAULT_SEARCH_TYPES)
        return list(dict.fromkeys(values))

    @staticmethod
    def _normalize_limit(limit: int | None) -> int:
        """Clamp result counts to a safe range."""
        return max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))

    def _serialize_technical(self, item: Any) -> list[dict[str, Any]]:
        """Serialize non-sensitive technical media data."""
        result: list[dict[str, Any]] = []
        for media in getattr(item, "media", []) or []:
            result.append(
                {
                    key: value
                    for key, value in {
                        "container": getattr(media, "container", None),
                        "bitrate": getattr(media, "bitrate", None),
                        "video_resolution": getattr(media, "videoResolution", None),
                        "video_codec": getattr(media, "videoCodec", None),
                        "audio_codec": getattr(media, "audioCodec", None),
                        "width": getattr(media, "width", None),
                        "height": getattr(media, "height", None),
                        "video_frame_rate": getattr(media, "videoFrameRate", None),
                        "audio_channels": getattr(media, "audioChannels", None),
                    }.items()
                    if value is not None
                }
            )
        return result

    def _serialize_item(
        self,
        item: Any,
        *,
        include_summary: bool = True,
        include_technical: bool = False,
        users: dict[int, str] | None = None,
    ) -> dict[str, Any]:
        """Convert a Plex media/history object to compact JSON-safe data."""
        duration = getattr(item, "duration", None)
        view_offset = getattr(item, "viewOffset", None)
        progress = None
        if duration and view_offset is not None:
            progress = round((float(view_offset) / float(duration)) * 100, 1)

        view_count = getattr(item, "viewCount", None)
        watched = None if view_count is None else bool(view_count)
        try:
            if hasattr(item, "isPlayed"):
                watched = bool(item.isPlayed)
        except Exception:
            pass

        account_id = getattr(item, "accountID", None)
        data: dict[str, Any] = {
            "rating_key": str(getattr(item, "ratingKey", "")) or None,
            "type": getattr(item, "type", None),
            "title": getattr(item, "title", None),
            "year": getattr(item, "year", None),
            "library": getattr(item, "librarySectionTitle", None),
            "library_id": getattr(item, "librarySectionID", None),
            "parent_title": getattr(item, "parentTitle", None),
            "grandparent_title": getattr(item, "grandparentTitle", None),
            "season": getattr(item, "parentIndex", None),
            "episode": (
                getattr(item, "index", None)
                if getattr(item, "type", None) == "episode"
                else None
            ),
            "duration_ms": duration,
            "view_offset_ms": view_offset,
            "progress_percent": progress,
            "view_count": view_count,
            "watched": watched,
            "added_at": _iso(getattr(item, "addedAt", None)),
            "last_viewed_at": _iso(getattr(item, "lastViewedAt", None)),
            "viewed_at": _iso(getattr(item, "viewedAt", None)),
            "content_rating": getattr(item, "contentRating", None),
            "rating": getattr(item, "rating", None),
            "audience_rating": getattr(item, "audienceRating", None),
            "studio": getattr(item, "studio", None),
            "guid": getattr(item, "guid", None),
            "genres": _tag_names(getattr(item, "genres", None)),
            "directors": _tag_names(getattr(item, "directors", None)),
            "thumb": getattr(item, "thumb", None),
            "account_id": account_id,
            "user": (
                users.get(int(account_id))
                if users and account_id is not None
                else None
            ),
        }
        if include_summary:
            data["summary"] = getattr(item, "summary", None)
        if include_technical:
            data["media"] = self._serialize_technical(item)
        return {
            key: value
            for key, value in data.items()
            if value not in (None, [], "")
        }

    def _search(
        self,
        query: str,
        search_types: list[str] | None,
        limit: int,
        library: str | None,
        include_summary: bool,
        include_technical: bool,
        library_id: str | int | None = None,
        server: PlexServer | None = None,
    ) -> dict[str, Any]:
        """Search Plex while preserving Plex's cross-category relevance ordering."""
        target_server = server or self._require_server()
        section = self._section(library, library_id, target_server)
        section_id = section.key if section else None
        media_types = self._normalize_types(search_types)
        requested_types = set(media_types)
        max_results = self._normalize_limit(limit)

        mediatype = media_types[0] if len(media_types) == 1 else None
        matches = target_server.search(
            query,
            mediatype=mediatype,
            limit=max_results,
            sectionId=section_id,
        )

        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for match in matches:
            match_type = str(getattr(match, "type", ""))
            if match_type not in requested_types:
                continue

            match_library_id = getattr(match, "librarySectionID", None)
            rating_key = getattr(match, "ratingKey", None)
            if match_library_id is None or rating_key is None:
                continue
            if section_id is not None and str(match_library_id) != str(section_id):
                continue

            identity = (match_type, str(rating_key))
            if identity in seen:
                continue
            seen.add(identity)

            if include_technical:
                try:
                    match = target_server.fetchItem(rating_key)
                except Exception:
                    pass

            results.append(
                self._serialize_item(
                    match,
                    include_summary=include_summary,
                    include_technical=include_technical,
                )
            )
            if len(results) >= max_results:
                break

        return {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
        }

    async def async_search(
        self,
        query: str,
        search_types: list[str] | None = None,
        limit: int = DEFAULT_LIMIT,
        library: str | None = None,
        include_summary: bool = True,
        include_technical: bool = False,
        library_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Search Plex."""
        return await self._async_run(
            self._search,
            query,
            search_types,
            limit,
            library,
            include_summary,
            include_technical,
            library_id,
        )

    def _recently_added(
        self,
        limit: int,
        library: str | None,
        media_types: list[str] | None,
        include_summary: bool,
        library_id: str | int | None = None,
        server: PlexServer | None = None,
    ) -> dict[str, Any]:
        """Return recently added media."""
        target_server = server or self._require_server()
        max_results = self._normalize_limit(limit)
        types = set(media_types or [])
        section = self._section(library, library_id, target_server)
        if section:
            items = section.recentlyAdded(maxresults=MAX_LIMIT)
        else:
            items = target_server.library.recentlyAdded()
        if types:
            items = [item for item in items if getattr(item, "type", None) in types]
        items = list(items)[:max_results]
        return {
            "success": True,
            "count": len(items),
            "results": [
                self._serialize_item(item, include_summary=include_summary)
                for item in items
            ],
        }

    async def async_recently_added(
        self,
        limit: int = DEFAULT_LIMIT,
        library: str | None = None,
        media_types: list[str] | None = None,
        include_summary: bool = True,
        library_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Return recently added media."""
        return await self._async_run(
            self._recently_added,
            limit,
            library,
            media_types,
            include_summary,
            library_id,
        )

    def _user_map(self) -> dict[int, str]:
        """Return Plex system account names keyed by account ID."""
        return {
            int(account.id): str(account.name)
            for account in self._require_server().systemAccounts()
        }

    @staticmethod
    def _resolve_user_id(
        users: dict[int, str],
        user: str | None,
        user_id: str | int | None,
    ) -> int | None:
        """Resolve a Plex account by exact ID or unambiguous case-insensitive name."""
        if user_id is not None:
            try:
                account_id = int(user_id)
            except (TypeError, ValueError) as err:
                raise PlexExtendedError(f"Invalid Plex user ID: {user_id}") from err
            if account_id not in users:
                raise PlexExtendedError(f"Plex user ID not found: {user_id}")
            if user and users[account_id].casefold() != user.casefold():
                raise PlexExtendedError(
                    f"Plex user ID {user_id} is '{users[account_id]}', not '{user}'"
                )
            return account_id

        if not user:
            return None

        wanted = user.casefold()
        matches = [
            account_id
            for account_id, name in users.items()
            if name.casefold() == wanted
        ]
        if not matches:
            raise PlexExtendedError(f"Plex user not found: {user}")
        if len(matches) > 1:
            ids = ", ".join(str(account_id) for account_id in matches)
            raise PlexExtendedError(
                f"Multiple Plex users are named '{user}'. Use user_id instead "
                f"(matching IDs: {ids})"
            )
        return matches[0]

    @staticmethod
    def _history_key(account_id: int | None, section_id: Any | None) -> str:
        """Build the same watched-history endpoint used by PlexAPI.history()."""
        args: list[tuple[str, str]] = [("sort", "viewedAt:desc")]
        if account_id is not None:
            args.append(("accountID", str(account_id)))
        if section_id is not None:
            args.append(("librarySectionID", str(section_id)))
        return f"/status/sessions/history/all?{urlencode(args)}"

    def _recently_watched(
        self,
        limit: int,
        library: str | None,
        user: str | None,
        media_types: list[str] | None,
        include_summary: bool,
        library_id: str | int | None = None,
        user_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Return Plex watch history, paging until requested filtered results are filled."""
        server = self._require_server()
        max_results = self._normalize_limit(limit)
        section = self._section(library, library_id)
        users = self._user_map()
        account_id = self._resolve_user_id(users, user, user_id)
        types = set(media_types or [])

        history_key = self._history_key(
            account_id,
            section.key if section else None,
        )
        matched: list[Any] = []
        offset = 0

        while len(matched) < max_results:
            page = list(
                server.fetchItems(
                    history_key,
                    container_start=offset,
                    container_size=HISTORY_PAGE_SIZE,
                    maxresults=HISTORY_PAGE_SIZE,
                )
            )
            if not page:
                break

            for item in page:
                if types and getattr(item, "type", None) not in types:
                    continue
                matched.append(item)
                if len(matched) >= max_results:
                    break

            if len(page) < HISTORY_PAGE_SIZE:
                break
            offset += HISTORY_PAGE_SIZE

        return {
            "success": True,
            "count": len(matched),
            "results": [
                self._serialize_item(
                    item,
                    include_summary=include_summary,
                    users=users,
                )
                for item in matched
            ],
        }

    async def async_recently_watched(
        self,
        limit: int = DEFAULT_LIMIT,
        library: str | None = None,
        user: str | None = None,
        media_types: list[str] | None = None,
        include_summary: bool = True,
        library_id: str | int | None = None,
        user_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Return watch history."""
        return await self._async_run(
            self._recently_watched,
            limit,
            library,
            user,
            media_types,
            include_summary,
            library_id,
            user_id,
        )

    def _continue_watching(
        self,
        limit: int,
        library: str | None,
        include_summary: bool,
        library_id: str | int | None = None,
        server: PlexServer | None = None,
    ) -> dict[str, Any]:
        """Return Continue Watching items."""
        target_server = server or self._require_server()
        max_results = self._normalize_limit(limit)
        section = self._section(library, library_id, target_server)
        items = (
            section.continueWatching()
            if section
            else target_server.continueWatching()
        )
        items = list(items)[:max_results]
        return {
            "success": True,
            "count": len(items),
            "results": [
                self._serialize_item(item, include_summary=include_summary)
                for item in items
            ],
        }

    async def async_continue_watching(
        self,
        limit: int = DEFAULT_LIMIT,
        library: str | None = None,
        include_summary: bool = True,
        library_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Return Continue Watching items."""
        return await self._async_run(
            self._continue_watching,
            limit,
            library,
            include_summary,
            library_id,
        )

    def _on_deck(
        self,
        limit: int,
        library: str | None,
        include_summary: bool,
        library_id: str | int | None = None,
        server: PlexServer | None = None,
    ) -> dict[str, Any]:
        """Return On Deck items."""
        target_server = server or self._require_server()
        max_results = self._normalize_limit(limit)
        section = self._section(library, library_id, target_server)
        items = section.onDeck() if section else target_server.library.onDeck()
        items = list(items)[:max_results]
        return {
            "success": True,
            "count": len(items),
            "results": [
                self._serialize_item(item, include_summary=include_summary)
                for item in items
            ],
        }

    async def async_on_deck(
        self,
        limit: int = DEFAULT_LIMIT,
        library: str | None = None,
        include_summary: bool = True,
        library_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Return On Deck items."""
        return await self._async_run(
            self._on_deck,
            limit,
            library,
            include_summary,
            library_id,
        )

    def _media_details(
        self,
        rating_key: str,
        include_technical: bool,
        server: PlexServer | None = None,
    ) -> dict[str, Any]:
        """Return details for a Plex rating key."""
        target_server = server or self._require_server()
        item = target_server.fetchItem(rating_key)
        return {
            "success": True,
            "result": self._serialize_item(
                item,
                include_summary=True,
                include_technical=include_technical,
            ),
        }

    async def async_media_details(
        self, rating_key: str, include_technical: bool = True
    ) -> dict[str, Any]:
        """Return details for a Plex item."""
        return await self._async_run(
            self._media_details,
            rating_key,
            include_technical,
        )

    def _list_libraries(self) -> dict[str, Any]:
        """Return available Plex libraries."""
        sections = self._require_server().library.sections()
        return {
            "success": True,
            "count": len(sections),
            "libraries": [
                {
                    "id": str(section.key),
                    "title": section.title,
                    "type": getattr(section, "type", None),
                    "uuid": getattr(section, "uuid", None),
                }
                for section in sections
            ],
        }

    async def async_list_libraries(self) -> dict[str, Any]:
        """Return available Plex libraries."""
        return await self._async_run(self._list_libraries)

    def _list_users(self) -> dict[str, Any]:
        """Return users known to this Plex server."""
        accounts = self._require_server().systemAccounts()
        return {
            "success": True,
            "count": len(accounts),
            "users": [
                {"id": int(account.id), "name": str(account.name)}
                for account in accounts
            ],
        }

    async def async_list_users(self) -> dict[str, Any]:
        """Return Plex users."""
        return await self._async_run(self._list_users)

    def _test_connection(self) -> dict[str, Any]:
        """Test server connectivity."""
        server = self._require_server()
        identity = server.identity()
        return {
            "success": True,
            "server": server.friendlyName,
            "machine_identifier": server.machineIdentifier,
            "version": getattr(identity, "version", None) or server.version,
            "platform": server.platform,
        }

    async def async_test_connection(self) -> dict[str, Any]:
        """Test server connectivity."""
        return await self._async_run(self._test_connection)
