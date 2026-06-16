# Rime Subway Dictionary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight Python project that generates Rime subway station dictionaries from AMap subway data.

**Architecture:** A single Python module under `scripts/` owns fetching, parsing, pinyin generation, dictionary rendering, README block updates, and root-level file writes. Tests use injected sample payloads and temporary directories so they do not hit live AMap endpoints. GitHub Actions runs the same generator and tests weekly, then commits only real generated-output changes.

**Tech Stack:** Python 3.11+, standard library `urllib`/`json`/`tomllib`, `pypinyin`, `pytest`, GitHub Actions.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-06-16-rime-subway-dict-design.md`
- Use @test-driven-development for each implementation task.
- Use @subagent-driven-development for execution.

## File Structure

Create or modify these files:

- `pyproject.toml`: project metadata, runtime dependency on `pypinyin`, pytest extra/config.
- `scripts/__init__.py`: package marker for `python -m scripts.generate`.
- `scripts/generate.py`: generator implementation and CLI entrypoint.
- `scripts/overrides.toml`: global station-name-to-pinyin override table.
- `tests/test_generate.py`: unit tests for parsing, rendering, deduplication, overrides, README replacement, and date preservation.
- `README.md`: default English README with generated block.
- `README.zh-CN.md`: Chinese README with generated block.
- `LICENSE`: MIT license.
- `.github/workflows/update.yml`: scheduled/manual generator workflow.
- Root `*.subway.dict.yaml`: generated output from the live AMap run.

Generated-file behavior:

- Keep generated dictionaries at repository root.
- Write city dictionaries in ascending `spell` order.
- Write `all.subway.dict.yaml`.
- Delete stale root-level `*.subway.dict.yaml` files whose names are no longer in the generated set.
- Preserve existing dictionary `version` dates when entry rows are unchanged.
- Preserve README "Last updated" date when station rows and city list are unchanged.

## Task 1: Project Scaffolding and Documentation Shell

**Files:**
- Create: `pyproject.toml`
- Create: `scripts/__init__.py`
- Create: `scripts/overrides.toml`
- Create: `README.md`
- Create: `README.zh-CN.md`
- Create: `LICENSE`
- Create: `.gitignore`

- [ ] **Step 1: Write the initial scaffold files**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "rime-subway-dict"
version = "0.1.0"
description = "Generate Rime dictionaries for subway station names."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = [
  "pypinyin>=0.51",
]

[project.optional-dependencies]
test = [
  "pytest>=8",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `scripts/__init__.py` as an empty file.

Create `scripts/overrides.toml`:

```toml
[pinyin]
```

Create `.gitignore`:

```gitignore
__pycache__/
.pytest_cache/
.venv/
*.pyc
```

Create README files with generated markers. `README.md` must be the default English document and include:

```markdown
# Rime Subway Dictionary

Rime Subway Dictionary generates custom Rime dictionaries for subway station names.

<!-- generated:start -->
Generated content will be updated by `python -m scripts.generate`.
<!-- generated:end -->

## Usage

Download a root-level `*.subway.dict.yaml` file and reference it from your Rime configuration.

Use a city file such as `beijing.subway.dict.yaml` for a smaller dictionary, or `all.subway.dict.yaml` for all supported cities and regions.

## Data Source

Station names are generated from AMap public subway web data. The dictionaries are intended only for Rime input assistance. If the data source becomes unavailable or its terms change, this project may adjust or stop automatic updates.

## Contributing

Report missing stations or incorrect pinyin through an issue. Pinyin corrections are maintained in `scripts/overrides.toml`.

## License

MIT
```

Create `README.zh-CN.md` with equivalent Chinese content and the same generated markers.

Create `LICENSE` using the MIT license text and copyright holder:

```text
MIT License

Copyright (c) 2026 realtong

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Run a basic sanity command**

Run: `python -m pip install -e ".[test]"`

Expected: dependencies install successfully.

- [ ] **Step 3: Commit scaffold**

```bash
git add pyproject.toml scripts/__init__.py scripts/overrides.toml README.md README.zh-CN.md LICENSE .gitignore
git commit -m "chore: scaffold python rime dictionary project"
```

## Task 2: Pure Parsing, Rendering, and README Unit Tests

**Files:**
- Create: `tests/test_generate.py`
- Create/Modify: `scripts/generate.py`

- [ ] **Step 1: Write failing tests for pure behavior**

Create `tests/test_generate.py` with tests like:

