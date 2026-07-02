from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace

from src.collectors.coinalyze_collector import CoinalyzeCollector
from src.collectors.snapshot_builder import SnapshotBuilder
from src.data_engine.coinalyze_provider import CoinalyzeHistoryProvider
from src.models import SymbolSnapshot
from src.storage.coinalyze import CoinalyzeStore
from src.storage.database import Database


class CoinalyzeLSFlowTests(unittest.TestCase):
    def test_documented_ls_history_shape_reaches_dashboard_snapshot_fields(self):
        payload = [
            {
                "symbol": "BTCUSDT_PERP.A",
                "history": [
                    {
                        "t": 1710000000,
                        "r": 1.75,
                        "l": 63.6364,
                        "s": 36.3636,
                    }
                ],
            }
        ]
        collector = CoinalyzeCollector(
            {"symbols": {"driver": "BTCUSDT", "followers": []}},
            store=SimpleNamespace(),
        )

        row = next(collector._parse_ls_history(payload))

        self.assertEqual(row["symbol"], "BTCUSDT")
        self.assertEqual(row["ls_ratio"], 1.75)
        self.assertEqual(row["ls_long"], 63.6364)
        self.assertEqual(row["ls_short"], 36.3636)

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"{tmp}/btc_radar.db")
            CoinalyzeStore(db).upsert_point(
                {
                    **row,
                    "funding_rate": 0.01,
                    "oi": 123456.0,
                }
            )

            point = CoinalyzeHistoryProvider(str(db.path)).latest("BTCUSDT")
            self.assertIsNotNone(point)
            self.assertEqual(point.ls_long, 63.6364)
            self.assertEqual(point.ls_short, 36.3636)

            snapshot = SymbolSnapshot(symbol="BTCUSDT")
            builder = SnapshotBuilder(client=SimpleNamespace(), cfg={})
            builder._apply_coinalyze(
                snapshot,
                {
                    "oi": point.oi,
                    "funding_rate": point.funding_rate * 100,
                    "ls_ratio": point.ls_ratio,
                    "ls_long": point.ls_long,
                    "ls_short": point.ls_short,
                },
            )

        self.assertEqual(snapshot.ls_posit_long, 63.6364)
        self.assertEqual(snapshot.ls_posit_short, 36.3636)
        self.assertEqual(snapshot.ls_ratio_long, 63.6364)
        self.assertEqual(snapshot.ls_ratio_short, 36.3636)
        self.assertEqual(snapshot.ls_account_long, 63.6364)
        self.assertEqual(snapshot.ls_account_short, 36.3636)
        self.assertEqual(snapshot.funding, 0.0001)
        self.assertEqual(snapshot.oi, 123456.0)


if __name__ == "__main__":
    unittest.main()
