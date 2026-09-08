# Plex Extended

Plex Extended is a Home Assistant custom integration for **querying, understanding, and safely changing selected parts of Plex**.

Home Assistant's built-in Plex integration is excellent for media players and playback. Plex Extended complements it with response-data actions and native Assist/LLM tools for questions and automations such as:

- “Do I have *Alien* on Plex?”
- “Find an unwatched horror film from the 1980s under two hours.”
- “Where am I up to in *Resident Alien*?”
- “What new TV episodes do I have to catch up on?”
- “What was added this week?”
- “Who is streaming Plex right now, and is anything transcoding?”
- “How many 4K movies do I have?”
- “What's in my Christmas playlist?”
- “Find *28 Years Later* on Plex Discover and add it to my Watchlist.”

It does **not** replace or modify Home Assistant's built-in Plex integration. Both can be installed against the same Plex server.

> **Home Assistant:** Plex Extended is tested against Home Assistant 2026.8+.

## What Plex Extended can do

### Search and understand your local library

- fuzzy title search;
- structured filtering by genre, year, runtime, ratings, watched state, resolution/HDR, codecs, audio/subtitle languages, labels and more;
- exact counts and facet summaries without returning huge item lists;
- Plex-native related/similar local media;
- item metadata and technical details.

### Understand viewing state

- episode-level progress for a TV show;
- next episode and in-progress episode;
- cross-show TV catch-up lists;
- Continue Watching and On Deck;
- recently watched history;
- recently added media;
- per-user watched/progress context.

### Browse Plex organization features

- libraries and users;
- collections and collection items;
- playlists and playlist items;
- configured plex.tv account Watchlist;
- Plex Discover search, including media not on the local server.

### Make narrowly scoped changes

Manual Home Assistant actions can:

- mark an exact Plex item watched or unwatched;
- add/remove exact Plex Discover items from the configured account's Watchlist;
- create and safely modify regular Plex playlists.

Potentially mutating **Assist** tools are separately opt-in and disabled by default.

### Inspect current playback

- active sessions;
- Plex user and media progress;
- local/remote/relay state;
- direct play, direct stream or transcode classification;
- source quality and session bandwidth metadata.

Plex Extended does not provide playback control.

## Installation

### HACS

Plex Extended is currently installed as a HACS custom repository:

1. Open **HACS** in Home Assistant.
2. Add `https://github.com/conorod1992/plex_extended` as a custom repository of type **Integration**.
3. Install **Plex Extended**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration → Plex Extended**.
6. Choose **Connect with Plex**.
7. Approve the authorization request on Plex's website.
8. If your account can access more than one Plex Media Server, choose the server you want to add.

You normally **do not need to find or paste a Plex token manually**.

### Manual installation

Copy:

```text
custom_components/plex_extended
```

to:

```text
/config/custom_components/plex_extended
```

and restart Home Assistant. Then add **Plex Extended** from **Settings → Devices & services**.

A manual Plex server URL + token setup option is also available as a fallback when the normal Plex website authorization flow cannot be used.

## Your first five minutes

After setup, the quickest way to confirm everything is working is **Developer Tools → Actions**.

### 1. Test the connection

Run:

```yaml
action: plex_extended.test_connection
```

### 2. Search your library

Run:

```yaml
action: plex_extended.search
data:
  query: Alien
```

Home Assistant displays the returned response data directly in Developer Tools.

### 3. Try a useful viewing-state query

```yaml
action: plex_extended.watch_status
data:
  title: Resident Alien
```

### 4. Use the result in an automation or script

Read/query actions return structured response data. In scripts and automations, capture it with `response_variable`:

```yaml
action: plex_extended.search
data:
  query: Alien
response_variable: plex_results
```

You can then use `plex_results` later in the script or automation.

You do **not** need to create Plex sensors containing enormous lists of media. Returning data only when an action is called is one of Plex Extended's main design goals.

## Which action should I use?