```python
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

    assert generate.extract_station_names(payload, "1100_drw_beijing.json") == {"苹果园", "金安桥"}


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

    assert updated == "Before\n<!-- generated:start -->\nnew\n<!-- generated:end -->\nAfter\n"


def test_load_overrides_reads_pinyin_table(tmp_path: Path):
    path = tmp_path / "overrides.toml"
    path.write_text('[pinyin]\n"重庆" = "chong qing"\n', encoding="utf-8")

    assert generate.load_overrides(path) == {"重庆": "chong qing"}
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: `pytest tests/test_generate.py -v`

Expected: FAIL because `scripts/generate.py` does not exist or functions are missing.

- [ ] **Step 3: Implement minimal pure generator functions**

Create `scripts/generate.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib

from pypinyin import lazy_pinyin


GENERATED_START = "<!-- generated:start -->"
GENERATED_END = "<!-- generated:end -->"


@dataclass(frozen=True)
class City:
    spell: str
    adcode: str
    cityname: str

    @property
    def srhdata(self) -> str:
        return f"{self.adcode}_drw_{self.spell}.json"

    @property
    def dictionary_name(self) -> str:
        return f"{self.spell}.subway"

    @property
    def dictionary_path_name(self) -> str:
        return f"{self.dictionary_name}.dict.yaml"


@dataclass(frozen=True, order=True)
class DictRow:
    name: str
    pinyin: str
    weight: int = 1


def parse_cities(payload: dict) -> list[City]:
    raw_cities = payload.get("citylist")
    if not isinstance(raw_cities, list):
        raise ValueError("citylist payload missing list field")
    cities: list[City] = []
    for raw in raw_cities:
        try:
            spell = str(raw["spell"]).strip()
            adcode = str(raw["adcode"]).strip()
            cityname = str(raw["cityname"]).strip()
        except KeyError as exc:
            raise ValueError(f"citylist item missing field: {exc}") from exc
        if not spell or not adcode or not cityname:
            raise ValueError(f"citylist item has empty field: {raw!r}")
        cities.append(City(spell=spell, adcode=adcode, cityname=cityname))
    return sorted(cities, key=lambda city: city.spell)


def extract_station_names(payload: dict, srhdata: str) -> set[str]:
    lines = payload.get("l")
    if not isinstance(lines, list):
        raise ValueError(f"{srhdata}: station payload missing line list")
    names: set[str] = set()
    for line_index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise ValueError(f"{srhdata}: line {line_index} is not an object")
        stations = line.get("st")
        if not isinstance(stations, list):
            raise ValueError(f"{srhdata}: line {line_index} missing station list")
        for station_index, station in enumerate(stations):
            if not isinstance(station, dict):
                raise ValueError(f"{srhdata}: station {line_index}/{station_index} is not an object")
            raw_name = station.get("n")
            if not isinstance(raw_name, str):
                raise ValueError(f"{srhdata}: station {line_index}/{station_index} missing usable name")
            name = raw_name.strip()
            if not name:
                raise ValueError(f"{srhdata}: station {line_index}/{station_index} missing usable name")
            names.add(name)
    return names


def normalize_pinyin(value: str) -> str:
    return re.sub(r"\\s+", " ", value.strip().lower())


def pinyin_for_name(name: str, overrides: dict[str, str]) -> str:
    if name in overrides:
        return normalize_pinyin(overrides[name])
    return normalize_pinyin(" ".join(lazy_pinyin(name)))


def build_rows(names: set[str], overrides: dict[str, str]) -> list[DictRow]:
    rows = [DictRow(name=name, pinyin=pinyin_for_name(name, overrides), weight=1) for name in names]
    return sorted(rows, key=lambda row: (row.pinyin, row.name))


def validate_row(row: DictRow) -> None:
    if not row.name.strip() or not row.pinyin.strip():
        raise ValueError(f"malformed dictionary row: {row!r}")
    if any(separator in row.name for separator in "\t\r\n"):
        raise ValueError(f"malformed dictionary row: {row!r}")
    if any(separator in row.pinyin for separator in "\t\r\n"):
        raise ValueError(f"malformed dictionary row: {row!r}")


def render_dictionary(dictionary_name: str, version: str, rows: list[DictRow]) -> str:
    header = (
        "# Rime dictionary\\n"
        "# encoding: utf-8\\n"
        "#\\n"
        "---\\n"
        f"name: {dictionary_name}\\n"
        f'version: "{version}"\\n'
        "sort: by_weight\\n"
        "use_preset_vocabulary: true\\n"
        "...\\n\\n"
    )
    for row in rows:
        validate_row(row)
    body = "".join(f"{row.name}\\t{row.pinyin}\\t{row.weight}\\n" for row in rows)
    return header + body


