# Plex Extended native Assist tool reference

Plex Extended exposes native tools through Home Assistant's built-in Assist LLM API when **Enable native Assist tools** is enabled for a Plex Extended config entry.

The main [README](../README.md) explains setup and permissions. The [action reference](action-reference.md) documents the shared backend behavior and Home Assistant actions in detail.

## Native Assist tool exposure

Read tools are available when native Assist tools are enabled for the server:

- `plex_extended__search`
- `plex_extended__discover_search`
- `plex_extended__query_library`
- `plex_extended__library_summary`
- `plex_extended__watch_status`
- `plex_extended__tv_catch_up`
- `plex_extended__related_media`
- `plex_extended__recently_added`
- `plex_extended__recently_watched`
- `plex_extended__continue_watching`
- `plex_extended__on_deck`
- `plex_extended__media_details`
- `plex_extended__active_streams`
- `plex_extended__list_collections`
- `plex_extended__collection_items`
- `plex_extended__list_playlists`
- `plex_extended__playlist_items`
- `plex_extended__watchlist`
- `plex_extended__list_libraries`
- `plex_extended__list_users`

Write tools are exposed only when their separate permission is enabled:

### Watch-state writes

Requires **Allow Assist to change Plex watch state**:

- `plex_extended__mark_watched`
- `plex_extended__mark_unwatched`

### Plex Watchlist writes

Requires **Allow Assist to change Plex Watchlist**:

- `plex_extended__add_to_watchlist`
- `plex_extended__remove_from_watchlist`

### Regular playlist writes

Requires **Allow Assist to change Plex playlists**:

- `plex_extended__create_playlist`
- `plex_extended__add_to_playlist`
- `plex_extended__remove_from_playlist`

All three write-permission families default to off. Manual Home Assistant actions are not controlled by these Assist-specific permissions.

## Multi-server behavior

Plex Extended constructs native tool schemas from the config entries that have **Enable native Assist tools** enabled.

- If one eligible server exists, tools can target it without an extra server selector.
- If several eligible servers exist, the tool schema includes a server selector.
- A disabled Plex Extended entry is omitted from the selector rather than accepted and rejected later at runtime.
- Each write-tool family only includes servers where that specific write permission is enabled.

## Tool-selection guidance

Plex Extended provides the model with guidance to distinguish common query types:

- local fuzzy title lookup → `plex_extended__search`
- Plex-wide online title lookup → `plex_extended__discover_search`
- structured local filtering → `plex_extended__query_library`
- counts/facets → `plex_extended__library_summary`
- one-show progress → `plex_extended__watch_status`
- cross-show episode backlog → `plex_extended__tv_catch_up`
- Plex-native related local titles → `plex_extended__related_media`
- current playback/transcoding → `plex_extended__active_streams`

The model is instructed to resolve exact Plex identifiers with read tools before a write and not to invent rating keys, playlist IDs, library IDs, user IDs, or Discover GUIDs.

## Response size and safety

LLM list/query tools use tighter default/result bounds than manual Home Assistant actions to keep responses token-efficient. Broad query tools omit summaries by default where appropriate.

Potentially mutating tools remain bounded and use the same backend verification rules as their manual Home Assistant equivalents.