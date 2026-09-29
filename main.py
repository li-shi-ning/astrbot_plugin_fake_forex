from __future__ import annotations

import asyncio
import base64
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

try:
    from .src.engine import (
        PAIR_IDS,
        PAIR_MAP,
        Account,
        FxError,
        Market,
        advance_market,
        borrow,
        close_position,
        instrument_defs,
        loan_limit,
        money,
        normalize_organ,
        normalize_pair,
        open_position,
        organ_day_total,
        organ_defs,
        price_text,
        register_instrument,
        repay,
        sell_organ,
        signed_money,
    )
    from .src.qqofficial import (
        ButtonSpec,
        extract_context,
        is_qqofficial_event,
        send_group_reply,
    )
    from .src.render import (
        render_account,
        render_chart,
        render_history,
        render_market,
        render_organs,
    )
    from .src.storage import FxStore
except ImportError:  # pragma: no cover - direct local import fallback
    from src.engine import (
        PAIR_IDS,
        PAIR_MAP,
        Account,
        FxError,
        Market,
        advance_market,
        borrow,
        close_position,
        instrument_defs,
        loan_limit,
        money,
        normalize_organ,
        normalize_pair,
        open_position,
        organ_day_total,
        organ_defs,
        price_text,
        register_instrument,
        repay,
        sell_organ,
        signed_money,
    )
    from src.qqofficial import (
        ButtonSpec,
        extract_context,
        is_qqofficial_event,
        send_group_reply,
    )
    from src.render import (
        render_account,
        render_chart,
        render_history,
        render_market,
        render_organs,
    )
    from src.storage import FxStore


PLUGIN_NAME = "astrbot_plugin_fake_forex"
BEIJING_TZ = timezone(timedelta(hours=8))
STATE_FILENAME = "fx_state.json"


@dataclass
class CommandOutcome:
    """Result of one fake forex command."""

    text: str = ""
    image: bytes | None = None
    buttons: list[ButtonSpec] | None = None
    error: bool = False


