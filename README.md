# Plex Extended

Plex Extended is a Home Assistant custom integration that exposes Plex as a queryable media library rather than only as a media player.

It complements Home Assistant's built-in Plex integration with response-data actions and native Home Assistant LLM tools for title search, Plex Discover search, structured library discovery, aggregate library summaries, TV viewing progress, recent media, watch history, collections, playlists, Plex Watchlist, Continue Watching, On Deck, active playback sessions, metadata, libraries, and users.

## Highlights

- **Connect with Plex** from the Home Assistant config flow; no manual token extraction is normally required.
- Discovers Plex Media Servers linked to the authorized Plex account and lets the user choose a server.
- Supports a manual server URL + token setup as a fallback.
- Uses its own Plex client identity and can coexist with Home Assistant's built-in Plex integration.
- Exposes query results as **response data**, avoiding huge list-like sensor attributes.
- Contributes **native Home Assistant LLM tools** to the built-in Assist LLM API, with per-server exposure control.
- Supports fuzzy title search and typed advanced library filtering.
- Supports exact aggregate counts and facet breakdowns without returning large item lists.
- Exposes episode-level TV progress, last watched/current episode, and the next episode to watch.
- Exposes current Plex playback sessions, including player/progress and direct-play/direct-stream/transcode details.
- Supports bounded recent-media queries and optional TV show/season grouping for large imports.
- Exposes Plex collections and playlists, including their items.
- Exposes the configured Plex account's plex.tv Watchlist, Plex Discover search, and safe exact-GUID Watchlist add/remove actions.
- Supports a configurable **default Plex user** for personalized viewing state, with per-query overrides.
- Supports multiple Plex servers.
- Supports stable Plex library/user/collection/playlist rating keys as well as convenient names.
- Provides explicit watched/unwatched update actions; Assist write tools are opt-in and disabled by default.
- Never returns Plex tokens, tokenized URLs, or local media file paths in action/tool results.
- Provides privacy-safe Home Assistant diagnostics.

## Installation

### HACS custom repository

1. Add `https://github.com/conorod1992/plex_extended` to HACS as an **Integration** custom repository.
2. Install **Plex Extended**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Plex Extended**.
5. Choose **Connect with Plex**.
6. Authorize the integration on Plex's website and select the desired server if more than one is available.

For development or manual installation, copy `custom_components/plex_extended` into `/config/custom_components/plex_extended` and restart Home Assistant.

The integration uses the same `PlexAPI` and `plexauth` dependency versions as the current Home Assistant core Plex integration to reduce dependency conflicts when both are installed.

## Plex user context

Viewing state in Plex is user-specific. Plex Extended can therefore use a selected Plex user's state consistently wherever returned data depends on viewing state, including watched/unwatched filtering, search/detail metadata, recently added metadata, TV progress, Continue Watching, On Deck, collections/playlists, watch history, and explicit watch-state updates.

Open **Settings → Devices & services → Plex Extended → Configure** to choose a **Default Plex user**. If no default user is selected, Plex Extended uses the configured server/account context.

The following capabilities use the configured default Plex user:

- `plex_extended.search` for returned watched/progress metadata
- `plex_extended.query_library`, including watched, unwatched, in-progress and last-viewed state
- `plex_extended.watch_status`
- `plex_extended.recently_added` for returned watched/progress metadata
- `plex_extended.recently_watched`
- `plex_extended.continue_watching`
- `plex_extended.on_deck`
- `plex_extended.media_details` for returned watched/progress metadata
- `plex_extended.mark_watched` / `plex_extended.mark_unwatched` for explicit viewing-state changes
- `plex_extended.list_collections` / `plex_extended.collection_items`
- `plex_extended.list_playlists` / `plex_extended.playlist_items`
- the equivalent native LLM tools

Each of those actions/tools accepts optional `user` and `user_id` values. An explicit value overrides the configured default for that call. `user_id` is the stable local Plex account ID returned by `plex_extended.list_users`; if both name and ID are supplied they must identify the same user.

