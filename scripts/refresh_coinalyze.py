#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import time
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config_loader import load_config  # noqa: E402
from src.storage.database import Database  # noqa: E402
from src.storage.snapshots import SnapshotStore  # noqa: E402
from src.storage.coinalyze import CoinalyzeStore  # noqa: E402
from src.storage.job_status import JobStatusStore  # noqa: E402
from src.services.market_service import MarketService  # noqa: E402
from src.collectors.coinalyze_collector import CoinalyzeCollector  # noqa: E402

JOB_NAME = 'coinalyze_heavy_refresh'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    started_at = _now()
    started = time.time()
    cfg = load_config()
    db = Database(cfg.get('storage', {}).get('db_path', 'data/btc_radar.db'))
    snapshot_store = SnapshotStore(db)
    coinalyze_store = CoinalyzeStore(db)
    job_store = JobStatusStore(db)
    collector = CoinalyzeCollector(cfg, coinalyze_store)
    market = MarketService(cfg, snapshot_store, coinalyze_store=coinalyze_store, job_status_store=job_store)

    try:
        print(f'[{started_at}] START {JOB_NAME}', flush=True)
        result = market.refresh_heavy_cycle(collector)
        finished_at = _now()
        duration_ms = int((time.time() - started) * 1000)
        status = result.get('status') or ('success' if result.get('ok') else 'failed')
        rows_saved = int(result.get('rows_saved') or 0)
        job_store.record(
            JOB_NAME,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            rows_saved=rows_saved,
            duration_ms=duration_ms,
            error=result.get('error') or (result.get('coinalyze') or {}).get('error'),
            details=result,
        )
        print(f'[{finished_at}] DONE {JOB_NAME} status={status} rows_saved={rows_saved} duration_ms={duration_ms}', flush=True)
        return 0 if rows_saved > 0 else 2
    except Exception as exc:  # noqa: BLE001
        finished_at = _now()
        duration_ms = int((time.time() - started) * 1000)
        job_store.record(
            JOB_NAME,
            started_at=started_at,
            finished_at=finished_at,
            status='failed',
            rows_saved=0,
            duration_ms=duration_ms,
            error=f'{type(exc).__name__}: {exc}',
            details={},
        )
        print(f'[{finished_at}] FAILED {JOB_NAME} error={type(exc).__name__}: {exc} duration_ms={duration_ms}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
