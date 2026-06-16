from pathlib import Path

import pytest

from scripts import generate


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.body


def test_parse_cities_sorts_by_spell():
    payload = {
        "citylist": [
            {"spell": "shanghai", "adcode": "3100", "cityname": "上海市"},
            {"spell": "beijing", "adcode": "1100", "cityname": "北京市"},
        ]
    }

    cities = generate.parse_cities(payload)

    assert [city.spell for city in cities] == ["beijing", "shanghai"]


@pytest.mark.parametrize("payload", [None, [], "citylist"])
def test_parse_cities_rejects_non_object_top_level_payloads(payload):
    with pytest.raises(ValueError, match="citylist payload must be an object"):
        generate.parse_cities(payload)


@pytest.mark.parametrize("raw_city", [None, [], "beijing"])
def test_parse_cities_rejects_non_object_city_records(raw_city):
    with pytest.raises(ValueError, match="citylist item must be an object"):
        generate.parse_cities({"citylist": [raw_city]})


@pytest.mark.parametrize(
    "raw_city",
    [
        {"spell": 1100, "adcode": "1100", "cityname": "北京市"},
        {"spell": "beijing", "adcode": 1100, "cityname": "北京市"},
        {"spell": "beijing", "adcode": "1100", "cityname": None},
        {"spell": "beijing", "adcode": " ", "cityname": "北京市"},
    ],
)
def test_parse_cities_requires_nonempty_string_fields(raw_city):
    with pytest.raises(
        ValueError, match="citylist item field must be a nonempty string"
    ):
        generate.parse_cities({"citylist": [raw_city]})


@pytest.mark.parametrize("spell", ["../x", "beijing/subway", "BeiJing", "bei-jing"])
def test_parse_cities_rejects_unsafe_spell_slugs(spell):
    raw_city = {"spell": spell, "adcode": "1100", "cityname": "北京市"}

    with pytest.raises(ValueError, match="unsafe spell slug"):
        generate.parse_cities({"citylist": [raw_city]})


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


