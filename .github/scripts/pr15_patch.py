from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1))


# Constants and public service names.
const = COMPONENT / "const.py"
replace(
    const,
    'CONF_ALLOW_LLM_WATCHLIST_MUTATIONS: Final = "allow_llm_watchlist_mutations"\n',
    'CONF_ALLOW_LLM_WATCHLIST_MUTATIONS: Final = "allow_llm_watchlist_mutations"\n'
    'CONF_ALLOW_LLM_PLAYLIST_MUTATIONS: Final = "allow_llm_playlist_mutations"\n',
)
replace(
    const,
    'SERVICE_PLAYLIST_ITEMS: Final = "playlist_items"\n',
    'SERVICE_PLAYLIST_ITEMS: Final = "playlist_items"\n'
    'SERVICE_CREATE_PLAYLIST: Final = "create_playlist"\n'
    'SERVICE_ADD_TO_PLAYLIST: Final = "add_to_playlist"\n'
    'SERVICE_REMOVE_FROM_PLAYLIST: Final = "remove_from_playlist"\n',
)

# Register the thin Home Assistant adapter.
init = COMPONENT / "__init__.py"
replace(
    init,
    'from .library_summary_service import async_setup_library_summary_service\n',
    'from .library_summary_service import async_setup_library_summary_service\n'
    'from .playlist_mutations_service import async_setup_playlist_mutation_services\n',
)
replace(
    init,
    '    await async_setup_discover_watchlist_services(hass)\n',
    '    await async_setup_discover_watchlist_services(hass)\n'
    '    await async_setup_playlist_mutation_services(hass)\n',
)

# Options flow: a distinct default-off permission for Assist playlist writes.
flow = COMPONENT / "config_flow.py"
replace(
    flow,
    '    CONF_ALLOW_LLM_WATCHLIST_MUTATIONS,\n',
    '    CONF_ALLOW_LLM_WATCHLIST_MUTATIONS,\n'
    '    CONF_ALLOW_LLM_PLAYLIST_MUTATIONS,\n',
)
replace(
    flow,
    '            allow_llm_watchlist_mutations = bool(\n'
    '                user_input.get(CONF_ALLOW_LLM_WATCHLIST_MUTATIONS, False)\n'
    '            )\n',
    '            allow_llm_watchlist_mutations = bool(\n'
    '                user_input.get(CONF_ALLOW_LLM_WATCHLIST_MUTATIONS, False)\n'
    '            )\n'
    '            allow_llm_playlist_mutations = bool(\n'
    '                user_input.get(CONF_ALLOW_LLM_PLAYLIST_MUTATIONS, False)\n'
    '            )\n',
)
replace(
    flow,
    '                options[CONF_ALLOW_LLM_WATCHLIST_MUTATIONS] = (\n'
    '                    allow_llm_watchlist_mutations\n'
    '                )\n',
    '                options[CONF_ALLOW_LLM_WATCHLIST_MUTATIONS] = (\n'
    '                    allow_llm_watchlist_mutations\n'
    '                )\n'
    '                options[CONF_ALLOW_LLM_PLAYLIST_MUTATIONS] = (\n'
    '                    allow_llm_playlist_mutations\n'
    '                )\n',
)
replace(
    flow,
    '            allow_llm_watchlist_mutations = bool(\n'
    '                self.config_entry.options.get(\n'
    '                    CONF_ALLOW_LLM_WATCHLIST_MUTATIONS, False\n'
    '                )\n'
    '            )\n',
    '            allow_llm_watchlist_mutations = bool(\n'
    '                self.config_entry.options.get(\n'
    '                    CONF_ALLOW_LLM_WATCHLIST_MUTATIONS, False\n'
    '                )\n'
    '            )\n'
    '            allow_llm_playlist_mutations = bool(\n'
    '                self.config_entry.options.get(\n'
    '                    CONF_ALLOW_LLM_PLAYLIST_MUTATIONS, False\n'
    '                )\n'
    '            )\n',
)
replace(
    flow,
    '                    vol.Required(\n'
    '                        CONF_ALLOW_LLM_WATCHLIST_MUTATIONS,\n'
    '                        default=allow_llm_watchlist_mutations,\n'
    '                    ): cv.boolean,\n',
    '                    vol.Required(\n'
    '                        CONF_ALLOW_LLM_WATCHLIST_MUTATIONS,\n'
    '                        default=allow_llm_watchlist_mutations,\n'
    '                    ): cv.boolean,\n'
    '                    vol.Required(\n'
    '                        CONF_ALLOW_LLM_PLAYLIST_MUTATIONS,\n'
    '                        default=allow_llm_playlist_mutations,\n'
    '                    ): cv.boolean,\n',
)

