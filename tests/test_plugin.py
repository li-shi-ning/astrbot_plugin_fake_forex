from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

_SPEC = importlib.util.spec_from_file_location(
    "fake_forex_plugin_main", PLUGIN_DIR / "main.py"
)
assert _SPEC is not None and _SPEC.loader is not None
plugin_main = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = plugin_main
_SPEC.loader.exec_module(plugin_main)


class FakeAPI:
    def __init__(self) -> None:
        self.group_messages: list[dict] = []

    async def post_group_message(self, **payload):
        self.group_messages.append(payload)
        return {"id": str(len(self.group_messages))}


class FakeBot:
    def __init__(self) -> None:
        self.api = FakeAPI()


class FakeRawMessage:
    def __init__(self, group_openid: str, member_openid: str) -> None:
        self.group_openid = group_openid
        self.id = "message-id"
        self.msg_seq = 1
        self.author = SimpleNamespace(member_openid=member_openid)


class FakeResult:
    def base64_image(self, _payload: str):
        return "image"


class FakeEvent:
    def __init__(self, member_openid: str = "member", admin: bool = False) -> None:
        self.bot = FakeBot()
        self.raw = FakeRawMessage("group-id", member_openid)
        self.message_obj = SimpleNamespace(raw_message=self.raw, message_id="message-id")
        self.message_str = ""
        self.admin = admin

    def get_platform_name(self) -> str:
        return "qq_official"

    def get_platform_id(self) -> str:
        return "qq_official"

    def get_group_id(self) -> str:
        return self.raw.group_openid

    def get_sender_id(self) -> str:
        return self.raw.author.member_openid

    def get_sender_name(self) -> str:
        return "玩家"

    def get_message_str(self) -> str:
        return self.message_str

    def is_admin(self) -> bool:
        return self.admin

    def plain_result(self, text: str) -> str:
        return text

    def make_result(self) -> FakeResult:
        return FakeResult()

    def stop_event(self) -> None:
        pass


def run(coro):
    return asyncio.run(coro)


async def collect(asyncgen) -> list:
    return [item async for item in asyncgen]


def test_menu_and_market_commands_send_group_payload(tmp_path: Path) -> None:
    with patch.object(plugin_main.StarTools, "get_data_dir", return_value=tmp_path):
        plugin = plugin_main.FakeForexPlugin(context=SimpleNamespace(), config={"tick_seconds": 3600})
        run(plugin.initialize())
        event = FakeEvent()

        run(collect(plugin.menu_command(event)))
        assert event.bot.api.group_messages
        assert "虚拟外汇" in str(event.bot.api.group_messages[-1]["markdown"])

        run(collect(plugin.market_command(event)))
        assert len(event.bot.api.group_messages) >= 2

def test_admin_can_add_custom_instrument(tmp_path: Path) -> None:
    with patch.object(plugin_main.StarTools, "get_data_dir", return_value=tmp_path):
        plugin = plugin_main.FakeForexPlugin(context=SimpleNamespace(), config={"tick_seconds": 3600})
        run(plugin.initialize())
        event = FakeEvent(admin=True)
        event.message_str = "外汇添加股票 NEWX 新股票 33.3"

        run(collect(plugin.add_instrument_command(event)))

        assert event.bot.api.group_messages
        assert "NEWX" in str(event.bot.api.group_messages[-1]["markdown"])

def test_sell_organ_command(tmp_path: Path) -> None:
    with patch.object(plugin_main.StarTools, "get_data_dir", return_value=tmp_path):
        plugin = plugin_main.FakeForexPlugin(context=SimpleNamespace(), config={"tick_seconds": 3600})
        run(plugin.initialize())
        event = FakeEvent()
        event.message_str = "外汇卖器官 心脏"

        run(collect(plugin.sell_organ_command(event)))

        assert event.bot.api.group_messages
        assert "心脏" in str(event.bot.api.group_messages[-1]["markdown"])

def test_rank_command(tmp_path: Path) -> None:
    with patch.object(plugin_main.StarTools, "get_data_dir", return_value=tmp_path):
        plugin = plugin_main.FakeForexPlugin(context=SimpleNamespace(), config={"tick_seconds": 3600})
        run(plugin.initialize())
        event = FakeEvent()

        run(collect(plugin.rank_command(event)))

        assert event.bot.api.group_messages
        assert "排行" in str(event.bot.api.group_messages[-1]["markdown"])