```yaml
action: plex_extended.watch_status
data:
  title: Resident Alien
  user: Conor
response_variable: plex_progress
```

Plex user switching requires the Plex account/token used to configure Plex Extended to be the server owner/admin. If the integration is connected to a shared server as a non-owner, the normal server context can still be used, but Plex Extended cannot switch that connection into another Plex user's context.

The Configure screen represents the currently authenticated Plex account as **Configured Plex account** and lists alternate household users separately. User-scoped Plex server connections are cached after the first successful switch.

### Native Assist tool exposure

Open **Settings → Devices & services → Plex Extended → Configure** to control whether a server contributes native Plex Extended tools to Home Assistant Assist. **Enable native Assist tools** is on by default for backwards compatibility. Turning it off removes that server from all Plex Extended native LLM tools while leaving every manual Home Assistant action available.

In a multi-server setup, disabled entries are omitted entirely from the LLM tools' server selector. If every Plex Extended entry disables native Assist tools, Plex Extended contributes no LLM tools. The separate **Allow Assist to change Plex watch state** option still defaults off; it has an effect only while native Assist tools are enabled for that server.

### Plex Watchlist is different

Plex's Watchlist is associated with the authenticated **plex.tv account**, not the selected local household-user context. `plex_extended.watchlist` therefore always uses the Plex account that configured that Plex Extended server entry. The Default Plex user setting and per-call `user`/`user_id` selectors deliberately do not apply to Watchlist.

## Actions

All Plex Extended actions return response data and can therefore be used with `response_variable` in scripts and automations.

### `plex_extended.search`

Search the user's Plex library by title/name. Plex's hub search provides partial/fuzzy matching and contextual relevance ordering.

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

For mixed media types, Plex Extended performs a single Plex hub search and filters the returned media afterwards, preserving Plex's cross-category relevance ordering. Optional fields include `library`, `library_id`, `user`, `user_id`, and `config_entry_id`.

### `plex_extended.query_library`

Run a structured media query rather than a fuzzy title search. This is intended for discovery, filtering, recommendations, and questions such as "find an unwatched 4K horror movie from the 1980s under two hours".

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

Supported typed criteria include partial title; genre; actor/director/collection/studio/content rating; audio/subtitle language; labels and country; duplicate/matched state; exact year/range/decade; watched/unwatched/in-progress; resolution/HDR; video/audio codec, container and audio-channel count; critic/audience/user rating ranges; runtime; added/last-viewed dates; and sorting.

Audio/subtitle language, label, country, duplicate and unmatched criteria use Plex's native server filters. Codec/container/channel criteria use PlexAPI's documented XML post-filtering after the server-native candidate set, so very broad technical queries can require Plex to return more metadata than a purely server-native query.

`media_type` can be `movie`, `show`, `season`, `episode`, `artist`, `album`, or `track`. If no library is supplied, Plex Extended automatically selects one only when exactly one compatible library exists. The action deliberately exposes a curated typed interface rather than arbitrary Plex filter dictionaries.


### `plex_extended.library_summary`

Returns an exact aggregate count using the same structured filters as `query_library`, without returning a list of matching media. This is the preferred action for questions such as “how many unwatched horror movies do I have?” or “which decades are most represented in my movie library?”.

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

Supported facets are `genre`, `year`, `decade`, `resolution`, `watched_state`, `content_rating`, `studio`, `collection`, `label`, `country`, `audio_language`, `subtitle_language`, `video_codec`, `audio_codec`, `container`, and `audio_channels`. Facets are ordered by descending count and carry `total_values` plus `truncated`, so a limited “top values” response cannot be mistaken for the complete distribution. Multi-valued facets such as genre, collection, and resolution count one item once in each distinct value it belongs to, so those facet counts can legitimately sum above the overall media count.

Count-only requests that use Plex-native filters read Plex's filtered `totalSize` directly instead of downloading all matching media. Requests for facets, total duration, or criteria that require PlexAPI-side post-filtering materialize the exact matching set. Tag/technical facets hydrate metadata in bounded rating-key batches rather than triggering one reload per item.

