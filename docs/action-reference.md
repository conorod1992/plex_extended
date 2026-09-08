# Plex Extended action reference

This page is the detailed reference for Plex Extended's Home Assistant actions.

If you are installing Plex Extended for the first time, start with the [main README](../README.md). It explains installation, first use, Plex user context, Assist permissions, and the main concepts used below.

## How action responses work

Read/query actions return response data. In **Developer Tools → Actions**, Home Assistant displays the response after you run the action. In a script or automation, save that response with `response_variable`:

```yaml
action: plex_extended.search
data:
  query: Alien
response_variable: plex_results
```

Write actions can also return confirmation data when a response is requested. Manual Home Assistant write actions remain available even if Assist write permissions are disabled.

If more than one Plex Extended server is configured, use the action UI's server selector or provide `config_entry_id` so the target server is unambiguous.

## Quick chooser

| Goal | Action |
| --- | --- |
| Find a title in your local Plex library | `plex_extended.search` |
| Search/filter the local library by metadata | `plex_extended.query_library` |
| Count or summarize matching media | `plex_extended.library_summary` |
| See where a user is up to in one show | `plex_extended.watch_status` |
| See unwatched/in-progress episodes across shows | `plex_extended.tv_catch_up` |
| Find Plex-native related local media | `plex_extended.related_media` |
| See recently added media | `plex_extended.recently_added` |
| See viewing history | `plex_extended.recently_watched` |
| Get Continue Watching / On Deck | `plex_extended.continue_watching` / `plex_extended.on_deck` |
| Inspect one exact Plex item | `plex_extended.media_details` |
| See current playback sessions | `plex_extended.active_streams` |
| Mark an exact item watched/unwatched | `plex_extended.mark_watched` / `plex_extended.mark_unwatched` |
| Browse collections | `plex_extended.list_collections` / `plex_extended.collection_items` |
| Browse playlists | `plex_extended.list_playlists` / `plex_extended.playlist_items` |
| Create or change a regular playlist | `plex_extended.create_playlist`, `add_to_playlist`, `remove_from_playlist` |
| Search Plex Discover | `plex_extended.discover_search` |
| Read the configured account's Plex Watchlist | `plex_extended.watchlist` |
| Add/remove a Plex Watchlist item | `plex_extended.add_to_watchlist` / `remove_from_watchlist` |
| List Plex libraries or users | `plex_extended.list_libraries` / `plex_extended.list_users` |
| Check the configured connection | `plex_extended.test_connection` |

## Search and library discovery

### `plex_extended.search`

Fuzzy/partial title search across the local Plex library. Plex Extended preserves Plex's cross-category relevance ordering when several media types are searched together.

```yaml
action: plex_extended.search
data:
  query: Alien
  search_types:
    - movie
    - show
  limit: 10
  include_summary: true
  include_technical: false
response_variable: plex_results
```

Useful optional selectors include `library`, `library_id`, `user`, `user_id`, and `config_entry_id`.

Use this when you know roughly what a title is called. Use `query_library` when you want structured filters instead.

### `plex_extended.query_library`

Structured local-library querying for discovery questions such as “find an unwatched 4K horror movie from the 1980s under two hours”.

```yaml
action: plex_extended.query_library
data:
  media_type: movie
  genres:
    - Horror
  year_min: 1980
  year_max: 1989
  watched_state: unwatched
  duration_min_minutes: 90
  duration_max_minutes: 120
  resolutions:
    - 4k
  hdr: hdr
  audience_rating_min: 7
  sort_by: audience_rating
  sort_order: desc
  limit: 10
response_variable: plex_results
```

Supported criteria include:

- partial title;
- genre, actor, director, collection, studio and content rating;
- audio/subtitle language, label and country;
- duplicate/unmatched state;
- exact year, ranges and decade;
- watched, unwatched and in-progress state;
- resolution and HDR;
- video/audio codec, container and audio-channel count;
- critic, audience and user rating ranges;
- runtime;
- added and last-viewed dates;
- sorting.

`media_type` can be `movie`, `show`, `season`, `episode`, `artist`, `album`, or `track`.

