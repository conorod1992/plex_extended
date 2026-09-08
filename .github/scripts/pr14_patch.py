from pathlib import Path


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text()
    found = text.count(old)
    if found < count:
        raise SystemExit(
            f"Expected at least {count} occurrence(s) in {path}, found {found}: {old[:120]!r}"
        )
    p.write_text(text.replace(old, new, count))


# Summary facets.
replace(
    "custom_components/plex_extended/const.py",
    '    "collection",\n)\n',
    '    "collection",\n    "label",\n    "country",\n    "audio_language",\n    "subtitle_language",\n    "video_codec",\n    "audio_codec",\n    "container",\n    "audio_channels",\n)\n',
)

# Home Assistant action schema: richer server-native and PlexAPI technical filters.
replace(
    "custom_components/plex_extended/services.py",
    'TEXT_LIST_SCHEMA = vol.All(\n    cv.ensure_list,\n    [vol.All(cv.string, vol.Length(min=1))],\n)\n',
    'TEXT_LIST_SCHEMA = vol.All(\n    cv.ensure_list,\n    [vol.All(cv.string, vol.Length(min=1))],\n)\nCHANNEL_LIST_SCHEMA = vol.All(\n    cv.ensure_list,\n    [vol.All(vol.Coerce(int), vol.Range(min=1, max=32))],\n)\n',
)
replace(
    "custom_components/plex_extended/services.py",
    '        vol.Optional("studios"): TEXT_LIST_SCHEMA,\n',
    '        vol.Optional("studios"): TEXT_LIST_SCHEMA,\n'
    '        vol.Optional("audio_languages"): TEXT_LIST_SCHEMA,\n'
    '        vol.Optional("subtitle_languages"): TEXT_LIST_SCHEMA,\n'
    '        vol.Optional("labels"): TEXT_LIST_SCHEMA,\n'
    '        vol.Optional("countries"): TEXT_LIST_SCHEMA,\n'
    '        vol.Optional("duplicates"): cv.boolean,\n'
    '        vol.Optional("unmatched"): cv.boolean,\n'
    '        vol.Optional("video_codecs"): TEXT_LIST_SCHEMA,\n'
    '        vol.Optional("audio_codecs"): TEXT_LIST_SCHEMA,\n'
    '        vol.Optional("containers"): TEXT_LIST_SCHEMA,\n'
    '        vol.Optional("audio_channels"): CHANNEL_LIST_SCHEMA,\n',
)

# Query backend: native Plex filters first, then documented PlexAPI XML filters.
replace(
    "custom_components/plex_extended/library_query.py",
    '        ("studios", "studio"),\n        ("resolutions", "resolution"),\n',
    '        ("studios", "studio"),\n'
    '        ("audio_languages", "audioLanguage"),\n'
    '        ("subtitle_languages", "subtitleLanguage"),\n'
    '        ("labels", "label"),\n'
    '        ("countries", "country"),\n'
    '        ("resolutions", "resolution"),\n',
)
replace(
    "custom_components/plex_extended/library_query.py",
    '    hdr_state = criteria.get("hdr", "any")\n'
    '    if hdr_state == "hdr":\n'
    '        filters["hdr"] = True\n'
    '    elif hdr_state == "sdr":\n'
    '        filters["hdr!"] = True\n'
    '    elif hdr_state != "any":\n'
    '        raise PlexExtendedError(f"Unsupported HDR state: {hdr_state}")\n\n',
    '    hdr_state = criteria.get("hdr", "any")\n'
    '    if hdr_state == "hdr":\n'
    '        filters["hdr"] = True\n'
    '    elif hdr_state == "sdr":\n'
    '        filters["hdr!"] = True\n'
    '    elif hdr_state != "any":\n'
    '        raise PlexExtendedError(f"Unsupported HDR state: {hdr_state}")\n\n'
    '    for input_key, plex_key in (("duplicates", "duplicate"), ("unmatched", "unmatched")):\n'
    '        if input_key not in criteria:\n'
    '            continue\n'
    '        if bool(criteria[input_key]):\n'
    '            filters[plex_key] = True\n'
    '        else:\n'
    '            filters[f"{plex_key}!"] = True\n\n',
)
replace(
    "custom_components/plex_extended/library_query.py",
    '    if duration_max is not None:\n'
    '        post_filters["duration__lte"] = int(float(duration_max) * 60_000)\n\n'
    '    return filters, post_filters\n',
    '    if duration_max is not None:\n'
    '        post_filters["duration__lte"] = int(float(duration_max) * 60_000)\n\n'
    '    for input_key, plex_attribute in (\n'
    '        ("video_codecs", "videoCodec"),\n'
    '        ("audio_codecs", "audioCodec"),\n'
    '        ("containers", "container"),\n'
    '    ):\n'
    '        values = [value.casefold() for value in _values(criteria.get(input_key))]\n'
    '        if values:\n'
    '            post_filters[f"media__{plex_attribute}__in"] = values\n\n'
    '    channels = criteria.get("audio_channels")\n'
    '    if channels is not None:\n'
    '        channel_values = [int(value) for value in _values(channels)]\n'
    '        if channel_values:\n'
    '            post_filters["media__audioChannels__in"] = channel_values\n\n'
    '    return filters, post_filters\n',
)

