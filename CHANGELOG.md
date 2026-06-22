# 更新日志

## v1.0.10

- 🐛 修复管理员不计入累积调用次数的问题

## v1.0.9

- ✨ 新增平均 Token 列（累积 Token ÷ 累积调用，以 k 为单位）
- ✨ 统计栏新增总体平均 Token

## v1.0.8

- 🐛 修复 Token 计量不准：明确取 prompt_tokens + completion_tokens（含缓存输入）
- 🔧 _extract_tokens 同时支持对象和字典格式的 usage

## v1.0.7

- 💄 简化 WebUI：去掉「总消耗/当日消耗」Tab 切换
- 💄 用户列表同时显示今日 Token 和累积 Token 两列

## v1.0.6

- ✨ 新增 Token 消耗统计
- ✨ WebUI 增加「总消耗 / 当日消耗」Tab 切换视图
- ✨ 顶部统计栏显示累积 Token 和今日 Token
- 🔧 新增 `on_llm_response` 钩子自动记录 Token

## v1.0.5

- 🐛 修复中文备注显示为 URL 编码的问题（改用 query 参数传递）

## v1.0.4

- ✨ WebUI 新增用户备注功能，点击 QQ 号旁的备注即可编辑
- 🔧 后端新增 `GET /remark/<uid>/<text>` API

## v1.0.3

- ✨ 重新实现 WebUI 管理页面，显示用户列表 + 已调用/剩余次数
- ✨ 支持 +10 / +1 / -1 / -10 快捷修改剩余次数
- 🔧 后端 Web API 改用纯路由参数，不依赖 `astrbot.api.web`

## v1.0.2

- 🐛 修复指令也被计入次数的问题（改用 `on_llm_request` 钩子）
- 🔧 只有真正调用 LLM 的对话才消耗次数
- 🔧 移除 `pages/` 目录，修复 WebUI "未找到该路由" 错误
- 🔧 重建静态 `pages/info/` 页面，无需后端 API

## v1.0.1

- 🐛 修复 `get_kv_data()` 缺少 `default` 参数导致的异常
- 🔧 移除 Web API / Pages 功能，兼容旧版 AstrBot
- 📝 完善 README 文档

## v1.0.0

- 🎉 初始版本
- 用户对话次数额度管理，每次对话 -1
- 次数用尽自动回复并阻止继续对话
- `/签到` 每日获取次数
- `/我的余额` 查询剩余次数
- `/帮助` 显示指令列表
- 管理员白名单免次数限制