def load_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    pinyin = data.get("pinyin", {})
    if not isinstance(pinyin, dict):
        raise ValueError("overrides.toml [pinyin] must be a table")
    return {str(name): normalize_pinyin(str(value)) for name, value in pinyin.items()}


def replace_generated_block(markdown: str, generated: str) -> str:
    start = markdown.find(GENERATED_START)
    end = markdown.find(GENERATED_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("README generated markers are missing or invalid")
    before = markdown[: start + len(GENERATED_START)]
    after = markdown[end:]
    return f"{before}\\n{generated.rstrip()}\\n{after}"
```

- [ ] **Step 4: Run tests and confirm they pass**

Run: `pytest tests/test_generate.py -v`

Expected: PASS.

- [ ] **Step 5: Commit pure generator behavior**

```bash
git add scripts/generate.py tests/test_generate.py
git commit -m "feat: add dictionary rendering primitives"
```

## Task 3: Fetching, File Writes, Date Preservation, and CLI

**Files:**
- Modify: `scripts/generate.py`
- Modify: `tests/test_generate.py`

- [ ] **Step 1: Add failing integration-style tests without network**

Append tests that inject fake fetch data and use a temp output directory:

```python
def test_generate_project_writes_city_all_and_readmes(tmp_path: Path):
    (tmp_path / "README.md").write_text("A\n<!-- generated:start -->\nold\n<!-- generated:end -->\n", encoding="utf-8")
    (tmp_path / "README.zh-CN.md").write_text("甲\n<!-- generated:start -->\n旧\n<!-- generated:end -->\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "overrides.toml").write_text('[pinyin]\n"重庆" = "chong qing"\n', encoding="utf-8")

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
    assert "Last updated: 2026.06.16" in (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "最后更新：2026.06.16" in (tmp_path / "README.zh-CN.md").read_text(encoding="utf-8")


def test_generate_project_preserves_dates_when_rows_and_city_list_are_unchanged(tmp_path: Path):
    # Seed files from a prior run.
    (tmp_path / "README.md").write_text("A\n<!-- generated:start -->\nLast updated: 2026.06.01\n\nSupported cities and regions: 1\n\n- 北京市 (`beijing`)\n<!-- generated:end -->\n", encoding="utf-8")
    (tmp_path / "README.zh-CN.md").write_text("甲\n<!-- generated:start -->\n最后更新：2026.06.01\n\n支持城市和地区：1\n\n- 北京市（`beijing`）\n<!-- generated:end -->\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "overrides.toml").write_text("[pinyin]\n", encoding="utf-8")
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
        "citylist.json": {"citylist": [{"spell": "beijing", "adcode": "1100", "cityname": "北京市"}]},
        "1100_drw_beijing.json": {"l": [{"st": [{"n": "苹果园"}]}]},
    }

    generate.generate_project(root=tmp_path, today="2026.06.16", fetch_json=lambda srhdata: payloads[srhdata])

    assert 'version: "2026.06.01"' in (tmp_path / "beijing.subway.dict.yaml").read_text(encoding="utf-8")
    assert "Last updated: 2026.06.01" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_generate_project_updates_readme_date_when_city_list_changes(tmp_path: Path):
    (tmp_path / "README.md").write_text("A\n<!-- generated:start -->\nLast updated: 2026.06.01\n\nSupported cities and regions: 1\n\n- 北京市 (`beijing`)\n<!-- generated:end -->\n", encoding="utf-8")
    (tmp_path / "README.zh-CN.md").write_text("甲\n<!-- generated:start -->\n最后更新：2026.06.01\n\n支持城市和地区：1\n\n- 北京市（`beijing`）\n<!-- generated:end -->\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "overrides.toml").write_text("[pinyin]\n", encoding="utf-8")
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
        "citylist.json": {"citylist": [{"spell": "beijing", "adcode": "1100", "cityname": "北京"}]},
        "1100_drw_beijing.json": {"l": [{"st": [{"n": "苹果园"}]}]},
    }

    generate.generate_project(root=tmp_path, today="2026.06.16", fetch_json=lambda srhdata: payloads[srhdata])

    assert 'version: "2026.06.01"' in (tmp_path / "beijing.subway.dict.yaml").read_text(encoding="utf-8")
    assert "Last updated: 2026.06.16" in (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "- 北京 (`beijing`)" in (tmp_path / "README.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests and confirm new tests fail**

Run: `pytest tests/test_generate.py -v`

Expected: FAIL because `generate_project` and supporting functions are missing.

- [ ] **Step 3: Implement fetch, write, preservation, and CLI**

Add to `scripts/generate.py`:

```python
import argparse
import json
from datetime import datetime
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


AMAP_SUBWAY_URL = "https://map.amap.com/service/subway"


def today_version() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y.%m.%d")


def fetch_json(srhdata: str, timeout: int = 30) -> dict:
    url = f"{AMAP_SUBWAY_URL}?srhdata={srhdata}"
    request = Request(url, headers={"accept": "application/json, text/javascript, */*; q=0.01"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"failed to fetch or parse AMap subway data for {srhdata}") from exc


def extract_entry_lines(dictionary_text: str) -> list[str]:
    marker = "...\\n"
    if marker not in dictionary_text:
        return []
    return [line for line in dictionary_text.split(marker, 1)[1].splitlines() if line.strip()]


def extract_version(dictionary_text: str) -> str | None:
    match = re.search(r'^version:\\s*"([^"]+)"\\s*$', dictionary_text, re.MULTILINE)
    return match.group(1) if match else None


def choose_version(path: Path, dictionary_name: str, today: str, rows: list[DictRow]) -> str:
    if not path.exists():
        return today
    existing = path.read_text(encoding="utf-8")
    existing_rows = extract_entry_lines(existing)
    new_rows = extract_entry_lines(render_dictionary(dictionary_name, today, rows))
    if existing_rows == new_rows:
        return extract_version(existing) or today
    return today


def build_readme_block(cities: list[City], last_updated: str, language: str) -> str:
    if language == "zh":
        lines = [f"最后更新：{last_updated}", "", f"支持城市和地区：{len(cities)}", ""]
        lines.extend(f"- {city.cityname}（`{city.spell}`）" for city in cities)
        return "\\n".join(lines)
    lines = [f"Last updated: {last_updated}", "", f"Supported cities and regions: {len(cities)}", ""]
    lines.extend(f"- {city.cityname} (`{city.spell}`)" for city in cities)
    return "\\n".join(lines)


def extract_readme_date(markdown: str, language: str) -> str | None:
    pattern = r"最后更新：([0-9]{4}\\.[0-9]{2}\\.[0-9]{2})" if language == "zh" else r"Last updated: ([0-9]{4}\\.[0-9]{2}\\.[0-9]{2})"
    match = re.search(pattern, markdown)
    return match.group(1) if match else None


def extract_generated_block(markdown: str) -> str:
    start = markdown.find(GENERATED_START)
    end = markdown.find(GENERATED_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("README generated markers are missing or invalid")
    return markdown[start + len(GENERATED_START) : end].strip()


def choose_readme_date(markdown: str, cities: list[City], today: str, language: str, dictionaries_changed: bool) -> str:
    existing_date = extract_readme_date(markdown, language)
    if not existing_date or dictionaries_changed:
        return today
    existing_block = extract_generated_block(markdown)
    expected_block = build_readme_block(cities, existing_date, language).strip()
    return existing_date if existing_block == expected_block else today


def write_text(path: Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def generate_project(root: Path, today: str | None = None, fetch_json: Callable[[str], dict] = fetch_json) -> None:
    today = today or today_version()
    overrides = load_overrides(root / "scripts" / "overrides.toml")
    cities = parse_cities(fetch_json("citylist.json"))
    city_rows: dict[City, list[DictRow]] = {}
    all_names: set[str] = set()

    for city in cities:
        names = extract_station_names(fetch_json(city.srhdata), city.srhdata)
        all_names.update(names)
        city_rows[city] = build_rows(names, overrides)

    generated_paths: set[Path] = {root / "all.subway.dict.yaml"}
    any_output_changed = False
    for city in cities:
        path = root / city.dictionary_path_name
        generated_paths.add(path)
        rows = city_rows[city]
        version = choose_version(path, city.dictionary_name, today, rows)
        any_output_changed |= write_text(path, render_dictionary(city.dictionary_name, version, rows))

    all_rows = build_rows(all_names, overrides)
    all_path = root / "all.subway.dict.yaml"
    all_version = choose_version(all_path, "all.subway", today, all_rows)
    any_output_changed |= write_text(all_path, render_dictionary("all.subway", all_version, all_rows))

    for path in root.glob("*.subway.dict.yaml"):
        if path not in generated_paths:
            path.unlink()
            any_output_changed = True

    for readme_name, language in [("README.md", "en"), ("README.zh-CN.md", "zh")]:
        readme_path = root / readme_name
        markdown = readme_path.read_text(encoding="utf-8")
        readme_date = choose_readme_date(markdown, cities, today, language, any_output_changed)
        block = build_readme_block(cities, readme_date, language)
        write_text(readme_path, replace_generated_block(markdown, block))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Rime subway dictionaries.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    generate_project(args.root)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests and confirm they pass**

Run: `pytest tests/test_generate.py -v`

Expected: PASS.

- [ ] **Step 5: Commit generator orchestration**

```bash
git add scripts/generate.py tests/test_generate.py
git commit -m "feat: add amap generation workflow"
```

## Task 4: GitHub Actions and Documentation Tests

**Files:**
- Create: `.github/workflows/update.yml`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `tests/test_generate.py`

- [ ] **Step 1: Add failing tests for README marker presence and workflow file**

Append:

```python
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
```

- [ ] **Step 2: Run tests and confirm workflow test fails**

Run: `pytest tests/test_generate.py -v`

Expected: FAIL because `.github/workflows/update.yml` does not exist.

- [ ] **Step 3: Add workflow**

Create `.github/workflows/update.yml`:

```yaml
name: Update dictionaries

on:
  workflow_dispatch:
  schedule:
    - cron: "17 20 * * 0"

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: python -m pip install -e ".[test]"

      - name: Generate dictionaries
        run: python -m scripts.generate

      - name: Run tests
        run: pytest

      - name: Commit generated changes
        run: |
          if git diff --quiet; then
            echo "No generated changes."
            exit 0
          fi
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A -- README.md README.zh-CN.md '*.subway.dict.yaml'
          git commit -m "chore: update subway dictionaries"
          git push
```

- [ ] **Step 4: Run tests and confirm they pass**

Run: `pytest tests/test_generate.py -v`

Expected: PASS.

- [ ] **Step 5: Commit workflow and docs shell**

```bash
git add .github/workflows/update.yml README.md README.zh-CN.md tests/test_generate.py
git commit -m "ci: add dictionary update workflow"
```

## Task 5: Live Generation and End-to-End Verification

**Files:**
- Modify: root `*.subway.dict.yaml`
- Modify: `README.md`
- Modify: `README.zh-CN.md`

- [ ] **Step 1: Run live generator**

Run: `python -m scripts.generate`

Expected: root-level `all.subway.dict.yaml` and one `<spell>.subway.dict.yaml` per AMap city are created. No raw AMap JSON or metadata JSON files are created.

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 3: Verify generated dictionary format**

Run:

```bash
python - <<'PY'
from pathlib import Path

files = sorted(Path('.').glob('*.subway.dict.yaml'))
assert files, 'no generated dictionary files'
assert Path('all.subway.dict.yaml') in files
for path in files:
    text = path.read_text(encoding='utf-8')
    assert '# Rime dictionary\n# encoding: utf-8\n#\n---\n' in text, path
    assert '\n...\n\n' in text, path
    for line in text.split('...\n\n', 1)[1].splitlines():
        if not line:
            continue
        parts = line.split('\t')
        assert len(parts) == 3, (path, line)
        assert parts[2] == '1', (path, line)
print(f'checked {len(files)} dictionary files')
PY
```

Expected: prints checked dictionary count and exits 0.

- [ ] **Step 4: Check stable regeneration**

Run:

```bash
git diff --stat
python -m scripts.generate
git diff --stat
```

Expected: the second generator run does not introduce additional date-only changes beyond the first generated output.

- [ ] **Step 5: Commit generated dictionaries**

```bash
git add -A -- README.md README.zh-CN.md '*.subway.dict.yaml'
git commit -m "chore: generate subway dictionaries"
```

## Task 6: Final Verification

**Files:**
- No intended file changes.

- [ ] **Step 1: Run clean full verification**

Run:

```bash
pytest -v
python -m scripts.generate
git diff --check
```

Expected:

- `pytest -v` passes.
- `python -m scripts.generate` exits 0.
- `git diff --check` reports no whitespace errors.

- [ ] **Step 2: Inspect final git state**

Run: `git status --short --branch`

Expected: clean working tree on the implementation branch, or only intentional generated diffs already committed.

- [ ] **Step 3: Summarize final outputs**

Report:

- Number of generated root-level `*.subway.dict.yaml` files.
- Whether `all.subway.dict.yaml` exists.
- Test command results.
- Any network/API caveats observed during live generation.
