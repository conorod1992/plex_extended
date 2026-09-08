from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old!r}")
    p.write_text(text.replace(old, new, 1))


replace(
    "custom_components/plex_extended/library_query.py",
    '        channel_values = [int(value) for value in _values(channels)]\n',
    '        # PlexAPI XML attributes are strings for list-membership operators.\n'
    '        # Keep the public schema numeric, but compare against the serialized values.\n'
    '        channel_values = _values(channels)\n',
)
replace(
    "tests/test_library_query.py",
    '    assert post_filters["media__audioChannels__in"] == [6, 8]\n',
    '    assert post_filters["media__audioChannels__in"] == ["6", "8"]\n',
)
replace(
    "custom_components/plex_extended/library_summary_llm.py",
    '        "is distributed by genre/year/decade/resolution/watch state/content rating/studio/"\n'
    '        "collection, or for the total runtime of matching media. Viewing-state criteria use "\n',
    '        "is distributed by genre/year/decade/resolution/watch state/content rating/studio/"\n'
    '        "collection/label/country/language/codec/container/channel count, or for the total "\n'
    '        "runtime of matching media. Viewing-state criteria use "\n',
)