When `include_total_duration` is enabled, the response includes `total_duration_minutes`, `duration_items`, and `duration_missing_items`; missing duration metadata is therefore explicit rather than silently treated as zero.
### `plex_extended.watch_status`

Return episode-level viewing progress for one TV show using either its stable Plex `rating_key` or a title.

```yaml
action: plex_extended.watch_status
data:
  title: Resident Alien
  include_specials: false
  include_seasons: true
  include_summary: false
response_variable: plex_progress
```

The response includes overall completion state, episode counts, completion percentage, last watched/current activity, the in-progress episode, next episode, and optionally per-season progress. Season 0/specials are excluded by default. Plex Extended prefers Plex's own On Deck result for the next episode and falls back to canonical episode order when necessary.


### `plex_extended.tv_catch_up`

Returns TV episodes the selected/default Plex user still has to watch, grouped by show. It is intended for cross-show questions such as “what new episodes do I have to catch up on?”; use `watch_status` instead for detailed progress in one specific show.

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

The optional `since`, `before`, and `within_days` fields use the same added-time semantics as `recently_added`: `since` is inclusive, `before` is exclusive, and date-only/timezone-less values use Home Assistant's configured timezone. With no time window the action returns a bounded newest-first catch-up queue rather than imposing an arbitrary hidden date cutoff.

Plex Extended asks PMS for unwatched candidates and, when enabled, in-progress candidates separately, then deduplicates and re-checks viewing state client-side. Season 0/specials are excluded by default. Results distinguish never-started from partially watched episodes, group them by stable show identity, return episodes in canonical season/episode order, and report independent show/episode-detail truncation. Candidate scans are capped at 1,000 episodes per Plex state query per TV library; `candidate_scan_truncated` is explicit if that safety bound is reached.


### `plex_extended.related_media`

Returns Plex's own related/recommendation hubs for one exact local movie or TV show. Plex's hub categories are preserved rather than flattened into a Plex Extended scoring algorithm, so the response can retain distinctions such as related titles or recommendations connected through people/metadata.

```yaml
action: plex_extended.related_media
data:
  rating_key: "1234"
  hub_limit: 6
  item_limit: 5
  include_summary: false
response_variable: plex_related
```

`rating_key` must be the exact positive numeric local ID returned by a Plex Extended read action such as `search` or `query_library`. Movies and TV shows are supported. Optional `library` / `library_id` fields assert the seed item's library rather than performing a fuzzy lookup.

The query runs in the selected/default Plex household-user context, so viewing-state metadata on returned local items follows the same user semantics as other Plex Extended library reads. Provider/online objects from Plex's related endpoint are excluded: a recommendation must expose both a local `rating_key` and `librarySectionID` to be returned.

Plex Extended uses the related items already included in Plex's hub response and deliberately does not auto-expand hubs that report `more`. Each hub reports `more_available_from_plex` and `results_truncated`, while the top-level response independently reports hub truncation. Items are deduplicated within a hub but may appear in multiple different hubs because that cross-hub repetition preserves Plex's explanation for why the title is related.

### `plex_extended.recently_added`

Returns recently added media with optional exact time windows and TV episode grouping.

```yaml
action: plex_extended.recently_added
data:
  within_days: 7
  group_tv_by: show
  limit: 10
response_variable: plex_recent
```

Use either `within_days` or `since` / `before`. `since` is inclusive and `before` is exclusive. Date-only and timezone-less values use Home Assistant's configured timezone. `group_tv_by` can be `none`, `show`, or `season`; grouping prevents one newly imported TV season from consuming the full response with individual episodes.

### `plex_extended.recently_watched`

Returns Plex play history sorted newest first, with user/library/media-type filters and the same `since`, `before`, and `within_days` controls.

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

History paging continues until the requested filtered result count is filled, the requested time window is exhausted, or Plex history is exhausted.

### `plex_extended.continue_watching`