@register(
    PLUGIN_NAME,
    "Codex",
    "QQ 官方群聊虚拟外汇交易插件，完全虚假行情，支持按钮、做多做空、保证金、杠杆、爆仓和贷款。",
    "1.0.0",
)
class FakeForexPlugin(Star):
    def __init__(self, context: Context, config: Any = None) -> None:
        super().__init__(context)
        self.config = dict(config) if config else {}
        self.tick_seconds = self._config_int("tick_seconds", 30, minimum=5)
        self.max_offline_ticks = self._config_int(
            "max_offline_ticks", 240, minimum=1, maximum=5000
        )
        self.initial_cash = self._config_float("initial_cash", 10000.0, minimum=100)
        data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        data_dir.mkdir(parents=True, exist_ok=True)
        self.store = FxStore(data_dir / STATE_FILENAME)
        self.market = Market.new()
        self.accounts: dict[str, dict[str, Account]] = {}
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Load the global market and per-group accounts."""

        state = await self.store.load()
        custom_instruments = (
            state.get("instruments") if isinstance(state, dict) else None
        )
        if isinstance(custom_instruments, list):
            for item in custom_instruments:
                if not isinstance(item, dict):
                    continue
                try:
                    register_instrument(
                        str(item.get("id") or ""),
                        str(item.get("name") or ""),
                        float(item.get("initial") or 0),
                        int(item.get("digits") or 2),
                    )
                except (FxError, TypeError, ValueError) as exc:
                    logger.warning("[FakeForex] invalid saved instrument: %s", exc)
        market_data = state.get("market") if isinstance(state, dict) else None
        if isinstance(market_data, dict):
            self.market = Market.from_dict(market_data)
        groups = state.get("groups") if isinstance(state, dict) else None
        if isinstance(groups, dict):
            self.accounts = {
                str(group_id): {
                    str(user_id): Account.from_dict(account_data)
                    for user_id, account_data in dict(players).items()
                }
                for group_id, players in groups.items()
                if isinstance(players, dict)
            }
        logger.info("[FakeForex] initialized: %s", self.store.path)

    async def terminate(self) -> None:
        """Persist the current state on unload."""

        await self._save_state()
        self.accounts.clear()

    # ------------------------------------------------------------------
    # Command registration
    # ------------------------------------------------------------------
    @filter.command(
        "外汇菜单", alias={"外汇帮助", "炒股菜单", "炒股帮助", "虚拟外汇", "外汇"}
    )
    async def menu_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "menu"):
            yield result
        event.stop_event()

    @filter.command("外汇行情", alias={"行情", "炒股行情", "虚拟外汇行情"})
    async def market_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "market"):
            yield result
        event.stop_event()

    @filter.command("外汇查看", alias={"查看", "查看行情", "外汇报价"})
    async def quote_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "quote"):
            yield result
        event.stop_event()

    @filter.command("外汇做多", alias={"做多", "买入", "外汇买入"})
    async def long_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "long"):
            yield result
        event.stop_event()

    @filter.command("外汇做空", alias={"做空", "卖空", "外汇卖空"})
    async def short_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "short"):
            yield result
        event.stop_event()

    @filter.command("外汇持仓", alias={"持仓", "我的持仓", "外汇仓位"})
    async def positions_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "positions"):
            yield result
        event.stop_event()

    @filter.command("外汇平仓", alias={"平仓", "外汇卖出平仓", "卖出平仓"})
    async def close_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "close"):
            yield result
        event.stop_event()

    @filter.command("外汇全平", alias={"全平", "全部平仓"})
    async def close_all_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "close_all"):
            yield result
        event.stop_event()

    @filter.command("外汇账户", alias={"账户", "我的账户", "外汇资产"})
    async def account_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "account"):
            yield result
        event.stop_event()

    @filter.command("外汇设置", alias={"设置外汇", "外汇默认", "交易设置"})
    async def settings_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "settings"):
            yield result
        event.stop_event()

    @filter.command("外汇借款", alias={"借款", "贷款"})
    async def borrow_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "borrow"):
            yield result
        event.stop_event()

    @filter.command("外汇还款", alias={"还款", "还贷"})
    async def repay_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "repay"):
            yield result
        event.stop_event()

    @filter.command("外汇历史", alias={"交易历史", "外汇记录", "成交记录"})
    async def history_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "history"):
            yield result
        event.stop_event()

    @filter.command(
        "外汇添加股票",
        alias={"添加股票", "股票添加", "外汇新增股票", "股票新增"},
    )
    async def add_instrument_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "add_instrument"):
            yield result
        event.stop_event()

    @filter.command(
        "外汇器官", alias={"器官菜单", "器官回收", "器官列表", "卖器官列表"}
    )
    async def organs_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "organs"):
            yield result
        event.stop_event()

    @filter.command("外汇卖器官", alias={"卖器官", "出售器官", "器官出售"})
    async def sell_organ_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "sell_organ"):
            yield result
        event.stop_event()

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    async def _handle_command(self, event: AstrMessageEvent, command: str):
        """Run one command under the global market lock."""

        group_id, user_id, name = self._identity(event)
        if not group_id:
            yield event.plain_result("虚拟外汇只能在群聊中使用。")
            return
        async with self.lock:
            try:
                await self._advance_market()
                outcome = await self._execute_command(
                    event, group_id, user_id, name, command
                )
                await self._save_state()
            except FxError as exc:
                outcome = CommandOutcome(text=str(exc), error=True)
            except Exception as exc:  # noqa: BLE001 - keep one group isolated
                logger.exception("[FakeForex] command %s failed: %s", command, exc)
                outcome = CommandOutcome(text=f"虚拟外汇处理失败：{exc}", error=True)

        if outcome.error:
            yield event.plain_result(outcome.text)
            return
        if outcome.image is not None:
            yield event.make_result().base64_image(
                base64.b64encode(outcome.image).decode("utf-8")
            )
            if not outcome.text and not outcome.buttons:
                return
        if await self._try_send_qqofficial(event, outcome.text, outcome.buttons):
            return
        if outcome.text:
            yield event.plain_result(outcome.text)

    async def _execute_command(
        self,
        event: AstrMessageEvent,
        group_id: str,
        user_id: str,
        name: str,
        command: str,
    ) -> CommandOutcome:
        """Execute one parsed command."""

        account = self._ensure_account(group_id, user_id, name)
        text = self._message_text(event)
        notes = self._take_notes(account)
        day = self._today()

        if command == "menu":
            return self._with_notes(notes, self._menu_outcome())
        if command == "market":
            return self._with_notes(notes, self._market_outcome(account))
        if command == "quote":
            pair_id = self._pair_arg(text)
            if pair_id is None:
                raise FxError("请带上股票代码或名称，例如：外汇查看 水母水产。")
            series = self.market.pairs[pair_id]
            change = series.change_percent()
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=(
                        f"{pair_id} {PAIR_MAP[pair_id]['name']} "
                        f"{price_text(pair_id, series.price)} {change:+.2f}%  "
                        f"买 {price_text(pair_id, self.market.ask(pair_id))} / "
                        f"卖 {price_text(pair_id, self.market.bid(pair_id))}  "
                        f"点差 {self.market.spread_pct(pair_id):.2f}%  "
                        f"最大杠杆 {self.market.max_leverage(pair_id)}x"
                        + self._news_suffix(pair_id)
                    ),
                    image=render_chart(self.market, pair_id),
                    buttons=self._pair_buttons(account, pair_id),
                ),
            )
        if command in {"long", "short"}:
            pair_id = self._pair_arg(text)
            if pair_id is None:
                raise FxError("请带上股票代码或名称，例如：外汇做多 水母水产 500 20。")
            numbers = self._numbers(text)
            margin = numbers[0] if numbers else None
            leverage = int(numbers[1]) if len(numbers) > 1 else None
            position = open_position(
                account,
                self.market,
                pair_id,
                side=1 if command == "long" else -1,
                margin=margin,
                leverage=leverage,
            )
            pnl = position.pnl(self.market)
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=(
                        f"已开仓 {position.pair} {position.side_label} "
                        f"保证金 {money(position.margin)} ×{position.leverage} "
                        f"开仓价 {price_text(position.pair, position.entry)} "
                        f"浮动盈亏 {signed_money(pnl)}"
                    ),
                    buttons=self._position_action_buttons(account, position.id),
                ),
            )
        if command == "positions":
            return self._with_notes(
                notes,
                CommandOutcome(
                    text="持仓",
                    image=render_account(account, self.market),
                    buttons=self._positions_buttons(account),
                ),
            )
        if command == "close":
            position_id = self._position_arg(text, account)
            record = close_position(account, self.market, position_id)
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=(
                        f"已平仓 {record['pair']} {record['side']} "
                        f"盈亏 {signed_money(record['pnl'])}"
                    ),
                    buttons=self._account_buttons(),
                ),
            )
        if command == "close_all":
            if not account.positions:
                raise FxError("当前没有持仓。")
            total = 0.0
            for position in list(account.positions):
                record = close_position(account, self.market, position.id)
                total += float(record["pnl"])
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=f"已全部平仓，合计盈亏 {signed_money(total)}",
                    buttons=self._account_buttons(),
                ),
            )
        if command == "account":
            return self._with_notes(
                notes,
                CommandOutcome(
                    text="账户",
                    image=render_account(account, self.market),
                    buttons=self._account_buttons(),
                ),
            )
        if command == "settings":
            return self._with_notes(notes, self._settings_outcome(account, text))
        if command == "borrow":
            amount = self._amount_arg(text)
            if amount is None:
                raise FxError("请带上借款金额，例如：外汇借款 10000。")
            debt = borrow(account, amount, day)
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=(
                        f"已借款 {money(amount)}，当前欠款 {money(debt)}，"
                        f"当前额度上限 {money(loan_limit(account))}，"
                        "每 30 分钟利率 3.00%，复利计息"
                    )
                ),
            )
        if command == "repay":
            amount = self._amount_arg(text)
            if amount is None:
                raise FxError("请带上还款金额，例如：外汇还款 5000。")
            paid = repay(account, amount)
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=f"已还款 {money(paid)}，剩余欠款 {money(account.debt)}"
                ),
            )
        if command == "history":
            return self._with_notes(
                notes,
                CommandOutcome(
                    text="交易历史",
                    image=render_history(account),
                    buttons=self._account_buttons(),
                ),
            )
        if command == "organs":
            return self._with_notes(notes, self._organs_outcome(account))
        if command == "sell_organ":
            organ_id = normalize_organ(text)
            if organ_id is None:
                raise FxError("请带上器官名，例如：外汇卖器官 心脏。")
            result = sell_organ(account, organ_id, day)
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=(
                        f"已出售 {result['name']}，到账 {money(result['price'])}；"
                        f"今日器官收入 {money(result['day_total'])}。"
                    ),
                    image=render_organs(account, day),
                    buttons=self._organ_buttons(account, day),
                ),
            )
        if command == "add_instrument":
            if not self._is_admin(event):
                raise FxError("只有管理员可以添加股票。")
            code, name, price, digits = self._parse_instrument_args(text)
            definition = register_instrument(code, name, price, digits)
            self.market.add_instrument(definition)
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=(
                        f"已添加 {definition['id']} {definition['name']} "
                        f"初始价 {price_text(definition['id'], float(definition['initial']))}"
                    ),
                    buttons=self._market_buttons(),
                ),
            )
        raise FxError("未知指令。")

    # ------------------------------------------------------------------
    # Outcomes and buttons
    # ------------------------------------------------------------------
    def _organs_outcome(self, account: Account) -> CommandOutcome:
        day = self._today()
        return CommandOutcome(
            text=f"器官回收站，今日已卖 {money(organ_day_total(account, day))}",
            image=render_organs(account, day),
            buttons=self._organ_buttons(account, day),
        )

    def _organ_buttons(self, account: Account, day: str) -> list[ButtonSpec]:
        buttons: list[ButtonSpec] = []
        for index, item in enumerate(organ_defs(), start=1):
            sold = account.organ_sold_day.get(item["id"]) == day
            price_label = f"{item['price'] / 1000:.0f}k"
            buttons.append(
                ButtonSpec(
                    f"fx_organ_{index}",
                    f"{item['name']} {price_label}{' 已卖' if sold else ''}",
                    f"外汇卖器官 {item['name']}",
                )
            )
        buttons.append(ButtonSpec("fx_organ_account", "账户", "外汇账户"))
        buttons.append(ButtonSpec("fx_organ_help", "帮助", "外汇帮助"))
        return buttons

    def _menu_outcome(self) -> CommandOutcome:
        text = (
            "虚拟外汇\n"
            "完全虚假行情，不接真实交易数据。\n\n"
            "外汇行情：查看全部股票\n"
            "外汇查看 水母水产：查看单个 K 线图\n"
            "外汇做多 水母水产 500 20\n"
            "外汇做空 水母水产 500 20\n"
            "外汇持仓 / 外汇平仓 编号\n"
            "外汇账户 / 外汇历史\n"
            "外汇设置 保证金 500 / 外汇设置 杠杆 20\n"
            "外汇器官 / 外汇卖器官 心脏\n"
            "外汇借款 10000 / 外汇还款 5000\n"
            "管理员：外汇添加股票 <代码> <名称> <初始价>\n\n"
            "规则：最低保证金 $10，最大杠杆 100x；"
            "开/平仓各收 0.05% 手续费，大单有滑点；"
            "每 30 分钟收持仓费，做空额外收借券费；"
            "波动率越高最大杠杆越低；突发新闻会造成跳空；"
            "爆仓额外收 1% 名义仓位罚金；"
            "贷款每 30 分钟按 3% 复利计息；"
            "基础额度 $200,000，每天额外 +$200,000。"
        )
        return CommandOutcome(text=text, buttons=self._menu_buttons())

    def _market_outcome(self, account: Account) -> CommandOutcome:
        text = "行情"
        news = self.market.latest_news(limit=3)
        if news:
            text += "\n" + "\n".join(f"· {item['text']}" for item in news)
        return CommandOutcome(
            text=text,
            image=render_market(self.market),
            buttons=self._market_buttons(),
        )

    def _news_suffix(self, pair_id: str) -> str:
        news = self.market.latest_news(pair_id, limit=1)
        if not news:
            return ""
        return f"\n最新：{news[0]['text']}"

    def _settings_outcome(self, account: Account, text: str) -> CommandOutcome:
        margin_match = re.search(r"保证金\s*[:：]?\s*(\d+(?:\.\d+)?)", text)
        leverage_match = re.search(r"杠杆\s*[:：]?\s*(\d+)", text)
        numbers = self._numbers(text)
        if margin_match:
            margin = float(margin_match.group(1))
            if margin < 10:
                raise FxError("最低保证金为 $10。")
            account.margin_default = margin
        elif "保证金" not in text and len(numbers) >= 1:
            margin = float(numbers[0])
            if margin < 10:
                raise FxError("最低保证金为 $10。")
            account.margin_default = margin
        if leverage_match:
            leverage = int(leverage_match.group(1))
            if not 1 <= leverage <= 100:
                raise FxError("杠杆范围是 1-100 倍。")
            account.leverage_default = leverage
        elif "杠杆" not in text and len(numbers) >= 2:
            leverage = int(numbers[1])
            if not 1 <= leverage <= 100:
                raise FxError("杠杆范围是 1-100 倍。")
            account.leverage_default = leverage
        return CommandOutcome(
            text=(
                f"默认保证金 {money(account.margin_default)}，"
                f"默认杠杆 {account.leverage_default}x"
            ),
            buttons=self._account_buttons(),
        )

    def _menu_buttons(self) -> list[ButtonSpec]:
        return [
            ButtonSpec("fx_menu_market", "行情", "外汇行情"),
            ButtonSpec("fx_menu_account", "账户", "外汇账户"),
            ButtonSpec("fx_menu_positions", "持仓", "外汇持仓"),
            ButtonSpec("fx_menu_history", "历史", "外汇历史"),
            ButtonSpec("fx_menu_organs", "器官", "外汇器官"),
            ButtonSpec("fx_menu_borrow", "借款", "外汇借款 10000"),
            ButtonSpec("fx_menu_repay", "还款", "外汇还款 5000"),
            ButtonSpec("fx_menu_help", "帮助", "外汇帮助"),
        ]

    def _market_buttons(self) -> list[ButtonSpec]:
        buttons = [
            ButtonSpec(f"fx_market_{index}", pair_id, f"外汇查看 {pair_id}")
            for index, pair_id in enumerate(PAIR_IDS, start=1)
        ]
        buttons.append(ButtonSpec("fx_market_account", "账户", "外汇账户"))
        buttons.append(ButtonSpec("fx_market_help", "帮助", "外汇帮助"))
        return buttons

    def _pair_buttons(self, account: Account, pair_id: str) -> list[ButtonSpec]:
        margin = (
            int(account.margin_default)
            if account.margin_default.is_integer()
            else account.margin_default
        )
        leverage = account.leverage_default
        return [
            ButtonSpec(
                "fx_pair_long",
                "做多",
                f"外汇做多 {pair_id} {margin} {leverage}",
                only_for=account.user_id,
            ),
            ButtonSpec(
                "fx_pair_short",
                "做空",
                f"外汇做空 {pair_id} {margin} {leverage}",
                only_for=account.user_id,
            ),
            ButtonSpec("fx_pair_market", "行情", "外汇行情"),
            ButtonSpec("fx_pair_positions", "持仓", "外汇持仓"),
            ButtonSpec("fx_pair_help", "帮助", "外汇帮助"),
        ]

    def _position_action_buttons(
        self, account: Account, position_id: str
    ) -> list[ButtonSpec]:
        return [
            ButtonSpec(
                "fx_position_close",
                "平仓",
                f"外汇平仓 {position_id}",
                only_for=account.user_id,
            ),
            ButtonSpec("fx_position_market", "行情", "外汇行情"),
            ButtonSpec("fx_position_account", "账户", "外汇账户"),
        ]

    def _positions_buttons(self, account: Account) -> list[ButtonSpec]:
        buttons: list[ButtonSpec] = []
        for position in account.positions[:20]:
            buttons.append(
                ButtonSpec(
                    f"fx_close_{position.id}",
                    f"平仓 {position.pair}",
                    f"外汇平仓 {position.id}",
                    only_for=account.user_id,
                )
            )
        buttons.append(
            ButtonSpec(
                "fx_positions_close_all",
                "全平",
                "外汇全平",
                only_for=account.user_id,
            )
        )
        buttons.append(ButtonSpec("fx_positions_market", "行情", "外汇行情"))
        buttons.append(ButtonSpec("fx_positions_account", "账户", "外汇账户"))
        return buttons

    def _account_buttons(self) -> list[ButtonSpec]:
        return [
            ButtonSpec("fx_account_market", "行情", "外汇行情"),
            ButtonSpec("fx_account_positions", "持仓", "外汇持仓"),
            ButtonSpec("fx_account_history", "历史", "外汇历史"),
            ButtonSpec("fx_account_organs", "器官", "外汇器官"),
            ButtonSpec("fx_account_help", "帮助", "外汇帮助"),
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _today(self) -> str:
        return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

    def _identity(self, event: AstrMessageEvent) -> tuple[str, str, str]:
        group_id = str(event.get_group_id() or "")
        user_id = str(event.get_sender_id() or "")
        name = str(event.get_sender_name() or "") or f"玩家_{user_id[-6:]}"
        return group_id, user_id, name

    def _ensure_account(self, group_id: str, user_id: str, name: str) -> Account:
        group = self.accounts.setdefault(group_id, {})
        account = group.get(user_id)
        if account is None:
            account = Account(user_id=user_id, name=name, cash=self.initial_cash)
            group[user_id] = account
        if name and account.name != name:
            account.name = name
        return account

    def _all_accounts(self) -> list[Account]:
        return [
            account
            for players in self.accounts.values()
            for account in players.values()
        ]

    async def _advance_market(self) -> None:
        advance_market(
            self.market,
            self._all_accounts(),
            self.tick_seconds,
            self.max_offline_ticks,
        )

    async def _save_state(self) -> None:
        await self.store.save(
            {
                "market": self.market.to_dict(),
                "instruments": instrument_defs(),
                "groups": {
                    group_id: {
                        user_id: account.to_dict()
                        for user_id, account in players.items()
                    }
                    for group_id, players in self.accounts.items()
                },
            }
        )

    async def _try_send_qqofficial(
        self,
        event: AstrMessageEvent,
        text: str,
        buttons: list[ButtonSpec] | None,
    ) -> bool:
        if not is_qqofficial_event(event):
            return False
        context = extract_context(event)
        if context is None:
            return False
        return await send_group_reply(event, context, text, buttons or [])

    def _with_notes(self, notes: list[str], outcome: CommandOutcome) -> CommandOutcome:
        if notes:
            prefix = "通知：" + "；".join(notes)
            outcome.text = f"{prefix}\n{outcome.text}".strip()
        return outcome

    def _take_notes(self, account: Account) -> list[str]:
        notes = list(account.notes)
        account.notes.clear()
        return notes

    def _message_text(self, event: AstrMessageEvent) -> str:
        getter = getattr(event, "get_message_str", None)
        if callable(getter):
            return str(getter() or "")
        return str(getattr(event, "message_str", "") or "")

    def _pair_arg(self, text: str) -> str | None:
        return normalize_pair(text)

    def _parse_instrument_args(self, text: str) -> tuple[str, str, float, int]:
        match = re.search(
            r"([A-Za-z0-9]{2,12})\s+([^\d\s]{1,24})\s+(\d+(?:\.\d+)?)(?:\s+(\d+))?",
            text,
        )
        if not match:
            raise FxError("格式：外汇添加股票 <代码> <名称> <初始价> [小数位]。")
        code, name, price, digits = match.groups()
        return code, name, float(price), int(digits) if digits else 2

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        try:
            return bool(event.is_admin())
        except Exception:  # noqa: BLE001 - test doubles may not implement it
            return False

    def _numbers(self, text: str) -> list[float]:
        return [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text)]

    def _position_arg(self, text: str, account: Account) -> str:
        match = re.search(r"p\d{3,}", text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
        numbers = re.findall(r"\d+", text)
        if numbers and account.positions:
            index = int(numbers[-1])
            if 1 <= index <= len(account.positions):
                return account.positions[index - 1].id
        raise FxError("请带上持仓编号，例如：外汇平仓 p1234567。")

    def _amount_arg(self, text: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(万)?", text)
        if not match:
            return None
        value = float(match.group(1))
        if match.group(2):
            value *= 10000
        return value

    def _config_int(
        self,
        key: str,
        default: int,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        raw = self.config.get(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _config_float(
        self,
        key: str,
        default: float,
        *,
        minimum: float | None = None,
    ) -> float:
        raw = self.config.get(key, default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default
        if minimum is not None:
            value = max(minimum, value)
        return value
