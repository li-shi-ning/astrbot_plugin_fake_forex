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
    INSTRUMENT_DEFS,
    Market,
    PAIR_MAP,
    accrue_interest,
    advance_market,
    borrow,
    check_liquidations,
    close_position,
    loan_daily_rate,
    normalize_pair,
    open_position,
    register_instrument,
    repay,
    tick_market,
)

# Keep the rule tests deterministic; spread has its own dedicated test below.
for _instrument in INSTRUMENT_DEFS:
    _instrument["spread"] = 0.0


def seeded_market() -> Market:
    return Market.new(random.Random(7))


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
    series.price = 1.0
    series.candles[-1]["close"] = 1.0

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
    series.price = 1.0
    position = open_position(account, market, "YZCC", -1, 100, 10)
    series.price = 0.9
    assert round(position.pnl(market), 2) == 100
    close_position(account, market, position.id)
    assert account.cash == 10100


def test_liquidation_at_eighty_percent() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["SMSC"]
    series.price = 1.0
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
    series.price = 1.0
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
    series.price = 100.0
    old_spread = PAIR_MAP["SMSC"]["spread"]
    PAIR_MAP["SMSC"]["spread"] = 0.2
    try:
        position = open_position(account, market, "SMSC", 1, 100, 10)
        assert position.entry > series.price
        assert market.bid("SMSC") < series.price < market.ask("SMSC")
    finally:
        PAIR_MAP["SMSC"]["spread"] = old_spread

def test_super_shock_jumps_price_and_sets_regime() -> None:
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
    assert series.regime != 0
    assert series.regime_ticks > 0
