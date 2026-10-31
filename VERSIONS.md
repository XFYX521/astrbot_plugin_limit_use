# 版本列表

插件：`astrbot_plugin_limit_use` · 作者：XFYX521 · 仓库：https://github.com/XFYX521/astrbot_plugin_limit_use

当前最新版本：**v2.0.1**（2026-10-31），tag `v2.0.1`

本文件与 `versions.json` 均由 `python scripts/gen_versions.py` 从 `CHANGELOG.md` 和 git 历史生成，请勿手改。

| 版本 | 日期 | 提交 | 主要变更 |
|:---|:---|:---|:---|
| v2.0.1 | 2026-10-31 | [c193226](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/c1932265a185af214232074d9d6b5025882ac089) | 🐛 修复 WebUI 只能看到「行情与投资」、无法切到「用户管理」：AstrBot 侧边栏默认扁平模式下每个插件只显示第一个视图 |
| v2.0.0 | 2026-10-31 | [ba0bcaf](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/ba0bcaf9ab6cb9366f2be65d71e762dd9a3067c8) | 💥 投资玩法重做：`/投资 <币种> <百分比>`，投入 = 当前余额的百分比（1–100，向下取整、最少 1 次），不再需要方向与杠杆 |
| v1.0.20 | 2026-10-31 | [ca3ec7e](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/ca3ec7eec8fd06dd5fda1fe59e7e58ddf565a51b) | 🎨 卡片改为满版绘制（无外边距、100% 宽高），字号再放大一档：标题 32px、正文 21–22px、表头 18px |
| v1.0.19 | 2026-10-31 | [afb39c6](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/afb39c604a9c50b35fa9a18f37fb507dfda4c4f0) | 🎨 优化 `/帮助`、`/投资` 卡片样式：字号整体放大，卡片填满画布并垂直居中，减少图片上下留白 |
| v1.0.18 | 2026-10-31 | [c9942fb](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/c9942fbdde1d2c9360740e54035950c22c27c42e) | ✨ 新增 `/投资`（投资模式）：用对话次数做多/做空，保证金交易结算，每日限 1 次 |
| v1.0.17 | 2026-10-31 | [709d83c](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/709d83c617c4ed81360edb0574449f4e8e4ddb6a) | 🐛 修复 weighted 签到在默认配置下恒得 0 次：`signin_weights` 默认值此前是字面量 `\n` 而非换行 |
| v1.0.16 | 2026-06-30 | [2d6cdf5](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/2d6cdf561a6dd34f45b0b47689133c3875112368) | ✨ 新增签到方式二（weighted）：自定义值+权重概率 |
| v1.0.15 | 2026-06-24 | [b01e843](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/b01e843c1e774edf6200515969b01f634b4d0299) | ✨ 新增 `/查看全部余额`（纯文本输出，格式：备注：剩余N；/帮助 不显示） |
| v1.0.14 | 2026-06-24 | [93076d8](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/93076d879fcc78082e33a43bbf725811fa84bb9e) | ✨ WebUI 用户列表新增「今日调用」列 |
| v1.0.13 | 2026-06-24 | [5b67407](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/5b674071208e050b05b8d8728bee42440f1b4c74) | ✨ 新增管理指令 `/查看全部余额`（仅管理员可用，/帮助 不显示） |
| v1.0.12 | 2026-06-23 | [83f16c2](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/83f16c24af0c170e963015546cb0d0e2adb6acee) | ✨ 签到奖励改为可配置的随机范围（daily_bonus_min / daily_bonus_max） |
| v1.0.11 | 2026-06-22 | [72132d0](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/72132d053ad868ecfcadcac6dd414c0dfa256648) | 💄 Token 显示优化：≥1000 显示 K，≥1000000 显示 M（保留两位小数） |
| v1.0.10 | 2026-06-22 | [b72644e](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/b72644efce12a351f7a5369a5e2af4a055d83c3f) | 🐛 修复管理员不计入累积调用次数的问题 |
| v1.0.9 | 2026-06-22 | [1ad44b8](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/1ad44b86a33943e23dc332db9a446852e447022f) | ✨ 新增平均 Token 列（累积 Token ÷ 累积调用，以 k 为单位） |
| v1.0.8 | 2026-06-22 | [1e6556f](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/1e6556f7f0fba02f36fa1e0dc9b73986b29f6e2e) | 🐛 修复 Token 计量不准：明确取 prompt_tokens + completion_tokens（含缓存输入） |
| v1.0.7 | 2026-06-22 | [42df78e](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/42df78e2942f8178b3b8992a41d12dfd4d895f1f) | 💄 简化 WebUI：去掉「总消耗/当日消耗」Tab 切换 |
| v1.0.6 | 2026-06-22 | [94bc1f8](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/94bc1f8f3898a1c4c55e04ad3c030e1cb224a351) | ✨ 新增 Token 消耗统计 |
| v1.0.5 | 2026-06-22 | [b8b95a1](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/b8b95a1f254b82bc27dbc5cb25a26f0ccbfebeb3) | 🐛 修复中文备注显示为 URL 编码的问题（改用 query 参数传递） |
| v1.0.4 | 2026-06-22 | [e80a426](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/e80a4260fe2a2a044abea15a836cdb51845c5d88) | ✨ WebUI 新增用户备注功能，点击 QQ 号旁的备注即可编辑 |
| v1.0.3 | 2026-06-21 | [ee22c1c](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/ee22c1cffa47dc3eee9b1308fdc2a7e08ebeecc8) | ✨ 重新实现 WebUI 管理页面，显示用户列表 + 已调用/剩余次数 |
| v1.0.2 | 2026-06-21 | [92810dd](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/92810dd33ae675bc36e41717b5320f8703a60904) | 🐛 修复指令也被计入次数的问题（改用 `on_llm_request` 钩子） |
| v1.0.1 | 2026-06-21 | [0c29ccb](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/0c29ccbc5990702b6976015fa2052c4503abb62c) | 🐛 修复 `get_kv_data()` 缺少 `default` 参数导致的异常 |
| v1.0.0 | 2026-06-21 | [181525f](https://github.com/XFYX521/astrbot_plugin_limit_use/commit/181525f0930c790a79b892d886e9b7409be1c06a) | 🎉 初始版本 |

完整变更见 [CHANGELOG.md](CHANGELOG.md)。

## 作为插件源使用（自动更新检测）

`versions.json` 同时是一个可直接添加的 AstrBot 插件源 JSON（`$meta` + 根键 `XFYX521/astrbot_plugin_limit_use`）。在 WebUI「插件市场 → 插件源」中添加：

```text
https://raw.githubusercontent.com/XFYX521/astrbot_plugin_limit_use/master/versions.json
```

添加时 AstrBot 会先请求该地址并读取 `$meta.name` 作为源名称。

**只有 `install_method == "market"` 的安装才会显示「有新版本」**，这是 AstrBot 前端的固定门槛（`updates_enabled && install_source.install_method === "market"`）。从链接/文件安装的插件只会看到「强制重新安装」。因此：

1. 首次安装：添加上述插件源后，直接从该源安装本插件；
2. 已从链接安装：在插件详情中「更换插件源」（后端接口 `POST /api/plugin/plugins/<plugin_id>/source`）绑定到该源，绑定后刷新插件页即可。

更新检测的版本比较规则（前端 `has_update`）：市场记录 `version` 与已装 `metadata.yaml` 的 `version` 都须以 `v?数字` 开头，去掉 `v` 前缀后按 `.` 分段比较数字；市场版本更高时才提示更新。本文件的当前版本与 `metadata.yaml` 由同一脚本生成，天然一致。

## 插件市场记录（PluginRecord）

按插件市场 JSON 规范（[2026-06-27](https://docs.astrbot.app/dev/plugin-market/2026-06-27.html)）生成的当前版本 `PluginRecord`，可直接作为市场源根对象中 `XFYX521/astrbot_plugin_limit_use` 键的值：

```json
{
  "author": "XFYX521",
  "name": "astrbot_plugin_limit_use",
  "version": "v2.0.1",
  "repo": "https://github.com/XFYX521/astrbot_plugin_limit_use",
  "desc": "给 QQ 用户设置对话次数额度，次数用完后需签到补充；支持按余额百分比模拟行情投资。",
  "short_desc": "按用户限制对话次数，额度用完后签到补充。",
  "tags": [
    "对话次数",
    "签到",
    "额度"
  ],
  "category": "其他",
  "display_name": "对话次数限制",
  "support_platforms": [
    "aiocqhttp"
  ],
  "astrbot_version": ">=4.29.0,<5",
  "download_url": "https://github.com/XFYX521/astrbot_plugin_limit_use/archive/refs/tags/v2.0.1.zip",
  "updated_at": "2026-10-31T00:00:00Z"
}
```

## 发布新版本

1. 修改 `metadata.yaml` 的 `version`（如 `v1.0.18`），并在 `CHANGELOG.md` 顶部新增对应条目；
2. 在 `main.py` 不做版本号声明（版本只来自 `metadata.yaml`）；
3. 运行 `python scripts/gen_versions.py` 重新生成 `versions.json` 与 `VERSIONS.md`；
4. 提交后打同名 annotated tag 并推送：

   ```bash
   git tag -a v1.0.18 -m "v1.0.18"
   git push origin master --tags
   ```

5. 若同时维护官方市场记录：`version` 与 `metadata.yaml` 一致、`repo` 填 `https://github.com/XFYX521/astrbot_plugin_limit_use`、`download_url` 用最新版的 `zip_url`（需 tag 已推送）。

## 说明

- 市场规范里的 `PluginRecord` 只有一个 `version` 字段，多版本历史由 `versions.json` 的 `$meta.releases` 承载（AstrBot 会跳过整个 `$meta`，不会误当成插件条目）。
- `zip_url` 只在对应 tag 已推送时生成；未打 tag 的历史版本留空。
- `v1.0.3` 当时未单独修改 `metadata.yaml` 的 `version`（到 v1.0.4 提交才更新），其提交按提交信息定位，见 `scripts/gen_versions.py` 的 `VERSION_OVERRIDES`。
