from __future__ import annotations

import time
import logging
from typing import Iterable

from src.collectors.okx_provider import OKXProvider
from src.runtime.runtime_state import runtime_state


class LivePriceEngine:
    """Runtime Layer V2 live price owner.

    Owns:
      - mark_price
      - last_price
      - spread
      - updated_at

    Does not write to SQLite.
    Does not calculate analytics.
    """

    def __init__(self, symbols: Iterable[str], cfg: dict | None = None):
        self.symbols = [str(s).upper() for s in symbols]
        self.cfg = cfg or {}
        runtime_cfg = self.cfg.get("runtime", {}) if isinstance(self.cfg, dict) else {}
        self.interval_sec = int(runtime_cfg.get("price_refresh_sec", 5) or 5)
        self.timeout = int(runtime_cfg.get("api_timeout_sec", 8) or 8)
        self.log = logging.getLogger(__name__)
        self.okx = OKXProvider(timeout=self.timeout, period="5m")
        self.last_refresh_ts = 0.0

    def refresh_once(self) -> dict:
        started = time.time()
        updated = 0
        errors: dict[str, str] = {}

        for sym in self.symbols:
            try:
                mark_price = self.okx.get_mark_price(sym)
                last_price = self.okx.get_last_price(sym)

                if mark_price is None and last_price is None:
                    errors[sym] = "no_price"
                    continue

                runtime_state.set_price(
                    sym,
                    mark_price=mark_price,
                    last_price=last_price,
                    source="OKX",
                )
                updated += 1

            except Exception as exc:
                errors[sym] = str(exc)
                self.log.warning("Live price refresh failed for %s: %s", sym, exc)

        self.last_refresh_ts = time.time()

        return {
            "ok": updated > 0,
            "updated": updated,
            "errors": errors,
            "duration_ms": int((time.time() - started) * 1000),
            "source": "OKX",
        }

    def refresh_if_needed(self, *, force: bool = False) -> dict:
        now = time.time()
        if not force and self.last_refresh_ts and (now - self.last_refresh_ts) < self.interval_sec:
            return {
                "ok": True,
                "status": "skipped",
                "age_sec": round(now - self.last_refresh_ts, 2),
            }
        return self.refresh_once()