Language/label/country/duplicate/unmatched criteria use Plex server-side filtering. Codec/container/channel filters use PlexAPI-side XML filtering after the server-native candidate query, so very broad technical filters can require more metadata transfer.

If no library is supplied, Plex Extended auto-selects a library only when exactly one compatible library exists. It intentionally exposes a curated typed schema instead of arbitrary raw Plex filter dictionaries.

### `plex_extended.library_summary`

Counts and aggregates media matching the same structured filters as `query_library`, without returning a large item list.

```yaml
action: plex_extended.library_summary
data:
  media_type: movie
  genres:
    - Horror
  watched_state: unwatched
  facets:
    - decade
    - resolution
  facet_limit: 10
  include_total_duration: true
response_variable: plex_summary
```

Supported facets are:

- `genre`
- `year`
- `decade`
- `resolution`
- `watched_state`
- `content_rating`
- `studio`
- `collection`
- `label`
- `country`
- `audio_language`
- `subtitle_language`
- `video_codec`
- `audio_codec`
- `container`
- `audio_channels`

Facet responses report truncation explicitly. Multi-valued facets can legitimately sum to more than the overall media count because one item can belong to several values.

Count-only requests using Plex-native filters use Plex's filtered `totalSize` directly. Facets, total duration, and PlexAPI-side technical filters materialize the exact matching set. When total duration is requested, missing duration metadata is reported separately rather than silently counted as zero.

### `plex_extended.related_media`

Returns Plex's own related/recommendation hubs for one exact local movie or TV show.

```yaml
action: plex_extended.related_media
data:
  rating_key: "1234"
  hub_limit: 6
  item_limit: 5
  include_summary: false
response_variable: plex_related
```

`rating_key` must be the exact positive numeric local ID returned by another Plex Extended read action. Optional `library` / `library_id` values assert the seed item's library; they do not fuzzily resolve it.

Plex Extended preserves Plex's hub categories/order rather than inventing a global recommendation score. Provider/online objects are excluded; returned recommendations must correspond to concrete local Plex media.

Plex Extended deliberately does not auto-expand hubs that Plex says contain more results. Each hub reports `more_available_from_plex` and `results_truncated`, while the top-level response reports `hubs_truncated` independently. Items are deduplicated within a hub but may legitimately appear in several different hubs because that preserves Plex's explanation for why an item is related.

## TV progress and recency

### `plex_extended.watch_status`

Returns episode-level progress for one TV show.

```yaml
action: plex_extended.watch_status
data:
  title: Resident Alien
  include_specials: false
  include_seasons: true
  include_summary: false
response_variable: plex_progress
```

You can target a show by title or stable Plex `rating_key`. The response includes episode counts, completion percentage, recent/current activity, in-progress episode, next episode, and optionally per-season detail.

Season 0/specials are excluded by default. Plex Extended prefers Plex's own On Deck result for the next episode and falls back to canonical episode order where needed.

### `plex_extended.tv_catch_up`

Returns remaining TV episodes across shows for the selected/default Plex user.

```yaml
action: plex_extended.tv_catch_up
data:
  within_days: 14
  include_specials: false
  include_in_progress: true
  limit: 10
  episode_limit: 5
response_variable: plex_catch_up
```

Use this for cross-show backlog questions. Use `watch_status` for detailed progress in one specific show.

Optional `since`, `before`, and `within_days` fields use added-time semantics: `since` is inclusive, `before` is exclusive, and date-only/timezone-less values use Home Assistant's configured timezone. `within_days` cannot be combined with `since`/`before`.

Season 0/specials are excluded by default. Results distinguish never-started and partially watched episodes and report show/result truncation independently. Candidate scans are bounded and report `candidate_scan_truncated` when the safety bound is reached.

### `plex_extended.recently_added`

Returns recently added local media.

```yaml
action: plex_extended.recently_added
data:
  within_days: 7
  group_tv_by: show
  limit: 10
response_variable: plex_recent
```

Use either `within_days` or `since`/`before`. `group_tv_by` can be `none`, `show`, or `season`; grouping prevents a newly imported TV season from filling the response with individual episodes.

