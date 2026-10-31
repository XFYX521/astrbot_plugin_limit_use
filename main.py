import asyncio
import datetime
import hashlib
import random
from html import escape as html_escape

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

try:  # 新版 AstrBot 官方 Web API
    from astrbot.api.web import error_response, json_response
except ImportError:  # 旧版没有该模块时退回 quart（保持插件可加载）
    from quart import jsonify

    def json_response(data):
        return jsonify(data)

    def error_response(message, status_code=400):
        return jsonify({"error": message}), status_code

PLUGIN_NAME = "astrbot_plugin_limit_use"
PLUGIN_DISPLAY_NAME = "对话次数限制"
PLUGIN_VERSION = "v2.1.0"

# 投资币种默认值（配置解析失败时兜底），基准价只用于展示现价
DEFAULT_ASSETS: list[tuple[str, float]] = [
    ("原石", 160.0),
    ("菲林", 100.0),
    ("水晶", 280.0),
    ("星琼", 160.0),
]


def _get_attr(obj, attr, default=0):
    """安全获取属性或字典键"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default) or default
    return getattr(obj, attr, default) or default


def _as_int(value, default: int = 0) -> int:
    """尽量转成 int，失败时返回默认值（防 WebUI 填入非法字符串）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _config_lines(raw) -> list[str]:
    """拆分配置中的多行文本，兼容字面量 ``\\n``、CRLF 与真换行。"""
    text = str(raw or "")
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [line.strip() for line in text.split("\n")]


def _parse_signin_weights(raw) -> tuple[list[int], list[int]]:
    """解析“每行 值:权重”的签到权重配置。

    权重 <= 0 或格式错误的行会被跳过。
    """
    values: list[int] = []
    weights: list[int] = []
    for line in _config_lines(raw):
        if not line or ":" not in line:
            continue
        left, _, right = line.partition(":")
        try:
            value = int(left.strip())
            weight = int(right.strip())
        except (TypeError, ValueError):
            continue
        if weight <= 0:
            continue
        values.append(value)
        weights.append(weight)
    return values, weights


def _parse_invest_assets(raw) -> list[tuple[str, float]]:
    """解析“每行 币种:基准价”的投资配置；非法行跳过。"""
    assets: list[tuple[str, float]] = []
    seen: set[str] = set()
    for line in _config_lines(raw):
        if not line or ":" not in line:
            continue
        name, _, price_text = line.partition(":")
        name = name.strip()
        try:
            price = float(price_text.strip())
        except (TypeError, ValueError):
            continue
        if not name or name in seen or price <= 0:
            continue
        seen.add(name)
        assets.append((name, price))
    return assets


def _parse_percent(raw) -> int | None:
    """解析投资比例：1–100 的整数（允许带 %），非法返回 None。"""
    text = str(raw or "").strip().replace("%", "").replace("％", "").strip()
    value = _as_int(text, -1)
    return value if 1 <= value <= 100 else None