# Native LLM query schema mirrors the same typed interface.
replace(
    "custom_components/plex_extended/llm_tools.py",
    'LLM_TEXT_LIST = vol.All(\n    cv.ensure_list,\n    [vol.All(cv.string, vol.Length(min=1))],\n)\n',
    'LLM_TEXT_LIST = vol.All(\n    cv.ensure_list,\n    [vol.All(cv.string, vol.Length(min=1))],\n)\n'
    'LLM_CHANNEL_LIST = vol.All(\n    cv.ensure_list,\n    [vol.All(vol.Coerce(int), vol.Range(min=1, max=32))],\n)\n',
)
replace(
    "custom_components/plex_extended/llm_tools.py",
    '        "for genre, people, year, collections, watched state, runtime, resolution/HDR, "\n'
    '        "ratings, dates, or sorting. Viewing-state filters use the configured default "\n',
    '        "for genre, people, year, collections, language/labels/country, duplicate or "\n'
    '        "match state, watched state, runtime, resolution/HDR, codec/container/channels, "\n'
    '        "ratings, dates, or sorting. Viewing-state filters use the configured default "\n',
)
replace(
    "custom_components/plex_extended/llm_tools.py",
    '                vol.Optional("studios"): LLM_TEXT_LIST,\n',
    '                vol.Optional("studios"): LLM_TEXT_LIST,\n'
    '                vol.Optional("audio_languages"): LLM_TEXT_LIST,\n'
    '                vol.Optional("subtitle_languages"): LLM_TEXT_LIST,\n'
    '                vol.Optional("labels"): LLM_TEXT_LIST,\n'
    '                vol.Optional("countries"): LLM_TEXT_LIST,\n'
    '                vol.Optional("duplicates"): cv.boolean,\n'
    '                vol.Optional("unmatched"): cv.boolean,\n'
    '                vol.Optional("video_codecs"): LLM_TEXT_LIST,\n'
    '                vol.Optional("audio_codecs"): LLM_TEXT_LIST,\n'
    '                vol.Optional("containers"): LLM_TEXT_LIST,\n'
    '                vol.Optional("audio_channels"): LLM_CHANNEL_LIST,\n',
)

