from __future__ import annotations

import random
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from src import engine as engine_module  # noqa: E402
from src.engine import (  # noqa: E402
    Account,
    FxError,
    apply_bankruptcy,
    apply_minor_refund,
    INSTRUMENT_DEFS,
    Market,
    PAIR_MAP,
    Position,
    accrue_interest,
    advance_market,
    borrow,
    buy_lottery_ticket,
    buy_organ,
    check_liquidations,
    close_position,
    loan_daily_rate,
    normalize_pair,
    LOTTERY_BASE_POOL,
    LOTTERY_MAX_POOL,
    MINOR_REFUND_LOCK_SECONDS,
    loan_limit,
    open_position,
    organ_defs,
    register_instrument,
    repay,
    sell_organ,
    settle_holding_fees,
    tick_market,
)

# Keep the rule tests deterministic; each new mechanic has a dedicated test.
for _instrument in INSTRUMENT_DEFS:
    _instrument["spread"] = 0.0
for _attr in (
    "TRADE_FEE_RATE",
    "SLIPPAGE_FACTOR",
    "HOLD_FEE_RATE",
    "SHORT_BORROW_FEE_RATE",
    "LIQUIDATION_PENALTY_RATE",
    "NEWS_CHANCE",
    "SUPER_SHOCK_CHANCE",
):
    setattr(engine_module, _attr, 0.0)


def seeded_market() -> Market:
    return Market.new(random.Random(7))


def set_flat_price(series, value: float) -> None:
    series.price = value
    series.candles = [
        {"open": value, "high": value, "low": value, "close": value}
        for _ in range(40)
    ]


def test_market_has_all_pairs_and_ticks() -> None:
    market = seeded_market()
    assert len(market.pairs) == 14
    assert all(len(series.candles) == 76 for series in market.pairs.values())

    old_price = market.price("SMSC")
    tick_market(market, random.Random(1))
    assert market.tick == 1
    assert market.price("SMSC") != old_price


def test_long_position_profit_and_close() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["SMSC"]
    set_flat_price(series, 1.0)

    position = open_position(account, market, "SMSC", 1, 100, 10)
    assert account.cash == 9900
    series.price = 1.1
    assert round(position.pnl(market), 2) == 100

    record = close_position(account, market, position.id)
    assert round(record["pnl"], 2) == 100
    assert round(account.cash, 2) == 10100


def test_short_position_profit_and_close() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["YZCC"]
    set_flat_price(series, 1.0)
    position = open_position(account, market, "YZCC", -1, 100, 10)
    series.price = 0.9
    assert round(position.pnl(market), 2) == 100
    close_position(account, market, position.id)
    assert account.cash == 10100


def test_liquidation_at_eighty_percent() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["SMSC"]
    set_flat_price(series, 1.0)
    open_position(account, market, "SMSC", 1, 100, 10)
    series.price = 0.92

    events = check_liquidations(account, market)

    assert events
    assert account.positions == []
    assert account.history[0]["liquidated"] is True
    assert round(account.history[0]["pnl"], 2) == -80
    assert round(account.cash, 2) == 9920


def test_loan_interest_and_repay() -> None:
    account = Account("u", "Tester")
    borrow(account, 10000)
    assert account.debt == 10000
    assert account.cash == 20000
    assert loan_daily_rate(10000) == 0.03

    periods = accrue_interest(account, now=account.loan_last_ts + 1800)
    assert periods == 1
    assert account.debt == 10300.0

    periods = accrue_interest(account, now=account.loan_last_ts + 1800)
    assert periods == 1
    assert account.debt == 10609.0

    paid = repay(account, 5000)
    assert paid == 5000
    assert account.cash == 15000
    assert account.debt == 5609.0


def test_advance_market_liquidates_across_accounts() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["SMSC"]
    set_flat_price(series, 1.0)
    position = open_position(account, market, "SMSC", 1, 100, 10)
    series.price = 0.5

    steps = advance_market(market, [account], tick_seconds=1, max_ticks=1, now=market.last_tick_ts + 1)

    assert steps == 1
    assert position not in account.positions
    assert account.notes


def test_open_position_rejects_invalid_values() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    try:
        open_position(account, market, "NOPE", 1, 100, 10)
    except FxError as exc:
        assert "没有这个股票" in str(exc)
    else:  # pragma: no cover - guard against regression
        raise AssertionError("invalid pair should fail")

    try:
        open_position(account, market, "SMSC", 1, 1, 10)
    except FxError as exc:
        assert "保证金至少" in str(exc)
    else:  # pragma: no cover - guard against regression
        raise AssertionError("small margin should fail")

def test_register_custom_instrument() -> None:
    definition = register_instrument("TESTX", "测试股", 10.5)
    assert definition["id"] == "TESTX"

    market = Market.new(random.Random(1))
    assert "TESTX" in market.pairs
    assert market.pairs["TESTX"].price > 0

