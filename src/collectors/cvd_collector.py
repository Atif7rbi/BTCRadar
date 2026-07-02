from __future__ import annotations
from ..models import SymbolSnapshot


class CVDCollector:
    def __init__(self, client, period: str = '5m'):
        self.client = client
        self.period = period

    def collect(self, snapshot: SymbolSnapshot) -> SymbolSnapshot:
        cvd, buy, sell = self.client.taker_flow(snapshot.symbol, self.period)
        snapshot.cvd = cvd
        snapshot.cvd_buy_vol = buy
        snapshot.cvd_sell_vol = sell
        return snapshot