### `plex_extended.recently_watched`

Returns Plex viewing history newest-first.

```yaml
action: plex_extended.recently_watched
data:
  since: "2026-09-01"
  before: "2026-09-08"
  media_types:
    - movie
  limit: 20
response_variable: plex_history
```

Supports user, library, media-type and time-window filtering. History paging continues until the requested filtered result count is filled, the requested time window is exhausted, or Plex history is exhausted.

### `plex_extended.continue_watching`

Returns the personalized Plex Continue Watching hub for the selected/default Plex user.

### `plex_extended.on_deck`

Returns personalized Plex On Deck media for the selected/default Plex user.

## Item details and playback sessions

### `plex_extended.media_details`

Fetches one exact Plex item by a `rating_key` returned by another Plex Extended action.

```yaml
action: plex_extended.media_details
data:
  rating_key: "1234"
  include_technical: true
response_variable: plex_item
```

Technical metadata can include container, bitrate, resolution, codecs, dimensions, frame rate and audio channels. Local media filesystem paths are intentionally not returned.

### `plex_extended.active_streams`

Returns current Plex playback sessions without controlling playback.

```yaml
action: plex_extended.active_streams
data:
  locality: remote
  states:
    - playing
response_variable: plex_streams
```

Results can include Plex user, media/progress, player/product/platform, local/remote/relay/security state, source quality, session bandwidth/location and delivery classification.

Delivery is classified as `direct_play`, `direct_stream`, `transcode`, or `unknown`. Client IP/public addresses, device machine identifiers, Plex tokens, session IDs and local file paths are intentionally excluded.

Filters are available for Plex username, media type, playback state, local/remote location and result limit.

## Viewing-state writes

### `plex_extended.mark_watched` / `plex_extended.mark_unwatched`

Explicitly updates the viewing state of one exact local Plex item for the selected/default Plex user.

```yaml
action: plex_extended.mark_watched
data:
  rating_key: "1234"
response_variable: plex_update
```

These actions require an exact local `rating_key`; title-only mutation is deliberately unsupported. Plex Extended re-fetches the item after the write and fails if Plex does not confirm the requested state.

For shows and seasons, Plex may apply the state to child episodes. Plex Extended reports that broader scope explicitly.

Manual Home Assistant watch-state actions are always available. Native Assist watch-state tools require the separate **Allow Assist to change Plex watch state** option.

## Collections and playlists

### `plex_extended.list_collections`

Lists collections in the selected/default Plex user context and returns stable collection rating keys.

```yaml
action: plex_extended.list_collections
data:
  media_type: movie
  title: Bond
  limit: 20
response_variable: plex_collections
```

### `plex_extended.collection_items`

Returns media inside one collection. Prefer a stable collection `rating_key` returned by `list_collections`; an exact title can be used when unambiguous.

```yaml
action: plex_extended.collection_items
data:
  rating_key: "2468"
  limit: 50
response_variable: plex_collection
```

If multiple collections share a title, Plex Extended does not guess. Use `rating_key` or a library selector.

### `plex_extended.list_playlists`

Lists playlists visible to the selected/default Plex user. `playlist_type` can be `video`, `audio`, or `photo`.

```yaml
action: plex_extended.list_playlists
data:
  playlist_type: video
  limit: 20
response_variable: plex_playlists
```

### `plex_extended.playlist_items`

Returns items in one playlist by stable playlist rating key or unambiguous exact title.

```yaml
action: plex_extended.playlist_items
data:
  title: Christmas
  limit: 50
response_variable: plex_playlist
```

### `plex_extended.create_playlist`

Creates a regular Plex playlist for the selected/default Plex user from one or more exact local media rating keys.

Important safety behavior:

- a regular playlist cannot be created empty;
- audio, video and photo media cannot be mixed;
- smart/radio playlists are not created by this action;
- exact-title existing playlists are handled conservatively;
- an identical existing item sequence is treated as an idempotent retry;
- a same-title playlist with different contents causes an error rather than silently creating another duplicate-name playlist;
- the final playlist state is re-read and verified.

