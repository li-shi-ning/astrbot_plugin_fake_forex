from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

INSTRUMENT_DEFS: list[dict[str, Any]] = [
    {"id": "SMSC", "name": "水母水产", "initial": 12.50, "digits": 2, "spread": 0.20},
    {"id": "YZCC", "name": "预制菜赌场", "initial": 8.88, "digits": 2, "spread": 0.20},
    {"id": "HYG", "name": "辉叶股", "initial": 45.60, "digits": 2, "spread": 0.20},
    {"id": "ZYG", "name": "真叶股", "initial": 52.30, "digits": 2, "spread": 0.20},
    {
        "id": "YFNHJ",
        "name": "茵菲诺黄金",
        "initial": 188.80,
        "digits": 2,
        "spread": 0.20,
    },
    {"id": "YTG", "name": "芋头股", "initial": 23.45, "digits": 2, "spread": 0.20},
    {"id": "MYG", "name": "卯月股", "initial": 77.77, "digits": 2, "spread": 0.20},
    {"id": "ASKC", "name": "爱素矿产", "initial": 31.20, "digits": 2, "spread": 0.20},
    {"id": "QYJT", "name": "千音集团", "initial": 66.60, "digits": 2, "spread": 0.20},
    {"id": "NMWY", "name": "糯米文娱", "initial": 18.88, "digits": 2, "spread": 0.20},
    {"id": "CQSS", "name": "长期素食", "initial": 14.20, "digits": 2, "spread": 0.20},
    {"id": "BMXY", "name": "白毛兽业", "initial": 9.90, "digits": 2, "spread": 0.20},
    {
        "id": "MTDBL",
        "name": "睦缇斯暴力公司",
        "initial": 120.00,
        "digits": 2,
        "spread": 0.20,
    },
    {"id": "XYKH", "name": "咲夜航空", "initial": 58.88, "digits": 2, "spread": 0.20},
]
PAIR_DEFS = INSTRUMENT_DEFS
PAIR_IDS = [item["id"] for item in INSTRUMENT_DEFS]
PAIR_MAP = {item["id"]: item for item in INSTRUMENT_DEFS}


def instrument_defs() -> list[dict[str, Any]]:
    """Return copies of all registered instruments."""

    return [dict(item) for item in INSTRUMENT_DEFS]


def register_instrument(
    code: str,
    name: str,
    initial: float,
    digits: int = 2,
    spread: float = 0.20,
) -> dict[str, Any]:
    """Register or update a custom instrument.

    Args:
        code: Uppercase alphanumeric instrument code.
        name: Display name shown in messages and images.
        initial: Initial simulated price.
        digits: Price decimal precision.

    Returns:
        The registered instrument definition.

    Raises:
        FxError: If the code, name, initial price, or precision is invalid.
    """

    normalized_code = re.sub(r"[^A-Z0-9]", "", str(code or "").upper())
    if not 2 <= len(normalized_code) <= 12:
        raise FxError("股票代码必须是 2-12 位字母或数字。")  # noqa: F821
    normalized_name = str(name or "").strip()
    if not normalized_name or len(normalized_name) > 24:
        raise FxError("股票名称不能为空，且不能超过 24 个字。")  # noqa: F821
    if float(initial) <= 0:
        raise FxError("初始价格必须大于 0。")  # noqa: F821
    digits = max(0, min(6, int(digits)))
    for item in INSTRUMENT_DEFS:
        if item["id"] == normalized_code:
            item.update(
                {
                    "name": normalized_name,
                    "initial": float(initial),
                    "digits": digits,
                    "spread": max(0.0, float(spread)),
                }
            )
            PAIR_MAP[normalized_code] = item
            return dict(item)
    definition = {
        "id": normalized_code,
        "name": normalized_name,
        "initial": float(initial),
        "digits": digits,
        "spread": max(0.0, float(spread)),
    }
    INSTRUMENT_DEFS.append(definition)
    PAIR_IDS.append(normalized_code)
    PAIR_MAP[normalized_code] = definition
    return dict(definition)


