# astrbot_plugin_limit_use

一个 **AstrBot** 插件，为 QQ 用户设置每日对话次数额度，用完需签到补充。

## 功能

- ✅ **次数限制** — 每个用户与 Bot 对话时，每次消耗 1 次额度
- ✅ **自动拦截** — 次数用完后自动回复指定内容，并阻止继续对话
- ✅ **每日签到** — 发送 `/签到` 领取每日奖励次数
- ✅ **余额查询** — 发送 `/我的余额` 查看剩余次数
- ✅ **帮助指令** — 发送 `/帮助` 查看所有可用指令
- ✅ **管理员免限** — 配置管理员 QQ 号列表，不限次数
- ✅ **WebUI 管理** — AstrBot 管理面板中可查看/修改各用户的次数数据

## 指令

| 指令 | 说明 |
|:---:|:---:|
| `/帮助` | 显示所有可用指令 |
| `/签到` | 每日签到，获取一定量的对话次数（每日限一次） |
| `/我的余额` | 查看当前剩余的对话次数 |

## 配置

在 AstrBot WebUI 的插件配置面板中可修改以下项：

| 配置项 | 类型 | 默认值 | 说明 |
|:---|:---:|:---:|:---|
| `default_quota` | int | `5` | 新用户初始对话次数 |
| `daily_bonus` | int | `5` | 每次签到增加的次数 |
| `limit_reply` | text | `呜呜，你的对话次数已经用完啦...` | 次数用尽时的回复内容 |
| `signin_reply` | text | `签到成功！获得 {bonus} 次对话次数...` | 签到成功回复，可用 `{bonus}` 占位符 |
| `quota_query_reply` | text | `你还有 {quota} 次对话次数哦...` | 余额查询回复，可用 `{quota}` 占位符 |
| `admin_users` | list | `[]` | 免次数限制的管理员 QQ 号列表，如 `["123456", "789012"]` |

## WebUI 管理页面

安装并启用插件后，在 AstrBot WebUI → 插件详情页中可以看到 **用户次数管理** 页面。

该页面展示所有用户的：
- QQ 号
- 累积调用次数
- 剩余次数
- 最后签到日期
- 次数状态（充足 / 不足 / 已用完）

支持**在线编辑**用户的累积调用次数和剩余次数，保存后即时生效。

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
├── pages/
│   └── user-quota/
│       └── index.html   # WebUI 管理页面
└── README.md            # 本文件
```

## 依赖

- AstrBot >= v4.9.2（使用 KV 存储功能）
- 消息平台：QQ（aiocqhttp）

## License

[MIT](LICENSE)
