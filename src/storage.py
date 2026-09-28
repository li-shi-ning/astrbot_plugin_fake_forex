from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from astrbot.api import logger


class FxStore:
    """Small JSON persistence layer for the fake forex plugin."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def load(self) -> dict[str, Any]:
        """Load the saved state, returning an empty dict when absent."""

        async with self._lock:
            return await asyncio.to_thread(self._load_sync)

    async def save(self, data: dict[str, Any]) -> None:
        """Atomically save the state."""

        async with self._lock:
            await asyncio.to_thread(self._save_sync, data)

    def _load_sync(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
            logger.warning("[FakeForex] state file is not an object: %s", self.path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("[FakeForex] failed to load state: %s", exc)
        return {}

    def _save_sync(self, data: dict[str, Any]) -> None:
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
            os.replace(temp_path, self.path)
        except OSError as exc:
            logger.warning("[FakeForex] failed to save state: %s", exc)