INITIAL_CASH = 10000.0
MIN_MARGIN = 10.0
DEFAULT_MARGIN = 500.0
DEFAULT_LEVERAGE = 20
MAX_LEVERAGE = 100
WARNING_RATIO = 0.6
LIQUIDATION_RATIO = 0.8
LOAN_MAX = 200000.0
LOAN_INTEREST_RATE = 0.03
LOAN_INTEREST_SECONDS = 1800
SUPER_SHOCK_CHANCE = 0.006
SUPER_SHOCK_MIN = 0.08
SUPER_SHOCK_MAX = 0.45
REGIME_TICKS_MIN = 30
REGIME_TICKS_MAX = 150
DEFAULT_SPREAD_PCT = 0.20
TRADE_FEE_RATE = 0.0005
SLIPPAGE_FACTOR = 0.05
MAX_SLIPPAGE_PCT = 1.5
HOLD_FEE_RATE = 0.0003
SHORT_BORROW_FEE_RATE = 0.0008
LIQUIDATION_PENALTY_RATE = 0.01
NEWS_CHANCE = 0.0015
NEWS_MIN = 0.05
NEWS_MAX = 0.25
DAILY_EXTRA_LOAN = 200000.0
LOTTERY_BASE_POOL = 200000.0
LOTTERY_TICKET_PRICE = 100.0
LOTTERY_POOL_INCREASE = LOTTERY_TICKET_PRICE * 1000
LOTTERY_MIN = 1
LOTTERY_MAX = 100
ORGAN_DEFS: list[dict[str, Any]] = [
    {"id": "heart", "name": "心脏", "price": 80000.0},
    {"id": "brain", "name": "大脑", "price": 75000.0},
    {"id": "liver", "name": "肝脏", "price": 50000.0},
    {"id": "kidney", "name": "肾脏", "price": 45000.0},
    {"id": "lung", "name": "肺", "price": 40000.0},
    {"id": "cornea", "name": "眼角膜", "price": 30000.0},
    {"id": "pancreas", "name": "胰腺", "price": 28000.0},
    {"id": "marrow", "name": "骨髓", "price": 25000.0},
    {"id": "stomach", "name": "胃", "price": 18000.0},
    {"id": "spleen", "name": "脾脏", "price": 15000.0},
    {"id": "skin", "name": "皮肤", "price": 12000.0},
    {"id": "bone", "name": "骨骼", "price": 10000.0},
    {"id": "neuron", "name": "神经", "price": 9000.0},
    {"id": "intestine", "name": "小肠", "price": 8000.0},
    {"id": "colon", "name": "大肠", "price": 7000.0},
    {"id": "thymus", "name": "胸腺", "price": 6000.0},
    {"id": "gallbladder", "name": "胆囊", "price": 5000.0},
    {"id": "tonsil", "name": "扁桃体", "price": 4000.0},
    {"id": "blood", "name": "血液", "price": 3000.0},
    {"id": "appendix", "name": "阑尾", "price": 2000.0},
]
ORGAN_MAP = {item["id"]: item for item in ORGAN_DEFS}
HISTORY_LIMIT = 25
CANDLE_LIMIT = 150
SEED_CANDLES = 76


class FxError(ValueError):
    """Raised when a forex game action is not legal."""


def normalize_pair(text: str) -> str | None:
    """Resolve a stock code or Chinese name from arbitrary user text."""

    raw = str(text or "").strip()
    if not raw:
        return None
    raw_upper = raw.upper()

    # Prefer exact or embedded codes such as ``外汇查看 SMSC``.
    for item in INSTRUMENT_DEFS:
        code = item["id"].upper()
        if code == raw_upper or code in raw_upper:
            return item["id"]

    # Then accept Chinese names such as ``外汇查看 水母水产``.
    for item in sorted(
        INSTRUMENT_DEFS, key=lambda value: len(value["name"]), reverse=True
    ):
        if item["name"] in raw:
            return item["id"]

    # Fallback for compact letter input such as ``sm sc``.
    letters = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    for item in INSTRUMENT_DEFS:
        code = item["id"].upper()
        if code in letters:
            return item["id"]
    return None


def organ_defs() -> list[dict[str, Any]]:
    """Return copies of the organ catalog."""

    return [dict(item) for item in ORGAN_DEFS]


def normalize_organ(text: str) -> str | None:
    """Resolve an organ name or id from user text."""

    raw = str(text or "").strip()
    if not raw:
        return None
    raw_upper = raw.upper()
    for item in sorted(ORGAN_DEFS, key=lambda value: len(value["name"]), reverse=True):
        if item["name"] in raw:
            return item["id"]
    for item in ORGAN_DEFS:
        if item["id"].upper() in raw_upper:
            return item["id"]
    return None


def organ_income_total(account: Account) -> float:
    """Return net cash earned from selling organs."""

    total = 0.0
    for item in account.organ_history:
        price = float(item.get("price") or 0)
        if item.get("action") == "buy":
            total -= price
        else:
            total += price
    return total


