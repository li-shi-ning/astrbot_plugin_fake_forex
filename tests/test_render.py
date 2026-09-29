from __future__ import annotations

import random
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from src.engine import Account, Market, open_position  # noqa: E402
from src.render import render_account, render_chart, render_history, render_market  # noqa: E402


def test_renderers_return_png_bytes() -> None:
    market = Market.new(random.Random(2))
    account = Account("u", "Tester")
    open_position(account, market, "SMSC", 1, 500, 20)

    for payload in (
        render_market(market),
        render_chart(market, "SMSC"),
        render_account(account, market),
        render_history(account),
    ):
        assert payload.startswith(b"\x89PNG")
        assert len(payload) > 1000
