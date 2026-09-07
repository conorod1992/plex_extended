# Plex Extended

Plex Extended is a Home Assistant custom integration that exposes Plex as a queryable media library rather than only as a media player.

It complements Home Assistant's built-in Plex integration with response-data actions and native Home Assistant LLM tools for title search, structured library discovery, TV viewing progress, recently added media, watch history, Continue Watching, On Deck, metadata, libraries, and users.

## Highlights

- **Connect with Plex** from the Home Assistant config flow; no manual token extraction is normally required.
- Discovers Plex Media Servers linked to the authorized Plex account and lets the user choose a server.
- Supports a manual server URL + token setup as a fallback.
- Uses its own Plex client identity and can coexist with Home Assistant's built-in Plex integration.
- Exposes query results as **response data**, avoiding huge list-like sensor attributes.
- Contributes **native Home Assistant LLM tools** to the built-in Assist LLM API.
- Supports fuzzy title search and typed advanced library filtering.
- Exposes episode-level TV progress, last watched/current episode, and the next episode to watch.
- Supports a configurable **default Plex user** for personalized viewing state, with per-query overrides.
- Supports multiple Plex servers.
- Supports stable Plex library/user IDs as well as convenient names.
- Never returns Plex tokens, tokenized URLs, or local media file paths in action/tool results.
- Provides privacy-safe Home Assistant diagnostics.

## Installation

### During private development

HACS's current repository validator/installer expects public GitHub repository content. While this repository is private, install a development build by copying:

```text
custom_components/plex_extended
```

into:

```text
/config/custom_components/plex_extended
```

and restart Home Assistant.

Then go to **Settings → Devices & services → Add integration → Plex Extended** and choose **Connect with Plex**.

### HACS custom repository

Once the repository is public:

1. Add this repository to HACS as an **Integration** custom repository.
2. Install **Plex Extended**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Plex Extended**.
5. Choose **Connect with Plex**.
6. Authorize the integration on Plex's website and select the desired server if more than one is available.

The integration uses the same `PlexAPI` and `plexauth` dependency versions as the current Home Assistant core Plex integration to reduce dependency conflicts when both are installed.

## Plex user context

Viewing state in Plex is user-specific. Plex Extended can therefore use a selected Plex user's state for watched/unwatched queries, TV progress, Continue Watching, On Deck, and watch history.

Open **Settings → Devices & services → Plex Extended → Configure** to choose a **Default Plex user**. If no default user is selected, Plex Extended keeps its previous behavior and uses the configured server/account context. This makes the feature backwards compatible for existing installations.

The following capabilities use the configured default Plex user:

- `plex_extended.query_library` when evaluating watched, unwatched, in-progress, last-viewed, or other user-specific state
- `plex_extended.watch_status`
- `plex_extended.recently_watched`
- `plex_extended.continue_watching`
- `plex_extended.on_deck`
- the equivalent native LLM tools

Each of those actions/tools also accepts optional `user` and `user_id` values. An explicit value overrides the configured default for that one call. `user_id` is the stable local Plex account ID returned by `plex_extended.list_users`; if both name and ID are supplied they must identify the same user.

For example:

```yaml
action: plex_extended.watch_status
data:
  title: Resident Alien
  user: Conor
response_variable: plex_progress
```

or:

```yaml
action: plex_extended.query_library
data:
  media_type: movie
  watched_state: unwatched
  user_id: "7"
  limit: 10
response_variable: plex_results
```

Plex user switching requires the Plex account/token used to configure Plex Extended to be the server owner/admin. The normal Plex website setup should therefore be completed using the server owner when household-user state is required. If the integration is connected to a shared server as a non-owner, the normal server context can still be used, but Plex Extended cannot switch that connection into another Plex user's context.

User-scoped Plex server connections are cached after the first successful switch so repeated automation or voice queries do not perform a fresh user switch every time.

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

For mixed media types, Plex Extended performs a single Plex hub search and filters the returned media afterwards. This preserves Plex's own cross-category relevance ordering rather than giving whichever media type is listed first priority over the result limit.

Optional fields include `library`, `library_id`, and `config_entry_id`. If only one Plex Extended server is loaded, `config_entry_id` can be omitted.

`library_id` is the stable Plex library section ID returned by `plex_extended.list_libraries`. Names remain convenient, but if two Plex sections share the same name Plex Extended will refuse to silently choose one and will ask for `library_id` instead.

Typical response:

