from __future__ import annotations
import requests
from typing import Any


class BinanceClient:
    def __init__(self, timeout: int = 8):
        self.timeout = timeout
        self.fapi = 'https://fapi.binance.com'

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = requests.get(self.fapi + path, params=params or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def price(self, symbol: str) -> float:
        data = self._get('/fapi/v1/ticker/price', {'symbol': symbol})
        return float(data['price'])

    def funding(self, symbol: str) -> float:
        data = self._get('/fapi/v1/premiumIndex', {'symbol': symbol})
        return float(data.get('lastFundingRate') or 0.0)

    def open_interest(self, symbol: str) -> float:
        data = self._get('/fapi/v1/openInterest', {'symbol': symbol})
        return float(data.get('openInterest') or 0.0)

    def klines(self, symbol: str, interval: str = '1m', limit: int = 60) -> list[list]:
        return self._get('/fapi/v1/klines', {'symbol': symbol, 'interval': interval, 'limit': limit})

    def _ls_endpoint(self, endpoint: str, symbol: str, period: str = '5m') -> tuple[float, float]:
        data = self._get(endpoint, {'symbol': symbol, 'period': period, 'limit': 1})
        if not data:
            return 50.0, 50.0
        row = data[-1]
        long_v = float(row.get('longAccount') or row.get('longPosition') or 0.5) * 100
        short_v = float(row.get('shortAccount') or row.get('shortPosition') or 0.5) * 100
        return long_v, short_v

    def ls_ratio(self, symbol: str, period: str = '5m') -> tuple[float, float]:
        return self._ls_endpoint('/futures/data/globalLongShortAccountRatio', symbol, period)

    def ls_account(self, symbol: str, period: str = '5m') -> tuple[float, float]:
        return self._ls_endpoint('/futures/data/topLongShortAccountRatio', symbol, period)

    def ls_posit(self, symbol: str, period: str = '5m') -> tuple[float, float]:
        return self._ls_endpoint('/futures/data/topLongShortPositionRatio', symbol, period)

    def taker_flow(self, symbol: str, period: str = '5m') -> tuple[float, float, float]:
        data = self._get('/futures/data/takerlongshortRatio', {'symbol': symbol, 'period': period, 'limit': 1})
        if not data:
            return 0.0, 0.0, 0.0
        row = data[-1]
        buy = float(row.get('buyVol') or 0.0)
        sell = float(row.get('sellVol') or 0.0)
        cvd = buy - sell
        return cvd, buy, sell
