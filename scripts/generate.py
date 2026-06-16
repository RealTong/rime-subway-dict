from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib

from pypinyin import lazy_pinyin


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


def parse_cities(payload: dict) -> list[City]:
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
