from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests


OKX_BASE_URL = "https://www.okx.com"

OKX_SYMBOLS = {
    "BTCUSDT": {"ccy": "BTC", "inst_id": "BTC-USDT-SWAP"},
    "ETHUSDT": {"ccy": "ETH", "inst_id": "ETH-USDT-SWAP"},
    "SOLUSDT": {"ccy": "SOL", "inst_id": "SOL-USDT-SWAP"},
    "XRPUSDT": {"ccy": "XRP", "inst_id": "XRP-USDT-SWAP"},
    "DOGEUSDT": {"ccy": "DOGE", "inst_id": "DOGE-USDT-SWAP"},
    "ADAUSDT": {"ccy": "ADA", "inst_id": "ADA-USDT-SWAP"},
}


@dataclass(frozen=True)
class OKXRatioValue:
    ts_ms: int
    ratio: float
    long_pct: float
    short_pct: float


@dataclass(frozen=True)
class OKXSymbolSnapshot:
    symbol: str
    ls_ratio: Optional[OKXRatioValue]
    ls_account: Optional[OKXRatioValue]
    ls_posit: Optional[OKXRatioValue]


class OKXProvider:
    def __init__(self, timeout: int = 10, period: str = "5m") -> None:
        self.timeout = timeout
        self.period = period

    def _get(self, path: str, params: dict) -> dict:
        r = requests.get(
            OKX_BASE_URL + path,
            params=params,
            timeout=self.timeout,
            headers={"User-Agent": "BTCRadar/okx-provider"},
        )
        r.raise_for_status()

        payload = r.json()
        if payload.get("code") != "0":
            raise RuntimeError(f"OKX error {payload.get('code')}: {payload.get('msg')}")
        return payload

    @staticmethod
    def _ratio_to_value(row: list) -> OKXRatioValue:
        ts_ms = int(row[0])
        ratio = float(row[1])

        long_pct = ratio / (1.0 + ratio) * 100.0
        short_pct = 100.0 - long_pct

        return OKXRatioValue(
            ts_ms=ts_ms,
            ratio=ratio,
            long_pct=long_pct,
            short_pct=short_pct,
        )

    def _latest_by_ccy(self, path: str, ccy: str) -> OKXRatioValue:
        payload = self._get(
            path,
            {
                "ccy": ccy,
                "period": self.period,
                "limit": "1",
            },
        )
        data = payload.get("data") or []
        if not data:
            raise RuntimeError(f"OKX empty data for ccy={ccy} path={path}")
        return self._ratio_to_value(data[0])

    def _latest_by_inst_id(self, path: str, inst_id: str) -> OKXRatioValue:
        payload = self._get(
            path,
            {
                "instId": inst_id,
                "period": self.period,
                "limit": "1",
            },
        )
        data = payload.get("data") or []
        if not data:
            raise RuntimeError(f"OKX empty data for instId={inst_id} path={path}")
        return self._ratio_to_value(data[0])

    def get_ls_snapshot(self, symbol: str) -> OKXSymbolSnapshot:
        if symbol not in OKX_SYMBOLS:
            raise ValueError(f"Unsupported OKX symbol: {symbol}")

        meta = OKX_SYMBOLS[symbol]
        ccy = meta["ccy"]
        inst_id = meta["inst_id"]

        ls_ratio = self._latest_by_ccy(
            "/api/v5/rubik/stat/contracts/long-short-account-ratio",
            ccy,
        )

        ls_account = self._latest_by_inst_id(
            "/api/v5/rubik/stat/contracts/long-short-account-ratio-contract-top-trader",
            inst_id,
        )

        ls_posit = self._latest_by_inst_id(
            "/api/v5/rubik/stat/contracts/long-short-position-ratio-contract-top-trader",
            inst_id,
        )

        return OKXSymbolSnapshot(
            symbol=symbol,
            ls_ratio=ls_ratio,
            ls_account=ls_account,
            ls_posit=ls_posit,
        )

    def get_funding_rate(self, symbol: str) -> float | None:
        meta = OKX_SYMBOLS[symbol]
        payload = self._get(
            "/api/v5/public/funding-rate",
            {"instId": meta["inst_id"]},
        )
        data = payload.get("data") or []
        if not data:
            return None
        return float(data[0].get("fundingRate"))

    def get_open_interest(self, symbol: str) -> float | None:
        meta = OKX_SYMBOLS[symbol]
        payload = self._get(
            "/api/v5/public/open-interest",
            {"instType": "SWAP", "instId": meta["inst_id"]},
        )
        data = payload.get("data") or []
        if not data:
            return None
        row = data[0]
        return float(row.get("oiUsd") or row.get("oiCcy") or row.get("oi") or 0)

    def get_taker_flow(self, symbol: str) -> tuple[float | None, float | None, float | None]:
        """Return buy_vol, sell_vol, delta. Best-effort OKX taker volume proxy for CVD."""
        meta = OKX_SYMBOLS[symbol]
        payload = self._get(
            "/api/v5/rubik/stat/taker-volume",
            {
                "ccy": meta["ccy"],
                "instType": "SWAP",
                "period": self.period,
                "limit": "1",
            },
        )
        data = payload.get("data") or []
        if not data:
            return None, None, None

        row = data[0]
        if isinstance(row, list) and len(row) >= 3:
            # OKX Rubik rows are timestamp + two flow values.
            a = float(row[1])
            b = float(row[2])
            buy_vol = max(a, b)
            sell_vol = min(a, b)
            return buy_vol, sell_vol, buy_vol - sell_vol

        return None, None, None

    def get_mark_price(self, symbol: str) -> float | None:
        meta = OKX_SYMBOLS[symbol]
        payload = self._get(
            "/api/v5/public/mark-price",
            {"instType": "SWAP", "instId": meta["inst_id"]},
        )
        data = payload.get("data") or []
        if not data:
            return None
        return float(data[0].get("markPx"))

    def get_last_price(self, symbol: str) -> float | None:
        meta = OKX_SYMBOLS[symbol]
        payload = self._get(
            "/api/v5/market/ticker",
            {"instId": meta["inst_id"]},
        )
        data = payload.get("data") or []
        if not data:
            return None
        return float(data[0].get("last"))

