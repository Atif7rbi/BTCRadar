from __future__ import annotations
import random
from datetime import datetime, timezone
from ..models import SymbolSnapshot, classify_cvd_pressure, classify_cvd_trend
from .vwap import calculate_vwap


class SnapshotBuilder:
    def __init__(self, client, cfg: dict):
        self.client = client
        self.cfg = cfg
        self.mock = bool(cfg.get('runtime', {}).get('mock_data', False))

    def build_mock(self, symbol: str) -> SymbolSnapshot:
        base = {'BTCUSDT': 67100, 'ETHUSDT': 3515, 'SOLUSDT': 172, 'DOGEUSDT': .153, 'XRPUSDT': .528}.get(symbol, 1)
        long_bias = random.uniform(43, 66)
        ts = datetime.now(timezone.utc).isoformat()
        return SymbolSnapshot(
            symbol=symbol,
            price=base * random.uniform(.995, 1.005),
            ls_posit_long=long_bias, ls_posit_short=100-long_bias,
            ls_ratio_long=random.uniform(43, 66), ls_ratio_short=0,
            ls_account_long=random.uniform(43, 66), ls_account_short=0,
            funding=random.uniform(-.0001, .0001),
            oi=random.uniform(1_000_000_000, 25_000_000_000),
            cvd=random.uniform(-100, 100),
            cvd_buy_vol=random.uniform(100000, 1000000),
            cvd_sell_vol=random.uniform(100000, 1000000),
            price_updated_at=ts, ls_updated_at=ts, updated_at=ts,
        )

    def finalize_mock(self, s: SymbolSnapshot) -> SymbolSnapshot:
        s.cvd_pressure = classify_cvd_pressure(s.cvd)
        s.cvd_trend = classify_cvd_trend(s.cvd, s.cvd_15m_ago)
        if s.cvd is not None and s.cvd_15m_ago is not None:
            try:
                s.cvd_delta_15m = round(float(s.cvd) - float(s.cvd_15m_ago), 4)
            except Exception:
                s.cvd_delta_15m = None
        for a,b in [('ls_ratio_long','ls_ratio_short'),('ls_account_long','ls_account_short')]:
            v = getattr(s, a)
            if getattr(s, b) in (0, None): setattr(s, b, 100 - float(v or 50))
        if s.vwap is None and s.price:
            s.vwap = s.price * random.uniform(.997, 1.003)
        return s

    def build_full(self, symbol: str) -> SymbolSnapshot:
        if self.mock:
            return self.finalize_mock(self.build_mock(symbol))
        now = datetime.now(timezone.utc).isoformat()
        s = SymbolSnapshot(symbol=symbol, updated_at=now)
        s.price = self.client.price(symbol); s.price_updated_at = now
        lp, sp = self.client.ls_posit(symbol); lr, sr = self.client.ls_ratio(symbol); la, sa = self.client.ls_account(symbol)
        s.ls_posit_long, s.ls_posit_short = lp, sp
        s.ls_ratio_long, s.ls_ratio_short = lr, sr
        s.ls_account_long, s.ls_account_short = la, sa
        s.ls_updated_at = now
        s.funding = self.client.funding(symbol)
        s.oi = self.client.open_interest(symbol)
        cvd, buy, sell = self.client.taker_flow(symbol)
        s.cvd, s.cvd_buy_vol, s.cvd_sell_vol = cvd, buy, sell
        try:
            s.vwap = calculate_vwap(self.client.klines(symbol, '1m', 120))
        except Exception:
            s.vwap = None
        return s

    def update_price_only(self, old: SymbolSnapshot) -> SymbolSnapshot:
        if self.mock:
            if old.price:
                old.price *= random.uniform(.999, 1.001)
            old.price_updated_at = datetime.now(timezone.utc).isoformat()
            old.updated_at = old.price_updated_at
            return old
        old.price = self.client.price(old.symbol)
        old.price_updated_at = datetime.now(timezone.utc).isoformat()
        old.updated_at = old.price_updated_at
        return old