def sell_organ(account: Account, organ_id: str) -> dict[str, Any]:
    """Sell one organ for cash without affecting trading.

    Each organ can be sold once until the player buys it back.

    Raises:
        FxError: If the organ is unknown or already sold.
    """

    normalized = normalize_organ(organ_id)
    if normalized is None:
        raise FxError("没有这个器官。")
    if normalized in account.organ_sold:
        raise FxError(f"已经卖过{ORGAN_MAP[normalized]['name']}了，可以先买回来。")
    item = ORGAN_MAP[normalized]
    price = float(item["price"])
    account.cash += price
    account.organ_sold.append(normalized)
    account.organ_history.insert(
        0,
        {
            "action": "sell",
            "organ": item["name"],
            "organ_id": normalized,
            "price": price,
            "time": time.time(),
        },
    )
    del account.organ_history[80:]
    return {
        "id": normalized,
        "name": item["name"],
        "price": price,
        "cash": account.cash,
        "income": organ_income_total(account),
    }


def buy_organ(account: Account, organ_id: str) -> dict[str, Any]:
    """Buy back an organ that was sold earlier.

    Raises:
        FxError: If the organ is unknown, not sold, or cash is insufficient.
    """

    normalized = normalize_organ(organ_id)
    if normalized is None:
        raise FxError("没有这个器官。")
    if normalized not in account.organ_sold:
        raise FxError(f"你还没有卖掉{ORGAN_MAP[normalized]['name']}。")
    item = ORGAN_MAP[normalized]
    price = float(item["price"])
    if account.cash < price:
        raise FxError(f"现金不足，买回{item['name']}需要 {money(price)}。")
    account.cash -= price
    account.organ_sold.remove(normalized)
    account.organ_history.insert(
        0,
        {
            "action": "buy",
            "organ": item["name"],
            "organ_id": normalized,
            "price": price,
            "time": time.time(),
        },
    )
    del account.organ_history[80:]
    return {
        "id": normalized,
        "name": item["name"],
        "price": price,
        "cash": account.cash,
        "income": organ_income_total(account),
    }


def is_bankrupt(account: Account, market: Market) -> bool:
    """Return whether the account meets the bankruptcy relief condition."""

    return account.cash <= 0 or account.equity(market) < 0


def apply_bankruptcy(account: Account, market: Market, day: str) -> dict[str, Any]:
    """Apply one bankruptcy relief.

    The player may apply up to three times per day, but only while the
    bankruptcy condition is met.  This deliberately does not touch
    ``history`` so the trading P/L leaderboard is unaffected by relief money.
    """

    if account.relief_day != day:
        account.relief_day = day
        account.relief_today = 0
    if account.relief_today >= 3:
        raise FxError("今天破产申请次数已经用完了（每天最多 3 次）。")
    if not is_bankrupt(account, market):
        raise FxError("你还没有达到破产条件（现金 <= 0 或净值 < 0）。")
    old_debt = account.debt
    account.debt = round(account.debt * 0.5, 2)
    if account.debt <= 0:
        account.debt = 0.0
        account.loan_principal = 0.0
        account.loan_rate = 0.0
        account.loan_last_ts = 0.0
        account.loan_ticks = 0
    account.cash = 10000.0
    account.relief_today += 1
    account.relief_count += 1
    return {
        "old_debt": old_debt,
        "remaining_debt": account.debt,
        "cash": account.cash,
        "count": account.relief_count,
        "today": account.relief_today,
        "remaining_today": 3 - account.relief_today,
    }


