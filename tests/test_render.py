from __future__ import annotations

import random
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from src.engine import Account, Market, open_position  # noqa: E402
from src.render import (  # noqa: E402
    render_account,
    render_chart,
    render_history,
    render_leaderboard,
    render_lottery_ticket,
    render_market,
)


def test_renderers_return_png_bytes() -> None:
    market = Market.new(random.Random(2))
    account = Account("u", "Tester")
    open_position(account, market, "SMSC", 1, 500, 20)

    for payload in (
        render_market(market),
        render_chart(market, "SMSC"),
        render_account(account, market),
        render_history(account),
        render_leaderboard(
            [
                {"rank": 1, "name": "甲", "pnl": 100.0, "equity": 10100.0},
                {"rank": 2, "name": "乙", "pnl": -50.0, "equity": 9950.0},
            ]
        ),
        render_lottery_ticket(
            {
                "chosen": 7,
                "draw": 8,
                "won": False,
                "payout": 0.0,
                "pool_after": 200100.0,
            },
            "Tester",
            200100.0,
        ),
    ):
        assert payload.startswith(b"\x89PNG")
        assert len(payload) > 1000
