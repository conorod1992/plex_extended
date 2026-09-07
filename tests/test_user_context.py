"""Tests for Plex Extended per-user viewing context."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def _install_homeassistant_stubs() -> None:
    """Install the small Home Assistant surface imported by client.py."""
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
    """Load one integration module without executing package __init__.py."""
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

const = _load_component_module("const", "const.py")
client_module = _load_component_module("client", "client.py")
context_module = _load_component_module("user_context", "user_context.py")

PlexExtendedClient = client_module.PlexExtendedClient
resolve_user_context = context_module.resolve_user_context
_browse_for_context = context_module._browse_for_context
_media_details_for_context = context_module._media_details_for_context
_recently_added_for_context = context_module._recently_added_for_context
_recently_watched_for_context = context_module._recently_watched_for_context
_search_for_context = context_module._search_for_context


class FakeSection:
    """Minimal user-scoped Plex library section."""

    def __init__(self, key: str = "2", title: str = "TV Shows") -> None:
        self.key = key
        self.title = title
        self.type = "show"
        self._continue = []
        self._on_deck = []
        self._recent = []

    def continueWatching(self):
        return list(self._continue)

    def onDeck(self):
        return list(self._on_deck)

    def recentlyAdded(self, maxresults=None):
        items = list(self._recent)
        return items[:maxresults] if maxresults is not None else items


class FakeLibrary:
    """Minimal Plex library container."""

    def __init__(self, sections: list[FakeSection] | None = None) -> None:
        self._sections = sections or [FakeSection()]
        self._on_deck = []
        self._recent = []

    def sections(self):
        return list(self._sections)

    def onDeck(self):
        return list(self._on_deck)

    def recentlyAdded(self):
        return list(self._recent)


class FakeServer:
    """Minimal Plex server with switchUser and personalized media state."""

    def __init__(self, label: str, accounts=None) -> None:
        self.label = label
        self.library = FakeLibrary()
        self.accounts = accounts or []
        self.switch_calls: list[str] = []
        self.switched: dict[str, FakeServer] = {}
        self._continue = []
        self._search = []
        self._items = {}
        self.history = []
        self.fetch_calls = []

    def systemAccounts(self):
        return list(self.accounts)

    def switchUser(self, name):
        self.switch_calls.append(str(name))
        return self.switched[str(name)]

    def continueWatching(self):
        return list(self._continue)

    def search(self, query, mediatype=None, limit=None, sectionId=None):
        matches = list(self._search)
        if mediatype is not None:
            matches = [item for item in matches if item.type == mediatype]
        return matches[:limit] if limit is not None else matches

    def fetchItem(self, rating_key):
        return self._items[str(rating_key)]

    def fetchItems(
        self,
        key,
        container_start=None,
        container_size=None,
        maxresults=None,
    ):
        start = int(container_start or 0)
        size = int(container_size or maxresults or len(self.history))
        self.fetch_calls.append({"key": key, "start": start, "size": size})
        return self.history[start : start + size]


def _item(
    title: str,
    account_id: int | None = None,
    *,
    media_type: str = "episode",
    view_count: int = 0,
) -> SimpleNamespace:
    """Create a compact fake media object."""
    return SimpleNamespace(
        title=title,
        type=media_type,
        ratingKey=title,
        librarySectionID=2,
        viewCount=view_count,
        accountID=account_id,
    )


def _client(server: FakeServer, default_user_id: str | None = None) -> PlexExtendedClient:
    """Create a synchronous client with config-entry options."""
    client = object.__new__(PlexExtendedClient)
    client._server = server
    options = {}
    if default_user_id is not None:
        options[const.CONF_DEFAULT_USER_ID] = default_user_id
    client.entry = SimpleNamespace(options=options)
    return client


def _household_servers() -> tuple[FakeServer, FakeServer, FakeServer]:
    """Return owner and two user-scoped fake servers."""
    accounts = [
        SimpleNamespace(id=1, name="Owner"),
        SimpleNamespace(id=7, name="Conor"),
        SimpleNamespace(id=8, name="Guest"),
    ]
    owner = FakeServer("owner", accounts)
    conor = FakeServer("conor")
    guest = FakeServer("guest")
    owner.switched = {"Conor": conor, "Guest": guest}
    return owner, conor, guest


def test_no_default_keeps_existing_owner_context_without_user_lookup() -> None:
    """Updating must not change old behavior when no default user is selected."""
    owner = FakeServer("owner")
    client = _client(owner)

    context = resolve_user_context(client)

    assert context.server is owner
    assert context.user_id is None
    assert owner.switch_calls == []


def test_default_user_switches_once_and_reuses_cached_server() -> None:
    """A configured default should use one cached Plex user connection."""
    owner, conor, _ = _household_servers()
    client = _client(owner, "7")

    first = resolve_user_context(client)
    second = resolve_user_context(client)

    assert first.server is conor
    assert second.server is conor
    assert first.user_id == 7
    assert first.user == "Conor"
    assert owner.switch_calls == ["Conor"]


def test_explicit_user_override_takes_priority_over_default() -> None:
    """An action/tool can deliberately query another household user."""
    owner, _, guest = _household_servers()
    client = _client(owner, "7")

    context = resolve_user_context(client, user_id="8")

    assert context.server is guest
    assert context.user_id == 8
    assert context.user == "Guest"
    assert owner.switch_calls == ["Guest"]


def test_owner_account_uses_existing_server_without_switch() -> None:
    """Plex local account ID 1 is the already-authenticated server owner."""
    owner, _, _ = _household_servers()
    client = _client(owner, "1")

    context = resolve_user_context(client)

    assert context.server is owner
    assert context.user_id == 1
    assert context.user == "Owner"
    assert owner.switch_calls == []


def test_continue_watching_uses_personalized_server_and_reports_user() -> None:
    """Continue Watching must come from the selected user's Plex context."""
    owner, conor, _ = _household_servers()
    conor._continue = [_item("Resident Alien")]
    client = _client(owner, "7")

    result = _browse_for_context(
        client,
        {"limit": 10, "include_summary": False},
        on_deck=False,
    )

    assert [item["title"] for item in result["results"]] == ["Resident Alien"]
    assert result["user_id"] == 7
    assert result["user"] == "Conor"