# Native Assist provider and narrow permission subset.
llm = COMPONENT / "llm.py"
replace(
    llm,
    '    CONF_ALLOW_LLM_MUTATIONS,\n    CONF_ALLOW_LLM_WATCHLIST_MUTATIONS,\n',
    '    CONF_ALLOW_LLM_MUTATIONS,\n'
    '    CONF_ALLOW_LLM_PLAYLIST_MUTATIONS,\n'
    '    CONF_ALLOW_LLM_WATCHLIST_MUTATIONS,\n',
)
replace(
    llm,
    'from .llm_policy import enabled_llm_clients\n',
    'from .llm_policy import enabled_llm_clients\n'
    'from .playlist_mutations_llm import (\n'
    '    AddToPlaylistPlexTool,\n'
    '    CreatePlaylistPlexTool,\n'
    '    RemoveFromPlaylistPlexTool,\n'
    ')\n',
)
replace(
    llm,
    '_LIBRARY_SUMMARY_PROMPT = (\n',
    '_PLAYLIST_MUTATION_PROMPT = (\n'
    '    " create_playlist, add_to_playlist, and remove_from_playlist change regular Plex "\n'
    '    "playlists for the selected/default Plex user. Use them only for an explicit user "\n'
    '    "request. Resolve exact local media rating_key values with read tools, and resolve "\n'
    '    "an existing playlist_rating_key with list_playlists before add/remove. Never invent "\n'
    '    "identifiers. Smart and radio playlists are read-only for these tools."\n'
    ')\n'
    '_LIBRARY_SUMMARY_PROMPT = (\n',
)
replace(
    llm,
    '    watchlist_mutation_clients = {\n'
    '        label: client\n'
    '        for label, client in clients.items()\n'
    '        if bool(\n'
    '            client.entry.options.get(CONF_ALLOW_LLM_WATCHLIST_MUTATIONS, False)\n'
    '        )\n'
    '    }\n',
    '    watchlist_mutation_clients = {\n'
    '        label: client\n'
    '        for label, client in clients.items()\n'
    '        if bool(\n'
    '            client.entry.options.get(CONF_ALLOW_LLM_WATCHLIST_MUTATIONS, False)\n'
    '        )\n'
    '    }\n'
    '    playlist_mutation_clients = {\n'
    '        label: client\n'
    '        for label, client in clients.items()\n'
    '        if bool(\n'
    '            client.entry.options.get(CONF_ALLOW_LLM_PLAYLIST_MUTATIONS, False)\n'
    '        )\n'
    '    }\n',
)
needle = '''    if watchlist_mutation_clients:
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

'''
replacement = needle + '''    if playlist_mutation_clients:
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

'''
replace(llm, needle, replacement)
replace(
    llm,
    '        f"{_WATCHLIST_MUTATION_PROMPT if watchlist_mutation_clients else \'\'}"\n',
    '        f"{_WATCHLIST_MUTATION_PROMPT if watchlist_mutation_clients else \'\'}"\n'
    '        f"{_PLAYLIST_MUTATION_PROMPT if playlist_mutation_clients else \'\'}"\n',
)