def buy_lottery_ticket(
    account: Account,
    chosen_number: int,
    pool: float,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Buy one lottery ticket, draw immediately, and settle the pool.

    The caller must already hold the lottery lock so two winners cannot
    settle the same pool concurrently.

    Returns:
        Ticket result containing chosen number, draw, win flag, payout, and
        the updated pool.

    Raises:
        FxError: If the number is invalid or cash is insufficient.
    """

    try:
        chosen = int(chosen_number)
    except (TypeError, ValueError) as exc:
        raise FxError("彩票数字必须是 1-100 的整数。") from exc
    if not LOTTERY_MIN <= chosen <= LOTTERY_MAX:
        raise FxError("彩票数字必须在 1-100 之间。")
    if account.cash < LOTTERY_TICKET_PRICE:
        raise FxError(f"现金不足，购买彩票需要 {money(LOTTERY_TICKET_PRICE)}。")

    account.cash -= LOTTERY_TICKET_PRICE
    pool += LOTTERY_POOL_INCREASE
    rng = rng or random.Random()
    draw = rng.randint(LOTTERY_MIN, LOTTERY_MAX)
    won = draw == chosen
    payout = pool if won else 0.0
    if won:
        account.cash += pool
        pool = LOTTERY_BASE_POOL

    record = {
        "chosen": chosen,
        "draw": draw,
        "won": won,
        "payout": payout,
        "pool_after": pool,
        "time": time.time(),
    }
    account.lottery_history.insert(0, record)
    del account.lottery_history[20:]
    return record


def loan_limit(account: Account) -> float:
    """Return the current total loan ceiling."""

    return LOAN_MAX + account.loan_extra_limit


def refresh_daily_loan(account: Account, day: str) -> bool:
    """Add the daily extra loan ceiling once per day."""

    if not day or account.loan_day == day:
        return False
    account.loan_day = day
    account.loan_extra_limit += DAILY_EXTRA_LOAN
    return True


def money(value: float) -> str:
    """Format a dollar amount."""

    return f"${value:,.2f}"


def signed_money(value: float) -> str:
    """Format a signed dollar amount."""

    return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"


def percent(value: float) -> str:
    """Format a percentage change."""

    return f"{value:+.2f}%"


def price_text(pair_id: str, value: float) -> str:
    """Format a pair price using its configured precision."""

    digits = PAIR_MAP.get(pair_id, {}).get("digits", 5)
    return f"{value:.{digits}f}"


def loan_daily_rate(amount: float) -> float:
    """Return the fixed compounded loan rate.

    The argument is kept for backward compatibility with older callers.
    """

    _ = amount
    return LOAN_INTEREST_RATE


def _seed_series(
    item: dict[str, Any], rng: random.Random, index: int = 0
) -> dict[str, Any]:
    """Build one simulated price series for an instrument."""

    value = float(item["initial"])
    candles: list[dict[str, float]] = []
    for step in range(SEED_CANDLES):
        open_price = value
        wave = (
            math.sin(step * 0.43 + index * 1.9) * 0.0008
            + math.cos(step * 0.19 + index) * 0.00055
        )
        value = open_price * (1 + wave + (rng.random() - 0.5) * 0.0019)
        spread = open_price * (0.0005 + rng.random() * 0.00065)
        candles.append(
            {
                "open": open_price,
                "high": max(open_price, value) + spread,
                "low": min(open_price, value) - spread,
                "close": value,
            }
        )
    return {"id": item["id"], "price": value, "candles": candles}


def _seed_market(rng: random.Random) -> dict[str, Any]:
    pairs = {
        item["id"]: _seed_series(item, rng, index)
        for index, item in enumerate(INSTRUMENT_DEFS)
    }
    return {"tick": 0, "last_tick_ts": time.time(), "pairs": pairs}


@dataclass
class PairSeries:
    id: str
    price: float
    candles: list[dict[str, float]] = field(default_factory=list)
    regime: float = 0.0
    regime_ticks: int = 0

    def change_percent(self) -> float:
        """Return the latest candle change percentage."""

        if len(self.candles) < 2:
            return 0.0
        previous = self.candles[-2]["close"]
        if previous == 0:
            return 0.0
        return (self.price / previous - 1) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "price": self.price,
            "candles": self.candles,
            "regime": self.regime,
            "regime_ticks": self.regime_ticks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PairSeries:
        return cls(
            id=str(data.get("id") or ""),
            price=float(data.get("price") or 0),
            candles=list(data.get("candles") or []),
            regime=float(data.get("regime") or 0),
            regime_ticks=int(data.get("regime_ticks") or 0),
        )


@dataclass
class Market:
    pairs: dict[str, PairSeries] = field(default_factory=dict)
    tick: int = 0
    last_tick_ts: float = 0.0
    news: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def new(cls, rng: random.Random | None = None) -> Market:
        """Create a fully simulated market."""

        return cls.from_dict(_seed_market(rng or random.Random()))

    def price(self, pair_id: str) -> float:
        return self.pairs[pair_id].price

    def spread_pct(self, pair_id: str) -> float:
        """Return the instrument spread percentage."""

        return float(PAIR_MAP.get(pair_id, {}).get("spread", DEFAULT_SPREAD_PCT))

    def bid(self, pair_id: str) -> float:
        """Return the price at which the player can sell."""

        half_spread = self.spread_pct(pair_id) / 200
        return self.price(pair_id) * (1 - half_spread)

    def ask(self, pair_id: str) -> float:
        """Return the price at which the player can buy."""

        half_spread = self.spread_pct(pair_id) / 200
        return self.price(pair_id) * (1 + half_spread)

    def recent_volatility_pct(self, pair_id: str, window: int = 20) -> float:
        """Return average absolute candle return over the recent window."""

        series = self.pairs.get(pair_id)
        if series is None:
            return 0.0
        closes = [float(candle["close"]) for candle in series.candles[-window - 1 :]]
        if len(closes) < 2:
            return 0.0
        returns = [
            abs(closes[index] / closes[index - 1] - 1)
            for index in range(1, len(closes))
            if closes[index - 1] > 0
        ]
        if not returns:
            return 0.0
        return sum(returns) / len(returns) * 100

    def max_leverage(self, pair_id: str) -> int:
        """Return the volatility-adjusted maximum leverage."""

        volatility = self.recent_volatility_pct(pair_id)
        required_margin_pct = max(1.0, min(50.0, volatility * 2.5))
        return max(1, min(MAX_LEVERAGE, int(100 / required_margin_pct)))

    def latest_news(
        self, pair_id: str | None = None, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Return recent news, optionally filtered to one instrument."""

        items = self.news
        if pair_id is not None:
            items = [item for item in items if item.get("pair") == pair_id]
        return list(items[:limit])

    def add_instrument(
        self, item: dict[str, Any], rng: random.Random | None = None
    ) -> PairSeries:
        """Add one simulated instrument series to the market."""

        pair_id = str(item["id"])
        if pair_id in self.pairs:
            return self.pairs[pair_id]
        index = len(self.pairs)
        series = _seed_series(item, rng or random.Random(), index)
        self.pairs[pair_id] = PairSeries.from_dict(series)
        return self.pairs[pair_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "last_tick_ts": self.last_tick_ts,
            "news": self.news,
            "pairs": {key: value.to_dict() for key, value in self.pairs.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Market:
        pairs = {
            key: PairSeries.from_dict(value)
            for key, value in dict(data.get("pairs") or {}).items()
        }
        market = cls(
            pairs=pairs,
            tick=int(data.get("tick") or 0),
            last_tick_ts=float(data.get("last_tick_ts") or time.time()),
            news=list(data.get("news") or []),
        )
        for item in INSTRUMENT_DEFS:
            if item["id"] not in market.pairs:
                market.add_instrument(item)
        return market


def tick_market(
    market: Market,
    rng: random.Random | None = None,
    now: float | None = None,
) -> None:
    """Advance every pair by one simulated tick."""

    rng = rng or random.Random()
    for index, (_pair_id, series) in enumerate(list(market.pairs.items())):
        open_price = series.price

        if rng.random() < SUPER_SHOCK_CHANCE:
            direction = 1 if rng.random() < 0.5 else -1
            magnitude = rng.uniform(SUPER_SHOCK_MIN, SUPER_SHOCK_MAX)
            close = max(open_price * 0.05, open_price * (1 + direction * magnitude))
        else:
            drift = math.sin((market.tick + 1) / 8.67 + index * 2) * 0.00036
            shock = (rng.random() - 0.5) * 0.019 if rng.random() < 0.018 else 0.0
            close = max(
                open_price * 0.5,
                open_price * (1 + drift + (rng.random() - 0.5) * 0.0042 + shock),
            )

        if rng.random() < NEWS_CHANCE:
            news_direction = 1 if rng.random() < 0.5 else -1
            news_move = rng.uniform(NEWS_MIN, NEWS_MAX)
            close = max(close * 0.1, close * (1 + news_direction * news_move))
            name = PAIR_MAP.get(_pair_id, {}).get("name", _pair_id)
            market.news.insert(
                0,
                {
                    "tick": market.tick,
                    "pair": _pair_id,
                    "text": (
                        f"{name} 突发消息，价格"
                        f"{'暴涨' if news_direction > 0 else '暴跌'} "
                        f"{news_move * 100:.1f}%"
                    ),
                },
            )
            del market.news[20:]
        series.regime = 0.0
        series.regime_ticks = 0

        wick = open_price * (rng.random() * 0.0015 + 0.0002)
        series.candles.append(
            {
                "open": open_price,
                "high": max(open_price, close) + wick,
                "low": min(open_price, close) - wick,
                "close": close,
            }
        )
        if len(series.candles) > CANDLE_LIMIT:
            del series.candles[: len(series.candles) - CANDLE_LIMIT]
        series.price = close
    market.tick += 1
    market.last_tick_ts = now if now is not None else time.time()


@dataclass
class Position:
    id: str
    pair: str
    side: int
    entry: float
    margin: float
    leverage: int
    notional: float
    opened_ts: float
    open_fee: float = 0.0
    slippage: float = 0.0
    holding_fee_ts: float = 0.0
    warned: bool = False

    @property
    def side_label(self) -> str:
        return "做多" if self.side == 1 else "做空"

    def pnl(self, market: Market) -> float:
        """Return the floating profit/loss for this position."""

        if self.entry <= 0:
            return 0.0
        exit_price = market.bid(self.pair) if self.side == 1 else market.ask(self.pair)
        exit_price = (
            exit_price * (1 - self.slippage / 100)
            if self.side == 1
            else exit_price * (1 + self.slippage / 100)
        )
        raw_pnl = self.notional * self.side * (exit_price / self.entry - 1)
        return max(-self.margin, raw_pnl)

    def risk_ratio(self, market: Market) -> float:
        """Return how much of the margin has been lost."""

        return max(0.0, -self.pnl(market) / self.margin)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pair": self.pair,
            "side": self.side,
            "entry": self.entry,
            "margin": self.margin,
            "leverage": self.leverage,
            "notional": self.notional,
            "opened_ts": self.opened_ts,
            "open_fee": self.open_fee,
            "slippage": self.slippage,
            "holding_fee_ts": self.holding_fee_ts,
            "warned": self.warned,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        return cls(
            id=str(data.get("id") or ""),
            pair=str(data.get("pair") or ""),
            side=int(data.get("side") or 1),
            entry=float(data.get("entry") or 0),
            margin=float(data.get("margin") or 0),
            leverage=int(data.get("leverage") or DEFAULT_LEVERAGE),
            notional=float(data.get("notional") or 0),
            opened_ts=float(data.get("opened_ts") or time.time()),
            open_fee=float(data.get("open_fee") or 0),
            slippage=float(data.get("slippage") or 0),
            holding_fee_ts=float(
                data.get("holding_fee_ts") or data.get("opened_ts") or time.time()
            ),
            warned=bool(data.get("warned")),
        )


@dataclass
class Account:
    user_id: str
    name: str
    cash: float = INITIAL_CASH
    debt: float = 0.0
    loan_principal: float = 0.0
    loan_rate: float = 0.0
    loan_ticks: int = 0
    loan_last_ts: float = 0.0
    loan_extra_limit: float = 0.0
    loan_day: str = ""
    organ_sold: list[str] = field(default_factory=list)
    organ_history: list[dict[str, Any]] = field(default_factory=list)
    relief_day: str = ""
    relief_today: int = 0
    relief_count: int = 0
    lottery_history: list[dict[str, Any]] = field(default_factory=list)
    margin_default: float = DEFAULT_MARGIN
    leverage_default: int = DEFAULT_LEVERAGE
    positions: list[Position] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def used_margin(self) -> float:
        return sum(position.margin for position in self.positions)

    def floating_pnl(self, market: Market) -> float:
        return sum(position.pnl(market) for position in self.positions)

    def equity(self, market: Market) -> float:
        return self.cash + self.used_margin() + self.floating_pnl(market) - self.debt

    def trading_pnl(self, market: Market) -> float:
        """Return realized plus floating trading profit/loss."""

        realized = sum(float(item.get("pnl") or 0) for item in self.history)
        return realized + self.floating_pnl(market)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "cash": self.cash,
            "debt": self.debt,
            "loan_principal": self.loan_principal,
            "loan_rate": self.loan_rate,
            "loan_ticks": self.loan_ticks,
            "loan_last_ts": self.loan_last_ts,
            "loan_extra_limit": self.loan_extra_limit,
            "loan_day": self.loan_day,
            "organ_sold": self.organ_sold,
            "organ_history": self.organ_history,
            "relief_day": self.relief_day,
            "relief_today": self.relief_today,
            "relief_count": self.relief_count,
            "lottery_history": self.lottery_history,
            "margin_default": self.margin_default,
            "leverage_default": self.leverage_default,
            "positions": [position.to_dict() for position in self.positions],
            "history": self.history,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Account:
        return cls(
            user_id=str(data.get("user_id") or ""),
            name=str(data.get("name") or ""),
            cash=float(
                data.get("cash") if data.get("cash") is not None else INITIAL_CASH
            ),
            debt=float(data.get("debt") or 0),
            loan_principal=float(data.get("loan_principal") or 0),
            loan_rate=float(data.get("loan_rate") or 0) or LOAN_INTEREST_RATE,
            loan_ticks=int(data.get("loan_ticks") or 0),
            loan_last_ts=float(data.get("loan_last_ts") or 0),
            loan_extra_limit=float(data.get("loan_extra_limit") or 0),
            loan_day=str(data.get("loan_day") or ""),
            organ_sold=(
                [str(value) for value in data.get("organ_sold") or []]
                or [str(key) for key in dict(data.get("organ_sold_day") or {}).keys()]
            ),
            organ_history=list(data.get("organ_history") or []),
            relief_day=str(data.get("relief_day") or ""),
            relief_today=int(data.get("relief_today") or 0),
            relief_count=int(data.get("relief_count") or 0),
            lottery_history=list(data.get("lottery_history") or []),
            margin_default=max(
                MIN_MARGIN, float(data.get("margin_default") or DEFAULT_MARGIN)
            ),
            leverage_default=int(data.get("leverage_default") or DEFAULT_LEVERAGE),
            positions=[
                Position.from_dict(item) for item in list(data.get("positions") or [])
            ],
            history=list(data.get("history") or []),
            notes=list(data.get("notes") or []),
        )


def open_position(
    account: Account,
    market: Market,
    pair_id: str,
    side: int,
    margin: float | None = None,
    leverage: int | None = None,
) -> Position:
    """Open a long/short position and lock margin."""

    normalized = normalize_pair(pair_id)
    if normalized is None:
        raise FxError("没有这个股票。")
    if side not in {1, -1}:
        raise FxError("方向只能是做多或做空。")
    margin_value = float(margin if margin is not None else account.margin_default)
    leverage_value = int(leverage if leverage is not None else account.leverage_default)
    if margin_value < MIN_MARGIN:
        raise FxError(f"保证金至少为 {money(MIN_MARGIN)}。")
    if not 1 <= leverage_value <= MAX_LEVERAGE:
        raise FxError(f"杠杆范围是 1-{MAX_LEVERAGE} 倍。")
    max_leverage = market.max_leverage(normalized)
    if leverage_value > max_leverage:
        raise FxError(f"当前波动率下该股票最大杠杆为 {max_leverage} 倍。")

    notional = margin_value * leverage_value
    equity_before = max(1.0, account.equity(market))
    slippage = min(MAX_SLIPPAGE_PCT, notional / equity_before * SLIPPAGE_FACTOR)
    open_fee = notional * TRADE_FEE_RATE
    if margin_value + open_fee > account.cash + 0.001:
        raise FxError(
            f"可用余额不足，需要保证金 {money(margin_value)} "
            f"和手续费 {money(open_fee)}，当前可用 {money(account.cash)}。"
        )

    entry = market.ask(normalized) if side == 1 else market.bid(normalized)
    entry = entry * (1 + slippage / 100) if side == 1 else entry * (1 - slippage / 100)
    if not math.isfinite(entry) or entry <= 0:
        raise FxError("行情尚未准备好。")

    account.cash -= margin_value + open_fee
    account.margin_default = margin_value
    account.leverage_default = leverage_value
    now = time.time()
    position = Position(
        id=f"p{int(now * 1000) % 10_000_000:07d}",
        pair=normalized,
        side=side,
        entry=entry,
        margin=margin_value,
        leverage=leverage_value,
        notional=notional,
        opened_ts=now,
        open_fee=open_fee,
        slippage=slippage,
        holding_fee_ts=now,
    )
    account.positions.insert(0, position)
    return position


def close_position(
    account: Account,
    market: Market,
    position_id: str,
    liquidated: bool = False,
) -> dict[str, Any]:
    """Close one position and settle it into cash."""

    target = next(
        (position for position in account.positions if position.id == position_id),
        None,
    )
    if target is None:
        raise FxError("找不到这个持仓编号。")
    raw_pnl = target.pnl(market)
    pnl = max(-target.margin, raw_pnl)
    close_fee = target.notional * TRADE_FEE_RATE
    penalty = target.notional * LIQUIDATION_PENALTY_RATE if liquidated else 0.0
    account.cash += max(0.0, target.margin + pnl - close_fee) - penalty
    account.positions.remove(target)
    record = {
        "pair": target.pair,
        "side": target.side_label,
        "pnl": pnl - close_fee - penalty,
        "gross_pnl": pnl,
        "fee": target.open_fee + close_fee,
        "penalty": penalty,
        "liquidated": liquidated,
        "time": time.time(),
    }
    account.history.insert(0, record)
    del account.history[HISTORY_LIMIT:]
    return record


def check_liquidations(account: Account, market: Market) -> list[str]:
    """Warn or liquidate positions whose loss reaches the threshold."""

    events: list[str] = []
    for position in list(account.positions):
        ratio = position.risk_ratio(market)
        if ratio < WARNING_RATIO - 1e-9:
            position.warned = False
        elif ratio >= LIQUIDATION_RATIO - 1e-9:
            record = close_position(account, market, position.id, liquidated=True)
            events.append(
                f"{position.pair} {position.side_label} 爆仓，亏损 {signed_money(record['pnl'])}。"
            )
        elif not position.warned:
            position.warned = True
            events.append(
                f"{position.pair} {position.side_label} 接近爆仓，"
                f"已亏损保证金 {ratio * 100:.1f}%。"
            )
    if events:
        account.notes.extend(events)
        del account.notes[:-20]
    return events


def accrue_interest(
    account: Account,
    now: float | None = None,
    interval_seconds: int = LOAN_INTEREST_SECONDS,
) -> int:
    """Settle compounded loan interest for each elapsed half-hour period.

    Returns:
        Number of interest periods settled.
    """

    if account.debt <= 0:
        return 0
    now = now if now is not None else time.time()
    if account.loan_last_ts <= 0:
        account.loan_last_ts = now
        account.loan_rate = LOAN_INTEREST_RATE
        return 0
    periods = int((now - account.loan_last_ts) // max(1, interval_seconds))
    if periods <= 0:
        return 0
    rate = account.loan_rate or LOAN_INTEREST_RATE
    for _ in range(periods):
        account.debt = round(account.debt * (1 + rate), 2)
    account.loan_last_ts += periods * interval_seconds
    return periods


def borrow(account: Account, amount: float, day: str | None = None) -> float:
    """Borrow money up to the current loan ceiling.

    The ceiling is the base limit plus any accumulated daily extra limit.
    """

    if amount < 1:
        raise FxError("借款金额至少为 $1。")
    if day:
        refresh_daily_loan(account, day)
    limit = loan_limit(account)
    if account.debt + amount > limit:
        available = max(0.0, limit - account.debt)
        raise FxError(f"当前贷款额度上限为 {money(limit)}，还可借 {money(available)}。")
    account.debt = round(account.debt + float(amount), 2)
    account.loan_principal = round(account.loan_principal + float(amount), 2)
    if account.loan_rate <= 0:
        account.loan_rate = LOAN_INTEREST_RATE
    if account.loan_last_ts <= 0:
        account.loan_last_ts = time.time()
    account.loan_ticks = 0
    account.cash += float(amount)
    return account.debt


def repay(account: Account, amount: float) -> float:
    """Repay debt using available cash."""

    if amount <= 0:
        raise FxError("还款金额必须大于 0。")
    if account.debt <= 0:
        raise FxError("当前没有欠款。")
    paid = min(float(amount), account.cash, account.debt)
    if paid <= 0:
        raise FxError("可用余额不足。")
    account.cash -= paid
    account.debt = round(account.debt - paid, 2)
    if account.debt <= 0:
        account.debt = 0.0
        account.loan_principal = 0.0
        account.loan_rate = 0.0
        account.loan_ticks = 0
        account.loan_last_ts = 0.0
    return paid


def settle_holding_fees(
    account: Account,
    now: float | None = None,
    interval_seconds: int = LOAN_INTEREST_SECONDS,
) -> float:
    """Charge periodic holding fees and short borrow fees.

    Returns:
        Total fee charged in this settlement.
    """

    now = now if now is not None else time.time()
    total = 0.0
    for position in account.positions:
        if position.holding_fee_ts <= 0:
            position.holding_fee_ts = position.opened_ts or now
        periods = int((now - position.holding_fee_ts) // max(1, interval_seconds))
        if periods <= 0:
            continue
        rate = HOLD_FEE_RATE
        if position.side == -1:
            rate += SHORT_BORROW_FEE_RATE
        fee = position.notional * rate * periods
        account.cash -= fee
        position.holding_fee_ts += periods * interval_seconds
        total += fee
    return total


def advance_market(
    market: Market,
    accounts: list[Account],
    tick_seconds: int,
    max_ticks: int = 240,
    now: float | None = None,
) -> int:
    """Advance the market lazily based on elapsed real time.

    Each account's positions are checked after each tick.  Liquidations are
    appended to ``account.notes`` so the next command can report them.
    """

    now = now if now is not None else time.time()
    elapsed = max(0.0, now - market.last_tick_ts)
    steps = min(int(elapsed // max(1, tick_seconds)), max(0, max_ticks))
    rng = random.Random()
    for _ in range(steps):
        tick_market(market, rng, now)
        for account in accounts:
            check_liquidations(account, market)
    for account in accounts:
        accrue_interest(account, now)
        settle_holding_fees(account, now)
    return steps
