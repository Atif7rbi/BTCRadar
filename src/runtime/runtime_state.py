from __future__ import annotations

import threading
import time
from dataclasses import dataclass, asdict


@dataclass
class LivePrice:
    symbol: str
    mark_price: float | None = None
    last_price: float | None = None
    spread: float | None = None
    spread_pct: float | None = None
    updated_at: float | None = None
    source: str = "OKX"


class RuntimeState:
    def __init__(self):
        self._lock = threading.RLock()
        self._prices: dict[str, LivePrice] = {}

    def set_price(self, symbol: str, mark_price=None, last_price=None, source: str = "OKX"):
        symbol = str(symbol).upper()
        now = time.time()

        spread = None
        spread_pct = None
        if mark_price is not None and last_price is not None:
            try:
                spread = float(last_price) - float(mark_price)
                spread_pct = (spread / float(mark_price)) * 100 if float(mark_price) else None
            except Exception:
                spread = None
                spread_pct = None

        with self._lock:
            self._prices[symbol] = LivePrice(
                symbol=symbol,
                mark_price=float(mark_price) if mark_price is not None else None,
                last_price=float(last_price) if last_price is not None else None,
                spread=spread,
                spread_pct=spread_pct,
                updated_at=now,
                source=source,
            )

    def get_price(self, symbol: str) -> dict:
        symbol = str(symbol).upper()
        with self._lock:
            p = self._prices.get(symbol)
            return asdict(p) if p else {"symbol": symbol}

    def all_prices(self) -> dict:
        with self._lock:
            return {sym: asdict(p) for sym, p in self._prices.items()}


runtime_state = RuntimeState()
