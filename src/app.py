from __future__ import annotations
import os
from flask import Flask

from .config_loader import load_config
from .logger import get_logger
from .storage.database import Database
from .storage.snapshots import SnapshotStore
from .storage.signals import SignalStore
from .storage.trades import TradeStore
from .storage.coinalyze import CoinalyzeStore
from .storage.job_status import JobStatusStore
from .services.market_service import MarketService
from .services.signal_service import SignalService
from .services.trade_service import TradeService
from .services.alert_service import AlertService
from .services.trade_lifecycle import TradeLifecycleService
from .collectors.coinalyze_collector import CoinalyzeCollector
from .dashboard.routes import create_dashboard


def _app_port(cfg: dict) -> int:
    env_port = os.getenv('BTCRADAR_PORT')
    if env_port:
        return int(env_port)
    return int(cfg.get('app', {}).get('port', 5005))


def create_app() -> Flask:
    cfg = load_config()
    log = get_logger('BTCRadar')

    db = Database(cfg.get('storage', {}).get('db_path', 'data/btc_radar.db'))

    snapshot_store = SnapshotStore(db)
    signal_store = SignalStore(db)
    trade_store = TradeStore(db)
    coinalyze_store = CoinalyzeStore(db)
    job_status_store = JobStatusStore(db)

    market = MarketService(cfg, snapshot_store, coinalyze_store=coinalyze_store, job_status_store=job_status_store)
    signal_service = SignalService(cfg, signal_store)
    trade_service = TradeService(trade_store, market)
    alert_service = AlertService(cfg, trade_store)
    trade_lifecycle = TradeLifecycleService(trade_store, market, cfg)

    coinalyze_collector = CoinalyzeCollector(cfg, coinalyze_store)

    # Passenger/shared hosting must not depend on daemon collector threads.
    # Cron owns Coinalyze refresh. Flask only loads cached snapshots and serves requests.
    market.start()

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
            trade_lifecycle,
            job_status_store,
        )
    )

    log.info('BTCRadar app created')
    return app


if __name__ == '__main__':
    cfg = load_config()
    app = create_app()
    app.run(
        host=cfg.get('app', {}).get('host', '0.0.0.0'),
        port=_app_port(cfg),
        debug=bool(cfg.get('app', {}).get('debug', False)),
    )
