from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import tomllib
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from pypinyin import lazy_pinyin


AMAP_SUBWAY_URL = "https://map.amap.com/service/subway"
GENERATED_START = "<!-- generated:start -->"
GENERATED_END = "<!-- generated:end -->"
SAFE_SPELL_RE = re.compile(r"^[a-z0-9_]+$")


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


def today_version() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y.%m.%d")


def fetch_json(srhdata: str, timeout: int = 30) -> dict:
    url = f"{AMAP_SUBWAY_URL}?srhdata={srhdata}"
    request = Request(
        url,
        headers={"accept": "application/json, text/javascript, */*; q=0.01"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"failed to fetch or parse AMap subway data for {srhdata}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"AMap subway data for {srhdata} is not an object")
    return payload


def parse_cities(payload: object) -> list[City]:
    if not isinstance(payload, dict):
        raise ValueError("citylist payload must be an object")
    raw_cities = payload.get("citylist")
    if not isinstance(raw_cities, list):
        raise ValueError("citylist payload missing list field")
    cities: list[City] = []
    for raw in raw_cities:
        if not isinstance(raw, dict):
            raise ValueError(f"citylist item must be an object: {raw!r}")
        try:
            spell = raw["spell"]
            adcode = raw["adcode"]
            cityname = raw["cityname"]
        except KeyError as exc:
            raise ValueError(f"citylist item missing field: {exc}") from exc
        for field, value in (
            ("spell", spell),
            ("adcode", adcode),
            ("cityname", cityname),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"citylist item field must be a nonempty string: {field}"
                )
        spell = spell.strip()
        adcode = adcode.strip()
        cityname = cityname.strip()
        if not SAFE_SPELL_RE.fullmatch(spell):
            raise ValueError(f"citylist item has unsafe spell slug: {spell!r}")
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
                raise ValueError(
                    f"{srhdata}: station {line_index}/{station_index} is not an object"
                )
            raw_name = station.get("n")
            if not isinstance(raw_name, str):
                raise ValueError(
                    f"{srhdata}: station {line_index}/{station_index} "
                    "missing usable name"
                )
            name = raw_name.strip()
            if not name:
                raise ValueError(
                    f"{srhdata}: station {line_index}/{station_index} "
                    "missing usable name"
                )
            names.add(name)
    return names


def normalize_pinyin(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def pinyin_for_name(name: str, overrides: dict[str, str]) -> str:
    if name in overrides:
        return normalize_pinyin(overrides[name])
    return normalize_pinyin(" ".join(lazy_pinyin(name)))


def build_rows(names: set[str], overrides: dict[str, str]) -> list[DictRow]:
    rows = [
        DictRow(name=name, pinyin=pinyin_for_name(name, overrides), weight=1)
        for name in names
    ]
    return sorted(rows, key=lambda row: (row.pinyin, row.name))


def validate_row(row: DictRow) -> None:
    if not row.name.strip() or not row.pinyin.strip():
        raise ValueError(f"malformed dictionary row: {row!r}")
    if any(separator in row.name for separator in "\t\r\n"):
        raise ValueError(f"malformed dictionary row: {row!r}")
    if any(separator in row.pinyin for separator in "\t\r\n"):
        raise ValueError(f"malformed dictionary row: {row!r}")
    if type(row.weight) is not int or row.weight <= 0:
        raise ValueError(f"malformed dictionary row: {row!r}")


def render_dictionary(dictionary_name: str, version: str, rows: list[DictRow]) -> str:
    header = (
        "# Rime dictionary\n"
        "# encoding: utf-8\n"
        "#\n"
        "---\n"
        f"name: {dictionary_name}\n"
        f'version: "{version}"\n'
        "sort: by_weight\n"
        "use_preset_vocabulary: true\n"
        "...\n\n"
    )
    for row in rows:
        validate_row(row)
    body = "".join(f"{row.name}\t{row.pinyin}\t{row.weight}\n" for row in rows)
    return header + body


def load_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    pinyin = data.get("pinyin", {})
    if not isinstance(pinyin, dict):
        raise ValueError("overrides.toml [pinyin] must be a table")
    overrides: dict[str, str] = {}
    for name, value in pinyin.items():
        if not isinstance(name, str):
            raise ValueError("override name must be a string")
        if not name.strip():
            raise ValueError("override name must be nonempty")
        if name != name.strip():
            raise ValueError("override name must not have surrounding whitespace")
        if not isinstance(value, str):
            raise ValueError(f"override pinyin must be a string: {name}")
        normalized = normalize_pinyin(value)
        if not normalized:
            raise ValueError(f"override pinyin must be nonempty: {name}")
        overrides[name] = normalized
    return overrides


def replace_generated_block(markdown: str, generated: str) -> str:
    if markdown.count(GENERATED_START) != 1 or markdown.count(GENERATED_END) != 1:
        raise ValueError("README generated markers are missing or duplicated")
    start = markdown.find(GENERATED_START)
    end = markdown.find(GENERATED_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("README generated markers are missing or invalid")
    before = markdown[: start + len(GENERATED_START)]
    after = markdown[end:]
    return f"{before}\n{generated.rstrip()}\n{after}"


def extract_entry_lines(dictionary_text: str) -> list[str]:
    marker = "...\n"
    if marker not in dictionary_text:
        return []
    return [
        line
        for line in dictionary_text.split(marker, 1)[1].splitlines()
        if line.strip()
    ]


def extract_version(dictionary_text: str) -> str | None:
    match = re.search(r'^version:\s*"([^"]+)"\s*$', dictionary_text, re.MULTILINE)
    return match.group(1) if match else None


def choose_version(
    path: Path, dictionary_name: str, today: str, rows: list[DictRow]
) -> str:
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
        return "\n".join(lines)
    lines = [
        f"Last updated: {last_updated}",
        "",
        f"Supported cities and regions: {len(cities)}",
        "",
    ]
    lines.extend(f"- {city.cityname} (`{city.spell}`)" for city in cities)
    return "\n".join(lines)


def extract_readme_date(markdown: str, language: str) -> str | None:
    pattern = (
        r"最后更新：([0-9]{4}\.[0-9]{2}\.[0-9]{2})"
        if language == "zh"
        else r"Last updated: ([0-9]{4}\.[0-9]{2}\.[0-9]{2})"
    )
    match = re.search(pattern, markdown)
    return match.group(1) if match else None


def extract_generated_block(markdown: str) -> str:
    if markdown.count(GENERATED_START) != 1 or markdown.count(GENERATED_END) != 1:
        raise ValueError("README generated markers are missing or duplicated")
    start = markdown.find(GENERATED_START)
    end = markdown.find(GENERATED_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("README generated markers are missing or invalid")
    return markdown[start + len(GENERATED_START) : end].strip()


def choose_readme_date(
    markdown: str,
    cities: list[City],
    today: str,
    language: str,
    dictionaries_changed: bool,
) -> str:
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


def generate_project(
    root: Path,
    today: str | None = None,
    fetch_json: Callable[[str], dict] = fetch_json,
) -> None:
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
        any_output_changed |= write_text(
            path, render_dictionary(city.dictionary_name, version, rows)
        )

    all_rows = build_rows(all_names, overrides)
    all_path = root / "all.subway.dict.yaml"
    all_version = choose_version(all_path, "all.subway", today, all_rows)
    any_output_changed |= write_text(
        all_path, render_dictionary("all.subway", all_version, all_rows)
    )

    for path in root.glob("*.subway.dict.yaml"):
        if path not in generated_paths:
            path.unlink()
            any_output_changed = True

    for readme_name, language in [("README.md", "en"), ("README.zh-CN.md", "zh")]:
        readme_path = root / readme_name
        markdown = readme_path.read_text(encoding="utf-8")
        readme_date = choose_readme_date(
            markdown, cities, today, language, any_output_changed
        )
        block = build_readme_block(cities, readme_date, language)
        write_text(readme_path, replace_generated_block(markdown, block))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Rime subway dictionaries.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    generate_project(args.root)


if __name__ == "__main__":
    main()
