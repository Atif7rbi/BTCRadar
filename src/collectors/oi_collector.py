from __future__ import annotations
from ..models import SymbolSnapshot


class OICollector:
    def __init__(self, client):
        self.client = client

    def collect(self, snapshot: SymbolSnapshot) -> SymbolSnapshot:
        snapshot.oi = self.client.open_interest(snapshot.symbol)
        return snapshot
