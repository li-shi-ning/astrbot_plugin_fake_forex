from __future__ import annotations

import asyncio
import base64
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

try:
    from .src.engine import (
        LOTTERY_BASE_POOL,
        LOTTERY_MAX_POOL,
        LOTTERY_POOL_INCREASE,
        LOTTERY_TICKET_PRICE,
        PAIR_IDS,
        PAIR_MAP,
        Account,
        FxError,
        Market,
        advance_market,
        apply_bankruptcy,
        borrow,
        buy_lottery_ticket,
        buy_organ,
        close_position,
        instrument_defs,
        loan_limit,
        money,
        normalize_organ,
        normalize_pair,
        open_position,
        organ_defs,
        organ_income_total,
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
        render_backpack,
        render_chart,
        render_history,
        render_leaderboard,
        render_lottery_leaderboard,
        render_lottery_ticket,
        render_market,
        render_marketplace,
        render_organs,
    )
    from .src.storage import FxStore
except ImportError:  # pragma: no cover - direct local import fallback
    from src.engine import (
        LOTTERY_BASE_POOL,
        LOTTERY_MAX_POOL,
        LOTTERY_POOL_INCREASE,
        LOTTERY_TICKET_PRICE,
        PAIR_IDS,
        PAIR_MAP,
        Account,
        FxError,
        Market,
        advance_market,
        apply_bankruptcy,
        borrow,
        buy_lottery_ticket,
        buy_organ,
        close_position,
        instrument_defs,
        loan_limit,
        money,
        normalize_organ,
        normalize_pair,
        open_position,
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
        render_backpack,
        render_chart,
        render_history,
        render_leaderboard,
        render_lottery_leaderboard,
        render_lottery_ticket,
        render_market,
        render_marketplace,
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
        self.lottery_pool = LOTTERY_BASE_POOL
        self.market_listings: dict[str, dict[str, Any]] = {}
        self.next_listing_id = 1
        self.accounts: dict[str, dict[str, Account]] = {}
        self.lock = asyncio.Lock()
        self.lottery_lock = asyncio.Lock()

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

    @filter.command("外汇排行", alias={"排行榜", "盈利排行", "外汇排行榜", "群友排行"})
    async def rank_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "rank"):
            yield result
        event.stop_event()

    @filter.command("破产申请", alias={"申请破产", "破产救济", "救济申请"})
    async def bankruptcy_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "bankruptcy"):
            yield result
        event.stop_event()

    @filter.command("彩票菜单", alias={"彩票", "彩票帮助", "虚拟彩票"})
    async def lottery_menu_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "lottery_menu"):
            yield result
        event.stop_event()

    @filter.command("买彩票", alias={"购买彩票", "彩票购买", "下注彩票"})
    async def lottery_buy_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "lottery_buy"):
            yield result
        event.stop_event()

    @filter.command("彩票奖池", alias={"奖池", "查看奖池"})
    async def lottery_pool_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "lottery_pool"):
            yield result
        event.stop_event()

    @filter.command(
        "彩票排行", alias={"中奖排行", "彩票排行榜", "中奖排行榜", "彩票榜"}
    )
    async def lottery_rank_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "lottery_rank"):
            yield result
        event.stop_event()

    @filter.command("市场菜单", alias={"市场", "市场帮助"})
    async def market_menu_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "market_menu"):
            yield result
        event.stop_event()

    @filter.command("集市", alias={"市场集市", "查看集市"})
    async def marketplace_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "marketplace"):
            yield result
        event.stop_event()

    @filter.command("上架", alias={"市场出售", "出售商品", "上架商品"})
    async def market_list_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "market_list"):
            yield result
        event.stop_event()

    @filter.command("下架", alias={"市场下架", "下架商品"})
    async def market_cancel_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "market_cancel"):
            yield result
        event.stop_event()

    @filter.command("购买", alias={"买商品", "市场购买", "购买商品"})
    async def market_buy_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "market_buy"):
            yield result
        event.stop_event()

    @filter.command("背包", alias={"我的背包", "查看背包"})
    async def backpack_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "backpack"):
            yield result
        event.stop_event()

    @filter.command("外汇卖器官", alias={"卖器官", "出售器官", "器官出售"})
    async def sell_organ_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "sell_organ"):
            yield result
        event.stop_event()

    @filter.command("外汇买器官", alias={"买器官", "购回器官", "器官买回"})
    async def buy_organ_command(self, event: AstrMessageEvent):
        async for result in self._handle_command(event, "buy_organ"):
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
        if command == "rank":
            entries: list[dict[str, Any]] = []
            for player in self.accounts.get(group_id, {}).values():
                realized = sum(float(item.get("pnl") or 0) for item in player.history)
                floating = player.floating_pnl(self.market)
                entries.append(
                    {
                        "name": player.name,
                        "realized": realized,
                        "floating": floating,
                        "pnl": realized + floating,
                    }
                )
            entries.sort(key=lambda item: float(item["pnl"]), reverse=True)
            for index, item in enumerate(entries, start=1):
                item["rank"] = index
            return self._with_notes(
                notes,
                CommandOutcome(
                    text="群友盈亏排行",
                    image=render_leaderboard(entries),
                    buttons=self._account_buttons(),
                ),
            )
        if command == "bankruptcy":
            result = apply_bankruptcy(account, self.market, day)
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=(
                        f"破产救济已到账：现金恢复到 {money(result['cash'])}，"
                        f"债务从 {money(result['old_debt'])} 降到 "
                        f"{money(result['remaining_debt'])}。\n"
                        f"今日剩余申请次数：{result['remaining_today']}/3。"
                        "本救济不计入交易盈亏排行榜。"
                    ),
                    buttons=self._account_buttons(),
                ),
            )
        if command == "lottery_menu":
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=(
                        f"彩票系统\n"
                        f"基础奖池 {money(LOTTERY_BASE_POOL)}\n"
                        f"当前奖池 {money(self.lottery_pool)} / 上限 {money(LOTTERY_MAX_POOL)}\n"
                        f"票价 {money(LOTTERY_TICKET_PRICE)}，数字 1-100\n"
                        f"每张彩票向奖池注入 {money(LOTTERY_POOL_INCREASE)}\n"
                        "买彩票 <数字> 立即开奖；中奖清空奖池，只保留基础奖池。"
                    ),
                    buttons=self._lottery_buttons(),
                ),
            )
        if command == "lottery_pool":
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=f"当前彩票奖池：{money(self.lottery_pool)}",
                    buttons=self._lottery_buttons(),
                ),
            )
        if command == "lottery_rank":
            entries: list[dict[str, Any]] = []
            for players in self.accounts.values():
                for player in players.values():
                    if player.lottery_winnings <= 0:
                        continue
                    entries.append(
                        {
                            "name": player.name,
                            "winnings": player.lottery_winnings,
                            "wins": player.lottery_win_count,
                        }
                    )
            entries.sort(key=lambda item: float(item["winnings"]), reverse=True)
            for index, item in enumerate(entries, start=1):
                item["rank"] = index
            return self._with_notes(
                notes,
                CommandOutcome(
                    text="彩票中奖排行（全服，含历史记录）",
                    image=render_lottery_leaderboard(entries, self.lottery_pool),
                    buttons=self._lottery_buttons(),
                ),
            )
        if command == "market_menu":
            return self._with_notes(notes, self._market_menu_outcome(account))
        if command == "marketplace":
            page = self._page_arg(text)
            return self._with_notes(notes, self._marketplace_outcome(account, page))
        if command == "market_list":
            name, price = self._parse_listing_args(text)
            mine = [
                item
                for item in self.market_listings.values()
                if item.get("seller_group") == group_id
                and item.get("seller_id") == user_id
            ]
            if len(mine) >= 5:
                raise FxError("你最多只能同时上架 5 件商品，请先下架一些。")
            listing_id = str(self.next_listing_id)
            self.next_listing_id += 1
            self.market_listings[listing_id] = {
                "id": listing_id,
                "name": name,
                "price": float(price),
                "seller_group": group_id,
                "seller_id": user_id,
                "seller_name": account.name,
                "created_at": time.time(),
            }
            return self._with_notes(
                notes,
                self._marketplace_outcome(
                    account,
                    page=1,
                    prefix=f"已上架 #{listing_id} {name}，价格 {money(price)}。",
                ),
            )
        if command == "market_cancel":
            listing_id = self._listing_id_arg(text)
            listing = self.market_listings.get(listing_id)
            if listing is None:
                raise FxError("找不到这个商品编号。")
            if not (
                listing.get("seller_group") == group_id
                and listing.get("seller_id") == user_id
            ):
                raise FxError("只能下架自己的商品。")
            del self.market_listings[listing_id]
            return self._with_notes(
                notes,
                self._marketplace_outcome(
                    account,
                    page=1,
                    prefix=f"已下架 #{listing_id} {listing.get('name')}。",
                ),
            )
        if command == "market_buy":
            listing_id = self._listing_id_arg(text)
            listing = self.market_listings.get(listing_id)
            if listing is None:
                raise FxError("找不到这个商品编号。")
            if (
                listing.get("seller_group") == group_id
                and listing.get("seller_id") == user_id
            ):
                raise FxError("不能购买自己的商品。")
            price = float(listing.get("price") or 0)
            if account.cash < price:
                raise FxError(f"现金不足，购买需要 {money(price)}。")
            seller_group = str(listing.get("seller_group") or "")
            seller_id = str(listing.get("seller_id") or "")
            seller = self.accounts.get(seller_group, {}).get(seller_id)
            if seller is None:
                raise FxError("卖家账户不存在。")
            account.cash -= price
            seller.cash += price
            account.inventory.append(
                {
                    "name": str(listing.get("name") or "商品"),
                    "price": price,
                    "seller_name": str(listing.get("seller_name") or "玩家"),
                    "time": time.time(),
                }
            )
            del self.market_listings[listing_id]
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=(
                        f"已购买 #{listing_id} {listing.get('name')}，"
                        f"花费 {money(price)}，已放入背包。"
                    ),
                    buttons=self._backpack_buttons(),
                ),
            )
        if command == "backpack":
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=f"背包：{len(account.inventory)} 件物品",
                    image=render_backpack(account),
                    buttons=self._backpack_buttons(),
                ),
            )
        if command == "lottery_buy":
            match = re.search(r"\d+", text)
            if match is None:
                raise FxError("请带上 1-100 的数字，例如：买彩票 88。")
            number = int(match.group(0))
            async with self.lottery_lock:
                result = buy_lottery_ticket(account, number, self.lottery_pool)
                self.lottery_pool = float(result["pool_after"])
            if result["won"]:
                result_text = (
                    f"彩票中奖！你选 {result['chosen']}，开出 {result['draw']}，"
                    f"赢得 {money(result['payout'])}。奖池已重置为 "
                    f"{money(self.lottery_pool)}。"
                )
            else:
                result_text = (
                    f"未中奖。你选 {result['chosen']}，开出 {result['draw']}，"
                    f"损失 {money(LOTTERY_TICKET_PRICE)}。当前奖池 "
                    f"{money(self.lottery_pool)}。"
                )
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=result_text,
                    image=render_lottery_ticket(
                        result, account.name, self.lottery_pool
                    ),
                    buttons=self._lottery_buttons(),
                ),
            )
        if command in {"sell_organ", "buy_organ"}:
            organ_id = normalize_organ(text)
            if organ_id is None:
                raise FxError("请带上器官名，例如：外汇卖器官 心脏。")
            if command == "sell_organ":
                result = sell_organ(account, organ_id)
                action = "出售"
            else:
                result = buy_organ(account, organ_id)
                action = "买回"
            return self._with_notes(
                notes,
                CommandOutcome(
                    text=(
                        f"已{action} {result['name']}，金额 {money(result['price'])}；"
                        f"累计净收入 {money(result['income'])}。"
                    ),
                    image=render_organs(account),
                    buttons=self._organ_buttons(account),
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
        return CommandOutcome(
            text=(
                f"器官回收站，已出售 {len(account.organ_sold)}/{len(organ_defs())} 个器官，"
                f"累计净收入 {money(organ_income_total(account))}"
            ),
            image=render_organs(account),
            buttons=self._organ_buttons(account),
        )

    def _organ_buttons(self, account: Account) -> list[ButtonSpec]:
        buttons: list[ButtonSpec] = []
        for index, item in enumerate(organ_defs(), start=1):
            sold = item["id"] in account.organ_sold
            price_label = f"{item['price'] / 1000:.0f}k"
            buttons.append(
                ButtonSpec(
                    f"fx_organ_{index}",
                    f"{item['name']} {price_label}{' 已卖' if sold else ''}",
                    f"外汇买器官 {item['name']}"
                    if sold
                    else f"外汇卖器官 {item['name']}",
                )
            )
        buttons.append(ButtonSpec("fx_organ_account", "账户", "外汇账户"))
        buttons.append(ButtonSpec("fx_organ_help", "帮助", "外汇帮助"))
        return buttons

    def _sorted_listings(self) -> list[dict[str, Any]]:
        return sorted(
            self.market_listings.values(),
            key=lambda item: int(item.get("id") or 0),
        )

    def _market_menu_outcome(self, account: Account) -> CommandOutcome:
        return CommandOutcome(
            text=(
                "市场菜单\n"
                "集市：查看别人上架的商品\n"
                "上架 <商品名> <价格>：上架商品，每人最多 5 件\n"
                "背包：查看自己买到的物品"
            ),
            buttons=self._market_menu_buttons(),
        )

    def _market_menu_buttons(self) -> list[ButtonSpec]:
        return [
            ButtonSpec("fx_market_go", "集市", "集市 1"),
            ButtonSpec("fx_market_list", "上架", "上架 "),
            ButtonSpec("fx_market_backpack", "背包", "背包"),
            ButtonSpec("fx_market_account", "账户", "外汇账户"),
            ButtonSpec("fx_market_help", "帮助", "市场帮助"),
        ]

    def _marketplace_outcome(
        self, account: Account, page: int = 1, prefix: str = ""
    ) -> CommandOutcome:
        listings = self._sorted_listings()
        total_pages = max(1, (len(listings) + 11) // 12)
        page = max(1, min(page, total_pages))
        page_text = (
            f"{prefix}\n" if prefix else ""
        ) + f"集市 第 {page}/{total_pages} 页，共 {len(listings)} 件商品。"
        return CommandOutcome(
            text=page_text,
            image=render_marketplace(listings, account.name),
            buttons=self._marketplace_buttons(account, page),
        )

    def _marketplace_buttons(self, account: Account, page: int = 1) -> list[ButtonSpec]:
        listings = self._sorted_listings()
        total_pages = max(1, (len(listings) + 11) // 12)
        page = max(1, min(page, total_pages))
        start_index = (page - 1) * 12
        buttons: list[ButtonSpec] = []
        for item in listings[start_index : start_index + 12]:
            listing_id = str(item.get("id") or "")
            price = float(item.get("price") or 0)
            label = f"{str(item.get('name') or '商品')[:6]} ${price:.0f}"
            if item.get("seller_id") == account.user_id:
                buttons.append(
                    ButtonSpec(
                        f"fx_market_cancel_{listing_id}",
                        f"下架 {label}",
                        f"下架 {listing_id}",
                        only_for=account.user_id,
                    )
                )
            else:
                buttons.append(
                    ButtonSpec(
                        f"fx_market_buy_{listing_id}",
                        f"买 {label}",
                        f"购买 {listing_id}",
                    )
                )
        prev_page = max(1, page - 1)
        next_page = min(total_pages, page + 1)
        buttons.extend(
            [
                ButtonSpec("fx_market_prev", "上一页", f"集市 {prev_page}"),
                ButtonSpec(
                    "fx_market_page",
                    f"第 {page}/{total_pages} 页",
                    f"集市 {page}",
                ),
                ButtonSpec("fx_market_next", "下一页", f"集市 {next_page}"),
            ]
        )
        return buttons

    def _page_arg(self, text: str) -> int:
        match = re.search(r"\d+", text)
        if match is None:
            return 1
        return max(1, int(match.group(0)))

    def _backpack_buttons(self) -> list[ButtonSpec]:
        return [
            ButtonSpec("fx_backpack_market", "市场", "市场菜单"),
            ButtonSpec("fx_backpack_account", "账户", "外汇账户"),
            ButtonSpec("fx_backpack_help", "帮助", "市场帮助"),
        ]

    def _next_listing_id_from_existing(self) -> int:
        ids = [
            int(item.get("id") or 0)
            for item in self.market_listings.values()
            if str(item.get("id") or "").isdigit()
        ]
        return max(ids, default=0) + 1

    def _parse_listing_args(self, text: str) -> tuple[str, float]:
        stripped = re.sub(r"^(?:市场出售|出售商品|上架商品|上架)\s*", "", text).strip()
        match = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)$", stripped)
        if match is None:
            if "-" in stripped:
                raise FxError("价格不能为负数。")
            raise FxError("格式：上架 <商品名> <价格>，例如：上架 空气 100。")
        name = match.group(1).strip()
        if not name:
            raise FxError("商品名不能为空。")
        price = float(match.group(2))
        if price < 0:
            raise FxError("价格不能为负数。")
        return name[:30], price

    def _listing_id_arg(self, text: str) -> str:
        match = re.search(r"#?(\d+)", text)
        if match is None:
            raise FxError("请带上商品编号，例如：购买 3。")
        return match.group(1)

    def _lottery_buttons(self) -> list[ButtonSpec]:
        return [
            ButtonSpec("fx_lottery_buy", "买彩票", "买彩票 "),
            ButtonSpec("fx_lottery_pool", "奖池", "彩票奖池"),
            ButtonSpec("fx_lottery_rank", "中奖排行", "彩票排行"),
            ButtonSpec("fx_lottery_account", "账户", "外汇账户"),
            ButtonSpec("fx_lottery_help", "帮助", "外汇帮助"),
        ]

    def _menu_outcome(self) -> CommandOutcome:
        text = (
            "虚拟外汇\n"
            "完全虚假行情，不接真实交易数据。\n\n"
            "外汇行情：查看全部股票\n"
            "外汇查看 水母水产：查看单个 K 线图\n"
            "外汇做多 水母水产 500 20\n"
            "外汇做空 水母水产 500 20\n"
            "外汇持仓 / 外汇平仓 编号\n"
            "外汇账户 / 外汇历史 / 外汇排行 / 破产申请\n"
            "彩票菜单 / 买彩票 88 / 彩票奖池 / 彩票排行\n"
            "市场菜单 / 上架 空气 100 / 购买 1 / 背包\n"
            "外汇设置 保证金 500 / 外汇设置 杠杆 20\n"
            "外汇器官 / 外汇卖器官 心脏 / 外汇买器官 心脏\n"
            "外汇借款 10000 / 外汇还款 5000\n"
            "管理员：外汇添加股票 <代码> <名称> <初始价>\n\n"
            "规则：最低保证金 $10，最大杠杆 100x；"
            "开/平仓各收 0.05% 手续费，大单有滑点；"
            "每 30 分钟收持仓费，做空额外收借券费；"
            "波动率越高最大杠杆越低；突发新闻会造成跳空；"
            "爆仓额外收 1% 名义仓位罚金；"
            "贷款每 30 分钟按 3% 复利计息；"
            "基础额度 $200,000，每天额外 +$200,000；"
            "破产申请每天最多 3 次，且现金<=0 或净值<0 时才能申请；"
            "彩票票价 $100，每张彩票向奖池注入 $10,000，奖池上限 $1,000,000，中奖清空奖池。"
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
            ButtonSpec("fx_menu_rank", "排行", "外汇排行"),
            ButtonSpec("fx_menu_organs", "器官", "外汇器官"),
            ButtonSpec("fx_menu_borrow", "借款", "外汇借款 10000"),
            ButtonSpec("fx_menu_repay", "还款", "外汇还款 5000"),
            ButtonSpec("fx_menu_bankruptcy", "破产申请", "破产申请"),
            ButtonSpec("fx_menu_lottery", "彩票", "彩票菜单"),
            ButtonSpec("fx_menu_market", "市场", "市场菜单"),
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
            ButtonSpec("fx_account_rank", "排行", "外汇排行"),
            ButtonSpec("fx_account_bankruptcy", "破产申请", "破产申请"),
            ButtonSpec("fx_account_lottery", "彩票", "彩票菜单"),
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
                "lottery_pool": self.lottery_pool,
                "market_listings": self.market_listings,
                "next_listing_id": self.next_listing_id,
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