def test_fetch_json_wraps_unicode_decode_errors(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse(b"\xff")

    monkeypatch.setattr(generate, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="failed to fetch or parse AMap subway data"):
        generate.fetch_json("citylist.json")


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


@pytest.mark.parametrize("weight", ["1", 0, -1, True])
def test_render_dictionary_rejects_malformed_row_weights(weight):
    with pytest.raises(ValueError, match="malformed dictionary row"):
        generate.render_dictionary(
            "beijing.subway",
            "2026.06.16",
            [generate.DictRow("苹果园", "ping guo yuan", weight)],
        )


def test_replace_generated_block_preserves_surrounding_content():
    markdown = "Before\n<!-- generated:start -->\nold\n<!-- generated:end -->\nAfter\n"

    updated = generate.replace_generated_block(markdown, "new")

    assert (
        updated
        == "Before\n<!-- generated:start -->\nnew\n<!-- generated:end -->\nAfter\n"
    )


@pytest.mark.parametrize(
    "markdown",
    [
        "Before\nold\n<!-- generated:end -->\nAfter\n",
        "Before\n<!-- generated:start -->\nold\nAfter\n",
        "Before\n<!-- generated:end -->\nold\n<!-- generated:start -->\nAfter\n",
        (
            "Before\n<!-- generated:start -->\nold\n<!-- generated:start -->\n"
            "<!-- generated:end -->\nAfter\n"
        ),
        (
            "Before\n<!-- generated:start -->\nold\n<!-- generated:end -->\n"
            "<!-- generated:end -->\nAfter\n"
        ),
    ],
)
def test_replace_generated_block_rejects_missing_duplicate_or_invalid_markers(markdown):
    with pytest.raises(ValueError, match="README generated markers"):
        generate.replace_generated_block(markdown, "new")


def test_load_overrides_reads_pinyin_table(tmp_path: Path):
    path = tmp_path / "overrides.toml"
    path.write_text('[pinyin]\n"重庆" = "chong qing"\n', encoding="utf-8")

    assert generate.load_overrides(path) == {"重庆": "chong qing"}


@pytest.mark.parametrize(
    "contents, match",
    [
        ('[pinyin]\n"重庆" = 123\n', "override pinyin must be a string"),
        ('[pinyin]\n"重庆" = "   "\n', "override pinyin must be nonempty"),
        ('[pinyin]\n"" = "kong"\n', "override name must be nonempty"),
    ],
)
def test_load_overrides_rejects_invalid_pinyin_entries(
    tmp_path: Path, contents: str, match: str
):
    path = tmp_path / "overrides.toml"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        generate.load_overrides(path)


def test_load_overrides_rejects_names_with_surrounding_whitespace(tmp_path: Path):
    path = tmp_path / "overrides.toml"
    path.write_text('[pinyin]\n" 重庆" = "chong qing"\n', encoding="utf-8")

    with pytest.raises(
        ValueError, match="override name must not have surrounding whitespace"
    ):
        generate.load_overrides(path)


def test_generate_project_writes_city_all_and_readmes(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "A\n<!-- generated:start -->\nold\n<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "README.zh-CN.md").write_text(
        "甲\n<!-- generated:start -->\n旧\n<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "overrides.toml").write_text(
        '[pinyin]\n"重庆" = "chong qing"\n', encoding="utf-8"
    )

    payloads = {
        "citylist.json": {
            "citylist": [
                {"spell": "beijing", "adcode": "1100", "cityname": "北京市"},
                {"spell": "chongqing", "adcode": "5000", "cityname": "重庆市"},
            ]
        },
        "1100_drw_beijing.json": {"l": [{"st": [{"n": "苹果园"}, {"n": "重庆"}]}]},
        "5000_drw_chongqing.json": {"l": [{"st": [{"n": "重庆"}, {"n": "大坪"}]}]},
    }

    generate.generate_project(
        root=tmp_path,
        today="2026.06.16",
        fetch_json=lambda srhdata: payloads[srhdata],
    )

    assert (tmp_path / "beijing.subway.dict.yaml").exists()
    assert (tmp_path / "chongqing.subway.dict.yaml").exists()
    all_text = (tmp_path / "all.subway.dict.yaml").read_text(encoding="utf-8")
    assert all_text.count("重庆\tchong qing\t1") == 1
    assert "Last updated: 2026.06.16" in (tmp_path / "README.md").read_text(
        encoding="utf-8"
    )
    assert "最后更新：2026.06.16" in (tmp_path / "README.zh-CN.md").read_text(
        encoding="utf-8"
    )


def test_generate_project_does_not_write_outputs_when_readme_markers_are_invalid(
    tmp_path: Path,
):
    (tmp_path / "README.md").write_text(
        "A\n<!-- generated:start -->\nold\n",
        encoding="utf-8",
    )
    (tmp_path / "README.zh-CN.md").write_text(
        "甲\n<!-- generated:start -->\n旧\n<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "overrides.toml").write_text(
        "[pinyin]\n", encoding="utf-8"
    )
    existing = generate.render_dictionary(
        "beijing.subway",
        "2026.06.01",
        [generate.DictRow("苹果园", "ping guo yuan", 1)],
    )
    existing_path = tmp_path / "beijing.subway.dict.yaml"
    existing_path.write_text(existing, encoding="utf-8")
    stale_path = tmp_path / "old.subway.dict.yaml"
    stale = "stale dictionary\n"
    stale_path.write_text(stale, encoding="utf-8")

    payloads = {
        "citylist.json": {
            "citylist": [
                {"spell": "beijing", "adcode": "1100", "cityname": "北京市"}
            ]
        },
        "1100_drw_beijing.json": {"l": [{"st": [{"n": "大坪"}]}]},
    }

    with pytest.raises(ValueError, match="README generated markers"):
        generate.generate_project(
            root=tmp_path,
            today="2026.06.16",
            fetch_json=lambda srhdata: payloads[srhdata],
        )

    assert existing_path.read_text(encoding="utf-8") == existing
    assert stale_path.read_text(encoding="utf-8") == stale
    assert not (tmp_path / "all.subway.dict.yaml").exists()


def test_generate_project_removes_only_stale_root_dictionaries(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "A\n<!-- generated:start -->\nold\n<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "README.zh-CN.md").write_text(
        "甲\n<!-- generated:start -->\n旧\n<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "overrides.toml").write_text(
        "[pinyin]\n", encoding="utf-8"
    )
    stale_path = tmp_path / "old.subway.dict.yaml"
    stale_path.write_text("old\n", encoding="utf-8")
    unrelated_path = tmp_path / "notes.txt"
    unrelated_path.write_text("keep\n", encoding="utf-8")
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested_dictionary = nested_dir / "old.subway.dict.yaml"
    nested_dictionary.write_text("keep nested\n", encoding="utf-8")

    payloads = {
        "citylist.json": {
            "citylist": [
                {"spell": "beijing", "adcode": "1100", "cityname": "北京市"}
            ]
        },
        "1100_drw_beijing.json": {"l": [{"st": [{"n": "苹果园"}]}]},
    }

    generate.generate_project(
        root=tmp_path,
        today="2026.06.16",
        fetch_json=lambda srhdata: payloads[srhdata],
    )

    assert not stale_path.exists()
    assert unrelated_path.read_text(encoding="utf-8") == "keep\n"
    assert nested_dictionary.read_text(encoding="utf-8") == "keep nested\n"


def test_generate_project_preserves_dates_when_rows_and_city_list_are_unchanged(
    tmp_path: Path,
):
    # Seed files from a prior run.
    (tmp_path / "README.md").write_text(
        "A\n<!-- generated:start -->\nLast updated: 2026.06.01\n\n"
        "Supported cities and regions: 1\n\n- 北京市 (`beijing`)\n"
        "<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "README.zh-CN.md").write_text(
        "甲\n<!-- generated:start -->\n最后更新：2026.06.01\n\n"
        "支持城市和地区：1\n\n- 北京市（`beijing`）\n"
        "<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "overrides.toml").write_text(
        "[pinyin]\n", encoding="utf-8"
    )
    existing = generate.render_dictionary(
        "beijing.subway",
        "2026.06.01",
        [generate.DictRow("苹果园", "ping guo yuan", 1)],
    )
    (tmp_path / "beijing.subway.dict.yaml").write_text(existing, encoding="utf-8")
    existing_all = generate.render_dictionary(
        "all.subway",
        "2026.06.01",
        [generate.DictRow("苹果园", "ping guo yuan", 1)],
    )
    (tmp_path / "all.subway.dict.yaml").write_text(existing_all, encoding="utf-8")

    payloads = {
        "citylist.json": {
            "citylist": [
                {"spell": "beijing", "adcode": "1100", "cityname": "北京市"}
            ]
        },
        "1100_drw_beijing.json": {"l": [{"st": [{"n": "苹果园"}]}]},
    }

    generate.generate_project(
        root=tmp_path,
        today="2026.06.16",
        fetch_json=lambda srhdata: payloads[srhdata],
    )

    assert 'version: "2026.06.01"' in (
        tmp_path / "beijing.subway.dict.yaml"
    ).read_text(encoding="utf-8")
    assert "Last updated: 2026.06.01" in (tmp_path / "README.md").read_text(
        encoding="utf-8"
    )


def test_generate_project_preserves_date_from_generated_block_only(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "Prose Last updated: 2026.01.01\n"
        "<!-- generated:start -->\nLast updated: 2026.06.01\n\n"
        "Supported cities and regions: 1\n\n- 北京市 (`beijing`)\n"
        "<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "README.zh-CN.md").write_text(
        "甲\n<!-- generated:start -->\n最后更新：2026.06.01\n\n"
        "支持城市和地区：1\n\n- 北京市（`beijing`）\n"
        "<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "overrides.toml").write_text(
        "[pinyin]\n", encoding="utf-8"
    )
    existing = generate.render_dictionary(
        "beijing.subway",
        "2026.06.01",
        [generate.DictRow("苹果园", "ping guo yuan", 1)],
    )
    (tmp_path / "beijing.subway.dict.yaml").write_text(existing, encoding="utf-8")
    existing_all = generate.render_dictionary(
        "all.subway",
        "2026.06.01",
        [generate.DictRow("苹果园", "ping guo yuan", 1)],
    )
    (tmp_path / "all.subway.dict.yaml").write_text(existing_all, encoding="utf-8")

    payloads = {
        "citylist.json": {
            "citylist": [
                {"spell": "beijing", "adcode": "1100", "cityname": "北京市"}
            ]
        },
        "1100_drw_beijing.json": {"l": [{"st": [{"n": "苹果园"}]}]},
    }

    generate.generate_project(
        root=tmp_path,
        today="2026.06.16",
        fetch_json=lambda srhdata: payloads[srhdata],
    )

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Prose Last updated: 2026.01.01" in readme
    assert "Last updated: 2026.06.01" in readme


def test_generate_project_updates_readme_date_when_city_list_changes(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "A\n<!-- generated:start -->\nLast updated: 2026.06.01\n\n"
        "Supported cities and regions: 1\n\n- 北京市 (`beijing`)\n"
        "<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "README.zh-CN.md").write_text(
        "甲\n<!-- generated:start -->\n最后更新：2026.06.01\n\n"
        "支持城市和地区：1\n\n- 北京市（`beijing`）\n"
        "<!-- generated:end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "overrides.toml").write_text(
        "[pinyin]\n", encoding="utf-8"
    )
    existing = generate.render_dictionary(
        "beijing.subway",
        "2026.06.01",
        [generate.DictRow("苹果园", "ping guo yuan", 1)],
    )
    (tmp_path / "beijing.subway.dict.yaml").write_text(existing, encoding="utf-8")
    existing_all = generate.render_dictionary(
        "all.subway",
        "2026.06.01",
        [generate.DictRow("苹果园", "ping guo yuan", 1)],
    )
    (tmp_path / "all.subway.dict.yaml").write_text(existing_all, encoding="utf-8")

    payloads = {
        "citylist.json": {
            "citylist": [
                {"spell": "beijing", "adcode": "1100", "cityname": "北京"}
            ]
        },
        "1100_drw_beijing.json": {"l": [{"st": [{"n": "苹果园"}]}]},
    }

    generate.generate_project(
        root=tmp_path,
        today="2026.06.16",
        fetch_json=lambda srhdata: payloads[srhdata],
    )

    assert 'version: "2026.06.01"' in (
        tmp_path / "beijing.subway.dict.yaml"
    ).read_text(encoding="utf-8")
    assert "Last updated: 2026.06.16" in (tmp_path / "README.md").read_text(
        encoding="utf-8"
    )
    assert "- 北京 (`beijing`)" in (tmp_path / "README.md").read_text(
        encoding="utf-8"
    )


def test_readmes_have_generated_markers():
    for path in [Path("README.md"), Path("README.zh-CN.md")]:
        text = path.read_text(encoding="utf-8")
        assert generate.GENERATED_START in text
        assert generate.GENERATED_END in text


def test_github_workflow_runs_generate_and_pytest():
    workflow = Path(".github/workflows/update.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "cron:" in workflow
    assert "python -m scripts.generate" in workflow
    assert "pytest" in workflow
    assert "contents: write" in workflow
