from __future__ import annotations
from datetime import datetime, timezone
from ..models import SymbolSnapshot


class LSCollector:
    def __init__(self, client, period: str = '5m'):
        self.client = client
        self.period = period

    def collect(self, snapshot: SymbolSnapshot) -> SymbolSnapshot:
        lp, sp = self.client.ls_posit(snapshot.symbol, self.period)
        lr, sr = self.client.ls_ratio(snapshot.symbol, self.period)
        la, sa = self.client.ls_account(snapshot.symbol, self.period)
        snapshot.ls_posit_long, snapshot.ls_posit_short = lp, sp
        snapshot.ls_ratio_long, snapshot.ls_ratio_short = lr, sr
        snapshot.ls_account_long, snapshot.ls_account_short = la, sa
        snapshot.ls_updated_at = datetime.now(timezone.utc).isoformat()
        return snapshot
