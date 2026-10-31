# 版本列表

插件：`astrbot_plugin_limit_use` · 作者：XFYX521 · 仓库：https://github.com/XFYX521/astrbot_plugin_limit_use

当前最新版本：**v1.0.17**（2026-10-31），tag `v1.0.17`

本文件与 `versions.json` 均由 `python scripts/gen_versions.py` 从 `CHANGELOG.md` 和 git 历史生成，请勿手改。

| 版本 | 日期 | 提交 | 主要变更 |
|:---|:---|:---|:---|
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

## 市场记录（可直接使用）

按插件市场 JSON 规范（2026-06-27）生成的当前版本 `PluginRecord`，可直接合并进市场源根对象（根 key 即 `plugin_id`）：

```json
{
  "XFYX521/astrbot_plugin_limit_use": {
    "author": "XFYX521",
    "name": "astrbot_plugin_limit_use",
    "version": "v1.0.17",
    "repo": "https://github.com/XFYX521/astrbot_plugin_limit_use",
    "desc": "给 QQ 用户设置对话次数额度，次数用完后需签到补充。",
    "display_name": "对话次数限制",
    "support_platforms": [
      "aiocqhttp"
    ],
    "astrbot_version": ">=4.29.0,<5",
    "download_url": "https://github.com/XFYX521/astrbot_plugin_limit_use/archive/refs/tags/v1.0.17.zip"
  }
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

5. 更新插件市场记录：`version` 与 `metadata.yaml` 一致、`repo` 填
   `https://github.com/XFYX521/astrbot_plugin_limit_use`、可选 `download_url` 用 `versions.json` 里最新版的 `zip_url`。

## 说明

- 市场规范（[2026-06-27](https://docs.astrbot.app/dev/plugin-market/2026-06-27.html)）的 `PluginRecord` 只有一个 `version` 字段，多版本历史由本文件与 `versions.json` 承载。
- `zip_url` 只在对应 tag 已推送时生成；未打 tag 的历史版本留空。
- `v1.0.3` 当时未单独修改 `metadata.yaml` 的 `version`（到 v1.0.4 提交才更新），其提交按提交信息定位，见 `scripts/gen_versions.py` 的 `VERSION_OVERRIDES`。
