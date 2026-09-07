"""Plex client and query helpers for Plex Extended."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from functools import partial
from typing import Any, TypeVar

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

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
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
            raise PlexExtendedAuthenticationError("Plex rejected the configured token") from err
        except RequestException as err:
            raise PlexExtendedConnectionError(f"Unable to connect to Plex: {err}") from err
        except Exception as err:
            raise PlexExtendedConnectionError(f"Unable to connect to Plex: {err}") from err

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
            raise PlexExtendedAuthenticationError("Plex authorization is no longer valid") from err
        except RequestException as err:
            raise PlexExtendedConnectionError(f"Unable to communicate with Plex: {err}") from err
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

    def _section(self, library: str | None) -> Any | None:
        """Find a library section case-insensitively."""
        if not library:
            return None
        server = self._require_server()
        wanted = library.casefold()
        for section in server.library.sections():
            if section.title.casefold() == wanted:
                return section
        raise PlexExtendedError(f"Plex library not found: {library}")

    @staticmethod
    def _normalize_types(search_types: list[str] | tuple[str, ...] | None) -> list[str]:
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
            "episode": getattr(item, "index", None)
            if getattr(item, "type", None) == "episode"
            else None,
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
            "user": users.get(account_id) if users and account_id is not None else None,
        }
        if include_summary:
            data["summary"] = getattr(item, "summary", None)
        if include_technical:
            data["media"] = self._serialize_technical(item)
        return {key: value for key, value in data.items() if value not in (None, [], "")}

    def _search(
        self,
        query: str,
        search_types: list[str] | None,
        limit: int,
        library: str | None,
        include_summary: bool,
        include_technical: bool,
    ) -> dict[str, Any]:
        """Search Plex using its hub search, preserving Plex relevance ordering."""
        server = self._require_server()
        section = self._section(library)
        section_id = section.key if section else None
        media_types = self._normalize_types(search_types)
        max_results = self._normalize_limit(limit)

        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for media_type in media_types:
            matches = server.search(
                query,
                mediatype=media_type,
                limit=max_results,
                sectionId=section_id,
            )
            for match in matches:
                # Plex hub search can include online/external media. Plex Extended is
                # deliberately a library search, so only return server library items.
                library_id = getattr(match, "librarySectionID", None)
                rating_key = getattr(match, "ratingKey", None)
                if library_id is None or rating_key is None:
                    continue
                identity = (str(getattr(match, "type", media_type)), str(rating_key))
                if identity in seen:
                    continue
                seen.add(identity)
                if include_technical:
                    try:
                        match = server.fetchItem(rating_key)
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
        )

    def _recently_added(
        self,
        limit: int,
        library: str | None,
        media_types: list[str] | None,
        include_summary: bool,
    ) -> dict[str, Any]:
        """Return recently added media."""
        server = self._require_server()
        max_results = self._normalize_limit(limit)
        types = set(media_types or [])
        section = self._section(library)
        if section:
            items = section.recentlyAdded(maxresults=MAX_LIMIT)
        else:
            items = server.library.recentlyAdded()
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
    ) -> dict[str, Any]:
        """Return recently added media."""
        return await self._async_run(
            self._recently_added, limit, library, media_types, include_summary
        )

    def _user_map(self) -> dict[int, str]:
        """Return Plex system account names keyed by account ID."""
        return {
            int(account.id): str(account.name)
            for account in self._require_server().systemAccounts()
        }

    def _recently_watched(
        self,
        limit: int,
        library: str | None,
        user: str | None,
        media_types: list[str] | None,
        include_summary: bool,
    ) -> dict[str, Any]:
        """Return Plex watch history."""
        server = self._require_server()
        max_results = self._normalize_limit(limit)
        section = self._section(library)
        users = self._user_map()
        account_id: int | None = None
        if user:
            wanted = user.casefold()
            account_id = next(
                (key for key, name in users.items() if name.casefold() == wanted), None
            )
            if account_id is None:
                raise PlexExtendedError(f"Plex user not found: {user}")

        types = set(media_types or [])
        fetch_count = min(MAX_LIMIT, max_results * 5) if types else max_results
        items = server.history(
            maxresults=fetch_count,
            accountID=account_id,
            librarySectionID=section.key if section else None,
        )
        if types:
            items = [item for item in items if getattr(item, "type", None) in types]
        items = list(items)[:max_results]
        return {
            "success": True,
            "count": len(items),
            "results": [
                self._serialize_item(
                    item,
                    include_summary=include_summary,
                    users=users,
                )
                for item in items
            ],
        }

    async def async_recently_watched(
        self,
        limit: int = DEFAULT_LIMIT,
        library: str | None = None,
        user: str | None = None,
        media_types: list[str] | None = None,
        include_summary: bool = True,
    ) -> dict[str, Any]:
        """Return watch history."""
        return await self._async_run(
            self._recently_watched,
            limit,
            library,
            user,
            media_types,
            include_summary,
        )

    def _continue_watching(
        self, limit: int, library: str | None, include_summary: bool
    ) -> dict[str, Any]:
        """Return Continue Watching items."""
        max_results = self._normalize_limit(limit)
        section = self._section(library)
        items = (
            section.continueWatching()
            if section
            else self._require_server().continueWatching()
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
    ) -> dict[str, Any]:
        """Return Continue Watching items."""
        return await self._async_run(
            self._continue_watching, limit, library, include_summary
        )

    def _on_deck(
        self, limit: int, library: str | None, include_summary: bool
    ) -> dict[str, Any]:
        """Return On Deck items."""
        max_results = self._normalize_limit(limit)
        section = self._section(library)
        items = section.onDeck() if section else self._require_server().library.onDeck()
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
    ) -> dict[str, Any]:
        """Return On Deck items."""
        return await self._async_run(self._on_deck, limit, library, include_summary)

    def _media_details(
        self, rating_key: str, include_technical: bool
    ) -> dict[str, Any]:
        """Return details for a Plex rating key."""
        item = self._require_server().fetchItem(rating_key)
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
            self._media_details, rating_key, include_technical
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
