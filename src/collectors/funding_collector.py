from __future__ import annotations
from ..models import SymbolSnapshot


class FundingCollector:
    def __init__(self, client):
        self.client = client

    def collect(self, snapshot: SymbolSnapshot) -> SymbolSnapshot:
        snapshot.funding = self.client.funding(snapshot.symbol)

        # Optional / defensive: if BinanceClient later exposes predicted funding,
        # attach it under the same aliases used by Followers Consensus.
        predicted = None
        for method_name in ("predicted_funding", "next_funding", "funding_predicted"):
            method = getattr(self.client, method_name, None)
            if callable(method):
                try:
                    predicted = method(snapshot.symbol)
                    break
                except Exception:
                    predicted = None

        if predicted is not None:
            snapshot.predicted_funding_rate = predicted
            snapshot.predicted_funding = predicted
            snapshot.next_funding_rate = predicted
            snapshot.next_funding = predicted
            snapshot.funding_predicted = predicted
            snapshot.funding_next = predicted

        return snapshot
