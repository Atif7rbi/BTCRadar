from __future__ import annotations
from datetime import datetime, timezone
from ..models import SymbolSnapshot


class PriceCollector:
    def __init__(self, client):
        self.client = client

    def collect(self, snapshot: SymbolSnapshot) -> SymbolSnapshot:
        snapshot.price = self.client.price(snapshot.symbol)
        snapshot.price_updated_at = datetime.now(timezone.utc).isoformat()
        return snapshot