# Diagnostics advertise the capability and non-sensitive permission state.
diag = COMPONENT / "diagnostics.py"
replace(
    diag,
    '    CONF_ALLOW_LLM_MUTATIONS,\n    CONF_ALLOW_LLM_WATCHLIST_MUTATIONS,\n',
    '    CONF_ALLOW_LLM_MUTATIONS,\n'
    '    CONF_ALLOW_LLM_PLAYLIST_MUTATIONS,\n'
    '    CONF_ALLOW_LLM_WATCHLIST_MUTATIONS,\n',
)
replace(
    diag,
    '    "playlist_items",\n',
    '    "playlist_items",\n'
    '    "create_playlist",\n'
    '    "add_to_playlist",\n'
    '    "remove_from_playlist",\n',
)
replace(
    diag,
    '            "assist_watchlist_mutations_enabled": bool(\n'
    '                entry.options.get(CONF_ALLOW_LLM_WATCHLIST_MUTATIONS, False)\n'
    '            ),\n',
    '            "assist_watchlist_mutations_enabled": bool(\n'
    '                entry.options.get(CONF_ALLOW_LLM_WATCHLIST_MUTATIONS, False)\n'
    '            ),\n'
    '            "assist_playlist_mutations_enabled": bool(\n'
    '                entry.options.get(CONF_ALLOW_LLM_PLAYLIST_MUTATIONS, False)\n'
    '            ),\n',
)

# Options strings / English translation.
for name in ("strings.json", "translations/en.json"):
    path = COMPONENT / name
    data = json.loads(path.read_text())
    init_step = data["options"]["step"]["init"]
    init_step["description"] = (
        "Choose the default Plex user and whether this server contributes native Plex "
        "Extended tools to Assist. Watch-state, playlist, and account Watchlist writes "
        "are separate opt-ins."
    )
    init_step["data"]["allow_llm_playlist_mutations"] = (
        "Allow Assist to change Plex playlists"
    )
    init_step["data_description"]["allow_llm_playlist_mutations"] = (
        "When native Assist tools are enabled, this exposes create/add/remove regular "
        "playlist tools for the selected/default Plex user. It is disabled by default, "
        "uses exact Plex rating keys, and does not permit smart or radio playlist edits."
    )
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

# Developer Tools metadata for the three write actions.
services_yaml = COMPONENT / "services.yaml"
text = services_yaml.read_text()
marker = "\n\ndiscover_search:\n"
if marker not in text:
    raise RuntimeError("services.yaml playlist insertion marker not found")
metadata = r'''

create_playlist:
  name: Create playlist
  description: Create a regular Plex playlist for the selected/default Plex user from exact local media rating keys. Smart playlists are not created by this action.
  fields:
    config_entry_id:
      name: Plex server
      selector:
        config_entry:
          integration: plex_extended
    title:
      name: Playlist title
      description: New playlist title. If an exact-title playlist already exists with different contents, the action fails instead of creating a duplicate.
      required: true
      selector:
        text:
    rating_keys:
      name: Media rating keys
      description: Exact local media rating keys returned by Plex Extended. YAML can supply a list of up to 50 values; audio, video and photo media cannot be mixed.
      required: true
      selector:
        text:
    user:
      name: Plex user
      description: Optional Plex user name. Overrides the configured default Plex user for this playlist.
      selector:
        text:
    user_id:
      name: Plex user ID
      description: Optional stable Plex account ID. Overrides the configured default Plex user for this playlist.
      selector:
        text:

add_to_playlist:
  name: Add to playlist
  description: Idempotently add exact local media items to one regular Plex playlist. Existing items are not duplicated.
  fields:
    config_entry_id:
      name: Plex server
      selector:
        config_entry:
          integration: plex_extended
    playlist_rating_key:
      name: Playlist rating key
      description: Exact stable playlist rating key returned by List playlists. Title-only mutation is deliberately unsupported.
      required: true
      selector:
        text:
    rating_keys:
      name: Media rating keys
      description: Exact local media rating keys to add. YAML can supply a list of up to 50 values.
      required: true
      selector:
        text:
    user:
      name: Plex user
      description: Optional Plex user name. Overrides the configured default Plex user.
      selector:
        text:
    user_id:
      name: Plex user ID
      description: Optional stable Plex account ID. Overrides the configured default Plex user.
      selector:
        text:

remove_from_playlist:
  name: Remove from playlist
  description: Idempotently remove exact local media from one regular Plex playlist. All occurrences of each requested item are removed; already-absent items are harmless.
  fields:
    config_entry_id:
      name: Plex server
      selector:
        config_entry:
          integration: plex_extended
    playlist_rating_key:
      name: Playlist rating key
      description: Exact stable playlist rating key returned by List playlists. Title-only mutation is deliberately unsupported.
      required: true
      selector:
        text:
    rating_keys:
      name: Media rating keys
      description: Exact local media rating keys to remove. YAML can supply a list of up to 50 values.
      required: true
      selector:
        text:
    user:
      name: Plex user
      description: Optional Plex user name. Overrides the configured default Plex user.
      selector:
        text:
    user_id:
      name: Plex user ID
      description: Optional stable Plex account ID. Overrides the configured default Plex user.
      selector:
        text:
'''
services_yaml.write_text(text.replace(marker, metadata + marker, 1))

