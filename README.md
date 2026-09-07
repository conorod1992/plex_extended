# Plex Extended

Plex Extended is a Home Assistant custom integration that exposes Plex as a queryable media library rather than only as a media player.

It complements Home Assistant's built-in Plex integration with response-data actions and native Home Assistant LLM tools for library search, recently added media, watch history, Continue Watching, On Deck, metadata, libraries, and users.

## Highlights

- **Connect with Plex** from the Home Assistant config flow; no manual token extraction is normally required.
- Discovers Plex Media Servers linked to the authorized Plex account and lets the user choose a server.
- Supports a manual server URL + token setup as a fallback.
- Uses its own Plex client identity and can coexist with Home Assistant's built-in Plex integration.
- Exposes query results as **response data**, avoiding huge list-like sensor attributes.
- Contributes **native Home Assistant LLM tools** to the built-in Assist LLM API.
- Supports multiple Plex servers.
- Never returns Plex tokens, tokenized URLs, or local media file paths in action/tool results.

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

## Actions

All Plex Extended actions return response data and can therefore be used with `response_variable` in scripts and automations.

### `plex_extended.search`

Search the user's Plex library. Plex's hub search provides partial/fuzzy matching.

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

Optional fields include `library` and `config_entry_id`. If only one Plex Extended server is loaded, `config_entry_id` can be omitted.

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
    duration_ms: 7020000
    watched: true
    genres:
      - Horror
      - Science Fiction
    summary: "..."
```

### `plex_extended.recently_added`

Returns recently added media. Supports `limit`, `library`, `media_types`, and `include_summary`.

### `plex_extended.recently_watched`

Returns Plex play history sorted newest first. Supports filtering by Plex user name, library, media type, and result limit. When no user is specified, history visible to the configured server token is returned.

### `plex_extended.continue_watching`

Returns the Plex Continue Watching hub, optionally limited to a library.

### `plex_extended.on_deck`

Returns Plex On Deck items, optionally limited to a library.

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

Returns available Plex library names, IDs, types, and UUIDs.

### `plex_extended.list_users`

Returns Plex system-account IDs and names for watch-history filtering.

### `plex_extended.test_connection`

Tests the configured Plex connection and returns basic server identity information.

## Native LLM tools

Home Assistant 2026.8+ automatically discovers `custom_components/plex_extended/llm.py`. When Plex Extended is loaded, it contributes these tools to the built-in **Assist** LLM API:

- `plex_extended__search`
- `plex_extended__recently_added`
- `plex_extended__recently_watched`
- `plex_extended__continue_watching`
- `plex_extended__on_deck`
- `plex_extended__media_details`
- `plex_extended__list_libraries`
- `plex_extended__list_users`

A compatible conversation integration can therefore answer questions such as:

- "Do I have Alien on Plex?"
- "What movies were added recently?"
- "What did I watch last night?"
- "What episode am I up to?"
- "Give me my Continue Watching list."
- "Show me the technical details for that movie."

LLM tool result limits are capped at 25 to keep tool responses reasonably token-efficient. Regular Home Assistant actions allow up to 50 results.

## Authentication

The normal setup flow uses Plex's website authorization process through `plexauth`:

1. Home Assistant creates a Plex authorization request for Plex Extended.
2. The browser is sent to Plex.
3. The user signs in/approves on Plex's site.
4. Plex Extended discovers the account's Plex Media Server resources.
5. The integration connects to the selected server using that server resource's access token.

Plex Extended never receives or stores the user's Plex password. If Plex later rejects the configured token, Plex Extended starts a Home Assistant reauthentication flow.

## Design

The integration has one underlying query implementation in `client.py`:

```text
Plex Media Server
       │
       ▼
PlexExtendedClient
       │
       ├── Home Assistant response-data actions
       │
       └── Home Assistant native LLM tools
```

The action and LLM layers are intentionally thin wrappers over the same client methods, preventing the behavior of the two interfaces from drifting apart.

## Relationship to Home Assistant's Plex integration

Plex Extended does **not** override or monkey-patch Home Assistant's built-in `plex` integration.

The intended split is:

- **Home Assistant Plex:** media players, playback, server/client activity, and existing Plex media-source behavior.
- **Plex Extended:** querying the library, metadata, recent additions, viewing state/history, and LLM/automation access.

Both integrations can be configured against the same Plex account/server at the same time.

## v1 scope

Version `0.1.0` focuses on read/query functionality. It deliberately does not yet add playback control, destructive library operations, watch-state mutation, or Tautulli-specific analytics.

## Development and validation

The repository validation workflow runs Python compilation and Home Assistant `hassfest` on every push and pull request. HACS validation is automatically enabled when the repository is public; the current HACS action cannot fetch private-repository manifests through its raw-content validation path.
