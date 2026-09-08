from pathlib import Path

services_path = Path("custom_components/plex_extended/services.yaml")
services = services_path.read_text()
marker = "\nrecently_added:\n"
assert services.count(marker) == 1
block = r'''

related_media:
  name: Related media
  description: Return Plex-native related/recommendation hubs for one exact local movie or TV show, preserving Plex's own hub categories and ordering.
  fields:
    config_entry_id:
      name: Plex server
      description: Plex Extended server to query. Optional when only one server is configured.
      selector:
        config_entry:
          integration: plex_extended
    rating_key:
      name: Rating key
      description: Exact positive numeric local Plex rating key for a movie or TV show, returned by Search or Query library.
      required: true
      selector:
        text:
    library:
      name: Library
      description: Optional exact library name used to assert that the seed item belongs to the expected library.
      selector:
        text:
    library_id:
      name: Library ID
      description: Optional stable library section ID used to assert the seed item's library.
      selector:
        text:
    user:
      name: Plex user
      description: Optional Plex user name. Overrides the configured default Plex user for viewing-state metadata in local results.
      selector:
        text:
    user_id:
      name: Plex user ID
      description: Optional stable Plex account ID returned by List users. Overrides the configured default user; if both name and ID are supplied, they must match.
      selector:
        text:
    hub_limit:
      name: Hub limit
      description: Maximum number of Plex related hubs to return after hubs without local media are removed.
      default: 10
      selector:
        number:
          min: 1
          max: 20
          mode: box
    item_limit:
      name: Items per hub
      description: Maximum number of already-loaded local Plex media items returned from each hub. Plex Extended does not automatically expand a hub that reports more items.
      default: 10
      selector:
        number:
          min: 1
          max: 20
          mode: box
    include_summary:
      name: Include summaries
      description: Include summaries for the seed and returned local media items.
      default: true
      selector:
        boolean:
'''
services_path.write_text(services.replace(marker, block + marker))

readme_path = Path("README.md")
readme = readme_path.read_text()
action_marker = "\n### `plex_extended.recently_added`\n"
assert readme.count(action_marker) == 1
action_block = r'''

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
'''
readme = readme.replace(action_marker, action_block + action_marker)

tool_marker = "- `plex_extended__tv_catch_up`\n"
assert readme.count(tool_marker) == 1
readme = readme.replace(
    tool_marker,
    tool_marker + "- `plex_extended__related_media`\n",
)

example_marker = '- "What new TV episodes do I have to catch up on?"\n'
assert readme.count(example_marker) == 1
readme = readme.replace(
    example_marker,
    example_marker + '- "What do I have on Plex that is similar to Alien?"\n',
)

old_guidance = (
    "The LLM guidance distinguishes local fuzzy search, Plex Discover search, "
    "structured item queries, aggregate library summaries, single-show TV progress, "
    "cross-show TV catch-up, recent-media windows, collections/playlists, and "
    "account-level Watchlist."
)
new_guidance = (
    "The LLM guidance distinguishes local fuzzy search, Plex Discover search, "
    "structured item queries, aggregate library summaries, single-show TV progress, "
    "cross-show TV catch-up, Plex-native related-media recommendations, recent-media "
    "windows, collections/playlists, and account-level Watchlist."
)
assert old_guidance in readme
readme_path.write_text(readme.replace(old_guidance, new_guidance))

Path(".github/scripts/related_media_docs.py").unlink()
Path(".github/workflows/related-media-docs.yml").unlink()