def test_normalize_pair_accepts_embedded_codes_and_chinese_names() -> None:
    assert normalize_pair("外汇查看 SMSC") == "SMSC"
    assert normalize_pair("外汇做多 SMSC 500 20") == "SMSC"
    assert normalize_pair("外汇查看 水母水产") == "SMSC"
    assert normalize_pair("外汇做空 芋头股 500 20") == "YTG"

def test_spread_is_applied_to_open_and_close() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["SMSC"]
    set_flat_price(series, 100.0)
    old_spread = PAIR_MAP["SMSC"]["spread"]
    PAIR_MAP["SMSC"]["spread"] = 0.2
    try:
        position = open_position(account, market, "SMSC", 1, 100, 10)
        assert position.entry > series.price
        assert market.bid("SMSC") < series.price < market.ask("SMSC")
    finally:
        PAIR_MAP["SMSC"]["spread"] = old_spread

def test_super_shock_jumps_price_without_persistent_trend() -> None:
    market = seeded_market()
    series = market.pairs["SMSC"]
    before = series.price
    old_chance = engine_module.SUPER_SHOCK_CHANCE
    engine_module.SUPER_SHOCK_CHANCE = 1.0
    try:
        engine_module.tick_market(market, random.Random(1))
    finally:
        engine_module.SUPER_SHOCK_CHANCE = old_chance

    move = abs(series.price / before - 1)
    assert move >= engine_module.SUPER_SHOCK_MIN
    assert series.regime == 0.0
    assert series.regime_ticks == 0

def test_trade_fee_and_liquidation_penalty() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["SMSC"]
    set_flat_price(series, 1.0)
    old_fee = engine_module.TRADE_FEE_RATE
    old_penalty = engine_module.LIQUIDATION_PENALTY_RATE
    engine_module.TRADE_FEE_RATE = 0.001
    engine_module.LIQUIDATION_PENALTY_RATE = 0.01
    try:
        position = open_position(account, market, "SMSC", 1, 100, 10)
        assert position.open_fee > 0
        assert account.cash < 9900

        series.price = 0.8
        record = close_position(account, market, position.id, liquidated=True)
        assert record["penalty"] > 0
        assert record["fee"] > 0
        assert record["pnl"] < record["gross_pnl"]
    finally:
        engine_module.TRADE_FEE_RATE = old_fee
        engine_module.LIQUIDATION_PENALTY_RATE = old_penalty


def test_slippage_worsens_large_order_entry() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["SMSC"]
    set_flat_price(series, 100.0)
    old_factor = engine_module.SLIPPAGE_FACTOR
    engine_module.SLIPPAGE_FACTOR = 0.1
    try:
        position = open_position(account, market, "SMSC", 1, 1000, 20)
        assert position.slippage > 0
        assert position.entry > market.ask("SMSC")
    finally:
        engine_module.SLIPPAGE_FACTOR = old_factor


def test_holding_and_short_borrow_fees() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["SMSC"]
    set_flat_price(series, 100.0)
    old_hold = engine_module.HOLD_FEE_RATE
    old_borrow = engine_module.SHORT_BORROW_FEE_RATE
    engine_module.HOLD_FEE_RATE = 0.001
    engine_module.SHORT_BORROW_FEE_RATE = 0.002
    try:
        position = open_position(account, market, "SMSC", -1, 100, 10)
        cash_before = account.cash
        fee = settle_holding_fees(
            account, now=position.holding_fee_ts + 1800
        )
        assert fee > 0
        assert account.cash < cash_before
    finally:
        engine_module.HOLD_FEE_RATE = old_hold
        engine_module.SHORT_BORROW_FEE_RATE = old_borrow


def test_news_event_can_fire() -> None:
    market = seeded_market()
    old_chance = engine_module.NEWS_CHANCE
    engine_module.NEWS_CHANCE = 1.0
    try:
        tick_market(market, random.Random(1))
    finally:
        engine_module.NEWS_CHANCE = old_chance
    assert market.news
    assert "突发消息" in market.news[0]["text"]


def test_high_volatility_reduces_max_leverage() -> None:
    market = seeded_market()
    series = market.pairs["SMSC"]
    series.candles = [
        {"open": value, "high": value, "low": value, "close": value}
        for value in ([50.0, 100.0] * 20)
    ]
    assert market.max_leverage("SMSC") < 100

def test_sell_and_buy_back_organ() -> None:
    account = Account("u", "Tester")
    catalog = organ_defs()
    assert len(catalog) >= 20

    result = sell_organ(account, "心脏")
    assert result["name"] == "心脏"
    assert account.cash == 10000 + result["price"]

    try:
        sell_organ(account, "心脏")
    except FxError as exc:
        assert "已经卖过" in str(exc)
    else:  # pragma: no cover - guard against regression
        raise AssertionError("sold organ should not be sold twice")

    buy_organ(account, "心脏")
    assert account.cash == 10000

    sell_organ(account, "心脏")
    assert account.cash == 10000 + result["price"]