| What you want | Action |
| --- | --- |
| Find something by title in your local library | `plex_extended.search` |
| Filter/discover local media by metadata | `plex_extended.query_library` |
| Count or summarize matching media | `plex_extended.library_summary` |
| See progress in one TV show | `plex_extended.watch_status` |
| Find unwatched/new episodes across shows | `plex_extended.tv_catch_up` |
| Find similar/related local media | `plex_extended.related_media` |
| See recent additions | `plex_extended.recently_added` |
| See viewing history | `plex_extended.recently_watched` |
| Get Continue Watching / On Deck | `plex_extended.continue_watching` / `plex_extended.on_deck` |
| Inspect one exact item | `plex_extended.media_details` |
| See active streams/transcodes | `plex_extended.active_streams` |
| Browse collections | `plex_extended.list_collections` / `plex_extended.collection_items` |
| Browse playlists | `plex_extended.list_playlists` / `plex_extended.playlist_items` |
| Create/change a regular playlist | `plex_extended.create_playlist`, `add_to_playlist`, `remove_from_playlist` |
| Search titles outside your local server | `plex_extended.discover_search` |
| View your plex.tv Watchlist | `plex_extended.watchlist` |
| Add/remove an exact Watchlist item | `plex_extended.add_to_watchlist` / `remove_from_watchlist` |
| Mark one exact local item watched/unwatched | `plex_extended.mark_watched` / `mark_unwatched` |
| List Plex libraries/users | `plex_extended.list_libraries` / `list_users` |
| Check connectivity | `plex_extended.test_connection` |

See the **[complete action reference](docs/action-reference.md)** for fields, examples, filtering semantics, IDs, truncation behavior, and mutation safety rules.

## Important concepts

### Local Plex search vs Plex Discover

These solve different problems:

- `plex_extended.search` searches media on **your configured Plex Media Server**.
- `plex_extended.discover_search` searches **Plex Discover**, so results can include titles you do not own locally.

Use Discover when you need a plex.tv identity, especially before changing the Plex Watchlist.

### Stable IDs vs titles

Plex Extended deliberately becomes stricter when an operation could be ambiguous or change data.

Read actions often let you start with a convenient title. Write actions generally require exact IDs returned by Plex Extended first.

Common identifiers are:

- local media `rating_key` — exact media item on your Plex server;
- collection `rating_key` — exact collection;
- `playlist_rating_key` — exact regular playlist;
- `library_id` — stable Plex library section;
- `user_id` — stable Plex system account;
- Discover `guid` — exact plex.tv movie/show identity used for Watchlist writes.

This prevents an automation or LLM from changing the wrong item because two things happen to share a name.

### Response data

Plex Extended is primarily an **action-based integration**, not a sensor integration.

Read actions return structured data only when called. This keeps large library/search results out of Home Assistant state attributes and makes the same backend useful to:

- Developer Tools;
- scripts;
- automations;
- native Assist/LLM tools.

### Multiple Plex servers

You can configure more than one Plex server.

When only one server is configured, Plex Extended can normally select it automatically. With multiple servers, Home Assistant actions expose a server selector; YAML calls can use `config_entry_id` to make the target explicit.

Native Assist tool schemas likewise include a server selector when more than one eligible Plex Extended entry is available.

## Plex user context

Plex viewing state is user-specific. Plex Extended can therefore run viewing-state-aware queries as the intended Plex household user.

Open:

**Settings → Devices & services → Plex Extended → Configure**

and choose a **Default Plex user**.

If you leave the default unset, Plex Extended uses the Plex server/account context created during setup.

User-aware capabilities include search metadata, structured watched-state filtering, TV progress, recent history, Continue Watching, On Deck, collections/playlists, media details and watched/unwatched writes.

Most user-aware actions also accept optional `user` and `user_id` values for one-call overrides. Prefer the stable `user_id` returned by `plex_extended.list_users` when an automation must remain unambiguous.

```yaml
action: plex_extended.watch_status
data:
  title: Resident Alien
  user: Guest
response_variable: guest_progress
```