def _settle_invest(balance: int, percent: int, rate: float, fee_percent: float) -> dict:
    """按“余额百分比”结算一次投资：投入 = 余额 × 百分比（向下取整，至少 1 次）。"""
    if balance <= 0:
        return {"stake": 0, "fee": 0, "pnl": 0, "after": 0}
    stake = min(balance, max(1, balance * percent // 100))
    fee = int(round(stake * max(0.0, fee_percent) / 100))
    gross = int(round(stake * rate))
    pnl = gross - fee
    return {"stake": stake, "fee": fee, "pnl": pnl, "after": max(0, balance + pnl)}


def _moving_rate(asset: str, day: str, volatility: float) -> float:
    """确定性模拟行情：同一「日期 + 币种」永远得到同一涨跌幅（小数形式）。"""
    if volatility <= 0:
        return 0.0
    digest = hashlib.sha256(f"{day}|{asset}".encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    percent = random.Random(seed).uniform(-volatility, volatility)
    return round(percent / 100, 6)


_CARD_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", -apple-system, sans-serif;
  background: #ffffff;
}
.card {
  width: 100%; min-height: 100vh;
  background: #ffffff; overflow: hidden;
  color: #1f2937;
  display: flex; flex-direction: column;
}
.head {
  padding: 26px 34px; color: #ffffff;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
}
.head .title { font-size: 32px; font-weight: 700; letter-spacing: 0.5px; }
.head .subtitle { font-size: 18px; opacity: 0.9; margin-top: 7px; }
.body {
  flex: 1; padding: 26px 34px;
  display: flex; flex-direction: column; justify-content: center; gap: 22px;
}
table { width: 100%; border-collapse: collapse; font-size: 21px; }
th, td { padding: 14px 12px; text-align: left; }
th { color: #6b7280; font-size: 18px; font-weight: 600; border-bottom: 2px solid #e5e7eb; }
td { border-bottom: 1px solid #f3f4f6; }
tr:last-child td { border-bottom: none; }
.kv { display: flex; flex-direction: column; }
.kv-row {
  display: flex; justify-content: space-between; align-items: baseline;
  padding: 13px 0; font-size: 22px;
}
.kv-row .k { color: #6b7280; }
.kv-row .v { font-weight: 600; }
.kv-row .v.pos { color: #16a34a; }
.kv-row .v.neg { color: #dc2626; }
.note {
  padding: 16px 18px; border-radius: 10px;
  background: #f5f3ff; color: #6d28d9; font-size: 19px; line-height: 1.7;
}
.footer { padding: 18px 34px 24px; color: #9ca3af; font-size: 16px; text-align: center; }
"""


def _build_card_html(title: str, subtitle: str, sections: list, footer: str = "") -> str:
    """把结构化的卡片数据渲染成浅色卡片 HTML（所有文本都会转义）。"""
    esc = html_escape
    parts: list[str] = []
    for section in sections:
        kind = section.get("type")
        if kind == "table":
            head = "".join(f"<th>{esc(str(h))}</th>" for h in section.get("headers", []))
            rows = []
            for row in section.get("rows", []):
                cells = []
                for cell in row:
                    cls = ""
                    if isinstance(cell, (tuple, list)) and len(cell) == 2:
                        cell, cls_name = cell
                        if cls_name:
                            cls = f' class="{esc(str(cls_name))}"'
                    cells.append(f"<td{cls}>{esc(str(cell))}</td>")
                rows.append("<tr>" + "".join(cells) + "</tr>")
            parts.append(
                f"<table><thead><tr>{head}</tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>"
            )
        elif kind == "kv":
            items = []
            for item in section.get("items", []):
                label, value = item[0], item[1]
                cls = f' class="{esc(str(item[2]))}"' if len(item) > 2 and item[2] else ""
                items.append(
                    f'<div class="kv-row"><span class="k">{esc(str(label))}</span>'
                    f'<span class="v"{cls}>{esc(str(value))}</span></div>'
                )
            parts.append('<div class="kv">' + "".join(items) + "</div>")
        elif kind == "note":
            parts.append(f'<div class="note">{esc(str(section.get("text", "")))}</div>')

    subtitle_html = f'<div class="subtitle">{esc(str(subtitle))}</div>' if subtitle else ""
    footer_html = f'<div class="footer">{esc(str(footer))}</div>' if footer else ""
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8" />'
        f"<style>{_CARD_CSS}</style></head><body><div class=\"card\">"
        f'<div class="head"><div class="title">{esc(str(title))}</div>{subtitle_html}</div>'
        f'<div class="body">{"".join(parts)}</div>{footer_html}</div></body></html>'
    )


def _extract_tokens(resp) -> int:
    """从 LLMResponse 中提取 token 消耗数 = prompt_tokens + completion_tokens（含缓存）"""
    raw = getattr(resp, "raw_completion", None)
    if raw is None:
        return 0
    try:
        usage = _get_attr(raw, "usage", None)
        if usage and usage != 0:
            # OpenAI / 兼容格式
            prompt = _get_attr(usage, "prompt_tokens", 0)
            completion = _get_attr(usage, "completion_tokens", 0)
            total = prompt + completion
            if total > 0:
                return total
            # fallback: total_tokens
            total = _get_attr(usage, "total_tokens", 0)
            if total > 0:
                return total

        # Google Gemini
        usage_meta = _get_attr(raw, "usage_metadata", None)
        if usage_meta and usage_meta != 0:
            return _get_attr(usage_meta, "total_token_count", 0)

        # Anthropic
        usage = _get_attr(raw, "usage", None)
        if usage and usage != 0:
            inp = _get_attr(usage, "input_tokens", 0)
            out = _get_attr(usage, "output_tokens", 0)
            return inp + out
    except Exception:
        pass
    return 0


class LimitUsePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 串行化 KV 读-改-写，避免同一用户并发消息时丢次数/漏记
        self._kv_lock = asyncio.Lock()

        # ── Web API ──
        try:
            context.register_web_api(
                f"/{PLUGIN_NAME}/users",
                self.api_get_users,
                ["GET"],
                "获取所有用户的次数/Tokens数据",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/update/<user_id>/<remaining>",
                self.api_update_user,
                ["GET"],
                "修改指定用户的剩余次数",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/investments",
                self.api_get_investments,
                ["GET"],
                "获取投资记录",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/market",
                self.api_get_market,
                ["GET"],
                "获取今日行情",
            )
            logger.info("LimitUsePlugin: Web API 已注册")
        except Exception as e:
            logger.warning(f"LimitUsePlugin: Web API 注册失败 ({e})，跳过")

        self._log_task = None

    async def initialize(self):
        """插件初始化后启动定时日志任务"""
        self._log_task = asyncio.create_task(self._daily_log_loop())
        logger.info("LimitUsePlugin: Token 日报定时任务已启动")

    # ══════════════════════════════════════════════
    #  KV 工具方法
    # ══════════════════════════════════════════════

    async def _get_quota(self) -> dict:
        return await self.get_kv_data("user_quota", {}) or {}

    async def _save_quota(self, data: dict):
        await self.put_kv_data("user_quota", data)

    async def _get_signin(self) -> dict:
        return await self.get_kv_data("user_signin", {}) or {}

    async def _save_signin(self, data: dict):
        await self.put_kv_data("user_signin", data)

    async def _get_total_usage(self) -> dict:
        return await self.get_kv_data("user_total_usage", {}) or {}

    async def _save_total_usage(self, data: dict):
        await self.put_kv_data("user_total_usage", data)

    async def _get_profiles(self) -> dict:
        """{uid: {"name": 最近昵称, "last": iso时间, "private": {name,last}, "groups": {gid: {name,last}}}}"""
        return await self.get_kv_data("user_profiles", {}) or {}

    async def _save_profiles(self, data: dict):
        await self.put_kv_data("user_profiles", data)

    async def _get_total_tokens(self) -> dict:
        """{uid: total_tokens}"""
        return await self.get_kv_data("user_total_tokens", {}) or {}

    async def _save_total_tokens(self, data: dict):
        await self.put_kv_data("user_total_tokens", data)

    async def _get_daily_tokens(self) -> dict:
        """{uid: {date: tokens}}"""
        return await self.get_kv_data("user_daily_tokens", {}) or {}

    async def _save_daily_tokens(self, data: dict):
        await self.put_kv_data("user_daily_tokens", data)

    async def _get_daily_log(self) -> dict:
        """{date: {uid: tokens, _total: total, _date: date}}"""
        return await self.get_kv_data("token_daily_log", {}) or {}

    async def _save_daily_log(self, data: dict):
        await self.put_kv_data("token_daily_log", data)

    async def _get_daily_usage(self) -> dict:
        """{uid: {date: count}} 每日调用次数"""
        return await self.get_kv_data("user_daily_usage", {}) or {}

    async def _save_daily_usage(self, data: dict):
        await self.put_kv_data("user_daily_usage", data)

    async def _record_daily_usage(self, user_id: str):
        """记录用户今日调用次数 +1"""
        today = datetime.date.today().isoformat()
        daily = await self._get_daily_usage()
        user_daily = daily.get(user_id, {})
        user_daily[today] = user_daily.get(today, 0) + 1
        daily[user_id] = user_daily
        await self._save_daily_usage(daily)

    async def _get_invest_daily(self) -> dict:
        """{uid: 上次投资日期}"""
        return await self.get_kv_data("invest_daily", {}) or {}

    async def _save_invest_daily(self, data: dict):
        await self.put_kv_data("invest_daily", data)

    async def _get_invest_history(self) -> list:
        return await self.get_kv_data("invest_history", []) or []

    async def _save_invest_history(self, data: list):
        await self.put_kv_data("invest_history", data)

    # ══════════════════════════════════════════════
    #  工具方法
    # ══════════════════════════════════════════════

    def _is_admin(self, user_id: str) -> bool:
        return user_id in (self.config.get("admin_users") or [])

    async def _bump_usage(self, user_id: str):
        """累积调用 +1，并记录今日调用。调用方需持有 self._kv_lock。"""
        usage = await self._get_total_usage()
        usage[user_id] = usage.get(user_id, 0) + 1
        await self._save_total_usage(usage)
        await self._record_daily_usage(user_id)

    def _chat_identity(self, event: AstrMessageEvent) -> tuple[str, str, str]:
        """返回 (用户ID, 最近昵称, 群号)。私聊时群号为空字符串。"""
        user_id = event.get_sender_id()
        try:
            nickname = (event.get_sender_name() or "").strip()
        except Exception:
            nickname = ""
        group_id = ""
        try:
            group_id = str(event.get_group_id() or "")
        except Exception:
            group_id = ""
        return user_id, nickname, group_id

    async def _touch_profile(self, event: AstrMessageEvent):
        """记录用户最近昵称与所在聊天窗口（群/私聊）。调用方需持有 self._kv_lock。"""
        user_id, nickname, group_id = self._chat_identity(event)
        if not user_id:
            return

        now = datetime.datetime.now().isoformat(timespec="seconds")
        profiles = await self._get_profiles()
        profile = profiles.get(user_id) or {}
        if nickname:
            profile["name"] = nickname
        profile["last"] = now

        if group_id:
            groups = profile.get("groups") or {}
            group = groups.get(group_id) or {}
            if nickname:
                group["name"] = nickname
            group["last"] = now
            groups[group_id] = group
            profile["groups"] = groups
        else:
            private = profile.get("private") or {}
            if nickname:
                private["name"] = nickname
            private["last"] = now
            profile["private"] = private

        profiles[user_id] = profile
        await self._save_profiles(profiles)

    # ── 投资模式工具 ──

    def _assets(self) -> list[tuple[str, float]]:
        """读取可投资币种，配置为空或全非法时回落到默认币种。"""
        assets = _parse_invest_assets(self.config.get("invest_assets", ""))
        return assets or list(DEFAULT_ASSETS)

    def _volatility(self) -> float:
        try:
            value = float(self.config.get("invest_volatility", 3))
        except (TypeError, ValueError):
            value = 3.0
        return max(0.0, value)

    def _fee_percent(self) -> float:
        try:
            value = float(self.config.get("invest_fee_percent", 0))
        except (TypeError, ValueError):
            value = 0.0
        return max(0.0, value)

    def _rate(self, asset: str, day: str) -> float:
        return _moving_rate(asset, day, self._volatility())

    def _market_rows(self, day: str) -> list[list]:
        rows: list[list] = []
        for name, base in self._assets():
            rate = self._rate(name, day)
            percent = rate * 100
            rows.append([
                name,
                f"{base:g}",
                (f"+{percent:.2f}%" if percent >= 0 else f"{percent:.2f}%", "pos" if percent >= 0 else "neg"),
                f"{base * (1 + rate):.2f}",
            ])
        return rows

    async def _card_result(self, event, title, subtitle, sections, footer, fallback_text):
        """优先渲染图片卡片，失败时依次回落到文转图、纯文本。"""
        render = getattr(self, "html_render", None)
        if render:
            try:
                url = await render(
                    _build_card_html(title, subtitle, sections, footer),
                    {},
                    options={"full_page": True, "type": "png"},
                )
                if url:
                    return event.image_result(url)
            except Exception as e:  # 未配置文转图/Playwright 时常见
                logger.warning(f"LimitUsePlugin: 卡片渲染失败，尝试回落 ({e})")

        text_image = getattr(self, "text_to_image", None)
        if text_image:
            try:
                url = await text_image(fallback_text)
                if url:
                    return event.image_result(url)
            except Exception as e:
                logger.warning(f"LimitUsePlugin: 文转图失败，回落纯文本 ({e})")

        return event.plain_result(fallback_text)

    async def _daily_status(self, user_id: str, today: str) -> str:
        """返回今天的每日动作状态：signin / invest / ''（签到与投资共享每日一次）。"""
        async with self._kv_lock:
            signin = await self._get_signin()
            invested = await self._get_invest_daily()
        if signin.get(user_id) == today:
            return "signin"
        if invested.get(user_id) == today:
            return "invest"
        return ""

    async def _invest_brief_result(self, event, user_id: str, today: str):
        """/投资 不带参数：今日行情 + 余额与今日状态 + 用法。"""
        quota = await self._get_quota()
        balance = quota.get(user_id, self.config["default_quota"])
        status = await self._daily_status(user_id, today)
        usage = "用法：/投资 原石 10（10 表示用当前余额的 10%，范围 1–100）"

        if status == "invest":
            status_text = "已投资（明天再来）"
        elif status == "signin":
            status_text = "今日已签到（签到与投资共享每日一次）"
        else:
            status_text = "未投资"

        sections = [
            {"type": "table", "headers": ["币种", "基准价", "今日涨跌", "现价"], "rows": self._market_rows(today)},
            {"type": "kv", "items": [
                ("我的余额", f"{balance} 次"),
                ("今日状态", status_text),
            ]},
            {"type": "note", "text": usage},
        ]
        fallback_lines = [
            f"📈 今日行情 · {today}",
            *[f"{row[0]}：基准{row[1]}　涨跌{row[2][0]}　现价{row[3]}" for row in self._market_rows(today)],
            f"我的余额：{balance} 次　今日状态：{status_text}",
            usage,
            "模拟行情，仅供娱乐",
        ]
        return await self._card_result(
            event,
            "📈 今日行情",
            today,
            sections,
            "模拟行情，仅供娱乐",
            "\n".join(fallback_lines),
        )

    # ══════════════════════════════════════════════
    #  LLM 请求钩子 —— 扣减次数
    # ══════════════════════════════════════════════

    @filter.on_llm_request()
    async def on_llm_req(self, event: AstrMessageEvent, req: "ProviderRequest"):
        user_id = event.get_sender_id()

        if self._is_admin(user_id):
            # 管理员不扣次数，但仍记录累积调用与最近昵称/聊天窗口
            async with self._kv_lock:
                await self._touch_profile(event)
                await self._bump_usage(user_id)
            return

        async with self._kv_lock:
            await self._touch_profile(event)
            quota = await self._get_quota()
            remain = quota.get(user_id, self.config["default_quota"])
            allowed = remain > 0
            if allowed:
                quota[user_id] = remain - 1
                await self._save_quota(quota)
                await self._bump_usage(user_id)

        if not allowed:
            await event.send(event.plain_result(self.config["limit_reply"]))
            event.stop_event()

    # ══════════════════════════════════════════════
    #  LLM 响应钩子 —— 记录 Token 消耗
    # ══════════════════════════════════════════════

    @filter.on_llm_response()
    async def on_llm_resp(self, event: AstrMessageEvent, resp: "LLMResponse"):
        """LLM 响应后记录 token 消耗"""
        tokens = _extract_tokens(resp)
        if tokens <= 0:
            return

        user_id = event.get_sender_id()
        today = datetime.date.today().isoformat()

        async with self._kv_lock:
            # 累积 token
            total = await self._get_total_tokens()
            total[user_id] = total.get(user_id, 0) + tokens
            await self._save_total_tokens(total)

            # 当日 token
            daily = await self._get_daily_tokens()
            user_daily = daily.get(user_id, {})
            user_daily[today] = user_daily.get(today, 0) + tokens
            daily[user_id] = user_daily
            await self._save_daily_tokens(daily)

    # ══════════════════════════════════════════════
    #  指令
    # ══════════════════════════════════════════════

    def _roll_bonus(self) -> int:
        """按 signin_mode 计算本次签到奖励；配置非法时回落到 range 模式。"""
        if self.config.get("signin_mode", "range") == "weighted":
            values, weights = _parse_signin_weights(self.config.get("signin_weights", ""))
            if values:
                return random.choices(values, weights=weights, k=1)[0]

        low = _as_int(self.config.get("daily_bonus_min", 5), 5)
        high = _as_int(self.config.get("daily_bonus_max", 5), 5)
        return random.randint(min(low, high), max(low, high))

    @filter.command("签到")
    async def signin(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        today = datetime.date.today().isoformat()

        async with self._kv_lock:
            await self._touch_profile(event)
            signin_records = await self._get_signin()
            invested = await self._get_invest_daily()
            already = signin_records.get(user_id) == today
            invested_today = invested.get(user_id) == today
            bonus = 0
            if not already and not invested_today:
                bonus = self._roll_bonus()
                quota = await self._get_quota()
                current = quota.get(user_id, self.config["default_quota"])
                quota[user_id] = max(0, current + bonus)
                await self._save_quota(quota)

                signin_records[user_id] = today
                await self._save_signin(signin_records)

        if invested_today:
            yield event.plain_result("你今天已经投资过啦，签到和投资共享每日一次，明天再来吧～")
            return
        if already:
            yield event.plain_result("你今天已经签过到啦，明天再来吧(｡•ᴗ•｡)")
            return

        reply = self.config["signin_reply"].replace("{bonus}", str(bonus))
        yield event.plain_result(reply)

    @filter.command("投资")
    async def invest(
        self,
        event: AstrMessageEvent,
        asset: str = "",
        arg1: str = "",
        arg2: str = "",
        arg3: str = "",
    ):
        """模拟行情，用当前余额的百分比投资（每日 1 次）"""
        if not self.config.get("invest_enabled", True):
            yield event.plain_result("投资模式已关闭，请联系管理员开启哦～")
            return

        user_id = event.get_sender_id()
        today = datetime.date.today().isoformat()
        assets = self._assets()
        names = [name for name, _ in assets]
        asset = str(asset or "").strip()

        if not asset:
            async with self._kv_lock:
                await self._touch_profile(event)
            yield await self._invest_brief_result(event, user_id, today)
            return

        if asset not in names:
            async with self._kv_lock:
                await self._touch_profile(event)
            yield event.plain_result(f"没有「{asset}」这个币种哦，可选：{'、'.join(names)}")
            return

        # 静默兼容旧格式：从任意位置取第一个 1–100 的整数作为百分比
        percent = None
        for raw in (arg1, arg2, arg3):
            value = _parse_percent(raw)
            if value is not None:
                percent = value
                break
        if percent is None:
            yield event.plain_result("用法：/投资 原石 10（10 表示用余额的 10%，范围 1–100）")
            return

        base = dict(assets)[asset]
        nickname = getattr(event, "get_sender_name", lambda: user_id)()
        reasons = {"signin": False, "invest": False, "empty": False}

        async with self._kv_lock:
            await self._touch_profile(event)
            quota = await self._get_quota()
            balance = quota.get(user_id, self.config["default_quota"])
            signin_records = await self._get_signin()
            daily = await self._get_invest_daily()
            if signin_records.get(user_id) == today:
                reasons["signin"] = True
            elif daily.get(user_id) == today:
                reasons["invest"] = True
            elif balance <= 0:
                reasons["empty"] = True
            else:
                rate = self._rate(asset, today)
                result = _settle_invest(balance, percent, rate, self._fee_percent())
                quota[user_id] = result["after"]
                await self._save_quota(quota)
                daily[user_id] = today
                await self._save_invest_daily(daily)

                entry = {
                    "time": datetime.datetime.now().isoformat(timespec="seconds"),
                    "date": today,
                    "user_id": user_id,
                    "nickname": nickname,
                    "asset": asset,
                    "percent": percent,
                    "stake": result["stake"],
                    "rate": rate,
                    "price": round(base * (1 + rate), 2),
                    "fee": result["fee"],
                    "pnl": result["pnl"],
                    "balance_before": balance,
                    "balance_after": result["after"],
                }
                history = await self._get_invest_history()
                history.append(entry)
                limit = max(1, _as_int(self.config.get("invest_history_limit", 200), 200))
                if len(history) > limit:
                    history = history[-limit:]
                await self._save_invest_history(history)

        if reasons["signin"]:
            yield event.plain_result("你今天已经签过到啦，签到和投资共享每日一次，明天再来吧～")
            return
        if reasons["invest"]:
            yield event.plain_result("你今天已经投资过啦，明天再来吧(｡•ᴗ•｡)")
            return
        if reasons["empty"]:
            yield event.plain_result("你的余额是 0 次啦，先 /签到 再来投资吧～")
            return

        stake, fee, pnl, after = result["stake"], result["fee"], result["pnl"], result["after"]
        change = rate * 100
        items = [
            ("玩家", nickname),
            ("投入比例", f"{percent}%（{stake} 次）"),
            ("今日行情", f"{asset} {'+' if change >= 0 else ''}{change:.2f}%"),
            ("现价", f"{base * (1 + rate):.2f}（基准 {base:g}）"),
        ]
        if fee > 0:
            items.append(("手续费", f"{fee} 次"))
        sections = [
            {"type": "kv", "items": items},
            {"type": "kv", "items": [
                ("盈亏", f"{pnl:+d} 次", "pos" if pnl >= 0 else "neg"),
                ("余额", f"{balance} → {after} 次"),
            ]},
        ]
        fallback = "\n".join([
            f"📈 {asset} 投资结算",
            f"{nickname}：{percent}% → 投入 {stake} 次",
            f"行情 {change:+.2f}%　盈亏 {pnl:+d} 次" + (f"　手续费 {fee} 次" if fee else ""),
            f"余额：{balance} → {after}",
            "模拟行情，仅供娱乐",
        ])
        yield await self._card_result(
            event,
            f"📈 {asset} 投资结算",
            f"{percent}% · 投入 {stake} 次",
            sections,
            "模拟行情，仅供娱乐",
            fallback,
        )

    @filter.command("我的余额")
    async def query_quota(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        async with self._kv_lock:
            await self._touch_profile(event)
            quota = await self._get_quota()
        remain = quota.get(user_id, self.config["default_quota"])
        reply = self.config["quota_query_reply"].replace("{quota}", str(remain))
        yield event.plain_result(reply)

    @filter.command("查看全部余额")
    async def view_all_quota(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        if not self._is_admin(user_id):
            yield event.plain_result("你没有权限使用此指令哦(｡•ᴗ•｡)")
            return
        async with self._kv_lock:
            quota = await self._get_quota()
            profiles = await self._get_profiles()
        default_quota = self.config["default_quota"]
        if not quota:
            yield event.plain_result("还没有用户数据呢～")
            return
        lines = []
        for uid in sorted(quota.keys()):
            name = (profiles.get(uid) or {}).get("name") or uid
            lines.append(f"{name}（{uid}）：剩余{quota.get(uid, default_quota)}")
        yield event.plain_result("\n".join(lines))

    @filter.command("帮助")
    async def help_cmd(self, event: AstrMessageEvent):
        """显示插件指令菜单（图片，失败回落文本）"""
        sections = [
            {"type": "table", "headers": ["指令", "说明"], "rows": [
                ("/帮助", "显示本菜单"),
                ("/签到", "每日签到获取对话次数"),
                ("/我的余额", "查看剩余对话次数"),
                ("/投资", "用余额百分比投资（每日 1 次，与签到共享）"),
            ]},
            {"type": "note", "text": "投资用法：/投资 原石 10（10 表示用当前余额的 10%，范围 1–100）"},
            {"type": "note", "text": "次数用完后会被拦截；签到或投资每天只能选一个。"},
        ]
        fallback = "\n".join([
            f"📋 {PLUGIN_DISPLAY_NAME} {PLUGIN_VERSION} 可用指令",
            "├ /帮助 — 显示本菜单",
            "├ /签到 — 每日签到获取对话次数",
            "├ /我的余额 — 查看剩余对话次数",
            "└ /投资 — 用余额百分比投资（与签到共享每日 1 次）",
            "投资用法：/投资 原石 10（10% ，范围 1–100）",
        ])
        yield await self._card_result(
            event,
            f"📋 {PLUGIN_DISPLAY_NAME}",
            f"{PLUGIN_VERSION} · 指令菜单",
            sections,
            "模拟行情，仅供娱乐",
            fallback,
        )

    # ══════════════════════════════════════════════
    #  Web API
    # ══════════════════════════════════════════════

    async def api_get_users(self):
        """返回所有用户的次数 + Token 数据"""
        today = datetime.date.today().isoformat()
        # 锁内一次性读取，避免并发写入导致各 key 之间快照错位
        async with self._kv_lock:
            quota = await self._get_quota()
            usage = await self._get_total_usage()
            signin = await self._get_signin()
            profiles = await self._get_profiles()
            total_tokens = await self._get_total_tokens()
            daily_tokens = await self._get_daily_tokens()
            daily_usage = await self._get_daily_usage()

        all_uids = (
            set(quota.keys()) | set(usage.keys()) | set(signin.keys())
            | set(profiles.keys()) | set(total_tokens.keys()) | set(daily_tokens.keys())
            | set(daily_usage.keys())
        )
        if not all_uids:
            return json_response({"users": []})

        today_tokens_sum = sum(
            d.get(today, 0) for d in daily_tokens.values()
        )
        total_tokens_sum = sum(total_tokens.values())

        users = []
        for uid in sorted(all_uids):
            user_daily = daily_tokens.get(uid, {})
            total_used = usage.get(uid, 0)
            total_tok = total_tokens.get(uid, 0)
            avg_k = round(total_tok / total_used / 1000, 1) if total_used > 0 else 0
            profile = profiles.get(uid) or {}
            groups = [
                {"group_id": gid, "name": (info or {}).get("name", ""), "last": (info or {}).get("last", "")}
                for gid, info in (profile.get("groups") or {}).items()
            ]
            groups.sort(key=lambda item: item["last"], reverse=True)
            private = profile.get("private") or {}
            users.append({
                "user_id": uid,
                "name": profile.get("name", ""),
                "is_admin": self._is_admin(uid),
                "remaining": quota.get(uid, self.config["default_quota"]),
                "total_used": total_used,
                "last_signin": signin.get(uid, ""),
                "total_tokens": total_tok,
                "today_tokens": user_daily.get(today, 0),
                "today_used": daily_usage.get(uid, {}).get(today, 0),
                "avg_tokens_k": avg_k,
                "private": private,
                "groups": groups,
            })

        return json_response({
            "users": users,
            "today_tokens_sum": today_tokens_sum,
            "total_tokens_sum": total_tokens_sum,
        })

    async def api_update_user(self, user_id: str, remaining: str):
        value = _as_int(remaining, -1)
        if value < 0:
            return error_response("remaining 必须是非负整数", status_code=400)

        async with self._kv_lock:
            quota = await self._get_quota()
            quota[user_id] = value
            await self._save_quota(quota)
            usage = await self._get_total_usage()

        return json_response({
            "ok": True,
            "user_id": user_id,
            "remaining": value,
            "total_used": usage.get(user_id, 0),
        })

    async def api_get_investments(self):
        """返回投资记录（最新在前）"""
        async with self._kv_lock:
            history = await self._get_invest_history()
        return json_response({"investments": list(reversed(history))})

    async def api_get_market(self):
        """返回今日行情与投资参数（供 WebUI 行情页使用）"""
        today = datetime.date.today().isoformat()
        assets = []
        for name, base in self._assets():
            rate = self._rate(name, today)
            assets.append({
                "name": name,
                "base": base,
                "rate": rate,
                "change_percent": round(rate * 100, 2),
                "price": round(base * (1 + rate), 2),
            })
        return json_response({
            "date": today,
            "assets": assets,
            "volatility": self._volatility(),
            "fee_percent": self._fee_percent(),
        })

    # ══════════════════════════════════════════════
    #  定时任务 —— 每天0点写入 Token 日报日志
    # ══════════════════════════════════════════════

    async def _daily_log_loop(self):
        """每天0点写入前一天的 Token 消耗日志"""
        while True:
            now = datetime.datetime.now()
            next_midnight = (now + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            wait = (next_midnight - now).total_seconds()
            await asyncio.sleep(wait)
            await self._log_yesterday_tokens()

    async def _log_yesterday_tokens(self):
        """将前一天的 Token 消耗存入 KV 存储"""
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

        async with self._kv_lock:
            daily = await self._get_daily_tokens()

            log_entry = {}
            day_total = 0
            for uid, days in sorted(daily.items()):
                if yesterday in days:
                    tok = days[yesterday]
                    log_entry[uid] = tok
                    day_total += tok

            log_entry["_total"] = day_total
            log_entry["_date"] = yesterday

            # 保存到日报记录
            daily_log = await self._get_daily_log()
            daily_log[yesterday] = log_entry
            await self._save_daily_log(daily_log)

        logger.info(f"Token 日报 [{yesterday}] 已归档: {day_total} tokens")

    async def terminate(self):
        """插件卸载/停用时调用"""
        if getattr(self, "_log_task", None):
            self._log_task.cancel()
            try:
                await self._log_task
            except asyncio.CancelledError:
                pass
            self._log_task = None
        logger.info("LimitUsePlugin 已卸载")
