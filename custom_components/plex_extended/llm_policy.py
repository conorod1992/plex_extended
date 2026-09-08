"""Native Assist exposure policy for Plex Extended."""

from __future__ import annotations

from typing import TypeVar

from .const import CONF_ENABLE_LLM_TOOLS

_T = TypeVar("_T")


def native_llm_tools_enabled(client: object) -> bool:
    """Return whether one Plex Extended client contributes native Assist tools.

    Existing entries predate this option, so absence deliberately means enabled.
    """
    entry = getattr(client, "entry", None)
    options = getattr(entry, "options", None) or {}
    return bool(options.get(CONF_ENABLE_LLM_TOOLS, True))


def enabled_llm_clients(clients: dict[str, _T]) -> dict[str, _T]:
    """Return enabled clients while preserving their unambiguous display labels."""
    return {
        label: client
        for label, client in clients.items()
        if native_llm_tools_enabled(client)
    }
