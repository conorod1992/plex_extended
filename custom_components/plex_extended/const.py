"""Constants for Plex Extended."""

from typing import Final

DOMAIN: Final = "plex_extended"

CONF_BASE_URL: Final = "base_url"
CONF_SERVER_TOKEN: Final = "server_token"
CONF_ACCOUNT_TOKEN: Final = "account_token"
CONF_CLIENT_ID: Final = "client_id"
CONF_MACHINE_IDENTIFIER: Final = "machine_identifier"
CONF_SERVER_NAME: Final = "server_name"
CONF_CONFIG_ENTRY_ID: Final = "config_entry_id"
CONF_DEFAULT_USER_ID: Final = "default_user_id"
CONF_ALLOW_LLM_MUTATIONS: Final = "allow_llm_mutations"
CONF_ALLOW_LLM_WATCHLIST_MUTATIONS: Final = "allow_llm_watchlist_mutations"
CONF_ENABLE_LLM_TOOLS: Final = "enable_llm_tools"

AUTH_CALLBACK_NAME: Final = "api:plex_extended:auth"
AUTH_CALLBACK_PATH: Final = "/api/plex_extended/auth"
HEADER_FRONTEND_BASE: Final = "HA-Frontend-Base"

X_PLEX_DEVICE_NAME: Final = "Home Assistant"
X_PLEX_PLATFORM: Final = "Home Assistant"
X_PLEX_PRODUCT: Final = "Plex Extended"
X_PLEX_VERSION: Final = "0.1.0"

DEFAULT_LIMIT: Final = 10
MAX_LIMIT: Final = 50
DEFAULT_FACET_LIMIT: Final = 20
MAX_FACET_LIMIT: Final = 50
HISTORY_PAGE_SIZE: Final = 100
DEFAULT_SEARCH_TYPES: Final = ["movie", "show"]
DEFAULT_LLM_INCLUDE_SUMMARY: Final = False
RECENT_TV_GROUPINGS: Final = ("none", "show", "season")
ACTIVE_STREAM_STATES: Final = ("playing", "paused", "buffering")
ACTIVE_STREAM_LOCALITIES: Final = ("any", "local", "remote")
LIBRARY_SUMMARY_FACETS: Final = (
    "genre",
    "year",
    "decade",
    "resolution",
    "watched_state",
    "content_rating",
    "studio",
    "collection",
)
SEARCH_TYPES: Final = (
    "movie",
    "show",
    "season",
    "episode",
    "artist",
    "album",
    "track",
    "collection",
)
QUERY_MEDIA_TYPES: Final = (
    "movie",
    "show",
    "season",
    "episode",
    "artist",
    "album",
    "track",
)
QUERY_WATCH_STATES: Final = ("any", "watched", "unwatched", "in_progress")
QUERY_HDR_STATES: Final = ("any", "hdr", "sdr")
QUERY_SORT_FIELDS: Final = (
    "title",
    "year",
    "added_at",
    "last_viewed_at",
    "critic_rating",
    "audience_rating",
    "user_rating",
    "duration",
    "resolution",
)
QUERY_SORT_ORDERS: Final = ("asc", "desc")
COLLECTION_MEDIA_TYPES: Final = ("movie", "show", "artist", "album")
PLAYLIST_TYPES: Final = ("audio", "video", "photo")
WATCHLIST_FILTERS: Final = ("all", "available", "released")
WATCHLIST_MEDIA_TYPES: Final = ("movie", "show")
WATCHLIST_SORT_FIELDS: Final = (
    "watchlisted_at",
    "title",
    "release_date",
    "critic_rating",
)

SERVICE_SEARCH: Final = "search"
SERVICE_DISCOVER_SEARCH: Final = "discover_search"
SERVICE_QUERY_LIBRARY: Final = "query_library"
SERVICE_LIBRARY_SUMMARY: Final = "library_summary"
SERVICE_WATCH_STATUS: Final = "watch_status"
SERVICE_RECENTLY_ADDED: Final = "recently_added"
SERVICE_RECENTLY_WATCHED: Final = "recently_watched"
SERVICE_CONTINUE_WATCHING: Final = "continue_watching"
SERVICE_ON_DECK: Final = "on_deck"
SERVICE_MEDIA_DETAILS: Final = "media_details"
SERVICE_ACTIVE_STREAMS: Final = "active_streams"
SERVICE_MARK_WATCHED: Final = "mark_watched"
SERVICE_MARK_UNWATCHED: Final = "mark_unwatched"
SERVICE_LIST_COLLECTIONS: Final = "list_collections"
SERVICE_COLLECTION_ITEMS: Final = "collection_items"
SERVICE_LIST_PLAYLISTS: Final = "list_playlists"
SERVICE_PLAYLIST_ITEMS: Final = "playlist_items"
SERVICE_WATCHLIST: Final = "watchlist"
SERVICE_ADD_TO_WATCHLIST: Final = "add_to_watchlist"
SERVICE_REMOVE_FROM_WATCHLIST: Final = "remove_from_watchlist"
SERVICE_LIST_LIBRARIES: Final = "list_libraries"
SERVICE_LIST_USERS: Final = "list_users"
SERVICE_TEST_CONNECTION: Final = "test_connection"