### Who can switch Plex users?

Plex user switching requires the Plex credentials used to configure Plex Extended to belong to the server owner/admin.

If Plex Extended is connected to somebody else's shared server as a non-owner, that normal connection can still be used, but Plex does not permit Plex Extended to switch it into another household user's server context.

### Watchlist is different

Plex Watchlist belongs to the authenticated **plex.tv account**, not a local Plex household-user context.

Therefore:

- `plex_extended.watchlist` uses the account that configured that Plex Extended entry;
- `discover_search` + Watchlist mutations operate at that account level;
- the **Default Plex user** does not change whose Watchlist is being read or modified.

Regular playlists, by contrast, follow the selected/default Plex household-user context.

## Native Assist / LLM tools

Home Assistant 2026.8+ can discover Plex Extended's native LLM tool platform. A compatible conversation agent using Home Assistant's built-in Assist LLM API can call Plex Extended directly instead of relying on prompt-only instructions or template sensors.

Examples include:

- “Do I have *Alien*?”
- “How many unwatched horror movies do I have?”
- “Where am I up to in *Resident Alien*?”
- “What new episodes do I need to catch up on?”
- “What do I have that is similar to *Alien*?”
- “Who is using Plex right now?”
- “Is anything transcoding?”

### Enable or disable Plex Extended tools per server

Go to:

**Settings → Devices & services → Plex Extended → Configure**

The **Enable native Assist tools** option is on by default. Turning it off removes that Plex server from Plex Extended's native LLM tool set without disabling normal Home Assistant actions.

### Assist writes are off by default

Plex Extended has separate permissions for:

- **Allow Assist to change Plex watch state**;
- **Allow Assist to change Plex Watchlist**;
- **Allow Assist to change Plex playlists**.

These are independent and default to off.

Manual Home Assistant actions are **not** controlled by those Assist-specific toggles.

When an Assist write family is enabled, Plex Extended still uses exact-ID contracts, post-write verification, bounded mutations, and model guidance that requires an explicit user request.

## Mutation safety

Plex Extended intentionally avoids broad or fuzzy mutation APIs.

### Watched/unwatched

`mark_watched` and `mark_unwatched` require an exact local media `rating_key`. Plex Extended re-reads the item and fails if Plex does not confirm the requested state.

### Watchlist

Watchlist add/remove requires both the exact Discover `guid` and the corresponding title returned by Plex Extended. Plex Extended re-runs Discover and requires an **exact GUID match** before it changes anything.

Adding an already-present item or removing an already-absent item is treated as an idempotent success.

### Regular playlists

Existing-playlist writes require an exact `playlist_rating_key` from `list_playlists`.

Playlist operations are designed to be retry-safe:

- add skips items already present;
- remove clears all occurrences of requested IDs and verifies progress;
- create detects same-title collisions conservatively;
- smart and radio playlists remain read-only;
- Plex Extended re-reads state after actual writes before reporting success.

## Detailed action reference

The README is intentionally focused on getting a new user from installation to a working setup without requiring them to read every backend detail first.

The full field-by-field and behavioral reference is in:

**[docs/action-reference.md](docs/action-reference.md)**

It covers all Plex Extended actions, including:

- advanced library filters and facets;
- date-window semantics;
- TV catch-up bounds/truncation;
- related-media hub behavior;
- active-stream fields;
- collection/playlist identity rules;
- playlist mutation idempotency;
- Discover/Watchlist identity rules;
- user and library selectors.

Home Assistant also exposes field descriptions directly in **Developer Tools → Actions**.

## Troubleshooting

### Plex authorization succeeds but the browser tab stays open

After Plex approval, Plex Extended asks the external browser tab/window to close and the original Home Assistant flow continues.

Browsers can block automatic closing. The fallback page provides a **Return to Home Assistant** button; using it is safe.

### No Plex server is found during Connect with Plex

Check that the Plex account you authorized can access the intended Plex Media Server and that the server is reachable.

