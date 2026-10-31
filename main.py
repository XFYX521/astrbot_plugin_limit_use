import asyncio
import datetime
import random

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

try:  # 新版 AstrBot 官方 Web API
    from astrbot.api.web import error_response, json_response, request
except ImportError:  # 旧版没有该模块时退回 quart（保持插件可加载）
    from quart import jsonify, request

    def json_response(data):
        return jsonify(data)

    def error_response(message, status_code=400):
        return jsonify({"error": message}), status_code

PLUGIN_NAME = "astrbot_plugin_limit_use"


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


def _parse_signin_weights(raw) -> tuple[list[int], list[int]]:
    """解析“每行 值:权重”的签到权重配置。

    兼容历史默认值中写坏的字面量 ``\\n``（反斜杠 + n，而不是真换行），
    也接受真实换行、CRLF。权重 <= 0 或格式错误的行会被跳过。
    """
    text = str(raw or "")
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    values: list[int] = []
    weights: list[int] = []
    for line in text.split("\n"):
        line = line.strip()
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
                f"/{PLUGIN_NAME}/remark/<user_id>",
                self.api_set_remark,
                ["GET"],
                "设置用户备注",
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

    async def _get_remarks(self) -> dict:
        return await self.get_kv_data("user_remarks", {}) or {}

    async def _save_remarks(self, data: dict):
        await self.put_kv_data("user_remarks", data)

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

    # ══════════════════════════════════════════════
    #  LLM 请求钩子 —— 扣减次数
    # ══════════════════════════════════════════════

    @filter.on_llm_request()
    async def on_llm_req(self, event: AstrMessageEvent, req: "ProviderRequest"):
        user_id = event.get_sender_id()

        if self._is_admin(user_id):
            # 管理员不扣次数，但仍记录累积调用
            async with self._kv_lock:
                await self._bump_usage(user_id)
            return

        async with self._kv_lock:
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
            signin_records = await self._get_signin()
            already = signin_records.get(user_id) == today
            bonus = 0
            if not already:
                bonus = self._roll_bonus()
                quota = await self._get_quota()
                current = quota.get(user_id, self.config["default_quota"])
                quota[user_id] = max(0, current + bonus)
                await self._save_quota(quota)

                signin_records[user_id] = today
                await self._save_signin(signin_records)

        if already:
            yield event.plain_result("你今天已经签过到啦，明天再来吧(｡•ᴗ•｡)")
            return

        reply = self.config["signin_reply"].replace("{bonus}", str(bonus))
        yield event.plain_result(reply)

    @filter.command("我的余额")
    async def query_quota(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
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
        quota = await self._get_quota()
        remarks = await self._get_remarks()
        default_quota = self.config["default_quota"]
        if not quota:
            yield event.plain_result("还没有用户数据呢～")
            return
        lines = [f"{remarks.get(uid, uid)}：剩余{quota.get(uid, default_quota)}" for uid in sorted(quota.keys())]
        yield event.plain_result("\n".join(lines))

    @filter.command("帮助")
    async def help_cmd(self, event: AstrMessageEvent):
        msg = (
            "📋 **可用指令列表**\n\n"
            "├ /帮助 — 显示本菜单\n"
            "├ /签到 — 每日签到获取对话次数\n"
            "└ /我的余额 — 查看剩余对话次数"
        )
        yield event.plain_result(msg)

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
            remarks = await self._get_remarks()
            total_tokens = await self._get_total_tokens()
            daily_tokens = await self._get_daily_tokens()
            daily_usage = await self._get_daily_usage()

        all_uids = (
            set(quota.keys()) | set(usage.keys()) | set(signin.keys())
            | set(remarks.keys()) | set(total_tokens.keys()) | set(daily_tokens.keys())
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
            users.append({
                "user_id": uid,
                "remark": remarks.get(uid, ""),
                "remaining": quota.get(uid, self.config["default_quota"]),
                "total_used": total_used,
                "last_signin": signin.get(uid, ""),
                "total_tokens": total_tok,
                "today_tokens": user_daily.get(today, 0),
                "today_used": daily_usage.get(uid, {}).get(today, 0),
                "avg_tokens_k": avg_k,
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

    async def api_set_remark(self, user_id: str):
        try:
            query = request.query  # 新版 astrbot.api.web 的 PluginMultiDict
        except AttributeError:
            query = request.args  # 旧版 quart 的 request
        text = (query.get("text") or "").strip()

        async with self._kv_lock:
            remarks = await self._get_remarks()
            if not text:
                remarks.pop(user_id, None)
            else:
                remarks[user_id] = text
            await self._save_remarks(remarks)

        return json_response({
            "ok": True,
            "user_id": user_id,
            "remark": remarks.get(user_id, ""),
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
