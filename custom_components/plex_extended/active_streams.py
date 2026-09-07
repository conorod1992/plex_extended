"""Active Plex stream queries for Plex Extended."""

from __future__ import annotations

from typing import Any

from .client import PlexExtendedClient
from .const import MAX_LIMIT


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    """Remove absent values while retaining useful False/zero values."""
    return {
        key: value
        for key, value in data.items()
        if value is not None and value != "" and value != [] and value != {}
    }


def _progress_percent(item: Any) -> float | None:
    """Return playback progress as a percentage when duration is known."""
    duration = getattr(item, "duration", None)
    offset = getattr(item, "viewOffset", None)
    if not duration or offset is None:
        return None
    try:
        return round((float(offset) / float(duration)) * 100, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _selected_media(item: Any) -> Any | None:
    """Return Plex's selected media version, falling back to the first version."""
    media = list(getattr(item, "media", []) or [])
    if not media:
        return None
    return next((value for value in media if bool(getattr(value, "selected", False))), media[0])


def _source_media(media: Any | None) -> dict[str, Any]:
    """Serialize the selected source media without local file paths."""
    if media is None:
        return {}
    return _compact(
        {
            "container": getattr(media, "container", None),
            "bitrate": getattr(media, "bitrate", None),
            "video_resolution": getattr(media, "videoResolution", None),
            "video_codec": getattr(media, "videoCodec", None),
            "audio_codec": getattr(media, "audioCodec", None),
            "audio_channels": getattr(media, "audioChannels", None),
            "width": getattr(media, "width", None),
            "height": getattr(media, "height", None),
        }
    )


def _delivery_decision(transcode: Any | None) -> str:
    """Classify Plex delivery without treating remux/direct-stream as transcoding."""
    if transcode is None:
        return "direct_play"

    decisions = {
        str(value).casefold()
        for value in (
            getattr(transcode, "videoDecision", None),
            getattr(transcode, "audioDecision", None),
            getattr(transcode, "subtitleDecision", None),
        )
        if value
    }
    if "transcode" in decisions:
        return "transcode"
    if decisions.intersection({"copy", "directstream", "direct_stream"}):
        return "direct_stream"
    return "unknown"


def _delivery(transcode: Any | None) -> dict[str, Any]:
    """Serialize delivery/transcode details."""
    if transcode is None:
        return {"decision": "direct_play"}

    hardware = bool(
        getattr(transcode, "transcodeHwFullPipeline", False)
        or getattr(transcode, "transcodeHwDecoding", None)
        or getattr(transcode, "transcodeHwEncoding", None)
    )
    return _compact(
        {
            "decision": _delivery_decision(transcode),
            "video_decision": getattr(transcode, "videoDecision", None),
            "audio_decision": getattr(transcode, "audioDecision", None),
            "subtitle_decision": getattr(transcode, "subtitleDecision", None),
            "source_video_codec": getattr(transcode, "sourceVideoCodec", None),
            "source_audio_codec": getattr(transcode, "sourceAudioCodec", None),
            "output_container": getattr(transcode, "container", None),
            "output_video_codec": getattr(transcode, "videoCodec", None),
            "output_audio_codec": getattr(transcode, "audioCodec", None),
            "output_audio_channels": getattr(transcode, "audioChannels", None),
            "output_width": getattr(transcode, "width", None),
            "output_height": getattr(transcode, "height", None),
            "protocol": getattr(transcode, "protocol", None),
            "speed": getattr(transcode, "speed", None),
            "throttled": getattr(transcode, "throttled", None),
            "hardware_transcoding": hardware,
            "hardware_requested": getattr(transcode, "transcodeHwRequested", None),
            "hardware_decoder": getattr(transcode, "transcodeHwDecodingTitle", None),
            "hardware_encoder": getattr(transcode, "transcodeHwEncodingTitle", None),
        }
    )


def _username(item: Any) -> str | None:
    """Return the session username without triggering a plex.tv account lookup."""
    usernames = list(getattr(item, "usernames", []) or [])
    if usernames and usernames[0]:
        return str(usernames[0])
    return None


def _serialize_active_session(item: Any) -> dict[str, Any]:
    """Serialize one /status/sessions media object into compact safe data."""
    player = getattr(item, "player", None)
    session = getattr(item, "session", None)
    transcode = getattr(item, "transcodeSession", None)
    source = _selected_media(item)

    media = _compact(
        {
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
            "duration_ms": getattr(item, "duration", None),
            "view_offset_ms": getattr(item, "viewOffset", None),
            "progress_percent": _progress_percent(item),
            "live": getattr(item, "live", None),
        }
    )

    player_data = _compact(
        {
            "name": getattr(player, "title", None),
            "product": getattr(player, "product", None),
            "platform": getattr(player, "platform", None),
            "device": getattr(player, "device", None),
            "model": getattr(player, "model", None),
            "state": getattr(player, "state", None),
            "local": getattr(player, "local", None),
            "relayed": getattr(player, "relayed", None),
            "secure": getattr(player, "secure", None),
        }
    )

    network = _compact(
        {
            "location": getattr(session, "location", None)
            or getattr(player, "location", None),
            "bandwidth": getattr(session, "bandwidth", None),
        }
    )

    return _compact(
        {
            "user": _username(item),
            "state": getattr(player, "state", None),
            "media": media,
            "player": player_data,
            "network": network,
            "source": _source_media(source),
            "delivery": _delivery(transcode),
        }
    )


def _active_streams(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return filtered active Plex sessions."""
    server = client._require_server()
    sessions = list(server.sessions())

    wanted_user = str(criteria.get("user", "")).strip().casefold()
    media_types = set(criteria.get("media_types") or [])
    states = {str(value).casefold() for value in (criteria.get("states") or [])}
    locality = str(criteria.get("locality", "any"))
    limit = client._normalize_limit(criteria.get("limit", MAX_LIMIT))

    filtered: list[Any] = []
    for item in sessions:
        player = getattr(item, "player", None)
        if wanted_user and (_username(item) or "").casefold() != wanted_user:
            continue
        if media_types and getattr(item, "type", None) not in media_types:
            continue
        state = str(getattr(player, "state", "") or "").casefold()
        if states and state not in states:
            continue
        local = getattr(player, "local", None)
        if locality == "local" and local is not True:
            continue
        if locality == "remote" and local is not False:
            continue
        filtered.append(item)

    visible = filtered[:limit]
    return {
        "success": True,
        "count": len(visible),
        "matching_sessions": len(filtered),
        "total_sessions": len(sessions),
        "truncated": len(visible) < len(filtered),
        "results": [_serialize_active_session(item) for item in visible],
    }


async def async_active_streams(
    client: PlexExtendedClient,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Return active streams through the client's executor lock."""
    return await client._async_run(_active_streams, client, dict(criteria))