If the plex.tv discovery route is unsuitable for your setup, use **Manual setup** with the server URL and Plex token.

### A household user cannot be selected or queried

Switching into another Plex household user's server context requires an owner/admin Plex connection. Shared non-owner server connections cannot switch users.

### A query says a library is ambiguous or cannot be selected

Plex Extended automatically chooses a library only when exactly one compatible library exists. If you have several compatible libraries, supply `library` or preferably stable `library_id`.

### An action is ambiguous because multiple Plex servers are configured

Choose the server in Home Assistant's action UI or supply `config_entry_id` in YAML.

### Plex Extended tools do not appear in Assist

Check all of the following:

1. **Enable native Assist tools** is enabled for the Plex Extended server.
2. Your conversation integration/agent supports Home Assistant's built-in Assist LLM API.
3. The Plex Extended config entry is loaded successfully.

If read tools appear but mutation tools do not, enable only the relevant Assist write permission under **Configure**.

### Assist can read Plex but cannot change watched state / playlists / Watchlist

That is the default safety configuration. Each write family has a separate opt-in under **Configure**.

### Watchlist results appear to ignore the Default Plex user

That is intentional. Plex Watchlist belongs to the authenticated plex.tv account, not the selected local household user.

### Plex says authentication has expired

If Plex rejects the stored server token, Plex Extended starts Home Assistant's normal reauthentication flow so the server identity can be retained while credentials are refreshed.

## Diagnostics and privacy

Home Assistant can download diagnostics from the Plex Extended config-entry menu.

Diagnostics include useful support information such as Plex server version/platform, connection scheme, enabled capabilities, and library section IDs/types.

Plex tokens, tokenized URLs, server host/URL, client identifiers, server machine identifiers, server name, library names and library UUIDs are redacted or omitted.

Normal Plex Extended action/tool results also intentionally avoid Plex tokens, tokenized URLs, local media filesystem paths, playback session IDs and client IP/public addresses.

## Authentication

The normal setup flow uses Plex's website authorization process through `plexauth`:

1. Home Assistant creates a Plex authorization request for Plex Extended.
2. Your browser is sent to Plex.
3. You sign in/approve on Plex's site.
4. Plex Extended discovers Plex Media Servers available to the account.
5. The selected server is connected using the access token Plex provides for that resource.

Plex Extended never receives or stores your Plex password.

Plex Discover and account-Watchlist features continue to communicate with plex.tv when used. Local-library queries communicate with the configured Plex Media Server.

## Relationship to Home Assistant's built-in Plex integration

Plex Extended does **not** override, patch, or replace Home Assistant's `plex` integration.

| Home Assistant Plex | Plex Extended |
| --- | --- |
| Media-player entities and playback controls | Query/aggregate Plex library data |
| Existing Plex media-source behavior | Structured response-data actions |
| Player/server activity already exposed by core | Rich active-session/transcode query data |
| Core Plex integration features | Per-user progress/history/discovery and safe selected mutations |
| — | Native Assist/LLM query tools |

Both can be configured against the same Plex account/server at the same time.

## v0.1.0 scope

The initial release focuses on rich querying plus **narrowly scoped, verifiable mutations**.

Included writes are limited to:

- watched/unwatched state for exact local Plex items;
- exact Plex Discover items in the configured account's Watchlist;
- regular Plex playlist creation/add/remove using exact identities.

Plex Extended deliberately does **not** provide playback control, broad destructive library operations, arbitrary raw Plex API calls, or Tautulli-specific analytics.

## Development and validation

The repository validation workflow runs:

- Python compilation;
- the fast backend/unit test suite;
- real Home Assistant integration-contract tests against the declared minimum Home Assistant release and current stable;
- Home Assistant `hassfest`;
- HACS validation.

The real Home Assistant contract suite covers config-entry setup/unload, config and reauthentication flows, options, service registration/dispatch, multi-server behavior, mutation response contracts, and native LLM platform discovery.