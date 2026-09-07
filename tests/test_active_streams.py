"""Tests for Plex Extended active stream queries."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def _install_homeassistant_stubs() -> None:
    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    core = ModuleType("homeassistant.core")

    class ConfigEntry:
        pass

    class HomeAssistant:
        pass

    config_entries.ConfigEntry = ConfigEntry
    core.HomeAssistant = HomeAssistant
    sys.modules.setdefault("homeassistant", homeassistant)
    sys.modules.setdefault("homeassistant.config_entries", config_entries)
    sys.modules.setdefault("homeassistant.core", core)


def _load_component_module(name: str, filename: str) -> ModuleType:
    full_name = f"custom_components.plex_extended.{name}"
    existing = sys.modules.get(full_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(full_name, COMPONENT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_install_homeassistant_stubs()
custom_components = sys.modules.setdefault("custom_components", ModuleType("custom_components"))
custom_components.__path__ = [str(ROOT / "custom_components")]
package = sys.modules.setdefault(
    "custom_components.plex_extended", ModuleType("custom_components.plex_extended")
)
package.__path__ = [str(COMPONENT)]

_load_component_module("const", "const.py")
_load_component_module("client", "client.py")
active_streams = _load_component_module("active_streams", "active_streams.py")

_active_streams = active_streams._active_streams
_delivery_decision = active_streams._delivery_decision
_serialize_active_session = active_streams._serialize_active_session


class FakeServer:
    def __init__(self, sessions):
        self._sessions = list(sessions)
        self.calls = 0

    def sessions(self):
        self.calls += 1
        return list(self._sessions)


class FakeClient:
    def __init__(self, sessions):
        self.server = FakeServer(sessions)

    def _require_server(self):
        return self.server

    @staticmethod
    def _normalize_limit(limit):
        return max(1, min(int(limit or 10), 50))


def _media(**overrides):
    values = {
        "selected": True,
        "container": "mkv",
        "bitrate": 15000,
        "videoResolution": "1080",
        "videoCodec": "h264",
        "audioCodec": "aac",
        "audioChannels": 6,
        "width": 1920,
        "height": 1080,
        "file": "/private/media/movie.mkv",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _player(**overrides):
    values = {
        "title": "Living Room TV",
        "product": "Plex for Android",
        "platform": "Android",
        "device": "TV",
        "model": "Example",
        "state": "playing",
        "local": True,
        "relayed": False,
        "secure": True,
        "location": "lan",
        "address": "192.0.2.10",
        "remotePublicAddress": "198.51.100.20",
        "machineIdentifier": "private-device-id",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _session(**overrides):
    values = {"location": "lan", "bandwidth": 16000, "id": "private-session-id"}
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeItem:
    def __init__(
        self,
        *,
        user="Conor",
        media_type="movie",
        player=None,
        session=None,
        transcode=None,
        media=None,
        title="Arrival",
        rating_key="123",
    ):
        self.usernames = [user] if user is not None else []
        self.type = media_type
        self.title = title
        self.ratingKey = rating_key
        self.year = 2016
        self.librarySectionTitle = "Movies"
        self.librarySectionID = 1
        self.parentTitle = None
        self.grandparentTitle = None
        self.parentIndex = None
        self.index = None
        self.duration = 400_000
        self.viewOffset = 100_000
        self.live = False
        self.player = player if player is not None else _player()
        self.session = session if session is not None else _session()
        self.transcodeSession = transcode
        self.media = list(media if media is not None else [_media()])

    @property
    def user(self):
        raise AssertionError("serializer must not trigger the plex.tv user property")


def test_direct_play_serialization_is_compact_and_private() -> None:
    item = FakeItem()

    result = _serialize_active_session(item)

    assert result["user"] == "Conor"
    assert result["state"] == "playing"
    assert result["media"]["progress_percent"] == 25.0
    assert result["media"]["rating_key"] == "123"
    assert result["player"]["name"] == "Living Room TV"
    assert result["player"]["local"] is True
    assert result["network"] == {"location": "lan", "bandwidth": 16000}
    assert result["source"]["video_resolution"] == "1080"
    assert result["delivery"] == {"decision": "direct_play"}

    serialized = repr(result)
    assert "192.0.2.10" not in serialized
    assert "198.51.100.20" not in serialized
    assert "private-device-id" not in serialized
    assert "private-session-id" not in serialized
    assert "/private/media/movie.mkv" not in serialized


def test_selected_media_version_is_used() -> None:
    item = FakeItem(
        media=[
            _media(selected=False, videoResolution="4k", bitrate=50000),
            _media(selected=True, videoResolution="720", bitrate=4000),
        ]
    )

    result = _serialize_active_session(item)

    assert result["source"]["video_resolution"] == "720"
    assert result["source"]["bitrate"] == 4000


def test_delivery_classifies_direct_stream_without_false_transcode() -> None:
    transcode = SimpleNamespace(
        videoDecision="copy",
        audioDecision="copy",
        subtitleDecision=None,
        sourceVideoCodec="h264",
        sourceAudioCodec="aac",
        container="mkv",
        videoCodec="h264",
        audioCodec="aac",
        audioChannels=2,
        width=1920,
        height=1080,
        protocol="http",
        speed=0.0,
        throttled=True,
        transcodeHwFullPipeline=False,
        transcodeHwDecoding=None,
        transcodeHwEncoding=None,
        transcodeHwRequested=False,
        transcodeHwDecodingTitle=None,
        transcodeHwEncodingTitle=None,
    )

    assert _delivery_decision(transcode) == "direct_stream"
    result = _serialize_active_session(FakeItem(transcode=transcode))
    assert result["delivery"]["decision"] == "direct_stream"
    assert result["delivery"]["video_decision"] == "copy"
    assert result["delivery"]["hardware_transcoding"] is False


def test_delivery_reports_transcode_and_hardware_details() -> None:
    transcode = SimpleNamespace(
        videoDecision="transcode",
        audioDecision="copy",
        subtitleDecision="burn",
        sourceVideoCodec="hevc",
        sourceAudioCodec="eac3",
        container="mpegts",
        videoCodec="h264",
        audioCodec="eac3",
        audioChannels=6,
        width=1280,
        height=720,
        protocol="hls",
        speed=2.3,
        throttled=False,
        transcodeHwFullPipeline=True,
        transcodeHwDecoding="nvdec",
        transcodeHwEncoding="nvenc",
        transcodeHwRequested=True,
        transcodeHwDecodingTitle="NVIDIA NVDEC",
        transcodeHwEncodingTitle="NVIDIA NVENC",
    )

    result = _serialize_active_session(FakeItem(transcode=transcode))

    assert result["delivery"]["decision"] == "transcode"
    assert result["delivery"]["source_video_codec"] == "hevc"
    assert result["delivery"]["output_video_codec"] == "h264"
    assert result["delivery"]["hardware_transcoding"] is True
    assert result["delivery"]["hardware_encoder"] == "NVIDIA NVENC"


def test_filters_user_state_media_and_locality() -> None:
    sessions = [
        FakeItem(user="Conor", media_type="movie", player=_player(local=True)),
        FakeItem(
            user="Guest",
            media_type="episode",
            player=_player(title="Guest iPad", state="paused", local=False),
            rating_key="456",
        ),
        FakeItem(
            user="Guest",
            media_type="movie",
            player=_player(title="Guest Phone", state="playing", local=False),
            rating_key="789",
        ),
    ]
    client = FakeClient(sessions)

    result = _active_streams(
        client,
        {
            "user": "guest",
            "media_types": ["episode"],
            "states": ["paused"],
            "locality": "remote",
            "limit": 50,
        },
    )

    assert client.server.calls == 1
    assert result["total_sessions"] == 3
    assert result["matching_sessions"] == 1
    assert result["count"] == 1
    assert result["truncated"] is False
    assert result["results"][0]["media"]["rating_key"] == "456"


def test_unknown_locality_is_not_misclassified_as_remote() -> None:
    client = FakeClient([FakeItem(player=_player(local=None))])

    result = _active_streams(client, {"locality": "remote", "limit": 50})

    assert result["matching_sessions"] == 0


def test_limit_reports_truncation_without_hiding_match_count() -> None:
    client = FakeClient([FakeItem(rating_key=str(index)) for index in range(3)])

    result = _active_streams(client, {"limit": 2, "locality": "any"})

    assert result["total_sessions"] == 3
    assert result["matching_sessions"] == 3
    assert result["count"] == 2
    assert result["truncated"] is True
