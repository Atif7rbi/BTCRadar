from __future__ import annotations

from dataclasses import dataclass, asdict
import time
from typing import Callable
import requests


@dataclass
class ProviderAttempt:
    provider: str
    ok: bool
    ts: float
    error: str | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class PriceRouter:
    """Fast price router independent from Binance.

    Rotates OKX -> Coinbase -> Kraken per tick and falls back immediately when
    the selected provider fails. Safe for request-bounded Flask code.
    """

    def __init__(self, timeout: int = 3, priority: list[str] | None = None):
        self.timeout = max(1, int(timeout or 3))
        self.providers = [p.lower() for p in (priority or ['okx', 'coinbase', 'kraken'])]
        self._index = 0
        self.last_attempts: dict[str, list[ProviderAttempt]] = {}
        self.last_price_provider: dict[str, str] = {}
        self.last_error: str | None = None

    def next_tick_provider(self) -> str:
        if not self.providers:
            return 'none'
        provider = self.providers[self._index % len(self.providers)]
        self._index = (self._index + 1) % len(self.providers)
        return provider

    def price(self, symbol: str, *, preferred: str | None = None) -> float:
        providers = self._ordered_providers(preferred)
        errors: list[str] = []
        for provider in providers:
            start = time.time()
            try:
                value = self._fetch(provider, symbol)
                self._record(symbol, ProviderAttempt(provider, True, time.time(), duration_ms=int((time.time()-start)*1000)))
                self.last_price_provider[symbol.upper()] = provider
                self.last_error = None
                return value
            except Exception as exc:  # noqa: BLE001
                err = f'{provider}: {exc}'
                errors.append(err)
                self._record(symbol, ProviderAttempt(provider, False, time.time(), error=str(exc), duration_ms=int((time.time()-start)*1000)))
                self.last_error = err
        raise RuntimeError('; '.join(errors) or 'No price providers configured')

    def _ordered_providers(self, preferred: str | None) -> list[str]:
        providers = list(self.providers)
        if preferred and preferred in providers:
            providers.remove(preferred)
            providers.insert(0, preferred)
        return providers

    def _record(self, symbol: str, attempt: ProviderAttempt) -> None:
        sym = symbol.upper()
        rows = self.last_attempts.setdefault(sym, [])
        rows.append(attempt)
        del rows[:-5]

    def _fetch(self, provider: str, symbol: str) -> float:
        fn: Callable[[str], float] | None = getattr(self, f'_fetch_{provider}', None)
        if not fn:
            raise RuntimeError(f'Unsupported provider {provider}')
        return fn(symbol.upper())

    @staticmethod
    def _base(symbol: str) -> str:
        return symbol.upper().removesuffix('USDT')

    def _fetch_okx(self, symbol: str) -> float:
        inst = f'{self._base(symbol)}-USDT-SWAP'
        r = requests.get('https://www.okx.com/api/v5/market/ticker', params={'instId': inst}, timeout=self.timeout)
        r.raise_for_status()
        data = r.json().get('data') or []
        if not data:
            raise RuntimeError(f'OKX empty ticker for {inst}')
        return float(data[0]['last'])

    def _fetch_coinbase(self, symbol: str) -> float:
        pair = f'{self._base(symbol)}-USDT'
        r = requests.get(f'https://api.coinbase.com/v2/prices/{pair}/spot', timeout=self.timeout)
        r.raise_for_status()
        return float((r.json().get('data') or {}).get('amount'))

    def _fetch_kraken(self, symbol: str) -> float:
        pair = f'{self._base(symbol)}USDT'
        r = requests.get('https://api.kraken.com/0/public/Ticker', params={'pair': pair}, timeout=self.timeout)
        r.raise_for_status()
        payload = r.json()
        if payload.get('error'):
            raise RuntimeError(', '.join(payload.get('error') or []))
        result = payload.get('result') or {}
        if not result:
            raise RuntimeError(f'Kraken empty ticker for {pair}')
        first = next(iter(result.values()))
        return float(first['c'][0])

    def status(self) -> dict:
        return {
            'providers': self.providers,
            'last_price_provider': dict(self.last_price_provider),
            'last_error': self.last_error,
            'last_attempts': {
                sym: [a.to_dict() for a in attempts]
                for sym, attempts in self.last_attempts.items()
            },
        }
