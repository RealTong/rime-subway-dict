# Rime 地铁词典

Rime 地铁词典用于为地铁站名称生成自定义 Rime 词典。

<!-- generated:start -->
生成内容将由 `python -m scripts.generate` 更新。
<!-- generated:end -->

## 使用方法

下载仓库根目录下的 `*.subway.dict.yaml` 文件，并在你的 Rime 配置中引用。

如果只需要较小词库，可以使用城市文件，例如 `beijing.subway.dict.yaml`；如果需要所有已支持城市和地区，可以使用 `all.subway.dict.yaml`。

## 数据来源

站点名称由高德地图公开地铁网页数据生成。这些词典仅用于辅助 Rime 输入。如果数据源不可用或其条款发生变化，本项目可能调整或停止自动更新。

## 贡献

如发现缺失站点或拼音错误，请通过 issue 反馈。拼音修正维护在 `scripts/overrides.toml`。

## 许可证

MIT
