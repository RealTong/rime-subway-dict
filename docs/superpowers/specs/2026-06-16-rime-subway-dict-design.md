# Rime Subway Dictionary Design

## Goal

Build an open source Rime dictionary project that helps users input city subway station names more accurately.

The project generates Rime `.dict.yaml` files from AMap subway data. It outputs one dictionary per city and one deduplicated all-in-one dictionary. Generated dictionary files are committed at the repository root so users can download them directly through GitHub Raw, a CDN, or a mirror.

## Scope

The first version will:

- Fetch the current city list from AMap's public subway endpoint.
- Fetch station data for every city or region returned by that city list.
- Generate root-level Rime dictionary files named `<city-spell>.subway.dict.yaml`.
- Generate `all.subway.dict.yaml` from all station names with global deduplication.
- Generate entries only from original AMap station names.
- Use `pypinyin` for normalized full-pinyin output.
- Support manual pinyin corrections through `scripts/overrides.toml`.
- Use a fixed weight of `1` for every entry.
- Update README generated sections with supported cities and generation time.
- Run automatically through GitHub Actions on a weekly schedule and by manual dispatch.

The first version will not:

- Generate additional `<station-name>站` entries.
- Filter stations by AMap status fields such as `su`.
- Commit raw AMap JSON responses or separate metadata JSON files.
- Implement city popularity ranking, transfer-station weighting, or custom sorting beyond Rime's configured dictionary sorting.

## Data Source

The generator uses AMap's public subway web endpoint:

- City list: `https://map.amap.com/service/subway?srhdata=citylist.json`
- City station data: `https://map.amap.com/service/subway?srhdata=<adcode>_drw_<spell>.json`

The city list currently returns objects with:

- `spell`: city identifier used in the station JSON filename and generated dictionary filename.
- `adcode`: administrative code used in the station JSON filename.
- `cityname`: display name for README support lists.

Station data is organized as line objects under `.l[]`, with stations under `.l[].st[]`. The station name is read from `n`. AMap's `sp` field is not used as the primary pinyin source because it mixes formats such as CamelCase, title case, and space-separated lowercase.

## Dictionary Output

Generated dictionary files are placed at the repository root:

```text
all.subway.dict.yaml
beijing.subway.dict.yaml
shanghai.subway.dict.yaml
...
```

Each file uses a dictionary name that matches the filename prefix:

```yaml
# Rime dictionary
# encoding: utf-8
#
#---
name: beijing.subway
version: "2026.06.16"
sort: by_weight
use_preset_vocabulary: true
...
```

Entries use exactly three tab-separated fields:

```text
苹果园	ping guo yuan	1
金安桥	jin an qiao	1
```

The generator must preserve the distinction between spaces and tabs:

- Spaces separate pinyin syllables inside the second field.
- Tabs separate Rime fields.

## Deduplication

Per-city dictionaries deduplicate by station name because transfer stations appear under multiple lines in AMap data.

The all-in-one dictionary also deduplicates globally by station name. If the same station name appears in multiple cities, only one entry is emitted in `all.subway.dict.yaml`.

## Pinyin Strategy

The generator uses `pypinyin` to generate normalized full pinyin for station names:

- Lowercase output.
- Syllables separated by single spaces.
- No tone marks or tone numbers.

Manual corrections live in `scripts/overrides.toml`. The override file maps station names to exact pinyin strings. Overrides are applied after station names are collected and before dictionary rows are rendered.

Example:

```toml
[pinyin]
"重庆北站南广场" = "chong qing bei zhan nan guang chang"
```

Overrides are intentionally simple and global. If a future station name needs different pronunciations in different cities, that can be addressed in a later version with city-scoped overrides.

## Project Structure

```text
README.md
README.zh-CN.md
LICENSE
pyproject.toml
all.subway.dict.yaml
beijing.subway.dict.yaml
...
scripts/
  __init__.py
  generate.py
  overrides.toml
tests/
  test_generate.py
.github/
  workflows/update.yml
```

Responsibilities:

- `scripts/generate.py`: fetch AMap data, extract station names, generate pinyin, write dictionaries, update README generated blocks.
- `scripts/overrides.toml`: manual pinyin corrections.
- `tests/test_generate.py`: focused tests for dictionary rendering, deduplication, override application, and README block updates.
- `.github/workflows/update.yml`: scheduled and manual update workflow.
- `README.md`: default English documentation with generated support data.
- `README.zh-CN.md`: Chinese documentation with generated support data.

## README Generated Blocks

Both README files include a generated block:

```markdown
<!-- generated:start -->
...
<!-- generated:end -->
```

The generator replaces only the content inside this block. The generated content includes:

- Last generated date.
- Total supported city or region count.
- Supported city or region list.

Manual README content outside the generated block is preserved.

## GitHub Actions

The update workflow runs:

- Weekly on a cron schedule.
- Manually through `workflow_dispatch`.

Workflow steps:

1. Check out the repository.
2. Set up Python.
3. Install project and test dependencies.
4. Run `python -m scripts.generate`.
5. Run `pytest`.
6. Commit and push only if generated files changed.

The workflow does not commit raw fetched data. It commits only dictionary files and README generated block updates.

## Error Handling

The generator should fail fast when:

- The city list cannot be fetched or parsed.
- A city station response cannot be fetched or parsed.
- A station record does not contain a usable station name.
- Dictionary rendering would create malformed tab-separated rows.
- README generated markers are missing.

Network errors should include the target `srhdata` value in the error message so failed city updates can be diagnosed quickly.

## Testing

Tests cover:

- Dictionary headers contain the expected Rime fields.
- Entry rows are tab-separated with exactly three fields.
- Pinyin syllables are space-separated within the second field.
- Per-city duplicate station names are removed.
- Global duplicate station names are removed from `all.subway.dict.yaml`.
- `scripts/overrides.toml` values override generated pinyin.
- README generated blocks are replaced without modifying surrounding content.

Tests should avoid hitting live AMap endpoints. Network-facing behavior can be covered through small sample payloads and dependency-injected fetch functions.

## User Installation Model

Users download one or more root-level `.dict.yaml` files and include them from their Rime configuration.

The README documents:

- What the project does.
- Data source and caveats.
- How to use a city dictionary.
- How to use the all-in-one dictionary.
- Supported city or region list.
- Last generation date.
- How to report incorrect pinyin or missing station names.

## License and Data Notice

Project code is licensed under MIT.

README documentation should clearly state:

- The generator is open source.
- Station names are generated from AMap public subway data.
- The dictionaries are intended for Rime input assistance.
- If the data source becomes unavailable or its terms change, the project may adjust or stop automatic updates.
