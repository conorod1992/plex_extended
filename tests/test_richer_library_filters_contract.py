"""Public contract checks for PR14 richer library filters."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "plex_extended"


def test_action_and_llm_schemas_expose_same_new_filters() -> None:
    services = (COMPONENT / "services.py").read_text()
    llm = (COMPONENT / "llm_tools.py").read_text()
    for field in (
        "audio_languages",
        "subtitle_languages",
        "labels",
        "countries",
        "duplicates",
        "unmatched",
        "video_codecs",
        "audio_codecs",
        "containers",
        "audio_channels",
    ):
        assert f'vol.Optional("{field}")' in services
        assert f'vol.Optional("{field}")' in llm


def test_summary_facets_and_developer_tools_include_new_dimensions() -> None:
    const = (COMPONENT / "const.py").read_text()
    yaml = (COMPONENT / "services.yaml").read_text()
    readme = (ROOT / "README.md").read_text()
    for facet in (
        "label",
        "country",
        "audio_language",
        "subtitle_language",
        "video_codec",
        "audio_codec",
        "container",
        "audio_channels",
    ):
        assert f'"{facet}"' in const
        assert f"- {facet}" in yaml
        assert f"`{facet}`" in readme


def test_native_and_technical_filters_remain_separate() -> None:
    backend = (COMPONENT / "library_query.py").read_text()

    for native_key in (
        'filters[plex_key] = values',
        '("audio_languages", "audioLanguage")',
        '("subtitle_languages", "subtitleLanguage")',
        '("labels", "label")',
        '("countries", "country")',
        '("duplicates", "duplicate")',
        '("unmatched", "unmatched")',
    ):
        assert native_key in backend

    for technical_key in (
        'post_filters[f"media__{plex_attribute}__in"]',
        'post_filters["media__audioChannels__in"]',
    ):
        assert technical_key in backend

    # PlexAPI's XML list-membership operator sees serialized attribute values.
    assert "channel_values = _values(channels)" in backend


def test_no_arbitrary_raw_plex_filter_escape_hatch_was_added() -> None:
    services = (COMPONENT / "services.py").read_text()
    llm = (COMPONENT / "llm_tools.py").read_text()
    assert 'vol.Optional("filters")' not in services
    assert 'vol.Optional("filters")' not in llm


def test_temporary_pr14_helpers_are_not_retained() -> None:
    for path in (
        ROOT / ".github/workflows/pr14-wire.yml",
        ROOT / ".github/scripts/pr14_patch.py",
        ROOT / ".github/workflows/pr14-fix.yml",
        ROOT / ".github/scripts/pr14_fix.py",
    ):
        assert not path.exists()