Returns the personalized Plex Continue Watching hub for the configured default Plex user, or the configured server context if no default user exists. Optional `user`/`user_id` values override the default for one call.

### `plex_extended.on_deck`

Returns personalized Plex On Deck items for the configured default Plex user, or the configured server context if no default user exists.

### `plex_extended.media_details`

Fetches a single Plex item by a `rating_key` returned by another Plex Extended query.

```yaml
action: plex_extended.media_details
data:
  rating_key: "1234"
  include_technical: true
response_variable: plex_item
```

Technical metadata can include container, bitrate, resolution, codecs, dimensions, frame rate, and audio channels. Local filesystem paths are deliberately not exposed.


### `plex_extended.active_streams`

Returns current Plex playback sessions without controlling the player. Results can include the Plex user, media and progress, player/product/platform, local/remote/relay/security state, selected source quality, session bandwidth/location, and delivery details.

```yaml
action: plex_extended.active_streams
data:
  locality: remote
  states:
    - playing
response_variable: plex_streams
```

Delivery is classified as `direct_play`, `direct_stream`, `transcode`, or `unknown`. A Plex transcode-session wrapper whose media components are copied rather than transcoded is reported as `direct_stream`, not as a true transcode. Client IP/public addresses, device machine identifiers, Plex tokens, session IDs, and local media file paths are deliberately not returned.

Filters are available for exact Plex username, media type, playback state, local/remote location, and result limit. This action is read-only; it does not pause, stop, or otherwise control playback.

### `plex_extended.mark_watched` / `plex_extended.mark_unwatched`

Explicitly change one local Plex item's viewing state for the selected/default Plex user. These are side-effecting actions and therefore require an exact local `rating_key`; they deliberately do not accept a title lookup.

```yaml
action: plex_extended.mark_watched
data:
  rating_key: "1234"
response_variable: plex_update
```

Plex Extended refetches the item after the write and returns an error if Plex does not confirm the requested state. The response includes the previous and current watched state plus the effective Plex user. For shows and seasons, Plex applies the state to child episodes as well; the response reports `scope: item_and_children` so that cascade is explicit.

The manual Home Assistant actions are always available. Native Assist write tools are a separate opt-in controlled by **Settings → Devices & services → Plex Extended → Configure → Allow Assist to change Plex watch state**.
### `plex_extended.list_collections`

Lists collections visible in the selected/default Plex user context and returns stable collection rating keys. Optional filters include library, collection media type, and partial title.

```yaml
action: plex_extended.list_collections
data:
  media_type: movie
  title: Bond
  limit: 20
response_variable: plex_collections
```

### `plex_extended.collection_items`

Returns media inside one Plex collection. Prefer a stable collection `rating_key` returned by `list_collections`; an exact title can be used when it is unambiguous.

```yaml
action: plex_extended.collection_items
data:
  rating_key: "2468"
  limit: 50
response_variable: plex_collection
```

Collection title ambiguity is never resolved by guessing; use `rating_key` or `library_id` when multiple collections share a title.

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

Returns items in one playlist using a stable playlist rating key or an unambiguous exact title.

```yaml
action: plex_extended.playlist_items
data:
  title: Christmas
  limit: 50
response_variable: plex_playlist
```


### `plex_extended.create_playlist` / `plex_extended.add_to_playlist` / `plex_extended.remove_from_playlist`

These actions make controlled changes to **regular** Plex playlists for the selected/default Plex user. Smart and radio playlists remain read-only.

Existing-playlist changes require the exact `playlist_rating_key` returned by `list_playlists`; title-only mutation is deliberately unsupported. Media targets are exact local `rating_key` values returned by Plex Extended read actions. A single action accepts up to 50 media keys.

`create_playlist` requires at least one media item because Plex regular playlists are created from concrete media. Audio, video and photo items cannot be mixed. If an exact-title playlist already exists, an identical item sequence is treated as an idempotent retry; different contents fail rather than silently creating another same-name playlist.

