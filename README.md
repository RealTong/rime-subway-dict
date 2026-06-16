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
