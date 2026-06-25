import datetime
import random
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

PLUGIN_NAME = "astrbot_plugin_limit_use"


def _get_attr(obj, attr, default=0):
    """安全获取属性或字典键"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default) or default
    return getattr(obj, attr, default) or default


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


@register(
    PLUGIN_NAME,
    "XFYX521",
    "给QQ用户设置对话次数额度，用完需签到补充。",
    "1.0.6",
)
class LimitUsePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # ── Web API ──
        try:
            context.register_web_api(
                f"/{PLUGIN_NAME}/users",
                self.api_get_users,
                ["GET"],
                "获取所有用户的次数/Tokens数据",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/update/<user_id>/<int:remaining>",
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
        import asyncio
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
    #  LLM 请求钩子 —— 扣减次数
    # ══════════════════════════════════════════════

    @filter.on_llm_request()
    async def on_llm_req(self, event: AstrMessageEvent, req: "ProviderRequest"):
        user_id = event.get_sender_id()

        admin_list = self.config.get("admin_users", [])
        if user_id in admin_list:
            # 管理员不扣次数，但仍记录累积调用
            usage = await self._get_total_usage()
            usage[user_id] = usage.get(user_id, 0) + 1
            await self._save_total_usage(usage)
            # 记录今日调用
            await self._record_daily_usage(user_id)
            return

        quota = await self._get_quota()
        remain = quota.get(user_id, self.config["default_quota"])

        if remain <= 0:
            reply = self.config["limit_reply"]
            await event.send(event.plain_result(reply))
            event.stop_event()
            return

        quota[user_id] = remain - 1
        await self._save_quota(quota)

        usage = await self._get_total_usage()
        usage[user_id] = usage.get(user_id, 0) + 1
        await self._save_total_usage(usage)
        # 记录今日调用
        await self._record_daily_usage(user_id)

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

    @filter.command("签到")
    async def signin(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        today = datetime.date.today().isoformat()

        signin_records = await self._get_signin()
        if signin_records.get(user_id) == today:
            yield event.plain_result("你今天已经签过到啦，明天再来吧(｡•ᴗ•｡)")
            return

        bonus_min = self.config["daily_bonus_min"]
        bonus_max = self.config["daily_bonus_max"]
        bonus = random.randint(
            min(bonus_min, bonus_max),
            max(bonus_min, bonus_max),
        )
        quota = await self._get_quota()
        current = quota.get(user_id, self.config["default_quota"])
        quota[user_id] = current + bonus
        await self._save_quota(quota)

        signin_records[user_id] = today
        await self._save_signin(signin_records)

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
        admin_list = self.config.get("admin_users", [])
        if user_id not in admin_list:
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
        quota = await self._get_quota()
        usage = await self._get_total_usage()
        signin = await self._get_signin()
        remarks = await self._get_remarks()
        total_tokens = await self._get_total_tokens()
        daily_tokens = await self._get_daily_tokens()
        daily_usage = await self._get_daily_usage()
        today = datetime.date.today().isoformat()

        all_uids = (
            set(quota.keys()) | set(usage.keys()) | set(signin.keys())
            | set(remarks.keys()) | set(total_tokens.keys()) | set(daily_tokens.keys())
            | set(daily_usage.keys())
        )
        if not all_uids:
            return {"users": []}

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

        return {
            "users": users,
            "today_tokens_sum": today_tokens_sum,
            "total_tokens_sum": total_tokens_sum,
        }

    async def api_update_user(self, user_id: str, remaining: int):
        quota = await self._get_quota()
        quota[user_id] = max(0, remaining)
        await self._save_quota(quota)

        usage = await self._get_total_usage()
        return {
            "ok": True,
            "user_id": user_id,
            "remaining": quota[user_id],
            "total_used": usage.get(user_id, 0),
        }

    async def api_set_remark(self, user_id: str):
        try:
            from quart import request as req
            text = req.args.get("text", "")
        except Exception:
            text = ""

        remarks = await self._get_remarks()
        if not text:
            remarks.pop(user_id, None)
        else:
            remarks[user_id] = text
        await self._save_remarks(remarks)
        return {"ok": True, "user_id": user_id, "remark": remarks.get(user_id, "")}

    # ══════════════════════════════════════════════
    #  定时任务 —— 每天0点写入 Token 日报日志
    # ══════════════════════════════════════════════

    async def _daily_log_loop(self):
        """每天0点写入前一天的 Token 消耗日志"""
        import asyncio
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
        if hasattr(self, '_log_task') and self._log_task:
            self._log_task.cancel()
        logger.info("LimitUsePlugin 已卸载")