`add_to_playlist` skips requested items already present, so retries do not create duplicate entries. `remove_from_playlist` removes **all occurrences** of each requested media item and treats already-absent items as success. Every actual write is re-read and verified before Plex Extended reports success.

Manual Home Assistant playlist-write actions are always available. Native Assist playlist-write tools are separately opt-in under **Configure → Allow Assist to change Plex playlists** and default off.

### `plex_extended.discover_search`

Searches Plex Discover rather than only the configured local library, so it can resolve movies/shows that are not on the server. Results carry the exact Plex Discover `guid` used by the safe Watchlist mutation actions.

```yaml
action: plex_extended.discover_search
data:
  query: 28 Years Later
  media_type: movie
  limit: 10
response_variable: plex_discover
```

`match_local` is disabled by default because local matching can require a GUID lookup for every Discover result. Enable it when you specifically need to know whether each online title is already present on this server.

### `plex_extended.watchlist`

Returns the configured Plex account's plex.tv Watchlist. By default Plex Extended also attempts to match each movie/show to the configured local server using Plex's stable GUID.

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

Each result includes online Watchlist metadata plus `on_server` when local matching is enabled. If exactly one local item matches, the response also supplies its local `rating_key`, library name, and library ID. Multiple local matches are returned explicitly rather than silently choosing one.

Supported Watchlist filters are `all`, `available`, and `released`. Sorting supports Watchlist-added time, title, release date, or critic rating. Because this is a plex.tv account-level feature, the integration's Default Plex user does **not** apply.

### `plex_extended.add_to_watchlist` / `plex_extended.remove_from_watchlist`

Explicitly change the configured plex.tv account's Watchlist. Both actions require the exact Discover `guid` plus the corresponding title returned by `discover_search`/Watchlist data. The title is used only to re-fetch candidates; the mutation proceeds only when Plex returns the **exact GUID**, so a stale or wrong GUID never falls back to a title match.

The actions are idempotent and verify Watchlist state after any write. They are account-level operations: the integration's Default Plex user does not apply.

Manual Home Assistant actions are always available. Native Assist Watchlist-write tools are separately opt-in under **Configure → Allow Assist to change Plex Watchlist** and default off.

### `plex_extended.list_libraries`

Returns available Plex library names, stable IDs, types, and UUIDs.

### `plex_extended.list_users`

Returns Plex system-account IDs and names for exact per-user viewing-state queries and for choosing the integration's default Plex user.

### `plex_extended.test_connection`

Tests the configured Plex connection and returns basic server identity information.

## Native LLM tools

Home Assistant 2026.8+ automatically discovers `custom_components/plex_extended/llm.py`. Plex Extended contributes these tools to the built-in **Assist** LLM API:

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
- `plex_extended__mark_watched` *(only when Assist write access is enabled)*
- `plex_extended__mark_unwatched` *(only when Assist write access is enabled)*
- `plex_extended__list_collections`
- `plex_extended__collection_items`
- `plex_extended__list_playlists`
- `plex_extended__playlist_items`
- `plex_extended__create_playlist` *(only when Assist playlist writes are enabled)*
- `plex_extended__add_to_playlist` *(only when Assist playlist writes are enabled)*
- `plex_extended__remove_from_playlist` *(only when Assist playlist writes are enabled)*
- `plex_extended__watchlist`
- `plex_extended__add_to_watchlist` *(only when Assist Watchlist writes are enabled)*
- `plex_extended__remove_from_watchlist` *(only when Assist Watchlist writes are enabled)*
- `plex_extended__list_libraries`
- `plex_extended__list_users`

A compatible conversation integration can therefore answer questions such as:

