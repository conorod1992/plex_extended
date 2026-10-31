"""Real PlexAPI + local HTTP server contract tests (no Plex account or secrets).

The tests deliberately instantiate the installed PlexAPI classes rather than
substituting fake Collection/Playlist objects. They exercise HTTP transport,
XML parsing, container pagination and failure handling together.
"""
from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest
from plexapi.server import PlexServer
from plexapi.exceptions import BadRequest, Unauthorized


class FixtureHandler(BaseHTTPRequestHandler):
    requests_seen = []
    ignore_offset = False
    fail_requests = False
    reject_next_items_request = False
    items_request_count = 0
    mixed_items = False
    duplicate_media = False
    radio = False

    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urlsplit(self.path)
        self.requests_seen.append((url.path, parse_qs(url.query), dict(self.headers)))
        if self.fail_requests:
            self.send_response(503)
            self.end_headers()
            return
        if url.path == "/playlists/9/items":
            type(self).items_request_count += 1
            if self.reject_next_items_request:
                type(self).reject_next_items_request = False
                self.send_response(401)
                self.end_headers()
                return
        if url.path == "/":
            payload = (
                '<MediaContainer size="0" friendlyName="Fixture PMS" '
                'machineIdentifier="fixture-machine" version="1.41.0" />'
            )
        elif url.path in {"/playlists", "/playlists/9"}:
            payload = (
                '<MediaContainer size="1">'
                '<Playlist ratingKey="9" key="/playlists/9" title="Test" '
                f'playlistType="video" type="playlist" leafCount="60" radio="{int(self.radio)}" />'
                '</MediaContainer>'
            )
        elif url.path == "/library/metadata/8":
            payload = (
                '<MediaContainer size="1"><Directory type="collection" '
                'ratingKey="8" key="/library/metadata/8" title="Test" '
                'subtype="movie" childCount="60" /></MediaContainer>'
            )
        elif url.path.startswith("/library/metadata/") and url.path.rsplit("/", 1)[1].isdigit():
            rating_key = int(url.path.rsplit("/", 1)[1])
            payload = (
                '<MediaContainer size="1">'
                f'<Video type="movie" title="Movie {rating_key - 100}" '
                f'ratingKey="{rating_key}" key="{url.path}" />'
                '</MediaContainer>'
            )
        elif url.path in {"/playlists/9/items", "/library/metadata/8/children"}:
            start = int(self.headers.get("X-Plex-Container-Start", "0"))
            size = int(self.headers.get("X-Plex-Container-Size", "25"))
            if self.ignore_offset:
                start = 0
            items = [
                f'<Video type="{"episode" if self.mixed_items and n < 50 else "movie"}" '
                f'title="Movie {0 if self.duplicate_media and n < 50 else n}" '
                f'ratingKey="{100 if self.duplicate_media and n < 50 else 100+n}" '
                + (f'playlistItemID="{n+1}" ' if url.path == "/playlists/9/items" else "")
                + f'key="/library/metadata/{100 if self.duplicate_media and n < 50 else 100+n}" />'
                for n in range(start, min(start + size, 60))
            ]
            payload = (
                f'<MediaContainer size="{len(items)}" totalSize="60">'
                + "".join(items) + "</MediaContainer>"
            )
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = payload.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@contextmanager
def fixture_server():
    class Handler(FixtureHandler):
        requests_seen = []
        ignore_offset = False
        fail_requests = False
        reject_next_items_request = False
        items_request_count = 0

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Handler, PlexServer(f"http://127.0.0.1:{server.server_port}", "fixture-token")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_real_plexapi_playlist_fetch_uses_container_headers():
    with fixture_server() as (handler, server):
        playlist = server.playlists()[0]
        items = playlist.fetchItems(
            "/playlists/9/items",
            container_start=25,
            container_size=10,
            maxresults=10,
        )
        assert [item.title for item in items] == [f"Movie {n}" for n in range(25, 35)]
        calls = [entry for entry in handler.requests_seen if entry[0] == "/playlists/9/items"]
        assert calls
        headers = calls[-1][2]
        assert headers["X-Plex-Container-Start"] == "25"
        assert headers["X-Plex-Container-Size"] == "10"


def test_real_plexapi_rejects_http_server_failure():
    with fixture_server() as (handler, server):
        handler.fail_requests = True
        with pytest.raises(BadRequest, match="503"):
            server.playlists()


def test_real_plexapi_playlist_items_match_fixture_pagination():
    with fixture_server() as (_, server):
        playlist = server.playlists()[0]
        results = playlist.items()
        assert len(results) == 60
        assert results[0].title == "Movie 0"
        assert results[-1].title == "Movie 59"


def test_real_plexapi_recovers_after_transient_unauthorized():
    """A rejected request must not permanently poison a PlexAPI session."""
    with fixture_server() as (handler, server):
        playlist = server.playlists()[0]
        handler.reject_next_items_request = True
        with pytest.raises(Unauthorized):
            playlist.fetchItems("/playlists/9/items", container_start=0, container_size=2, maxresults=2)
        recovered = playlist.fetchItems(
            "/playlists/9/items", container_start=2, container_size=2, maxresults=2
        )
        assert [item.title for item in recovered] == ["Movie 2", "Movie 3"]
        assert handler.items_request_count == 2


def test_real_plexapi_repeated_pages_expose_ignored_offsets():
    """Exercise a broken server via real PlexAPI rather than a fake fetchItems."""
    with fixture_server() as (handler, server):
        playlist = server.playlists()[0]
        handler.ignore_offset = True
        first = playlist.fetchItems(
            "/playlists/9/items", container_start=0, container_size=3, maxresults=3
        )
        second = playlist.fetchItems(
            "/playlists/9/items", container_start=3, container_size=3, maxresults=3
        )
        assert [x.ratingKey for x in first] == [x.ratingKey for x in second]
        requests = [x for x in handler.requests_seen if x[0] == "/playlists/9/items"]
        assert requests[-2][2]["X-Plex-Container-Start"] == "0"
        assert requests[-1][2]["X-Plex-Container-Start"] == "3"