### `plex_extended.add_to_playlist`

Adds exact media rating keys to an existing regular playlist identified by exact `playlist_rating_key`.

Items already present are skipped, so retries are idempotent. Smart/radio playlists are rejected and the final state is verified.

### `plex_extended.remove_from_playlist`

Removes exact media rating keys from an existing regular playlist identified by exact `playlist_rating_key`.

All occurrences of each requested item are removed. Already-absent items are harmless, progress is bounded/verified, and Plex Extended fails rather than looping if Plex reports success without actually changing state.

A manual playlist mutation accepts up to 50 media IDs. Native Assist playlist-write tools require the separate **Allow Assist to change Plex playlists** option and use a lower per-call bound.

## Plex Discover and Watchlist

### `plex_extended.discover_search`

Searches Plex Discover, including titles not present on the configured local server.

```yaml
action: plex_extended.discover_search
data:
  query: 28 Years Later
  media_type: movie
  limit: 10
response_variable: plex_discover
```

Results include the exact Plex Discover `guid` used by safe Watchlist mutations. `match_local` is disabled by default because local matching can require one local GUID lookup per Discover result.

### `plex_extended.watchlist`

Returns the configured plex.tv account's Watchlist.

```yaml
action: plex_extended.watchlist
data:
  media_type: movie
  filter: released
  sort_by: watchlisted_at
  sort_order: desc
  match_local: true
  limit: 25
response_variable: plex_watchlist
```

Supported Watchlist filters are `all`, `available`, and `released`. Sorting supports Watchlist-added time, title, release date and critic rating.

When local matching is enabled, results report whether the title is present on the configured Plex server and can include its local rating key/library identity.

Watchlist is a **plex.tv account-level** feature. The integration's Default Plex user and per-call household-user selectors do not apply.

### `plex_extended.add_to_watchlist` / `plex_extended.remove_from_watchlist`

Changes the configured plex.tv account's Watchlist.

Both actions require the exact Discover `guid` and corresponding title returned by Plex Extended. The title is used only to re-query Discover; Plex Extended requires an exact GUID match before changing state, so a stale/wrong GUID does not silently fall back to a title match.

Writes are idempotent and the final Watchlist state is verified.

Manual Home Assistant Watchlist mutations are always available. Native Assist Watchlist-write tools require **Allow Assist to change Plex Watchlist**.

## Server and identity helpers

### `plex_extended.list_libraries`

Returns available Plex library names, stable IDs, types and UUIDs.

Use a stable `library_id` when library names are duplicated or when you want an automation to remain unambiguous.

### `plex_extended.list_users`

Returns Plex system-account IDs and names. Use these IDs for exact user-scoped queries and when choosing the integration's Default Plex user.

### `plex_extended.test_connection`

Tests the configured Plex server connection and returns basic server identity information.

## Plex user context

Viewing state is user-specific. Actions that depend on watched/progress/history state use the configured **Default Plex user** unless a call provides `user` or `user_id`.

`user_id` is the stable Plex account ID returned by `list_users`. If both name and ID are supplied, they must identify the same user.

Plex user switching requires the Plex account/token used to configure Plex Extended to be the server owner/admin. A non-owner connection to a shared server can use its normal server context but cannot switch into another household user's context.

Collections and regular playlists use the selected/default household-user context. Plex Watchlist is intentionally different because it belongs to the authenticated plex.tv account.

## Privacy and identifiers

Plex Extended uses exact IDs for potentially destructive or ambiguous operations rather than guessing from titles.

Important identifiers include:

- local media `rating_key` — exact item identity on the Plex Media Server;
- collection `rating_key` — exact collection identity;
- `playlist_rating_key` — exact regular-playlist identity;
- `library_id` — stable library section identity;
- `user_id` — stable Plex system-account identity;
- Discover `guid` — exact plex.tv movie/show identity for Watchlist operations.

Plex Extended does not return Plex tokens, tokenized URLs, local media filesystem paths, playback session IDs, or client IP/public addresses in normal action/tool output.