def test_daily_extra_loan_ceiling() -> None:
    account = Account("u", "Tester")
    borrow(account, 10000, "2026-01-01")
    assert loan_limit(account) == 400000
    assert account.debt == 10000

    borrow(account, 200000, "2026-01-01")
    assert account.debt == 210000

    borrow(account, 200000, "2026-01-02")
    assert loan_limit(account) == 600000
    assert account.debt == 410000

def test_bankruptcy_relief_conditions_and_daily_limit() -> None:
    market = seeded_market()
    account = Account("u", "Tester", cash=0.0, debt=100000.0)
    pnl_before = account.trading_pnl(market)

    first = apply_bankruptcy(account, market, "2026-01-01")
    assert first["cash"] == 10000.0
    assert account.cash == 10000.0
    assert account.debt == 50000.0
    assert account.trading_pnl(market) == pnl_before
    assert first["remaining_today"] == 2

    apply_bankruptcy(account, market, "2026-01-01")
    apply_bankruptcy(account, market, "2026-01-01")
    assert account.debt == 12500.0

    try:
        apply_bankruptcy(account, market, "2026-01-01")
    except FxError as exc:
        assert "次数已经用完" in str(exc)
    else:  # pragma: no cover - guard against regression
        raise AssertionError("bankruptcy relief should be limited to 3 per day")

    healthy = Account("v", "Healthy", cash=50000.0, debt=0.0)
    try:
        apply_bankruptcy(healthy, market, "2026-01-01")
    except FxError as exc:
        assert "没有达到破产条件" in str(exc)
    else:  # pragma: no cover - guard against regression
        raise AssertionError("healthy account should not get bankruptcy relief")

class FixedRng:
    def __init__(self, value: int) -> None:
        self.value = value

    def randint(self, _minimum: int, _maximum: int) -> int:
        return self.value


def test_lottery_ticket_loss_accumulates_and_win_resets_pool() -> None:
    account = Account("u", "Tester", cash=10000.0)
    market = seeded_market()
    pnl_before = account.trading_pnl(market)
    pool = LOTTERY_BASE_POOL

    loss = buy_lottery_ticket(account, 7, pool, FixedRng(8))
    pool = float(loss["pool_after"])
    assert loss["won"] is False
    assert account.cash == 9900.0
    assert pool == LOTTERY_BASE_POOL + 10000

    win = buy_lottery_ticket(account, 8, pool, FixedRng(8))
    assert win["won"] is True
    assert win["payout"] == pool + 10000
    assert win["pool_after"] == LOTTERY_BASE_POOL
    assert account.cash == 9800.0 + 220000.0
    assert account.trading_pnl(market) == pnl_before
    assert account.lottery_history

def test_lottery_pool_caps_at_one_million() -> None:
    account = Account("u", "Tester", cash=10000.0)
    result = buy_lottery_ticket(
        account, 7, LOTTERY_MAX_POOL - 5000, FixedRng(8)
    )
    assert result["pool_after"] == LOTTERY_MAX_POOL

def test_minor_refund_resets_account_and_locks_purchases() -> None:
    market = seeded_market()
    account = Account(
        "u",
        "Tester",
        cash=0.0,
        debt=100000.0,
        organ_sold=["heart"],
        inventory=[{"name": "空气", "price": 1.0}],
    )
    account.positions.append(
        Position(
            id="test",
            pair="SMSC",
            side=1,
            entry=10.0,
            margin=100.0,
            leverage=10,
            notional=1000.0,
            opened_ts=0.0,
        )
    )
    pnl_before = account.trading_pnl(market)
    now = 1000.0

    result = apply_minor_refund(account, market, 10000.0, now=now)

    assert result["cash"] == 10000.0
    assert account.cash == 10000.0
    assert account.debt == 0.0
    assert account.positions
    assert account.trade_lock_until == now + MINOR_REFUND_LOCK_SECONDS
    assert account.organ_sold == ["heart"]
    assert account.inventory
    assert account.trading_pnl(market) == pnl_before


def test_minor_refund_requires_bankruptcy() -> None:
    market = seeded_market()
    healthy = Account("u", "Tester", cash=50000.0, debt=0.0)
    try:
        apply_minor_refund(healthy, market, 10000.0)
    except FxError as exc:
        assert "没有达到未成年退款条件" in str(exc)
    else:  # pragma: no cover - guard against regression
        raise AssertionError("healthy account should not get minor refund")

def test_realized_pnl_is_cumulative_after_history_truncation() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["SMSC"]
    set_flat_price(series, 1.0)

    position = open_position(account, market, "SMSC", 1, 100, 10)
    series.price = 1.1
    record = close_position(account, market, position.id)

    assert account.realized_pnl == record["pnl"]
    assert account.trade_count == 1

    account.history.clear()
    assert account.trading_pnl(market) == record["pnl"]