def test_history_uses_default_user_id_when_no_override_is_supplied() -> None:
    """Recently watched should inherit the configured default user filter."""
    owner, _, _ = _household_servers()
    owner.history = [_item("Pilot", account_id=7)]
    client = _client(owner, "7")

    result = _recently_watched_for_context(
        client,
        {"limit": 1, "media_types": ["episode"], "include_summary": False},
    )

    assert "accountID=7" in owner.fetch_calls[0]["key"]
    assert result["user_id"] == 7
    assert result["user"] == "Conor"


def test_search_watched_state_comes_from_default_user_context() -> None:
    """Fuzzy search must not expose owner watch state when another default is set."""
    owner, conor, _ = _household_servers()
    conor._search = [_item("Alien", media_type="movie", view_count=1)]
    client = _client(owner, "7")

    result = _search_for_context(
        client,
        {
            "query": "Alien",
            "search_types": ["movie"],
            "limit": 10,
            "include_summary": False,
        },
    )

    assert result["results"][0]["watched"] is True
    assert result["user_id"] == 7


def test_recently_added_watch_state_comes_from_default_user_context() -> None:
    """Global recent-add order can still return personalized watch metadata."""
    owner, conor, _ = _household_servers()
    conor.library._recent = [_item("New Film", media_type="movie", view_count=1)]
    client = _client(owner, "7")

    result = _recently_added_for_context(
        client,
        {"limit": 10, "include_summary": False},
    )

    assert result["results"][0]["watched"] is True
    assert result["user"] == "Conor"


def test_media_details_progress_comes_from_default_user_context() -> None:
    """Detailed metadata must agree with search/query watch state for the same user."""
    owner, conor, _ = _household_servers()
    conor._items["Alien"] = _item("Alien", media_type="movie", view_count=1)
    client = _client(owner, "7")

    result = _media_details_for_context(
        client,
        {"rating_key": "Alien", "include_technical": False},
    )

    assert result["result"]["watched"] is True
    assert result["user_id"] == 7