# Aggregate facets for the same metadata dimensions.
replace(
    "custom_components/plex_extended/library_summary.py",
    '_HYDRATED_FACETS = {"genre", "resolution", "collection", "watched_state"}\n',
    '_HYDRATED_FACETS = {\n'
    '    "genre",\n'
    '    "resolution",\n'
    '    "collection",\n'
    '    "watched_state",\n'
    '    "label",\n'
    '    "country",\n'
    '    "audio_language",\n'
    '    "subtitle_language",\n'
    '    "video_codec",\n'
    '    "audio_codec",\n'
    '    "container",\n'
    '    "audio_channels",\n'
    '}\n',
)
replace(
    "custom_components/plex_extended/library_summary.py",
    'def _resolution_values(item: Any) -> list[str]:\n'
    '    """Return unique media resolutions for an item."""\n'
    '    values: list[str] = []\n'
    '    for media in getattr(item, "media", None) or []:\n'
    '        resolution = getattr(media, "videoResolution", None)\n'
    '        if resolution:\n'
    '            values.append(str(resolution))\n'
    '    return values\n\n\n',
    'def _media_attribute_values(item: Any, attribute: str) -> list[Any]:\n'
    '    """Return values for one attribute across every media version."""\n'
    '    values: list[Any] = []\n'
    '    for media in getattr(item, "media", None) or []:\n'
    '        value = getattr(media, attribute, None)\n'
    '        if value is not None and value != "":\n'
    '            values.append(value)\n'
    '    return values\n\n\n'
    'def _stream_language_values(item: Any, stream_type: int) -> list[str]:\n'
    '    """Return language codes/names from audio or subtitle streams."""\n'
    '    values: list[str] = []\n'
    '    for media in getattr(item, "media", None) or []:\n'
    '        for part in getattr(media, "parts", None) or []:\n'
    '            for stream in getattr(part, "streams", None) or []:\n'
    '                if getattr(stream, "streamType", None) != stream_type:\n'
    '                    continue\n'
    '                value = getattr(stream, "languageCode", None) or getattr(stream, "language", None)\n'
    '                if value:\n'
    '                    values.append(str(value))\n'
    '    return values\n\n\n'
    'def _resolution_values(item: Any) -> list[str]:\n'
    '    """Return unique media resolutions for an item."""\n'
    '    return [str(value) for value in _media_attribute_values(item, "videoResolution")]\n\n\n',
)
replace(
    "custom_components/plex_extended/library_summary.py",
    '    if facet == "watched_state":\n'
    '        value = _watched_state(item)\n'
    '        return [value] if value is not None else []\n\n'
    '    data = object.__getattribute__(item, "__dict__")\n',
    '    if facet == "watched_state":\n'
    '        value = _watched_state(item)\n'
    '        return [value] if value is not None else []\n'
    '    if facet == "label":\n'
    '        return _tag_values(item, "labels")\n'
    '    if facet == "country":\n'
    '        return _tag_values(item, "countries")\n'
    '    if facet == "audio_language":\n'
    '        return _stream_language_values(item, 2)\n'
    '    if facet == "subtitle_language":\n'
    '        return _stream_language_values(item, 3)\n'
    '    if facet == "video_codec":\n'
    '        return [str(value) for value in _media_attribute_values(item, "videoCodec")]\n'
    '    if facet == "audio_codec":\n'
    '        return [str(value) for value in _media_attribute_values(item, "audioCodec")]\n'
    '    if facet == "container":\n'
    '        return [str(value) for value in _media_attribute_values(item, "container")]\n'
    '    if facet == "audio_channels":\n'
    '        return _media_attribute_values(item, "audioChannels")\n\n'
    '    data = object.__getattribute__(item, "__dict__")\n',
)

# Developer Tools metadata for query_library and library_summary (same field block twice).
services = Path("custom_components/plex_extended/services.yaml")
text = services.read_text()
studios_block = '''    studios:\n      name: Studios\n      description: Match any supplied studio. YAML can supply a list.\n      selector:\n        text:\n'''
if text.count(studios_block) < 2:
    raise SystemExit("Expected query_library and library_summary studios blocks")
extra_fields = '''    audio_languages:\n      name: Audio languages\n      description: Match any Plex audio language code/name, such as eng or jpn. This is a Plex-native server filter. YAML can supply a list.\n      selector:\n        text:\n    subtitle_languages:\n      name: Subtitle languages\n      description: Match any Plex subtitle language code/name, such as eng. This is a Plex-native server filter. YAML can supply a list.\n      selector:\n        text:\n    labels:\n      name: Labels\n      description: Match any Plex label. YAML can supply a list.\n      selector:\n        text:\n    countries:\n      name: Countries\n      description: Match any Plex country tag. YAML can supply a list.\n      selector:\n        text:\n    duplicates:\n      name: Has duplicate versions\n      description: When true, match Plex duplicate items; when false, exclude duplicates. Leave unset for either.\n      selector:\n        boolean:\n    unmatched:\n      name: Unmatched\n      description: When true, match items Plex has not matched; when false, require matched items. Leave unset for either.\n      selector:\n        boolean:\n    video_codecs:\n      name: Video codecs\n      description: Match any media version whose Plex videoCodec equals one of these values, such as hevc or h264. PlexAPI applies this after the server-native filters. YAML can supply a list.\n      selector:\n        text:\n    audio_codecs:\n      name: Audio codecs\n      description: Match any media version whose Plex audioCodec equals one of these values, such as truehd, eac3 or aac. PlexAPI applies this after the server-native filters. YAML can supply a list.\n      selector:\n        text:\n    containers:\n      name: Containers\n      description: Match any media version container, such as mkv or mp4. PlexAPI applies this after the server-native filters. YAML can supply a list.\n      selector:\n        text:\n    audio_channels:\n      name: Audio channels\n      description: Match any media version with this channel count, such as 2, 6 or 8. YAML can supply a list.\n      selector:\n        number:\n          min: 1\n          max: 32\n          mode: box\n'''
text = text.replace(studios_block, studios_block + extra_fields, 2)
facet_anchor = '''            - studio\n            - collection\n'''
if facet_anchor not in text:
    raise SystemExit("Facet options anchor missing")
