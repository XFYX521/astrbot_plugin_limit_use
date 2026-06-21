import datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

PLUGIN_NAME = "astrbot_plugin_limit_use"


@register(
    PLUGIN_NAME,
    "XFYX521",
    "给QQ用户设置对话次数额度，用完需签到补充。",
    "1.0.0",
)
class LimitUsePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        logger.info("LimitUsePlugin 已加载")

    # ══════════════════════════════════════════════
    #  KV 工具方法
    # ══════════════════════════════════════════════

    async def _get_quota(self) -> dict:
        return await self.get_kv_data("user_quota") or {}

    async def _save_quota(self, data: dict):
        await self.put_kv_data("user_quota", data)

    async def _get_signin(self) -> dict:
        return await self.get_kv_data("user_signin") or {}

    async def _save_signin(self, data: dict):
        await self.put_kv_data("user_signin", data)

    async def _get_total_usage(self) -> dict:
        """获取累积调用次数 {uid: total_used}"""
        return await self.get_kv_data("user_total_usage") or {}

    async def _save_total_usage(self, data: dict):
        await self.put_kv_data("user_total_usage", data)

    def _is_command(self, text: str) -> bool:
        return text.strip().startswith("/")

    # ══════════════════════════════════════════════
    #  事件监听 —— 拦截所有消息，扣减次数
    # ══════════════════════════════════════════════

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        text = event.message_str.strip()

        if not text or self._is_command(text):
            return

        # 管理员免限
        admin_list = self.config.get("admin_users", [])
        if user_id in admin_list:
            return

        # 检查剩余次数
        quota = await self._get_quota()
        remain = quota.get(user_id, self.config["default_quota"])

        if remain <= 0:
            reply = self.config["limit_reply"]
            yield event.plain_result(reply)
            event.stop_event()
            return

        # 扣次数
        quota[user_id] = remain - 1
        await self._save_quota(quota)

        # 记录累积调用
        usage = await self._get_total_usage()
        usage[user_id] = usage.get(user_id, 0) + 1
        await self._save_total_usage(usage)

    # ══════════════════════════════════════════════
    #  指令：/签到
    # ══════════════════════════════════════════════

    @filter.command("签到")
    async def signin(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        today = datetime.date.today().isoformat()

        signin_records = await self._get_signin()
        if signin_records.get(user_id) == today:
            yield event.plain_result("你今天已经签过到啦，明天再来吧(｡•ᴗ•｡)")
            return

        bonus = self.config["daily_bonus"]
        quota = await self._get_quota()
        current = quota.get(user_id, self.config["default_quota"])
        quota[user_id] = current + bonus
        await self._save_quota(quota)

        signin_records[user_id] = today
        await self._save_signin(signin_records)

        reply = self.config["signin_reply"].replace("{bonus}", str(bonus))
        yield event.plain_result(reply)

    # ══════════════════════════════════════════════
    #  指令：/我的余额
    # ══════════════════════════════════════════════

    @filter.command("我的余额")
    async def query_quota(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        quota = await self._get_quota()
        remain = quota.get(user_id, self.config["default_quota"])
        reply = self.config["quota_query_reply"].replace("{quota}", str(remain))
        yield event.plain_result(reply)

    # ══════════════════════════════════════════════
    #  指令：/帮助
    # ══════════════════════════════════════════════

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
    #  插件销毁
    # ══════════════════════════════════════════════

    async def terminate(self):
        logger.info("LimitUsePlugin 已卸载")
