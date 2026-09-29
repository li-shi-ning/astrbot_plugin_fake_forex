from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .engine import (
    PAIR_DEFS,
    Account,
    Market,
    money,
    price_text,
    signed_money,
)

WIDTH = 960
BG = (18, 24, 30)
PANEL = (27, 35, 43)
GRID = (45, 56, 66)
TEXT = (226, 234, 238)
MUTED = (145, 160, 170)
GREEN = (110, 231, 183)
RED = (248, 113, 113)
YELLOW = (250, 204, 21)

CJK_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]
CJK_BOLD_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]
FONT_CANDIDATES = [
    *CJK_FONT_CANDIDATES,
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]
FONT_BOLD_CANDIDATES = [
    *CJK_BOLD_CANDIDATES,
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
]


def pair_change(market: Market, pair_id: str) -> float:
    """Return the latest change percentage for *pair_id*."""

    return market.pairs[pair_id].change_percent()


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = FONT_BOLD_CANDIDATES if bold else FONT_CANDIDATES
    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, **kwargs) -> None:
    draw.text(
        xy,
        value,
        font=kwargs.pop("font", _font(16)),
        fill=kwargs.pop("fill", TEXT),
        **kwargs,
    )


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _sparkline_points(
    candles: list[dict[str, float]], left: int, top: int, width: int, height: int
) -> list[tuple[float, float]]:
    values = [float(candle["close"]) for candle in candles[-48:]]
    if len(values) < 2:
        return []
    low = min(values)
    high = max(values)
    span = high - low or 1.0
    return [
        (
            left + index / (len(values) - 1) * width,
            top + height - (value - low) / span * height,
        )
        for index, value in enumerate(values)
    ]


def render_market(market: Market) -> bytes:
    """Render a market overview image with mini sparklines."""

    row_height = 74
    header = 78
    height = header + row_height * len(PAIR_DEFS) + 30
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)
    _text(
        draw,
        (28, 22),
        "虚拟外汇 | 模拟行情",
        font=_font(24, True),
        fill=TEXT,
    )
    _text(draw, (28, 52), f"第 {market.tick} 期", font=_font(15), fill=MUTED)
    _text(draw, (WIDTH - 160, 52), "虚假数据", font=_font(15, True), fill=YELLOW)

    for index, item in enumerate(PAIR_DEFS):
        top = header + index * row_height
        draw.rounded_rectangle(
            (18, top, WIDTH - 18, top + row_height - 10),
            radius=12,
            fill=PANEL,
        )
        pair_id = item["id"]
        series = market.pairs[pair_id]
        change = series.change_percent()
        color = GREEN if change >= 0 else RED
        _text(draw, (38, top + 14), pair_id, font=_font(20, True), fill=TEXT)
        _text(
            draw,
            (38, top + 40),
            item["name"],
            font=_font(13),
            fill=MUTED,
        )
        _text(
            draw,
            (220, top + 14),
            price_text(pair_id, series.price),
            font=_font(20, True),
            fill=TEXT,
        )
        _text(
            draw, (220, top + 42), f"{change:+.2f}%", font=_font(15, True), fill=color
        )

        points = _sparkline_points(series.candles, 420, top + 15, 360, 36)
        if points:
            draw.line(points, fill=color, width=2, joint="curve")
        _text(draw, (WIDTH - 140, top + 24), "查看", font=_font(15, True), fill=MUTED)
    return _png_bytes(image)


def render_chart(market: Market, pair_id: str) -> bytes:
    """Render a candlestick chart for one forex pair."""

    item = next((entry for entry in PAIR_DEFS if entry["id"] == pair_id), None)
    if item is None:
        raise ValueError("unknown pair")
    series = market.pairs[pair_id]
    candles = series.candles[-60:]
    image = Image.new("RGB", (WIDTH, 470), BG)
    draw = ImageDraw.Draw(image)
    change = series.change_percent()
    color = GREEN if change >= 0 else RED
    _text(draw, (28, 20), pair_id, font=_font(28, True), fill=TEXT)
    _text(draw, (28, 56), item["name"], font=_font(16), fill=MUTED)
    _text(
        draw,
        (WIDTH - 300, 24),
        price_text(pair_id, series.price),
        font=_font(28, True),
        fill=TEXT,
    )
    _text(draw, (WIDTH - 300, 62), f"{change:+.2f}%", font=_font(18, True), fill=color)

    left, top, right, bottom = 70, 120, WIDTH - 40, 400
    draw.rectangle((left, top, right, bottom), fill=PANEL)
    if not candles:
        return _png_bytes(image)

    low = min(float(candle["low"]) for candle in candles)
    high = max(float(candle["high"]) for candle in candles)
    span = high - low or 1.0
    step = (right - left) / max(1, len(candles))
    body_width = max(3, int(step * 0.55))

    for index in range(5):
        y = top + (bottom - top) * index / 4
        draw.line((left, y, right, y), fill=GRID, width=1)
        value = high - span * index / 4
        _text(draw, (10, int(y) - 8), f"{value:.5f}", font=_font(12), fill=MUTED)

    for index, candle in enumerate(candles):
        x = left + step * index + step / 2
        open_price = float(candle["open"])
        close = float(candle["close"])
        high_price = float(candle["high"])
        low_price = float(candle["low"])
        candle_color = GREEN if close >= open_price else RED
        high_y = bottom - (high_price - low) / span * (bottom - top)
        low_y = bottom - (low_price - low) / span * (bottom - top)
        open_y = bottom - (open_price - low) / span * (bottom - top)
        close_y = bottom - (close - low) / span * (bottom - top)
        draw.line((x, high_y, x, low_y), fill=candle_color, width=2)
        draw.rectangle(
            (
                x - body_width / 2,
                min(open_y, close_y),
                x + body_width / 2,
                max(open_y, close_y),
            ),
            fill=candle_color,
        )

    _text(draw, (left, bottom + 18), f"最低 {low:.5f}", font=_font(13), fill=MUTED)
    _text(
        draw,
        (right - 220, bottom + 18),
        f"最高 {high:.5f}  |  K线 {len(candles)}",
        font=_font(13),
        fill=MUTED,
    )
    _text(draw, (WIDTH - 180, 440), "模拟行情", font=_font(14, True), fill=YELLOW)
    return _png_bytes(image)