text = text.replace(
    facet_anchor,
    '''            - studio\n            - collection\n            - label\n            - country\n            - audio_language\n            - subtitle_language\n            - video_codec\n            - audio_codec\n            - container\n            - audio_channels\n''',
    1,
)
services.write_text(text)

# README documentation.
replace(
    "README.md",
    'Supported typed criteria include partial title; genre; actor/director/collection/studio/content rating; exact year/range/decade; watched/unwatched/in-progress; resolution/HDR; critic/audience/user rating ranges; runtime; added/last-viewed dates; and sorting.\n',
    'Supported typed criteria include partial title; genre; actor/director/collection/studio/content rating; audio/subtitle language; labels and country; duplicate/matched state; exact year/range/decade; watched/unwatched/in-progress; resolution/HDR; video/audio codec, container and audio-channel count; critic/audience/user rating ranges; runtime; added/last-viewed dates; and sorting.\n\nAudio/subtitle language, label, country, duplicate and unmatched criteria use Plex\'s native server filters. Codec/container/channel criteria use PlexAPI\'s documented XML post-filtering after the server-native candidate set, so very broad technical queries can require Plex to return more metadata than a purely server-native query.\n',
)
replace(
    "README.md",
    'Supported facets are `genre`, `year`, `decade`, `resolution`, `watched_state`, `content_rating`, `studio`, and `collection`. ',
    'Supported facets are `genre`, `year`, `decade`, `resolution`, `watched_state`, `content_rating`, `studio`, `collection`, `label`, `country`, `audio_language`, `subtitle_language`, `video_codec`, `audio_codec`, `container`, and `audio_channels`. ',
)

# Behavioral regression tests on the existing module fixtures.
query_tests = Path("tests/test_library_query.py")
text = query_tests.read_text()
marker = "\ndef test_watched_and_sdr_filters_use_plex_false_operators() -> None:\n"
if marker not in text:
    raise SystemExit("library_query test insertion marker missing")
new_tests = '''\ndef test_richer_library_filters_split_native_and_technical_criteria() -> None:\n    filters, post_filters = _build_filters(\n        {\n            "audio_languages": ["eng", "jpn"],\n            "subtitle_languages": ["eng"],\n            "labels": ["Keep"],\n            "countries": ["Ireland"],\n            "duplicates": True,\n            "unmatched": False,\n            "video_codecs": ["HEVC", "h264"],\n            "audio_codecs": ["TRUEHD"],\n            "containers": ["MKV"],\n            "audio_channels": [6, 8],\n        }\n    )\n\n    assert filters["audioLanguage"] == ["eng", "jpn"]\n    assert filters["subtitleLanguage"] == ["eng"]\n    assert filters["label"] == ["Keep"]\n    assert filters["country"] == ["Ireland"]\n    assert filters["duplicate"] is True\n    assert filters["unmatched!"] is True\n    assert post_filters["media__videoCodec__in"] == ["hevc", "h264"]\n    assert post_filters["media__audioCodec__in"] == ["truehd"]\n    assert post_filters["media__container__in"] == ["mkv"]\n    assert post_filters["media__audioChannels__in"] == [6, 8]\n\n\ndef test_false_duplicate_filter_uses_plex_boolean_false_operator() -> None:\n    filters, _ = _build_filters({"duplicates": False})\n    assert filters == {"duplicate!": True}\n\n'''
query_tests.write_text(text.replace(marker, new_tests + marker, 1))