def test_lottery_buy_command(tmp_path: Path) -> None:
    with patch.object(plugin_main.StarTools, "get_data_dir", return_value=tmp_path):
        plugin = plugin_main.FakeForexPlugin(context=SimpleNamespace(), config={"tick_seconds": 3600})
        run(plugin.initialize())
        event = FakeEvent()
        event.message_str = "买彩票 77"

        run(collect(plugin.lottery_buy_command(event)))

        assert event.bot.api.group_messages
        assert "奖池" in str(event.bot.api.group_messages[-1]["markdown"])

def test_lottery_rank_command(tmp_path: Path) -> None:
    with patch.object(plugin_main.StarTools, "get_data_dir", return_value=tmp_path):
        plugin = plugin_main.FakeForexPlugin(context=SimpleNamespace(), config={"tick_seconds": 3600})
        run(plugin.initialize())
        event = FakeEvent()
        event.message_str = "彩票排行"

        run(collect(plugin.lottery_rank_command(event)))

        assert event.bot.api.group_messages
        assert "排行" in str(event.bot.api.group_messages[-1]["markdown"])

def test_marketplace_list_and_buy_flow(tmp_path: Path) -> None:
    with patch.object(plugin_main.StarTools, "get_data_dir", return_value=tmp_path):
        plugin = plugin_main.FakeForexPlugin(context=SimpleNamespace(), config={"tick_seconds": 3600})
        run(plugin.initialize())
        owner = FakeEvent("owner")
        buyer = FakeEvent("buyer")

        owner.message_str = "上架 空气 100"
        run(collect(plugin.market_list_command(owner)))
        assert len(plugin.market_listings) == 1
        listing_id = next(iter(plugin.market_listings))

        buyer.message_str = f"购买 {listing_id}"
        run(collect(plugin.market_buy_command(buyer)))

        owner_account = plugin.accounts["group-id"]["owner"]
        buyer_account = plugin.accounts["group-id"]["buyer"]
        assert owner_account.cash == 10100.0
        assert buyer_account.cash == 9900.0
        assert buyer_account.inventory[0]["name"] == "空气"
        assert plugin.market_listings == {}
        assert buyer_account.trading_pnl(plugin.market) == 0.0


def test_marketplace_limit_and_negative_price(tmp_path: Path) -> None:
    with patch.object(plugin_main.StarTools, "get_data_dir", return_value=tmp_path):
        plugin = plugin_main.FakeForexPlugin(context=SimpleNamespace(), config={"tick_seconds": 3600})
        run(plugin.initialize())
        owner = FakeEvent("owner")

        for index in range(5):
            owner.message_str = f"上架 商品{index} {index + 1}"
            run(collect(plugin.market_list_command(owner)))
        assert len(plugin.market_listings) == 5

        owner.message_str = "上架 商品5 6"
        results = run(collect(plugin.market_list_command(owner)))
        assert results
        assert len(plugin.market_listings) == 5

        owner.message_str = "上架 负数商品 -1"
        results = run(collect(plugin.market_list_command(owner)))
        assert results
        assert len(plugin.market_listings) == 5

def test_marketplace_pagination_layout(tmp_path: Path) -> None:
    with patch.object(plugin_main.StarTools, "get_data_dir", return_value=tmp_path):
        plugin = plugin_main.FakeForexPlugin(context=SimpleNamespace(), config={"tick_seconds": 3600})
    for index in range(1, 14):
        plugin.market_listings[str(index)] = {
            "id": str(index),
            "name": f"商品{index}",
            "price": float(index),
            "seller_id": "other",
            "seller_name": "别人",
        }
    account = plugin_main.Account("me", "我")
    page_one = plugin._marketplace_buttons(account, 1)
    page_two = plugin._marketplace_buttons(account, 2)
    assert len(page_one) == 15
    assert [item.label for item in page_one[-3:]] == ["上一页", "第 1/2 页", "下一页"]
    assert len(page_two) == 4
    assert [item.label for item in page_two[-3:]] == ["上一页", "第 2/2 页", "下一页"]

def test_leaderboard_baseline_recalculates_from_current_equity(tmp_path: Path) -> None:
    with patch.object(plugin_main.StarTools, "get_data_dir", return_value=tmp_path):
        plugin = plugin_main.FakeForexPlugin(context=SimpleNamespace(), config={"tick_seconds": 3600, "initial_cash": 10000})
    account = plugin_main.Account("u", "Tester", cash=15000.0, debt=0.0)
    plugin.accounts = {"group-id": {"u": account}}

    migrated = plugin._recalculate_leaderboard_baseline()

    assert migrated == 1
    assert account.realized_pnl == 5000.0
    assert account.trading_pnl(plugin.market) == 5000.0
