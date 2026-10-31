# astrbot_plugin_limit_use

一个 **AstrBot** 插件，为 QQ 用户设置对话次数额度，次数用完后需签到补充。

## 功能

- ✅ **次数限制** — 每个用户与 Bot 对话时，每次消耗 1 次额度
- ✅ **自动拦截** — 次数用完后自动回复指定内容，并阻止继续对话
- ✅ **每日签到** — 发送 `/签到` 领取每日奖励次数（固定范围或自定义权重两种模式）
- ✅ **余额查询** — 发送 `/我的余额` 查看剩余次数
- ✅ **帮助指令** — 发送 `/帮助` 查看所有可用指令
- ✅ **管理员免限** — 配置管理员 QQ 号列表，不限次数
- ✅ **WebUI 管理** — 在 AstrBot 管理面板的插件详情页中查看/修改各用户的次数数据

## 指令

| 指令 | 权限 | 说明 |
|:---:|:---:|:---|
| `/帮助` | 所有人 | 显示所有可用指令 |
| `/签到` | 所有人 | 每日签到，获取一定量的对话次数（每日限一次） |
| `/我的余额` | 所有人 | 查看当前剩余的对话次数 |
| `/查看全部余额` | 管理员 | 以「备注：剩余N」的形式列出所有用户的余额（`/帮助` 中不显示） |

## 配置

在 AstrBot WebUI 的插件配置面板中可修改以下项：

| 配置项 | 类型 | 默认值 | 说明 |
|:---|:---:|:---:|:---|
| `default_quota` | int | `5` | 新用户初始对话次数 |
| `daily_bonus_min` | int | `5` | 签到奖励随机范围的最小值 |
| `daily_bonus_max` | int | `5` | 签到奖励随机范围的最大值（与最小值相等则为固定值） |
| `signin_mode` | string | `range` | `range`：按最小-最大范围随机；`weighted`：按 `signin_weights` 权重随机 |
| `signin_weights` | text | `5:1\n3:2\n10:1` | `weighted` 模式的权重配置，每行一组「值:权重」 |
| `limit_reply` | text | `呜呜，你的对话次数已经用完啦...` | 次数用尽时的回复内容 |
| `signin_reply` | text | `签到成功！获得 {bonus} 次对话次数...` | 签到成功回复，可用 `{bonus}` 占位符 |
| `quota_query_reply` | text | `你还有 {quota} 次对话次数哦...` | 余额查询回复，可用 `{quota}` 占位符 |
| `admin_users` | list | `[]` | 免次数限制的管理员 QQ 号列表，如 `["123456", "789012"]` |

> `signin_weights` 每行格式为 `值:权重`，例如 `5:1` 表示获得 5 次对话次数的权重为 1。
> 格式错误的行会被忽略；若整段配置都无法解析，`weighted` 模式会回落到 `daily_bonus_min`～`daily_bonus_max` 范围随机。

## WebUI 管理页面

安装并启用插件后，在 AstrBot WebUI → 插件详情页中可以打开 **用户管理** 视图（`views/info/`）。

页面包含：

- 顶部统计栏：用户总数、累积调用、剩余总次数、累积 Token、今日 Token、平均 Token
- 用户表格：QQ 号、备注、已调用、今日调用、剩余次数、今日 Token、累积 Token、平均 Token
- 操作按钮：`+10` / `+1` / `-1` / `-10` 快捷调整剩余次数，点击备注即可编辑

数据全部来自插件 KV 存储，修改后即时生效。

## 安装

### 通过 AstrBot 插件市场

1. 打开 AstrBot WebUI
2. 进入「插件管理」
3. 搜索 `astrbot_plugin_limit_use`
4. 点击安装

### 手动安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/XFYX521/astrbot_plugin_limit_use.git
```

然后在 WebUI 中重载插件即可。

## 开发

```
astrbot_plugin_limit_use/
├── main.py              # 插件主逻辑
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # 配置定义
├── views/
│   └── info/
│       └── index.html   # WebUI 用户管理视图
├── tests/
│   └── test_plugin_offline.py  # 离线单元测试（无需 AstrBot 环境）
└── README.md            # 本文件
```

## 依赖

- **AstrBot ≥ 4.29.0**（`views/` 插件视图从 4.29.0 起可用；最低版本同时写在 `metadata.yaml` 的 `astrbot_version` 中，低版本会拒绝加载并提示）
- 早于 4.29.0 的 AstrBot 不会渲染本插件的 WebUI 用户管理页面，请先升级
- 消息平台：QQ（aiocqhttp）

无第三方 Python 依赖，无需 `requirements.txt`。

## 验收步骤

离线部分：`python -m py_compile main.py`、`python tests/test_plugin_offline.py`。

在真实 AstrBot 中请逐项确认：

1. 重载插件后 WebUI 插件配置页出现上述 9 个配置项，`signin_weights` 默认值显示为三行。
2. 普通用户首次对话扣 1 次；额度为 0 时收到 `limit_reply` 且不再调用 LLM。
3. `/签到` 首次获得奖励，同一天再次发送提示已签到；`weighted` 模式下奖励只出现配置过的值。
4. `/我的余额`、`/帮助` 正常；管理员发送 `/查看全部余额` 输出「备注：剩余N」。
5. WebUI 用户管理视图：数据加载、`+10`/`-1` 调整次数、备注编辑保存、刷新按钮均正常。
6. 浏览器直接访问非法参数（如 `/astrbot_plugin_limit_use/update/<QQ号>/abc`）返回 400 而非 500。

## 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)

## License

[AGPL-3.0](LICENSE)