summary_tests = Path("tests/test_library_summary.py")
text = summary_tests.read_text()
append = '''\n\ndef test_new_metadata_facets_cover_tags_streams_and_media_versions() -> None:\n    item = SimpleNamespace(\n        labels=[SimpleNamespace(tag="Favourite")],\n        countries=[SimpleNamespace(tag="Ireland")],\n        media=[\n            SimpleNamespace(\n                videoCodec="hevc",\n                audioCodec="truehd",\n                container="mkv",\n                audioChannels=8,\n                videoResolution="4k",\n                parts=[\n                    SimpleNamespace(\n                        streams=[\n                            SimpleNamespace(streamType=2, languageCode="eng", language="English"),\n                            SimpleNamespace(streamType=3, languageCode="spa", language="Spanish"),\n                        ]\n                    )\n                ],\n            ),\n            SimpleNamespace(\n                videoCodec="h264",\n                audioCodec="aac",\n                container="mp4",\n                audioChannels=2,\n                videoResolution="1080",\n                parts=[],\n            ),\n        ],\n    )\n\n    expected = {\n        "label": ["Favourite"],\n        "country": ["Ireland"],\n        "audio_language": ["eng"],\n        "subtitle_language": ["spa"],\n        "video_codec": ["hevc", "h264"],\n        "audio_codec": ["truehd", "aac"],\n        "container": ["mkv", "mp4"],\n        "audio_channels": [8, 2],\n    }\n    for facet, values in expected.items():\n        assert summary_module._facet_values(item, facet) == values\n\n\ndef test_technical_filter_forces_materialized_summary_count() -> None:\n    section = FakeSection()\n    section.search_results = [_partial(1), _partial(2)]\n    server = FakeServer([section], total_size=99)\n\n    result = _library_summary(\n        _client(server),\n        {\n            "media_type": "movie",\n            "video_codecs": ["hevc"],\n            "watched_state": "any",\n            "hdr": "any",\n        },\n    )\n\n    assert result["count"] == 2\n    assert server.query_calls == []\n    assert section.search_calls[0]["media__videoCodec__in"] == ["hevc"]\n'''
if "test_new_metadata_facets_cover_tags_streams_and_media_versions" in text:
    raise SystemExit("summary tests already patched")
summary_tests.write_text(text + append)

# Static public-contract test.
Path("tests/test_richer_library_filters_contract.py").write_text('''"""Public contract checks for PR14 richer library filters."""\n\nfrom pathlib import Path\n\nROOT = Path(__file__).parents[1]\nCOMPONENT = ROOT / "custom_components" / "plex_extended"\n\n\ndef test_action_and_llm_schemas_expose_same_new_filters() -> None:\n    services = (COMPONENT / "services.py").read_text()\n    llm = (COMPONENT / "llm_tools.py").read_text()\n    for field in (\n        "audio_languages",\n        "subtitle_languages",\n        "labels",\n        "countries",\n        "duplicates",\n        "unmatched",\n        "video_codecs",\n        "audio_codecs",\n        "containers",\n        "audio_channels",\n    ):\n        assert f'vol.Optional("{field}")' in services\n        assert f'vol.Optional("{field}")' in llm\n\n\ndef test_summary_facets_and_developer_tools_include_new_dimensions() -> None:\n    const = (COMPONENT / "const.py").read_text()\n    yaml = (COMPONENT / "services.yaml").read_text()\n    readme = (ROOT / "README.md").read_text()\n    for facet in (\n        "label",\n        "country",\n        "audio_language",\n        "subtitle_language",\n        "video_codec",\n        "audio_codec",\n        "container",\n        "audio_channels",\n    ):\n        assert f'"{facet}"' in const\n        assert f"- {facet}" in yaml\n        assert f"`{facet}`" in readme\n\n\ndef test_no_arbitrary_raw_plex_filter_escape_hatch_was_added() -> None:\n    services = (COMPONENT / "services.py").read_text()\n    llm = (COMPONENT / "llm_tools.py").read_text()\n    assert 'vol.Optional("filters")' not in services\n    assert 'vol.Optional("filters")' not in llm\n\n\ndef test_temporary_pr14_helpers_are_not_retained() -> None:\n    assert not (ROOT / ".github/workflows/pr14-wire.yml").exists()\n    assert not (ROOT / ".github/scripts/pr14_patch.py").exists()\n''')
