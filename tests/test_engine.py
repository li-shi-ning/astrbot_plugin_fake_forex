from __future__ import annotations

import random
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from src.engine import (  # noqa: E402
    Account,
    FxError,
    Market,
    advance_market,
    borrow,
    check_liquidations,
    close_position,
    loan_daily_rate,
    open_position,
    repay,
    tick_market,
)


def seeded_market() -> Market:
    return Market.new(random.Random(7))


def test_market_has_all_pairs_and_ticks() -> None:
    market = seeded_market()
    assert len(market.pairs) == 7
    assert all(len(series.candles) == 76 for series in market.pairs.values())

    old_price = market.price("EUR/USD")
    tick_market(market, random.Random(1))
    assert market.tick == 1
    assert market.price("EUR/USD") != old_price


def test_long_position_profit_and_close() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["EUR/USD"]
    series.price = 1.0
    series.candles[-1]["close"] = 1.0

    position = open_position(account, market, "EUR/USD", 1, 100, 10)
    assert account.cash == 9900
    series.price = 1.1
    assert round(position.pnl(market), 2) == 100

    record = close_position(account, market, position.id)
    assert round(record["pnl"], 2) == 100
    assert round(account.cash, 2) == 10100


def test_short_position_profit_and_close() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["GBP/USD"]
    series.price = 1.0
    position = open_position(account, market, "GBP/USD", -1, 100, 10)
    series.price = 0.9
    assert round(position.pnl(market), 2) == 100
    close_position(account, market, position.id)
    assert account.cash == 10100


def test_liquidation_at_eighty_percent() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["EUR/USD"]
    series.price = 1.0
    open_position(account, market, "EUR/USD", 1, 100, 10)
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
    assert loan_daily_rate(10000) == 0.0001

    account.loan_ticks = 0
    account.debt = round(account.debt * (1 + account.loan_rate), 2)
    assert account.debt > 10000

    paid = repay(account, 5000)
    assert paid == 5000
    assert account.cash == 15000
    assert account.debt == 5001.0


def test_advance_market_liquidates_across_accounts() -> None:
    market = seeded_market()
    account = Account("u", "Tester")
    series = market.pairs["EUR/USD"]
    series.price = 1.0
    position = open_position(account, market, "EUR/USD", 1, 100, 10)
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
        assert "没有这个外汇对" in str(exc)
    else:  # pragma: no cover - guard against regression
        raise AssertionError("invalid pair should fail")

    try:
        open_position(account, market, "EUR/USD", 1, 1, 10)
    except FxError as exc:
        assert "保证金至少" in str(exc)
    else:  # pragma: no cover - guard against regression
        raise AssertionError("small margin should fail")
