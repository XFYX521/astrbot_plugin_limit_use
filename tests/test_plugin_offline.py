"""离线单元测试：不依赖 AstrBot 运行环境，用桩模块 import main.py。

运行：python tests/test_plugin_offline.py
"""

import asyncio
import copy
import datetime
import importlib
import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

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

    # 离线环境没有文转图/Playwright，渲染必然失败，用于验证回落链
    async def html_render(self, tmpl, data, options=None):
        raise RuntimeError("html_render unavailable in tests")

    async def text_to_image(self, text, return_url=True):
        raise RuntimeError("text_to_image unavailable in tests")


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
    def __init__(self, user_id="10001", nickname="测试用户"):
        self._user_id = user_id
        self._nickname = nickname
        self.sent = []
        self.stopped = False

    def get_sender_id(self):
        return self._user_id

    def get_sender_name(self):
        return self._nickname

    def plain_result(self, text):
        return ("plain", text)

    def image_result(self, url):
        return ("image", url)

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


class VersionRegistryTest(unittest.TestCase):
    """versions.json 必须同时是合法的 AstrBot 插件源 JSON。"""

    PLUGIN_ID = "XFYX521/astrbot_plugin_limit_use"

    def setUp(self):
        self.text = (ROOT / "versions.json").read_text(encoding="utf-8")
        self.data = json.loads(self.text)

    def test_root_has_meta_and_single_plugin_entry(self):
        self.assertIsInstance(self.data, dict)
        self.assertIn("$meta", self.data)
        self.assertEqual(self.data["$meta"]["schema_version"], 1)
        # AstrBot 会把除 $meta 外的每个 dict 值当成插件条目；数组会被前端展开成垃圾条目
        entries = [
            key
            for key, value in self.data.items()
            if key != "$meta" and isinstance(value, dict)
        ]
        self.assertEqual(entries, [self.PLUGIN_ID])
        record = self.data[self.PLUGIN_ID]
        for key in ("author", "name", "version", "repo", "desc"):
            self.assertTrue(record.get(key), key)
        self.assertEqual(record["name"], ROOT.name)
        self.assertTrue(record["repo"].startswith("https://github.com/"))
        metadata_version = re.search(
            r"^version:\s*(\S+)", (ROOT / "metadata.yaml").read_text(encoding="utf-8"), re.M
        ).group(1)
        self.assertEqual(record["version"], metadata_version)
        self.assertEqual(record["version"], self.data["$meta"]["releases"][0]["version"])

    def test_release_history_lives_under_meta(self):
        releases = self.data["$meta"]["releases"]
        self.assertGreaterEqual(len(releases), 1)
        for release in releases:
            self.assertRegex(release["version"], r"^v\d+\.\d+\.\d+$")
        # 根级不能出现数组值（前端 getPluginCollections 会遍历所有键）
        self.assertEqual([k for k, v in self.data.items() if isinstance(v, list)], [])


class InvestAssetsTest(unittest.TestCase):
    def test_schema_default_assets(self):
        assets = main._parse_invest_assets(load_schema_defaults()["invest_assets"])
        self.assertEqual([name for name, _ in assets], ["原石", "菲林", "水晶", "星琼"])
        self.assertEqual([price for _, price in assets], [160.0, 100.0, 280.0, 160.0])

    def test_literal_backslash_n_and_invalid_lines(self):
        raw = "原石:160\\n坏行\\n菲林:0\\n水晶:abc\\n星琼:120\\n星琼:999"
        self.assertEqual(
            main._parse_invest_assets(raw),
            [("原石", 160.0), ("星琼", 120.0)],
        )

    def test_garbage_falls_back_to_default_assets(self):
        plugin = make_plugin(invest_assets="完全不是配置")
        self.assertEqual([name for name, _ in plugin._assets()], ["原石", "菲林", "水晶", "星琼"])

    def test_leverage_options(self):
        self.assertEqual(main._parse_leverage_options("2, 5x，10"), [2, 5, 10])
        self.assertEqual(main._parse_leverage_options("bad"), [])
        self.assertEqual(make_plugin(invest_leverage_options="bad")._leverage_options(), [2, 5])


class MovingRateTest(unittest.TestCase):
    def test_same_day_same_asset_is_deterministic(self):
        first = main._moving_rate("原石", "2026-10-31", 3)
        second = main._moving_rate("原石", "2026-10-31", 3)
        self.assertEqual(first, second)

    def test_rate_within_configured_volatility(self):
        for day in ("2026-10-01", "2026-10-02", "2026-10-03"):
            for asset in ("原石", "菲林", "水晶", "星琼"):
                rate = main._moving_rate(asset, day, 3)
                self.assertGreaterEqual(rate, -0.03)
                self.assertLessEqual(rate, 0.03)

    def test_zero_volatility_is_flat(self):
        self.assertEqual(main._moving_rate("原石", "2026-10-31", 0), 0.0)


class InvestCommandTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._rate_mock = mock.Mock(return_value=0.02)
        self._rate_patch = mock.patch.object(main, "_moving_rate", self._rate_mock)
        self._rate_patch.start()
        self.addCleanup(self._rate_patch.stop)

    async def test_long_profit_and_fee(self):
        plugin = make_plugin()
        await plugin.put_kv_data("user_quota", {"10001": 100})
        event = FakeEvent()
        replies = await collect(plugin.invest(event, "原石", "做多", "100", "5x"))

        # 100 次 × 5x × 2% = 10 次毛利；手续费 100×1% = 1 次
        self.assertEqual(len(replies), 1)
        self.assertIn("+9", replies[0][1])  # 无文转图环境回落纯文本
        quota = await plugin._get_quota()
        self.assertEqual(quota["10001"], 109)
        history = await plugin._get_invest_history()
        self.assertEqual(history[-1]["pnl"], 9)
        self.assertEqual(history[-1]["fee"], 1)
        self.assertEqual(history[-1]["direction"], "做多")
        daily = await plugin._get_invest_daily()
        self.assertEqual(daily["10001"], datetime.date.today().isoformat())

    async def test_short_default_leverage(self):
        plugin = make_plugin()
        await plugin.put_kv_data("user_quota", {"10001": 100})
        event = FakeEvent()
        await collect(plugin.invest(event, "菲林", "short", "100"))

        # 做空时行情 +2% 记为 -2%：100×2x×(-2%) = -4 次，手续费 1 次
        quota = await plugin._get_quota()
        self.assertEqual(quota["10001"], 95)
        history = await plugin._get_invest_history()
        self.assertEqual(history[-1]["leverage"], 2)
        self.assertEqual(history[-1]["direction"], "做空")

    async def test_loss_is_clamped_to_zero(self):
        self._rate_mock.return_value = -0.5
        plugin = make_plugin()
        await plugin.put_kv_data("user_quota", {"10001": 20})
        event = FakeEvent()
        await collect(plugin.invest(event, "原石", "做多", "20", "5x"))

        # 20×5×(-50%) = -50 次，手续费 0 次：余额最多亏到 0
        quota = await plugin._get_quota()
        self.assertEqual(quota["10001"], 0)
        history = await plugin._get_invest_history()
        self.assertEqual(history[-1]["pnl"], -50)
        self.assertEqual(history[-1]["balance_after"], 0)

    async def test_daily_limit_and_insufficient_balance(self):
        plugin = make_plugin()
        await plugin.put_kv_data("user_quota", {"10001": 100})
        first = await collect(plugin.invest(FakeEvent(), "原石", "做多", "10"))
        self.assertEqual(len(first), 1)

        second = await collect(plugin.invest(FakeEvent(), "原石", "做多", "10"))
        self.assertIn("已经投资过", second[0][1])
        self.assertEqual(len(await plugin._get_invest_history()), 1)

        plugin2 = make_plugin()
        await plugin2.put_kv_data("user_quota", {"10001": 5})
        too_much = await collect(plugin2.invest(FakeEvent(), "原石", "做多", "10"))
        self.assertIn("不能超过当前余额", too_much[0][1])
        self.assertEqual(await plugin2._get_invest_history(), [])

    async def test_disabled_and_bad_params(self):
        plugin = make_plugin(invest_enabled=False)
        disabled = await collect(plugin.invest(FakeEvent(), "原石", "做多", "10"))
        self.assertIn("已关闭", disabled[0][1])

        plugin = make_plugin()
        await plugin.put_kv_data("user_quota", {"10001": 100})
        bad_asset = await collect(plugin.invest(FakeEvent(), "钻石", "做多", "10"))
        self.assertIn("没有「钻石」", bad_asset[0][1])
        bad_dir = await collect(plugin.invest(FakeEvent(), "原石", "乱写", "10"))
        self.assertIn("做多", bad_dir[0][1])
        bad_lev = await collect(plugin.invest(FakeEvent(), "原石", "做多", "10", "9x"))
        self.assertIn("杠杆", bad_lev[0][1])
        bad_stake = await collect(plugin.invest(FakeEvent(), "原石", "做多", "0"))
        self.assertIn("正整数", bad_stake[0][1])


class CardFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_help_card_falls_back_to_text(self):
        plugin = make_plugin()
        replies = await collect(plugin.help_cmd(FakeEvent()))
        text = replies[0][1]
        self.assertEqual(replies[0][0], "plain")
        self.assertIn(main.PLUGIN_VERSION, text)
        self.assertIn("/投资", text)
        # 管理员指令仍不对外展示
        self.assertNotIn("查看全部余额", text)

    async def test_invest_brief_contains_market_and_balance(self):
        plugin = make_plugin()
        await plugin.put_kv_data("user_quota", {"10001": 7})
        replies = await collect(plugin.invest(FakeEvent()))
        text = replies[0][1]
        self.assertIn("今日行情", text)
        self.assertIn("我的余额：7 次", text)
        self.assertIn("未投资", text)

    def test_card_html_escapes_user_content(self):
        html = main._build_card_html(
            "<script>alert(1)</script>",
            "副标题 & 符号",
            [
                {"type": "kv", "items": [("昵称", "<img src=x onerror=1>")]},
                {"type": "table", "headers": ["<b>"], "rows": [["<i>"]]},
            ],
            "尾巴",
        )
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp;", html)


class InvestApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_investments_returns_latest_first(self):
        plugin = make_plugin()
        await plugin.put_kv_data("invest_history", [
            {"time": "2026-10-30T10:00:00", "asset": "原石"},
            {"time": "2026-10-31T10:00:00", "asset": "星琼"},
        ])
        result = await plugin.api_get_investments()
        self.assertEqual([item["asset"] for item in result["investments"]], ["星琼", "原石"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
