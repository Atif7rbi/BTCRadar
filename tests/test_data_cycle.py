from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from src.dashboard.routes import create_dashboard
from src.data_engine.fallback import FallbackPriceRouter
from src.data_engine.price_provider import PriceQuote
from src.models import RadarSignal, SymbolSnapshot
from src.services.market_service import MarketService


class MemorySnapshotStore:
    def __init__(self):
        self.rows = []

    def insert(self, snapshot):
        self.rows.append(snapshot)


class CycleBuilder:
    def __init__(self):
        self.heavy_calls = 0
        self.price_calls = 0
        self.prices = [101.0, 102.0, 103.0]

    def build_heavy(self, symbol):
        self.heavy_calls += 1
        return SymbolSnapshot(
            symbol=symbol,
            funding=0.0001,
            oi=12345.0,
            ls_posit_long=61.0,
            ls_posit_short=39.0,
            ls_ratio_long=61.0,
            ls_ratio_short=39.0,
            ls_account_long=61.0,
            ls_account_short=39.0,
        )

    def update_price_only(self, snapshot):
        self.price_calls += 1
        snapshot.price = self.prices.pop(0)
        snapshot.price_updated_at = f"price-{self.price_calls}"
        snapshot.updated_at = snapshot.price_updated_at
        return snapshot


class FakeCollector:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def refresh_once(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("coinalyze failed")
        return {"ok": True, "refreshed_at": "cycle-1", "rows_saved": 1}


def market_for_cycle(builder=None, collector=None):
    market = MarketService.__new__(MarketService)
    market.cfg = {
        "symbols": {"driver": "BTCUSDT", "followers": []},
        "runtime": {},
        "market_monitor": {"enabled": False},
    }
    market.symbols = ["BTCUSDT"]
    market.snapshots = {}
    market.builder = builder or CycleBuilder()
    market.store = MemorySnapshotStore()
    market.coinalyze_collector = collector
    market.log = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        exception=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )
    market.last_price_update = 0
    market.last_ls_update = 0
    market.last_ls_at = None
    market.heavy_cycle_interval = 900
    market.price_interval = 5
    market._price_updates_paused = False
    market._heavy_refresh_in_progress = False
    market._data_cycle_lock = SimpleNamespace(
        __enter__=lambda self: self,
        __exit__=lambda self, exc_type, exc, tb: False,
    )
    market._predicted_funding_cache = {}
    market._predicted_funding_cache_ts = 0
    market._coinalyze_funding_pair_cache = {}
    market._coinalyze_funding_pair_cache_ts = 0
    market._attach_cvd_15m_trend = lambda *a, **k: None
    market._maybe_record_market_monitor_snapshot = lambda *a, **k: None
    return market


class DataCycleTests(unittest.TestCase):
    def test_price_overlay_does_not_change_heavy_fields_between_cycles(self):
        builder = CycleBuilder()
        market = market_for_cycle(builder=builder)

        market.refresh_heavy_cycle()
        before = market.snapshots["BTCUSDT"].to_dict()

        market.refresh_prices()
        after = market.snapshots["BTCUSDT"].to_dict()

        self.assertEqual(after["price"], 101.0)
        for field in (
            "funding",
            "oi",
            "ls_posit_long",
            "ls_posit_short",
            "ls_ratio_long",
            "ls_ratio_short",
            "ls_account_long",
            "ls_account_short",
        ):
            self.assertEqual(after[field], before[field])

    def test_coinalyze_refresh_pauses_price_updates(self):
        builder = CycleBuilder()
        market = market_for_cycle(builder=builder)
        market.snapshots["BTCUSDT"] = builder.build_heavy("BTCUSDT")
        market._price_updates_paused = True

        market.refresh_prices()

        self.assertEqual(builder.price_calls, 0)
        self.assertIsNone(market.snapshots["BTCUSDT"].price)

    def test_coinalyze_failure_keeps_previous_heavy_snapshot(self):
        builder = CycleBuilder()
        market = market_for_cycle(builder=builder, collector=FakeCollector(fail=True))
        market.snapshots["BTCUSDT"] = builder.build_heavy("BTCUSDT")
        before = market.snapshots["BTCUSDT"].to_dict()

        with self.assertRaises(RuntimeError):
            market.refresh_heavy_cycle()

        self.assertEqual(market.snapshots["BTCUSDT"].to_dict(), before)


@dataclass
class FakeProvider:
    name: str
    prices: list[float]
    fail: bool = False

    def price(self, symbol):
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        return PriceQuote(symbol=symbol, price=self.prices.pop(0), provider=self.name)

    def candles(self, symbol, interval="1m", limit=120):
        return []


class RoundRobinPriceTests(unittest.TestCase):
    def test_price_router_rotates_and_falls_back_immediately(self):
        okx = FakeProvider("okx", [100.0], fail=True)
        coinbase = FakeProvider("coinbase", [101.0])
        kraken = FakeProvider("kraken", [102.0])
        router = FallbackPriceRouter([okx, coinbase, kraken], cache_ttl_sec=0)

        first = router.price("BTCUSDT")
        second = router.price("BTCUSDT")

        self.assertEqual(first.provider, "coinbase")
        self.assertEqual(second.provider, "kraken")
        self.assertEqual(
            [a.provider for a in router.last_attempts["BTCUSDT"]],
            ["kraken"],
        )


class ApiStateNoHeavyRefreshTests(unittest.TestCase):
    def test_api_state_does_not_call_market_refresh_or_coinalyze(self):
        market = SimpleNamespace(
            snapshots={"BTCUSDT": SymbolSnapshot(symbol="BTCUSDT", price=100.0, funding=0.0001)},
            last_ls_at="cycle-1",
            status=lambda: {},
            followers_consensus=lambda: {},
            refresh_if_needed=lambda *a, **k: (_ for _ in ()).throw(AssertionError("refresh called")),
        )
        signal_service = SimpleNamespace(
            analyze=lambda snapshots: RadarSignal(
                state="WAIT",
                recommendation="WAIT",
                score=0,
                spread=0,
                long_votes=0,
                short_votes=0,
                created_at="now",
            ),
            score_followers=lambda followers, sig: followers,
            spread_trend=lambda: None,
        )
        trade_service = SimpleNamespace(sync_pnl=lambda: [])
        trade_store = SimpleNamespace(
            open_trades=lambda: [],
            closed_trades=lambda limit: [],
            stats=lambda initial: {},
        )
        collector = SimpleNamespace(refresh_once=lambda: (_ for _ in ()).throw(AssertionError("coinalyze called")))
        app = create_dashboard(
            market,
            signal_service,
            trade_service,
            trade_store,
            {"symbols": {"driver": "BTCUSDT", "followers": []}, "account": {"initial_equity_usd": 1000}},
            coinalyze_collector=collector,
        )

        from flask import Flask

        flask_app = Flask(__name__)
        flask_app.register_blueprint(app)

        response = flask_app.test_client().get("/api/state")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["btc"]["price"], 100.0)


if __name__ == "__main__":
    unittest.main()
