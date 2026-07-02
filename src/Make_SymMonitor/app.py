from __future__ import annotations
from flask import Flask

from .config_loader import load_config
from .logger import get_logger
from .storage.database import Database
from .storage.snapshots import SnapshotStore
from .storage.signals import SignalStore
from .storage.trades import TradeStore
from .storage.coinalyze import CoinalyzeStore
from .services.market_service import MarketService
from .services.signal_service import SignalService
from .services.trade_service import TradeService
from .services.alert_service import AlertService
from .collectors.coinalyze_collector import CoinalyzeCollector
from .dashboard.routes import create_dashboard


def create_app() -> Flask:
    cfg = load_config()
    log = get_logger('BTCRadar')

    db = Database(cfg.get('storage', {}).get('db_path', 'data/btc_radar.db'))

    snapshot_store = SnapshotStore(db)
    signal_store = SignalStore(db)
    trade_store = TradeStore(db)
    coinalyze_store = CoinalyzeStore(db)

    market = MarketService(cfg, snapshot_store)
    signal_service = SignalService(cfg, signal_store)
    trade_service = TradeService(trade_store, market)
    alert_service = AlertService(cfg, trade_store)

    coinalyze_collector = CoinalyzeCollector(cfg, coinalyze_store)

    market.start()
    coinalyze_collector.start()

    app = Flask(
        __name__,
        template_folder='dashboard/templates',
        static_folder='dashboard/static',
    )

    app.register_blueprint(
        create_dashboard(
            market,
            signal_service,
            trade_service,
            trade_store,
            cfg,
            coinalyze_store,
            coinalyze_collector,
            alert_service,
        )
    )

    log.info('BTCRadar app created')
    return app


if __name__ == '__main__':
    cfg = load_config()
    app = create_app()
    app.run(
        host=cfg.get('app', {}).get('host', '0.0.0.0'),
        port=int(cfg.get('app', {}).get('port', 5005)),
        debug=bool(cfg.get('app', {}).get('debug', False)),
    )