```yaml
success: true
query: Alien
count: 2
results:
  - rating_key: "1234"
    type: movie
    title: Alien
    year: 1979
    library: Movies
    library_id: 1
    duration_ms: 7020000
    watched: true
    genres:
      - Horror
      - Science Fiction
    summary: "..."
```

### `plex_extended.query_library`

Run a structured media query rather than a fuzzy title search. This is intended for discovery, filtering, recommendations, and LLM questions such as "find an unwatched 4K horror movie from the 1980s under two hours".

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

Supported typed criteria include:

- partial title
- genre (match any) and `genres_all` (require all)
- actor, director, collection, content rating, and studio
- exact year, inclusive year range, and decade
- Plex-native `watched`, `unwatched`, and `in_progress` states
- resolution and HDR/SDR
- critic, audience, and user rating ranges
- inclusive minimum/maximum runtime in minutes
- added-date and last-viewed-date before/after filters, including Plex relative values such as `30d`
- sorting by title, year, added date, last viewed date, ratings, runtime, or resolution

Most categorical filters accept either one string or a YAML list. Multiple values within fields such as `genres`, `actors`, or `directors` use Plex's OR semantics; `genres_all` provides Plex's AND semantics for genres.

`media_type` is required and can be `movie`, `show`, `season`, `episode`, `artist`, `album`, or `track`. If neither `library` nor `library_id` is supplied, Plex Extended automatically selects the library only when exactly one compatible library exists. It refuses to guess if, for example, the server contains multiple movie libraries.

When a default Plex user is configured, user-specific filters such as `watched_state` and `last_viewed_*` are evaluated through that user's Plex context. Optional `user`/`user_id` values can override the default for an individual query. The response identifies the effective user when one was selected.

The action deliberately exposes a curated typed interface rather than arbitrary Plex filter/operator dictionaries. This keeps automation validation and native LLM tool calling predictable while still using Plex's own filtering engine.

### `plex_extended.watch_status`

Return episode-level viewing progress for one TV show. Supply either the show's stable Plex `rating_key` or a title. `year`, `library`, and `library_id` can be supplied to disambiguate title lookups.

```yaml
action: plex_extended.watch_status
data:
  title: Resident Alien
  include_specials: false
  include_seasons: true
  include_summary: false
response_variable: plex_progress
```

The response includes:

- overall status (`unwatched`, `in_progress`, `complete`, or `empty`)
- total and fully watched episode counts
- `unwatched_episodes` for episodes that have not been started
- `in_progress_episodes` for started but unfinished episodes
- `remaining_episodes` for all episodes that are not yet fully watched
- completion percentage based on fully watched episodes
- last fully watched episode
- most recent episode activity
- currently in-progress episode, where applicable
- the next episode to watch
- optional per-season progress summaries using the same distinct counts

All episode state and Plex On Deck selection come from the configured default Plex user's context when one is selected. `user` or `user_id` can override the default for one call, and the response identifies the effective user.

Season 0/specials are excluded by default so an unwatched special does not make an otherwise completed series appear unfinished. Set `include_specials: true` to include them in counts and completion.

For the next episode, Plex Extended prefers Plex's own show-level On Deck result. If Plex has no usable On Deck result, it falls back to the first unplayed episode in canonical season/episode order. Specials returned by On Deck are ignored when `include_specials` is false. This also means a partially watched On Deck episode can correctly be returned as the episode to resume.

A title lookup prefers exact case-insensitive matches. If more than one exact show matches, Plex Extended refuses to guess and returns candidate rating keys; an optional `year` can resolve remakes or same-title shows. A known `rating_key` is therefore the preferred stable identifier when chaining from `search` or `query_library`.

### `plex_extended.recently_added`

Returns recently added media. Supports `limit`, `library`, `library_id`, `media_types`, and `include_summary`.

### `plex_extended.recently_watched`

Returns Plex play history sorted newest first. Supports filtering by Plex user name/ID, library name/ID, media type, and result limit.

If neither `user` nor `user_id` is supplied, Plex Extended applies the configured default Plex user when one exists. If no default is configured, history visible to the configured server token is returned, preserving the original behavior. An explicit user overrides the configured default for the individual call.

Filtered history is paged until Plex Extended has filled the requested result count or Plex history is exhausted. For example, asking for 10 movies will not stop early merely because the newest history pages are dominated by TV episodes.

`user_id` is the stable Plex account ID returned by `plex_extended.list_users`. As with libraries, names are supported for convenience but IDs provide exact addressing.

### `plex_extended.continue_watching`