- "Do I have Alien on Plex?"
- "Find 28 Years Later on Plex Discover and add it to my Watchlist."
- "Find an unwatched horror movie from the 1980s around 90 to 120 minutes."
- "How many unwatched horror movies do I have?"
- "Which decades have the most movies in my library?"
- "Where am I up to in Resident Alien?"
- "What new TV episodes do I have to catch up on?"
- "What do I have on Plex that is similar to Alien?"
- "What was added to Plex in the last week?"
- "Which TV shows got new episodes this week?"
- "What did I watch between Monday and Friday?"
- "What's in my James Bond collection?"
- "What's in my Christmas playlist?"
- "Create a Weekend Movies playlist with these three films."
- "Add that movie to my Weekend Movies playlist."
- "Which things on my Plex Watchlist are already on my server?"
- "Give me my Continue Watching list."
- "Who is using Plex right now?"
- "Is anything currently transcoding?"
- "Where is Guest up to in that show?"
- "Mark that episode as watched."

The LLM guidance distinguishes local fuzzy search, Plex Discover search, structured item queries, aggregate library summaries, single-show TV progress, cross-show TV catch-up, Plex-native related-media recommendations, recent-media windows, collections/playlists, and account-level Watchlist. It prefers stable rating keys when moving from collection/playlist listing to item retrieval or mutation, and understands that regular playlists use the selected/default household-user context while Watchlist is account-level.

Watch-state, regular-playlist, and account-Watchlist mutation tools are **not exposed to Assist by default**. They use separate opt-ins. When explicitly enabled, the model is instructed to act only on an explicit user request and to resolve exact Plex identifiers with read tools first rather than inventing them. Playlist add/remove additionally require the exact playlist `rating_key` from `list_playlists`. In multi-server setups, each write-tool family exposes only the server entries on which its own option is enabled.

LLM search/list/query tools omit summaries by default to keep broad results token-efficient. LLM result limits are capped at 25; regular Home Assistant actions allow up to 50 and continue to include summaries by default for backwards compatibility.

## Diagnostics

Home Assistant can download diagnostics from the Plex Extended config-entry menu. Diagnostics include useful support information such as Plex server version/platform, connection scheme, enabled capabilities, and library section IDs/types.

Plex tokens, server URL/host, Plex client identifier, server machine identifier, server name, library names, and library UUIDs are deliberately redacted or omitted.

## Authentication

The normal setup flow uses Plex's website authorization process through `plexauth`:

1. Home Assistant creates a Plex authorization request for Plex Extended.
2. The browser is sent to Plex.
3. The user signs in/approves on Plex's site.
4. Plex Extended discovers the account's Plex Media Server resources.
5. The integration connects to the selected server using that server resource's access token.

After authorization, the external browser window/tab is asked to close automatically and the original Home Assistant config flow continues. If the browser blocks automatic closing, the fallback page provides a Return to Home Assistant button.

Plex Extended never receives or stores the user's Plex password. If Plex later rejects the configured token, Plex Extended starts a Home Assistant reauthentication flow.

## Design

Plex Extended keeps the Home Assistant action and native LLM layers as thin interfaces over shared backends:

```text
Plex Media Server / plex.tv
          │
          ▼
PlexExtendedClient + user context + query/summary/progress/recent/list backends
          │
          ├── Home Assistant response-data actions
          │
          └── Home Assistant native LLM tools
```

This prevents action and LLM behavior from drifting apart. User-scoped server contexts are resolved in one shared layer, while account-scoped plex.tv Watchlist behavior is kept explicitly separate.

## Relationship to Home Assistant's Plex integration

Plex Extended does **not** override or monkey-patch Home Assistant's built-in `plex` integration.

- **Home Assistant Plex:** media players, playback, server/client activity, and existing Plex media-source behavior.
- **Plex Extended:** querying and aggregating the library, metadata, recent additions, collections/playlists/Watchlist, active playback sessions, per-user viewing state/history/progress, controlled watch-state updates, and LLM/automation access.

Both integrations can be configured against the same Plex account/server at the same time.

## v1 scope

Version `0.1.0` focuses on query functionality plus narrowly scoped, explicit watched/unwatched updates. It deliberately does not add playback control, broader destructive library operations, or Tautulli-specific analytics.

## Development and validation

The repository validation workflow runs Python compilation, focused unit tests, Home Assistant `hassfest`, and HACS validation on pushes and pull requests.
