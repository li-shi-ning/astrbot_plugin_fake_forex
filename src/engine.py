from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

INSTRUMENT_DEFS: list[dict[str, Any]] = [
    {"id": "SMSC", "name": "水母水产", "initial": 12.50, "digits": 2},
    {"id": "YZCC", "name": "预制菜赌场", "initial": 8.88, "digits": 2},
    {"id": "HYG", "name": "辉叶股", "initial": 45.60, "digits": 2},
    {"id": "ZYG", "name": "真叶股", "initial": 52.30, "digits": 2},
    {"id": "YFNHJ", "name": "茵菲诺黄金", "initial": 188.80, "digits": 2},
    {"id": "YTG", "name": "芋头股", "initial": 23.45, "digits": 2},
    {"id": "MYG", "name": "卯月股", "initial": 77.77, "digits": 2},
    {"id": "ASKC", "name": "爱素矿产", "initial": 31.20, "digits": 2},
    {"id": "QYJT", "name": "千音集团", "initial": 66.60, "digits": 2},
    {"id": "NMWY", "name": "糯米文娱", "initial": 18.88, "digits": 2},
    {"id": "CQSS", "name": "长期素食", "initial": 14.20, "digits": 2},
    {"id": "BMXY", "name": "白毛兽业", "initial": 9.90, "digits": 2},
    {"id": "MTDBL", "name": "睦缇斯暴力公司", "initial": 120.00, "digits": 2},
    {"id": "XYKH", "name": "咲夜航空", "initial": 58.88, "digits": 2},
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
                }
            )
            PAIR_MAP[normalized_code] = item
            return dict(item)
    definition = {
        "id": normalized_code,
        "name": normalized_name,
        "initial": float(initial),
        "digits": digits,
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
LOAN_INTEREST_TICKS = 20
HISTORY_LIMIT = 25
CANDLE_LIMIT = 150
SEED_CANDLES = 76


class FxError(ValueError):
    """Raised when a forex game action is not legal."""


def normalize_pair(text: str) -> str | None:
    """Normalize user input such as ``eurusd`` or ``eur/usd``."""

    compact = (
        str(text or "")
        .strip()
        .upper()
        .replace(" ", "")
        .replace("-", "")
        .replace("/", "")
    )
    for pair_id in PAIR_IDS:
        if compact == pair_id.replace("/", ""):
            return pair_id
    return None


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

    digits = PAIR_MAP[pair_id]["digits"]
    return f"{value:.{digits}f}"


def loan_daily_rate(amount: float) -> float:
    """Return the tiered daily loan rate used by the reference toy."""

    if amount <= 10000:
        return 0.0001
    if amount <= 50000:
        return 0.0002
    if amount <= 100000:
        return 0.0003
    return 0.0004


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

    def change_percent(self) -> float:
        """Return the latest candle change percentage."""

        if len(self.candles) < 2:
            return 0.0
        previous = self.candles[-2]["close"]
        if previous == 0:
            return 0.0
        return (self.price / previous - 1) * 100

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "price": self.price, "candles": self.candles}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PairSeries:
        return cls(
            id=str(data.get("id") or ""),
            price=float(data.get("price") or 0),
            candles=list(data.get("candles") or []),
        )


@dataclass
class Market:
    pairs: dict[str, PairSeries] = field(default_factory=dict)
    tick: int = 0
    last_tick_ts: float = 0.0

    @classmethod
    def new(cls, rng: random.Random | None = None) -> Market:
        """Create a fully simulated market."""

        return cls.from_dict(_seed_market(rng or random.Random()))

    def price(self, pair_id: str) -> float:
        return self.pairs[pair_id].price

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
    for index, item in enumerate(PAIR_DEFS):
        series = market.pairs[item["id"]]
        open_price = series.price
        drift = math.sin((market.tick + 1) / 8.67 + index * 2) * 0.00036
        shock = (rng.random() - 0.5) * 0.019 if rng.random() < 0.018 else 0.0
        close = max(
            open_price * 0.5,
            open_price * (1 + drift + (rng.random() - 0.5) * 0.0042 + shock),
        )
        wick = open_price * (rng.random() * 0.0007 + 0.00015)
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
    warned: bool = False

    @property
    def side_label(self) -> str:
        return "做多" if self.side == 1 else "做空"

    def pnl(self, market: Market) -> float:
        """Return the floating profit/loss for this position."""

        current = market.price(self.pair)
        if self.entry <= 0:
            return 0.0
        return self.notional * self.side * (current / self.entry - 1)

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "cash": self.cash,
            "debt": self.debt,
            "loan_principal": self.loan_principal,
            "loan_rate": self.loan_rate,
            "loan_ticks": self.loan_ticks,
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
            loan_rate=float(data.get("loan_rate") or 0),
            loan_ticks=int(data.get("loan_ticks") or 0),
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
    if margin_value > account.cash + 0.001:
        raise FxError(f"可用余额不足，当前可用 {money(account.cash)}。")
    if not 1 <= leverage_value <= MAX_LEVERAGE:
        raise FxError(f"杠杆范围是 1-{MAX_LEVERAGE} 倍。")
    entry = market.price(normalized)
    if not math.isfinite(entry) or entry <= 0:
        raise FxError("行情尚未准备好。")

    account.cash = max(0.0, account.cash - margin_value)
    account.margin_default = margin_value
    account.leverage_default = leverage_value
    position = Position(
        id=f"p{int(time.time() * 1000) % 10_000_000:07d}",
        pair=normalized,
        side=side,
        entry=entry,
        margin=margin_value,
        leverage=leverage_value,
        notional=margin_value * leverage_value,
        opened_ts=time.time(),
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
    account.cash += max(0.0, target.margin + pnl)
    account.positions.remove(target)
    record = {
        "pair": target.pair,
        "side": target.side_label,
        "pnl": pnl,
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


def accrue_interest(account: Account) -> None:
    """Accrue one daily loan interest payment."""

    if account.debt <= 0:
        return
    account.debt = round(account.debt * (1 + account.loan_rate), 2)


def borrow(account: Account, amount: float) -> float:
    """Borrow money and increase debt."""

    if amount < 1:
        raise FxError("借款金额至少为 $1。")
    if amount > LOAN_MAX:
        raise FxError(f"单次借款上限为 {money(LOAN_MAX)}。")
    if account.debt > 0:
        raise FxError("请先还清当前贷款，才能再次借款。")
    account.debt = float(amount)
    account.loan_principal = float(amount)
    account.loan_rate = loan_daily_rate(amount)
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
    return paid


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
    if steps <= 0:
        return 0
    rng = random.Random()
    for _ in range(steps):
        tick_market(market, rng, now)
        for account in accounts:
            if account.debt > 0:
                account.loan_ticks += 1
                if account.loan_ticks >= LOAN_INTEREST_TICKS:
                    account.loan_ticks = 0
                    accrue_interest(account)
            check_liquidations(account, market)
    return steps