Returns the personalized Plex Continue Watching hub for the configured default Plex user, or the configured server context if no default user exists. Optional `user`/`user_id` values override the default for one call. Results can also be limited by `library` or `library_id`.

### `plex_extended.on_deck`

Returns personalized Plex On Deck items for the configured default Plex user, or the configured server context if no default user exists. Optional `user`/`user_id` values override the default for one call. Results can also be limited by `library` or `library_id`.

### `plex_extended.media_details`

Fetches a single Plex item by the `rating_key` returned by another Plex Extended query.

```yaml
action: plex_extended.media_details
data:
  rating_key: "1234"
  include_technical: true
response_variable: plex_item
```

Technical metadata can include container, bitrate, resolution, video/audio codecs, dimensions, frame rate, and audio channel count. File system paths are deliberately not exposed.

### `plex_extended.list_libraries`

Returns available Plex library names, stable IDs, types, and UUIDs.

### `plex_extended.list_users`

Returns Plex system-account IDs and names for exact per-user viewing-state queries and for choosing the integration's default Plex user.

### `plex_extended.test_connection`

Tests the configured Plex connection and returns basic server identity information.

## Native LLM tools

Home Assistant 2026.8+ automatically discovers `custom_components/plex_extended/llm.py`. When Plex Extended is loaded, it contributes these tools to the built-in **Assist** LLM API:

- `plex_extended__search`
- `plex_extended__query_library`
- `plex_extended__watch_status`
- `plex_extended__recently_added`
- `plex_extended__recently_watched`
- `plex_extended__continue_watching`
- `plex_extended__on_deck`
- `plex_extended__media_details`
- `plex_extended__list_libraries`
- `plex_extended__list_users`

A compatible conversation integration can therefore answer questions such as:

- "Do I have Alien on Plex?"
- "Find an unwatched horror movie from the 1980s around 90 to 120 minutes."
- "What are my highest-rated 4K science-fiction movies?"
- "Which Christopher Nolan films do I have that I haven't watched?"
- "Where am I up to in Resident Alien?"
- "Have I finished Severance?"
- "What's the next episode of The Last of Us I should watch?"
- "What movies were added recently?"
- "What did I watch last night?"
- "Give me my Continue Watching list."
- "Where is Guest up to in that show?"
- "Show me the technical details for that movie."

The LLM prompt distinguishes `search` (title/name lookup), `query_library` (structured filtering and recommendations), and `watch_status` (TV-series progress/next-episode questions).

Viewing-state LLM tools automatically use the Plex user selected in the integration's options. The prompt tells the model not to invent or repeatedly specify a user for ordinary questions; `user`/`user_id` should only be supplied when the request clearly concerns another Plex user.

LLM search/list/query tools omit summaries by default so a broad query does not spend tokens returning many full plot descriptions. `watch_status` also omits the season-by-season breakdown by default for LLM calls because the overall counts and last/current/next episode normally answer the question directly. The action can return the full season breakdown by default.

LLM tool result limits are capped at 25. Regular Home Assistant actions allow up to 50 results and continue to include summaries by default for backwards compatibility.

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

To query another household user's personalized viewing state, the configured Plex account must be the Plex server owner/admin because Plex only allows the owner/admin connection to switch into another user context.

## Design

Plex Extended keeps the Home Assistant action and native LLM layers as thin interfaces over shared query implementations:

```text
Plex Media Server
       │
       ▼
PlexExtendedClient + per-user context + typed query/progress backends
       │
       ├── Home Assistant response-data actions
       │
       └── Home Assistant native LLM tools
```

This prevents the behavior of the action and LLM interfaces from drifting apart. User-scoped server contexts are resolved in one shared layer so watched state, TV progress, personalized hubs, and history use the same selection rules.

## Relationship to Home Assistant's Plex integration

Plex Extended does **not** override or monkey-patch Home Assistant's built-in `plex` integration.

The intended split is:

- **Home Assistant Plex:** media players, playback, server/client activity, and existing Plex media-source behavior.
- **Plex Extended:** querying the library, metadata, recent additions, per-user viewing state/history/progress, and LLM/automation access.

Both integrations can be configured against the same Plex account/server at the same time.

## v1 scope

Version `0.1.0` focuses on read/query functionality. It deliberately does not yet add playback control, destructive library operations, watch-state mutation, or Tautulli-specific analytics.

## Development and validation

The repository validation workflow runs Python compilation, focused unit tests, and Home Assistant `hassfest` on every push and pull request. HACS validation is automatically enabled when the repository is public; the current HACS action cannot fetch private-repository manifests through its raw-content validation path.