def render_account(account: Account, market: Market) -> bytes:
    """Render an account summary and open positions."""

    positions = account.positions
    height = 420 + max(1, len(positions)) * 44
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)
    _text(draw, (28, 22), "账户", font=_font(26, True), fill=TEXT)
    _text(draw, (28, 58), account.name, font=_font(16), fill=MUTED)

    equity = account.equity(market)
    floating = account.floating_pnl(market)
    rows = [
        ("现金", money(account.cash), TEXT),
        ("占用保证金", money(account.used_margin()), TEXT),
        ("浮动盈亏", signed_money(floating), GREEN if floating >= 0 else RED),
        ("净值", money(equity), GREEN if equity >= 0 else RED),
        ("负债", money(account.debt), YELLOW if account.debt > 0 else TEXT),
    ]
    for index, (label, value, color) in enumerate(rows):
        top = 100 + index * 34
        draw.rounded_rectangle((24, top, WIDTH - 24, top + 30), radius=8, fill=PANEL)
        _text(draw, (40, top + 6), label, font=_font(15), fill=MUTED)
        _text(draw, (WIDTH - 260, top + 6), value, font=_font(16, True), fill=color)

    header_top = 290
    _text(draw, (28, header_top), "持仓", font=_font(20, True), fill=TEXT)
    if not positions:
        _text(draw, (28, header_top + 36), "暂无持仓", font=_font(15), fill=MUTED)
        return _png_bytes(image)

    _text(draw, (28, header_top + 32), "编号", font=_font(13), fill=MUTED)
    _text(draw, (170, header_top + 32), "股票", font=_font(13), fill=MUTED)
    _text(draw, (300, header_top + 32), "方向", font=_font(13), fill=MUTED)
    _text(draw, (390, header_top + 32), "保证金", font=_font(13), fill=MUTED)
    _text(draw, (540, header_top + 32), "开仓价", font=_font(13), fill=MUTED)
    _text(draw, (680, header_top + 32), "当前价", font=_font(13), fill=MUTED)
    _text(draw, (800, header_top + 32), "盈亏", font=_font(13), fill=MUTED)
    for index, position in enumerate(positions):
        top = header_top + 58 + index * 44
        pnl = position.pnl(market)
        color = GREEN if pnl >= 0 else RED
        draw.rounded_rectangle((20, top, WIDTH - 20, top + 38), radius=8, fill=PANEL)
        _text(draw, (28, top + 10), position.id, font=_font(12), fill=MUTED)
        _text(draw, (170, top + 9), position.pair, font=_font(14, True), fill=TEXT)
        _text(
            draw,
            (300, top + 9),
            "做多" if position.side == 1 else "做空",
            font=_font(13, True),
            fill=GREEN if position.side == 1 else RED,
        )
        _text(
            draw,
            (390, top + 9),
            f"${position.margin:,.0f} x{position.leverage}",
            font=_font(13),
            fill=TEXT,
        )
        _text(
            draw,
            (540, top + 9),
            price_text(position.pair, position.entry),
            font=_font(13),
            fill=TEXT,
        )
        _text(
            draw,
            (680, top + 9),
            price_text(position.pair, market.price(position.pair)),
            font=_font(13),
            fill=TEXT,
        )
        _text(draw, (800, top + 9), signed_money(pnl), font=_font(13, True), fill=color)
    return _png_bytes(image)


def render_history(account: Account, limit: int = 12) -> bytes:
    """Render recent closed trades."""

    history = account.history[:limit]
    height = 150 + max(1, len(history)) * 38
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)
    _text(draw, (28, 22), "交易历史", font=_font(26, True), fill=TEXT)
    if not history:
        _text(draw, (28, 90), "暂无成交记录", font=_font(16), fill=MUTED)
        return _png_bytes(image)
    for index, item in enumerate(history):
        top = 84 + index * 38
        pnl = float(item.get("pnl") or 0)
        color = GREEN if pnl >= 0 else RED
        draw.rounded_rectangle((24, top, WIDTH - 24, top + 32), radius=8, fill=PANEL)
        _text(
            draw,
            (38, top + 6),
            str(item.get("pair") or "?"),
            font=_font(15, True),
            fill=TEXT,
        )
        _text(
            draw,
            (220, top + 6),
            str(item.get("side") or "?"),
            font=_font(14),
            fill=MUTED,
        )
        liquidated = bool(item.get("liquidated"))
        _text(
            draw,
            (360, top + 6),
            "爆仓" if liquidated else "平仓",
            font=_font(13, True),
            fill=RED if liquidated else MUTED,
        )
        _text(
            draw,
            (WIDTH - 220, top + 6),
            signed_money(pnl),
            font=_font(15, True),
            fill=color,
        )
    return _png_bytes(image)