# README: document retry/identity semantics and native tools.
readme = ROOT / "README.md"
text = readme.read_text()
marker = "\n### `plex_extended.discover_search`\n"
if marker not in text:
    raise RuntimeError("README playlist insertion marker not found")
section = r'''

### `plex_extended.create_playlist` / `plex_extended.add_to_playlist` / `plex_extended.remove_from_playlist`

These actions make controlled changes to **regular** Plex playlists for the selected/default Plex user. Smart and radio playlists remain read-only.

Existing-playlist changes require the exact `playlist_rating_key` returned by `list_playlists`; title-only mutation is deliberately unsupported. Media targets are exact local `rating_key` values returned by Plex Extended read actions. A single action accepts up to 50 media keys.

`create_playlist` requires at least one media item because Plex regular playlists are created from concrete media. Audio, video and photo items cannot be mixed. If an exact-title playlist already exists, an identical item sequence is treated as an idempotent retry; different contents fail rather than silently creating another same-name playlist.

`add_to_playlist` skips requested items already present, so retries do not create duplicate entries. `remove_from_playlist` removes **all occurrences** of each requested media item and treats already-absent items as success. Every actual write is re-read and verified before Plex Extended reports success.

Manual Home Assistant playlist-write actions are always available. Native Assist playlist-write tools are separately opt-in under **Configure → Allow Assist to change Plex playlists** and default off.
'''
text = text.replace(marker, section + marker, 1)
text = text.replace(
    '- `plex_extended__playlist_items`\n',
    '- `plex_extended__playlist_items`\n'
    '- `plex_extended__create_playlist` *(only when Assist playlist writes are enabled)*\n'
    '- `plex_extended__add_to_playlist` *(only when Assist playlist writes are enabled)*\n'
    '- `plex_extended__remove_from_playlist` *(only when Assist playlist writes are enabled)*\n',
    1,
)
text = text.replace(
    '- "What\'s in my Christmas playlist?"\n',
    '- "What\'s in my Christmas playlist?"\n'
    '- "Create a Weekend Movies playlist with these three films."\n'
    '- "Add that movie to my Weekend Movies playlist."\n',
    1,
)
text = text.replace(
    'The LLM guidance distinguishes local fuzzy search, Plex Discover search, structured item queries, aggregate library summaries, TV progress, recent-media windows, collections/playlists, and account-level Watchlist. It prefers stable rating keys when moving from collection/playlist listing to item retrieval and understands that Watchlist is not affected by the configured household-user default.\n',
    'The LLM guidance distinguishes local fuzzy search, Plex Discover search, structured item queries, aggregate library summaries, TV progress, recent-media windows, collections/playlists, and account-level Watchlist. It prefers stable rating keys when moving from collection/playlist listing to item retrieval or mutation, and understands that regular playlists use the selected/default household-user context while Watchlist is account-level.\n',
    1,
)
text = text.replace(
    'Watch-state mutation tools and account-Watchlist mutation tools are **not exposed to Assist by default**. They use separate opt-ins. When explicitly enabled in the integration options, the model is instructed to use them only for an explicit user request, resolve an exact local `rating_key` with a read tool first, and never invent an identifier. In multi-server setups, write tools expose only the server entries on which this option is enabled.\n',
    'Watch-state, regular-playlist, and account-Watchlist mutation tools are **not exposed to Assist by default**. They use separate opt-ins. When explicitly enabled, the model is instructed to act only on an explicit user request and to resolve exact Plex identifiers with read tools first rather than inventing them. Playlist add/remove additionally require the exact playlist `rating_key` from `list_playlists`. In multi-server setups, each write-tool family exposes only the server entries on which its own option is enabled.\n',
    1,
)
readme.write_text(text)

