from pathlib import Path

import pytest

from scripts import generate


def test_parse_cities_sorts_by_spell():
    payload = {
        "citylist": [
            {"spell": "shanghai", "adcode": "3100", "cityname": "上海市"},
            {"spell": "beijing", "adcode": "1100", "cityname": "北京市"},
        ]
    }

    cities = generate.parse_cities(payload)

    assert [city.spell for city in cities] == ["beijing", "shanghai"]


def test_extract_station_names_deduplicates_by_name():
    payload = {
        "l": [
            {"st": [{"n": "苹果园"}, {"n": "金安桥"}]},
            {"st": [{"n": "苹果园"}]},
        ]
    }

    assert generate.extract_station_names(payload, "1100_drw_beijing.json") == {
        "苹果园",
        "金安桥",
    }


def test_extract_station_names_rejects_malformed_station_records():
    with pytest.raises(ValueError, match="missing station list"):
        generate.extract_station_names({"l": [{}]}, "broken.json")

    with pytest.raises(ValueError, match="missing usable name"):
        generate.extract_station_names({"l": [{"st": [{}]}]}, "broken.json")

    with pytest.raises(ValueError, match="missing usable name"):
        generate.extract_station_names({"l": [{"st": [{"n": None}]}]}, "broken.json")


def test_rows_apply_overrides_and_sort_by_pinyin_then_name():
    rows = generate.build_rows({"重庆", "苹果园"}, {"重庆": "chong qing"})

    assert rows == [
        generate.DictRow("重庆", "chong qing", 1),
        generate.DictRow("苹果园", "ping guo yuan", 1),
    ]


def test_pinyin_for_name_lowercases_non_chinese_fragments():
    assert generate.pinyin_for_name("T3航站楼", {}) == "t3 hang zhan lou"


def test_render_dictionary_uses_rime_header_and_tabs():
    text = generate.render_dictionary(
        "beijing.subway",
        "2026.06.16",
        [generate.DictRow("苹果园", "ping guo yuan", 1)],
    )

    assert "# Rime dictionary\n# encoding: utf-8\n#\n---\n" in text
    assert "name: beijing.subway\n" in text
    assert "苹果园\tping guo yuan\t1\n" in text
    assert "苹果园 ping guo yuan 1" not in text


def test_render_dictionary_rejects_malformed_rows():
    with pytest.raises(ValueError, match="malformed dictionary row"):
        generate.render_dictionary(
            "beijing.subway",
            "2026.06.16",
            [generate.DictRow("坏\t站", "huai zhan", 1)],
        )

    with pytest.raises(ValueError, match="malformed dictionary row"):
        generate.render_dictionary(
            "beijing.subway",
            "2026.06.16",
            [generate.DictRow("坏站", "", 1)],
        )


def test_replace_generated_block_preserves_surrounding_content():
    markdown = "Before\n<!-- generated:start -->\nold\n<!-- generated:end -->\nAfter\n"

    updated = generate.replace_generated_block(markdown, "new")

    assert (
        updated
        == "Before\n<!-- generated:start -->\nnew\n<!-- generated:end -->\nAfter\n"
    )


def test_load_overrides_reads_pinyin_table(tmp_path: Path):
    path = tmp_path / "overrides.toml"
    path.write_text('[pinyin]\n"重庆" = "chong qing"\n', encoding="utf-8")

    assert generate.load_overrides(path) == {"重庆": "chong qing"}
