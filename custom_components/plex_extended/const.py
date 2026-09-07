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

AUTH_CALLBACK_NAME: Final = "api:plex_extended:auth"
AUTH_CALLBACK_PATH: Final = "/api/plex_extended/auth"
HEADER_FRONTEND_BASE: Final = "HA-Frontend-Base"

X_PLEX_DEVICE_NAME: Final = "Home Assistant"
X_PLEX_PLATFORM: Final = "Home Assistant"
X_PLEX_PRODUCT: Final = "Plex Extended"
X_PLEX_VERSION: Final = "0.1.0"

DEFAULT_LIMIT: Final = 10
MAX_LIMIT: Final = 50
HISTORY_PAGE_SIZE: Final = 100
DEFAULT_SEARCH_TYPES: Final = ["movie", "show"]
DEFAULT_LLM_INCLUDE_SUMMARY: Final = False
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

SERVICE_SEARCH: Final = "search"
SERVICE_QUERY_LIBRARY: Final = "query_library"
SERVICE_WATCH_STATUS: Final = "watch_status"
SERVICE_RECENTLY_ADDED: Final = "recently_added"
SERVICE_RECENTLY_WATCHED: Final = "recently_watched"
SERVICE_CONTINUE_WATCHING: Final = "continue_watching"
SERVICE_ON_DECK: Final = "on_deck"
SERVICE_MEDIA_DETAILS: Final = "media_details"
SERVICE_LIST_LIBRARIES: Final = "list_libraries"
SERVICE_LIST_USERS: Final = "list_users"
SERVICE_TEST_CONNECTION: Final = "test_connection"
