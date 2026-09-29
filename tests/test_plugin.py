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
