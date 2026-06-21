import datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

PLUGIN_NAME = "astrbot_plugin_limit_use"


@register(
    PLUGIN_NAME,
    "XFYX521",
    "给QQ用户设置对话次数额度，用完需签到补充。",
    "1.0.4",
)
class LimitUsePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # ── Web API（供 WebUI 管理页面使用） ──
        try:
            context.register_web_api(
                f"/{PLUGIN_NAME}/users",
                self.api_get_users,
                ["GET"],
                "获取所有用户的次数数据",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/update/<user_id>/<int:remaining>",
                self.api_update_user,
                ["GET"],
                "修改指定用户的剩余次数",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/remark/<user_id>/<remark>",
                self.api_set_remark,
                ["GET"],
                "设置用户备注",
            )
            logger.info("LimitUsePlugin: Web API 已注册")
        except Exception as e:
            logger.warning(f"LimitUsePlugin: Web API 注册失败 ({e})，跳过")

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
        """获取用户备注 {uid: remark}"""
        return await self.get_kv_data("user_remarks", {}) or {}

    async def _save_remarks(self, data: dict):
        await self.put_kv_data("user_remarks", data)

    # ══════════════════════════════════════════════
    #  LLM 请求钩子 —— 每次调 LLM 前扣减次数
    # ══════════════════════════════════════════════

    @filter.on_llm_request()
    async def on_llm_req(self, event: AstrMessageEvent, req: "ProviderRequest"):
        user_id = event.get_sender_id()

        admin_list = self.config.get("admin_users", [])
        if user_id in admin_list:
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

        bonus = self.config["daily_bonus"]
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
    #  Web API —— 返回 dict 即可（自动转 JSON）
    # ══════════════════════════════════════════════

    async def api_get_users(self):
        """返回所有用户的次数数据"""
        quota = await self._get_quota()
        usage = await self._get_total_usage()
        signin = await self._get_signin()
        remarks = await self._get_remarks()

        all_uids = set(quota.keys()) | set(usage.keys()) | set(signin.keys()) | set(remarks.keys())
        if not all_uids:
            return {"users": []}

        users = []
        for uid in sorted(all_uids):
            users.append({
                "user_id": uid,
                "remark": remarks.get(uid, ""),
                "remaining": quota.get(uid, self.config["default_quota"]),
                "total_used": usage.get(uid, 0),
                "last_signin": signin.get(uid, ""),
            })
        return {"users": users}

    async def api_update_user(self, user_id: str, remaining: int):
        """修改指定用户的剩余次数"""
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

    async def api_set_remark(self, user_id: str, remark: str):
        """设置用户备注"""
        remarks = await self._get_remarks()
        if remark == "_clear_":
            remarks.pop(user_id, None)
        else:
            remarks[user_id] = remark
        await self._save_remarks(remarks)
        return {"ok": True, "user_id": user_id, "remark": remarks.get(user_id, "")}

    # ══════════════════════════════════════════════
    #  插件销毁
    # ══════════════════════════════════════════════

    async def terminate(self):
        logger.info("LimitUsePlugin 已卸载")
