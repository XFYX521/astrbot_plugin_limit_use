"""离线单元测试：不依赖 AstrBot 运行环境，用桩模块 import main.py。

运行：python tests/test_plugin_offline.py
"""

import asyncio
import copy
import datetime
import importlib
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ─────────────────────────── 桩：astrbot 相关模块 ───────────────────────────
class _FakeLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class _FakeFilter:
    """把所有装饰器变成恒等函数。"""

    @staticmethod
    def _identity(*args, **kwargs):
        def deco(func):
            return func

        return deco

    command = _identity
    command_group = _identity
    on_llm_request = _identity
    on_llm_response = _identity


class _FakeContext:
    def register_web_api(self, *args, **kwargs):
        pass


class _FakeStar:
    def __init__(self, context):
        self.context = context
        self._kv = {}

    async def get_kv_data(self, key, default=None):
        # 与真实 KV 一致：读到的是独立副本，改返回值不会自动落盘
        if key in self._kv:
            return copy.deepcopy(self._kv[key])
        return copy.deepcopy(default)

    async def put_kv_data(self, key, value):
        self._kv[key] = copy.deepcopy(value)


class _FakeRequest:
    def __init__(self):
        self.query = {}


def _install_astrbot_stubs():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.AstrBotConfig = dict
    api.logger = _FakeLogger()

    event = types.ModuleType("astrbot.api.event")
    event.filter = _FakeFilter()
    event.AstrMessageEvent = object

    star = types.ModuleType("astrbot.api.star")
    star.Context = object
    star.Star = _FakeStar

    web = types.ModuleType("astrbot.api.web")
    web.request = _FakeRequest()
    # 真实 json_response 返回裸 JSON body，error_response 返回错误信封
    web.json_response = lambda data=None, *, status_code=200, headers=None: data
    web.error_response = (
        lambda message, *, status_code=400, data=None, headers=None: {
            "status": "error",
            "message": message,
            "data": data,
        }
    )

    api.event = event
    api.star = star
    api.web = web
    astrbot.api = api

    sys.modules.update({
        "astrbot": astrbot,
        "astrbot.api": api,
        "astrbot.api.event": event,
        "astrbot.api.star": star,
        "astrbot.api.web": web,
    })


_install_astrbot_stubs()
import main  # noqa: E402  （必须在桩安装之后再导入）


# ─────────────────────────── 测试辅助 ───────────────────────────
def load_schema_defaults() -> dict:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    return {name: item.get("default") for name, item in schema.items()}


class FakeEvent:
    def __init__(self, user_id="10001"):
        self._user_id = user_id
        self.sent = []
        self.stopped = False

    def get_sender_id(self):
        return self._user_id

    def plain_result(self, text):
        return ("plain", text)

    async def send(self, result):
        self.sent.append(result)

    def stop_event(self):
        self.stopped = True


def make_plugin(**overrides):
    config = load_schema_defaults()
    config.update(overrides)
    return main.LimitUsePlugin(_FakeContext(), config)


async def collect(gen):
    return [item async for item in gen]


# ─────────────────────────── 测试用例 ───────────────────────────
class SigninWeightsTest(unittest.TestCase):
    def test_schema_default_uses_real_newlines(self):
        raw = load_schema_defaults()["signin_weights"]
        self.assertIn("\n", raw)
        self.assertNotIn("\\n", raw)
        values, weights = main._parse_signin_weights(raw)
        self.assertEqual(values, [5, 3, 10])
        self.assertEqual(weights, [1, 2, 1])

    def test_literal_backslash_n_is_tolerated(self):
        # 旧版本默认值写坏成字面量反斜杠 + n，用户配置可能仍是这个样子
        values, weights = main._parse_signin_weights("5:1\\n3:2\\n10:1")
        self.assertEqual(values, [5, 3, 10])
        self.assertEqual(weights, [1, 2, 1])

    def test_invalid_lines_are_skipped(self):
        values, weights = main._parse_signin_weights("5:1\n坏行\n3:0\nx:2\n\n10:2")
        self.assertEqual(values, [5, 10])
        self.assertEqual(weights, [1, 2])

    def test_garbage_returns_empty(self):
        self.assertEqual(main._parse_signin_weights("完全不是配置"), ([], []))
        self.assertEqual(main._parse_signin_weights(None), ([], []))


class RollBonusTest(unittest.IsolatedAsyncioTestCase):
    async def test_weighted_mode_uses_configured_values(self):
        plugin = make_plugin(signin_mode="weighted")
        results = {plugin._roll_bonus() for _ in range(200)}
        self.assertTrue(results <= {5, 3, 10})
        self.assertTrue(results)  # 不会恒为 0

    async def test_invalid_weighted_falls_back_to_range(self):
        plugin = make_plugin(signin_mode="weighted", signin_weights="坏配置")
        self.assertEqual(plugin._roll_bonus(), 5)  # 默认 min=max=5

    async def test_range_mode(self):
        plugin = make_plugin(signin_mode="range", daily_bonus_min=2, daily_bonus_max=4)
        results = {plugin._roll_bonus() for _ in range(200)}
        self.assertTrue(results <= {2, 3, 4})


class SigninCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_first_signin_adds_bonus_and_records_date(self):
        plugin = make_plugin(signin_mode="range", daily_bonus_min=5, daily_bonus_max=5)
        event = FakeEvent()
        replies = await collect(plugin.signin(event))
        self.assertEqual(len(replies), 1)
        self.assertIn("5", replies[0][1])

        quota = await plugin._get_quota()
        self.assertEqual(quota["10001"], 10)  # default_quota 5 + 5
        signin = await plugin._get_signin()
        self.assertEqual(signin["10001"], datetime.date.today().isoformat())

    async def test_second_signin_same_day_is_rejected(self):
        plugin = make_plugin(signin_mode="range", daily_bonus_min=5, daily_bonus_max=5)
        event = FakeEvent()
        await collect(plugin.signin(event))
        replies = await collect(plugin.signin(event))
        self.assertIn("已经签过", replies[0][1])
        quota = await plugin._get_quota()
        self.assertEqual(quota["10001"], 10)  # 不再增加


class LlmRequestTest(unittest.IsolatedAsyncioTestCase):
    async def test_normal_user_consumes_one_quota(self):
        plugin = make_plugin()
        await plugin.put_kv_data("user_quota", {"10001": 1})
        event = FakeEvent()
        await plugin.on_llm_req(event, None)

        quota = await plugin._get_quota()
        self.assertEqual(quota["10001"], 0)
        usage = await plugin._get_total_usage()
        self.assertEqual(usage["10001"], 1)
        self.assertFalse(event.stopped)

    async def test_zero_quota_blocks_and_replies(self):
        plugin = make_plugin()
        await plugin.put_kv_data("user_quota", {"10001": 0})
        event = FakeEvent()
        await plugin.on_llm_req(event, None)

        self.assertTrue(event.stopped)
        self.assertEqual(event.sent, [("plain", plugin.config["limit_reply"])])
        usage = await plugin._get_total_usage()
        self.assertNotIn("10001", usage)

    async def test_admin_is_not_charged(self):
        plugin = make_plugin(admin_users=["99999"])
        event = FakeEvent("99999")
        await plugin.on_llm_req(event, None)

        quota = await plugin._get_quota()
        self.assertEqual(quota, {})
        usage = await plugin._get_total_usage()
        self.assertEqual(usage["99999"], 1)
        self.assertFalse(event.stopped)


class TokenExtractTest(unittest.TestCase):
    def test_openai_dict_usage(self):
        resp = types.SimpleNamespace(
            raw_completion={"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        )
        self.assertEqual(main._extract_tokens(resp), 15)

    def test_gemini_usage_metadata(self):
        resp = types.SimpleNamespace(
            raw_completion=types.SimpleNamespace(
                usage_metadata=types.SimpleNamespace(total_token_count=42)
            )
        )
        self.assertEqual(main._extract_tokens(resp), 42)

    def test_anthropic_usage(self):
        resp = types.SimpleNamespace(
            raw_completion=types.SimpleNamespace(
                usage=types.SimpleNamespace(input_tokens=7, output_tokens=3)
            )
        )
        self.assertEqual(main._extract_tokens(resp), 10)

    def test_missing_usage_returns_zero(self):
        self.assertEqual(main._extract_tokens(types.SimpleNamespace(raw_completion=None)), 0)


class WebApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_update_user_accepts_valid_int(self):
        plugin = make_plugin()
        result = await plugin.api_update_user("10001", "3")
        self.assertEqual(result["remaining"], 3)
        # 必须真正落盘（get_kv_data 返回副本，未 put 就不会出现在存储里）
        self.assertEqual(plugin._kv["user_quota"], {"10001": 3})
        self.assertEqual((await plugin._get_quota())["10001"], 3)

    async def test_update_user_rejects_invalid_value(self):
        plugin = make_plugin()
        result = await plugin.api_update_user("10001", "abc")
        self.assertEqual(result["status"], "error")
        self.assertIn("remaining", result["message"])
        quota = await plugin._get_quota()
        self.assertEqual(quota, {})

    async def test_set_and_clear_remark(self):
        plugin = make_plugin()
        main.request.query = {"text": "小明"}
        await plugin.api_set_remark("10001")
        self.assertEqual((await plugin._get_remarks())["10001"], "小明")

        main.request.query = {"text": ""}
        await plugin.api_set_remark("10001")
        self.assertNotIn("10001", await plugin._get_remarks())

    async def test_get_users_returns_json_body(self):
        plugin = make_plugin()
        await plugin.put_kv_data("user_quota", {"10001": 2})
        result = await plugin.api_get_users()
        self.assertIn("users", result)
        self.assertEqual(result["users"][0]["remaining"], 2)


class QuartFallbackTest(unittest.TestCase):
    """旧版 AstrBot 没有 astrbot.api.web 时，应退回 quart 实现且不报错。"""

    def test_fallback_to_quart(self):
        saved_web = sys.modules.pop("astrbot.api.web")
        quart = types.ModuleType("quart")
        quart.jsonify = lambda data: ("jsonified", data)
        quart.request = types.SimpleNamespace(args={})
        sys.modules["quart"] = quart
        try:
            reloaded = importlib.reload(main)
            self.assertEqual(reloaded.json_response({"a": 1}), ("jsonified", {"a": 1}))
            body, status = reloaded.error_response("boom")
            self.assertEqual(body, ("jsonified", {"error": "boom"}))
            self.assertEqual(status, 400)
        finally:
            sys.modules.pop("quart", None)
            sys.modules["astrbot.api.web"] = saved_web
            importlib.reload(main)


if __name__ == "__main__":
    unittest.main(verbosity=2)
