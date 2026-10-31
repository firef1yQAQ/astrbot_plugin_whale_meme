# 表情包配图 (whale_meme)

给 AstrBot 的回复加表情包，并且不让同一个 emoji 刷屏。

## 功能

- 解析回复里的 `&&分类&&` 标记，替换成对应分类里随机一张图
- 没有标记时，按关键词匹配「用户这句话 + 回复内容」选分类，概率触发配图
- 自动扫描 `meme_manager` 目录下所有已装表情包，跨包随机
- 🐟 只有 2% 的概率保留一次，其余全部清除；`>_<` 一并清理

## 依赖

需要先安装 `meme_manager` 插件并导入至少一套表情包（目录：`data/plugin_data/meme_manager/packs`）。

## 安装

放进 `data/plugins/`，重启 AstrBot。适用于 AstrBot >= 4.0.0。