# Static contracts for the public surfaces / permissions.
(ROOT / "tests" / "test_playlist_mutations_contract.py").write_text(r'''"""Contract checks for safe playlist mutation exposure."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def test_manual_playlist_mutations_are_optional_response_actions() -> None:
    adapter = (COMPONENT / "playlist_mutations_service.py").read_text()
    setup = (COMPONENT / "__init__.py").read_text()
    for name in ("SERVICE_CREATE_PLAYLIST", "SERVICE_ADD_TO_PLAYLIST", "SERVICE_REMOVE_FROM_PLAYLIST"):
        assert name in adapter
    assert "supports_response=SupportsResponse.OPTIONAL" in adapter
    assert "async_setup_playlist_mutation_services" in setup


def test_existing_playlist_writes_require_exact_playlist_id() -> None:
    backend = (COMPONENT / "playlist_mutations.py").read_text()
    adapter = (COMPONENT / "playlist_mutations_service.py").read_text()
    tool = (COMPONENT / "playlist_mutations_llm.py").read_text()
    assert 'vol.Required("playlist_rating_key")' in adapter
    assert 'vol.Required("playlist_rating_key")' in tool
    assert "_playlist_by_rating_key" in backend
    assert 'criteria.get("title")' not in backend.split("def _add_to_playlist", 1)[1]
    assert 'criteria.get("title")' not in backend.split("def _remove_from_playlist", 1)[1]


def test_playlist_assist_writes_have_separate_default_off_permission() -> None:
    const = (COMPONENT / "const.py").read_text()
    flow = (COMPONENT / "config_flow.py").read_text()
    provider = (COMPONENT / "llm.py").read_text()
    strings = (COMPONENT / "strings.json").read_text()
    assert 'CONF_ALLOW_LLM_PLAYLIST_MUTATIONS: Final = "allow_llm_playlist_mutations"' in const
    assert "CONF_ALLOW_LLM_PLAYLIST_MUTATIONS, False" in flow
    assert "playlist_mutation_clients" in provider
    assert "CONF_ALLOW_LLM_PLAYLIST_MUTATIONS, False" in provider
    assert '"allow_llm_playlist_mutations": "Allow Assist to change Plex playlists"' in strings


def test_docs_diagnostics_and_metadata_expose_all_three_mutations() -> None:
    yaml = (COMPONENT / "services.yaml").read_text()
    diagnostics = (COMPONENT / "diagnostics.py").read_text()
    readme = (ROOT / "README.md").read_text()
    for name in ("create_playlist", "add_to_playlist", "remove_from_playlist"):
        assert f"\n{name}:\n" in yaml
        assert f'"{name}"' in diagnostics
        assert f"plex_extended.{name}" in readme
        assert f"plex_extended__{name}" in readme
    assert '"assist_playlist_mutations_enabled"' in diagnostics


def test_playlist_mutation_backend_has_no_title_fallback_for_existing_writes() -> None:
    backend = (COMPONENT / "playlist_mutations.py").read_text()
    assert "server.createPlaylist" in backend
    assert "playlist.addItems" in backend
    assert "playlist.removeItems" in backend
    assert "Smart Plex playlists cannot be edited item-by-item" in backend
    assert "Plex radio playlists cannot be edited item-by-item" in backend


def test_temporary_pr15_helpers_are_not_retained() -> None:
    assert not (ROOT / ".github" / "scripts" / "pr15_patch.py").exists()
    assert not (ROOT / ".github" / "workflows" / "pr15-wire.yml").exists()
''')
