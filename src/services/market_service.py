from __future__ import annotations
import threading, time
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict, deque
from ..config_loader import get_absolute_db_path
from ..data_engine.price_provider import PriceRouter
from ..collectors.snapshot_builder import SnapshotBuilder
from ..models import SymbolSnapshot
from ..storage.snapshots import SnapshotStore
from ..logger import get_logger


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _classify_cvd_trend(delta):
    d = _safe_float(delta)
    if d is None:
        return None
    if d > 0:
        return 'RISING'
    if d < 0:
        return 'FALLING'
    return 'FLAT'



def _funding_value(snapshot, *names):
    """Read current/predicted funding from a SymbolSnapshot defensively.

    Different collectors may name predicted funding differently. This keeps the
    consensus layer passive and compatible with older snapshots.
    """
    for name in names:
        v = _safe_float(getattr(snapshot, name, None)) if snapshot else None
        if v is not None:
            return v
    return None


def _score_state(score: int) -> str:
    if score >= 100:
        return 'EXTREME'
    if score >= 75:
        return 'HIGH'
    if score >= 50:
        return 'MODERATE'
    if score >= 25:
        return 'LOW'
    return 'NONE'


def _funding_agreement(current, predicted, threshold: float) -> str:
    cur = _safe_float(current)
    nxt = _safe_float(predicted)
    if cur is None or nxt is None:
        return 'UNKNOWN'
    if cur >= threshold and nxt >= threshold:
        return 'POSITIVE_STRONG'
    if cur <= -threshold and nxt <= -threshold:
        return 'NEGATIVE_STRONG'
    if cur > 0 and nxt > 0:
        return 'POSITIVE_WEAK'
    if cur < 0 and nxt < 0:
        return 'NEGATIVE_WEAK'
    if cur > 0 and nxt < 0:
        return 'POS_TO_NEG'
    if cur < 0 and nxt > 0:
        return 'NEG_TO_POS'
    return 'MIXED'


def _symbol_consensus(symbol: str, snapshot, threshold_ls: float, threshold_funding: float) -> dict:
    current_funding = _funding_value(snapshot, 'funding')
    next_funding = _funding_value(
        snapshot,
        'predicted_funding',
        'predicted_funding_rate',
        'next_funding',
        'next_funding_rate',
        'funding_next',
        'funding_predicted',
    )
    long_ls = _safe_float(getattr(snapshot, 'ls_posit_long', None)) if snapshot else None
    short_ls = _safe_float(getattr(snapshot, 'ls_posit_short', None)) if snapshot else None

    short_ok = (
        long_ls is not None and long_ls >= threshold_ls and
        current_funding is not None and current_funding >= threshold_funding and
        next_funding is not None and next_funding >= threshold_funding
    )
    long_ok = (
        short_ls is not None and short_ls >= threshold_ls and
        current_funding is not None and current_funding <= -threshold_funding and
        next_funding is not None and next_funding <= -threshold_funding
    )

    return {
        'symbol': str(symbol or '').upper(),
        'short_score': 25 if short_ok else 0,
        'long_score': 25 if long_ok else 0,
        'short_ok': bool(short_ok),
        'long_ok': bool(long_ok),
        'ls_posit_long': long_ls,
        'ls_posit_short': short_ls,
        'current_funding': current_funding,
        'next_funding': next_funding,
        'funding_agreement': _funding_agreement(current_funding, next_funding, threshold_funding),
    }


class MarketService:
    def __init__(self, cfg: dict, snapshot_store: SnapshotStore, coinalyze_store=None, job_status_store=None):
        self.cfg = cfg
        self.log = get_logger('BTCRadar.MarketService')
        self.client = None  # Hosting mode: no direct Binance client; Coinalyze/SQLite fallback only.
        self.builder = SnapshotBuilder(self.client, cfg)
        self.store = snapshot_store
        self.coinalyze_store = coinalyze_store
        self.job_status_store = job_status_store
        provider_cfg = (cfg.get('price_providers') or {}) if isinstance(cfg, dict) else {}
        self.price_router = PriceRouter(
            timeout=int(provider_cfg.get('timeout_sec', cfg.get('runtime', {}).get('api_timeout_sec', 3))),
            priority=list(provider_cfg.get('priority', ['okx', 'coinbase', 'kraken'])),
        )
        self.price_interval = int(cfg.get('runtime', {}).get('price_refresh_sec', 60))
        self.ls_interval = int(cfg.get('runtime', {}).get('ls_refresh_sec', 300))
        self.symbols = [cfg['symbols']['driver']] + list(cfg['symbols'].get('followers', []))
        self.snapshots: dict[str, SymbolSnapshot] = {}
        self.last_price_update: float = 0
        self.last_ls_update: float = 0
        self.cvd_trend_window_sec = int(cfg.get('runtime', {}).get('cvd_trend_window_sec', 900))
        self._cvd_history: dict[str, deque[tuple[float, float]]] = defaultdict(deque)
        self._stop = False
        self._thread: threading.Thread | None = None
        self.db_path = self._resolve_db_path()
        self._predicted_funding_cache: dict[str, float | None] = {}
        self._predicted_funding_cache_ts: float = 0
        self._coinalyze_funding_pair_cache: dict[str, tuple[float | None, float | None]] = {}
        self._coinalyze_funding_pair_cache_ts: float = 0
        self.market_monitor_cfg = self.cfg.get('market_monitor', {}) if isinstance(self.cfg, dict) else {}
        self.market_monitor_enabled = bool(self.market_monitor_cfg.get('enabled', True))
        self.market_monitor_interval_sec = int(self.market_monitor_cfg.get('snapshot_interval_minutes', 60)) * 60
        self._last_market_monitor_snapshot_hour: str | None = None
        self._ensure_market_monitor_schema()


    def _resolve_db_path(self) -> str:
        """Resolve DB path in the same project-root anchored way as Database."""
        return get_absolute_db_path(self.cfg)

    @staticmethod
    def _normalize_coinalyze_funding(value):
        """Convert Coinalyze funding percent units into decimal rate units.

        Coinalyze history values are stored as displayed percentages, e.g.
        -0.01537 means -0.01537%. The dashboard fmtFunding() expects decimal
        rate units, e.g. -0.0001537, because it multiplies by 100 for display.
        """
        v = _safe_float(value)
        if v is None:
            return None
        return v / 100.0

    def _latest_predicted_funding_from_db(self, symbol: str):
        sym = str(symbol or '').upper()
        if not sym:
            return None

        db_file = Path(self.db_path)
        if not db_file.exists():
            return None

        try:
            with sqlite3.connect(str(db_file)) as conn:
                row = conn.execute(
                    """
                    SELECT predicted_funding_rate
                    FROM btc_radar_coinalyze_history
                    WHERE symbol = ?
                      AND predicted_funding_rate IS NOT NULL
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (sym,),
                ).fetchone()
        except Exception as e:
            self.log.debug('predicted funding lookup failed for %s: %s', sym, e)
            return None

        if not row:
            return None

        return self._normalize_coinalyze_funding(row[0])

    def _latest_coinalyze_funding_pair_from_db(self, symbol: str) -> tuple[float | None, float | None]:
        """Return latest stored Coinalyze current+predicted funding as decimal rates.

        This is used by Market Monitor so Current F and Next F come from the
        same Coinalyze hourly row instead of accidentally duplicating the same
        snapshot-side value in both columns.
        """
        sym = str(symbol or '').upper()
        if not sym:
            return None, None

        db_file = Path(self.db_path)
        if not db_file.exists():
            return None, None

        try:
            with sqlite3.connect(str(db_file)) as conn:
                row = conn.execute(
                    """
                    SELECT funding_rate, predicted_funding_rate
                    FROM btc_radar_coinalyze_history
                    WHERE symbol = ?
                      AND (funding_rate IS NOT NULL OR predicted_funding_rate IS NOT NULL)
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (sym,),
                ).fetchone()
        except Exception as e:
            self.log.debug('coinalyze funding pair lookup failed for %s: %s', sym, e)
            return None, None

        if not row:
            return None, None

        return (
            self._normalize_coinalyze_funding(row[0]),
            self._normalize_coinalyze_funding(row[1]),
        )

    def _latest_coinalyze_funding_pair(self, symbol: str) -> tuple[float | None, float | None]:
        now_ts = time.time()
        if now_ts - self._coinalyze_funding_pair_cache_ts > 30:
            self._coinalyze_funding_pair_cache = {}
            self._coinalyze_funding_pair_cache_ts = now_ts

        sym = str(symbol or '').upper()
        if sym not in self._coinalyze_funding_pair_cache:
            self._coinalyze_funding_pair_cache[sym] = self._latest_coinalyze_funding_pair_from_db(sym)

        return self._coinalyze_funding_pair_cache.get(sym, (None, None))

    def _latest_predicted_funding(self, symbol: str):
        """Return latest predicted funding with a short cache to avoid DB spam."""
        now_ts = time.time()
        if now_ts - self._predicted_funding_cache_ts > 30:
            self._predicted_funding_cache = {}
            self._predicted_funding_cache_ts = now_ts

        sym = str(symbol or '').upper()
        if sym not in self._predicted_funding_cache:
            self._predicted_funding_cache[sym] = self._latest_predicted_funding_from_db(sym)

        return self._predicted_funding_cache.get(sym)

    def _attach_next_funding(self, symbol: str, snapshot: SymbolSnapshot):
        """Attach next/predicted funding to snapshots for Followers Consensus.

        This is passive research data only. It does not change BTC score,
        Follow Score, recommendation, entry, or exit logic.
        """
        next_funding = self._latest_predicted_funding(symbol)
        if next_funding is None:
            return

        # Expose several aliases because both Python services and app.js read
        # these fields defensively under different names.
        setattr(snapshot, 'predicted_funding_rate', next_funding)
        setattr(snapshot, 'predicted_funding', next_funding)
        setattr(snapshot, 'next_funding_rate', next_funding)
        setattr(snapshot, 'next_funding', next_funding)

    def start(self):
        """Start local-development refresh loop only when explicitly enabled.

        On Passenger/shared hosting, Coinalyze is owned by Cron and Flask must
        not depend on daemon threads for correctness.
        """
        enabled = bool(self.cfg.get('runtime', {}).get('background_services_enabled', False))
        if not enabled:
            self.bootstrap_from_cache()
            self.log.info('Market background loop disabled; serving from SQLite/cache')
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        self.log.info('Market service started')
        while not self._stop:
            now_ts = time.time()
            try:
                if not self.snapshots or now_ts - self.last_ls_update >= self.ls_interval:
                    self.refresh_full()
                elif now_ts - self.last_price_update >= self.price_interval:
                    self.refresh_prices()
            except Exception as e:
                self.log.exception('Market refresh failed: %s', e)
            time.sleep(1)

    def bootstrap_from_cache(self) -> None:
        """Load latest persisted snapshots from SQLite into runtime memory."""
        loaded = 0
        for sym in self.symbols:
            row = self.store.latest(sym)
            if not row:
                continue
            snap = self._snapshot_from_row(row)
            self.snapshots[sym] = snap
            loaded += 1
            if snap.price_updated_at:
                try:
                    self.last_price_update = max(self.last_price_update, datetime.fromisoformat(str(snap.price_updated_at).replace('Z', '+00:00')).timestamp())
                except Exception:
                    pass
            if snap.ls_updated_at:
                try:
                    self.last_ls_update = max(self.last_ls_update, datetime.fromisoformat(str(snap.ls_updated_at).replace('Z', '+00:00')).timestamp())
                except Exception:
                    pass
        if loaded:
            self.log.info('Loaded %s snapshots from SQLite cache', loaded)

    def _snapshot_from_row(self, row: dict) -> SymbolSnapshot:
        allowed = set(SymbolSnapshot.__dataclass_fields__.keys())
        payload = {k: row.get(k) for k in allowed if k in row}
        payload['symbol'] = str(payload.get('symbol') or row.get('symbol')).upper()
        payload['updated_at'] = payload.get('updated_at') or ''
        return SymbolSnapshot(**payload)

    def _snapshot_from_coinalyze_row(self, symbol: str, row: dict, previous: SymbolSnapshot | None = None) -> SymbolSnapshot:
        now = datetime.now(timezone.utc).isoformat()
        snap = previous or SymbolSnapshot(symbol=symbol, updated_at=now)
        snap.symbol = symbol
        snap.updated_at = now
        # Keep latest displayed price if one exists; price overlay can update it later.
        snap.price = getattr(previous, 'price', None) if previous else None
        snap.price_updated_at = getattr(previous, 'price_updated_at', None) if previous else None
        # Coinalyze funding is stored as displayed percent; dashboard expects decimal rate.
        snap.funding = self._normalize_coinalyze_funding(row.get('funding_rate'))
        predicted = self._normalize_coinalyze_funding(row.get('predicted_funding_rate'))
        if predicted is not None:
            setattr(snap, 'predicted_funding_rate', predicted)
            setattr(snap, 'predicted_funding', predicted)
            setattr(snap, 'next_funding_rate', predicted)
            setattr(snap, 'next_funding', predicted)
        snap.oi = _safe_float(row.get('oi'))
        ls_long = _safe_float(row.get('ls_long'))
        ls_short = _safe_float(row.get('ls_short'))
        ls_ratio = _safe_float(row.get('ls_ratio'))
        snap.ls_posit_long = ls_long
        snap.ls_posit_short = ls_short
        # Compatibility: dashboard has three LS layers; Coinalyze currently supplies one LS source.
        snap.ls_ratio_long = ls_long
        snap.ls_ratio_short = ls_short
        snap.ls_account_long = ls_long
        snap.ls_account_short = ls_short
        if ls_ratio is not None:
            setattr(snap, 'coinalyze_ls_ratio', ls_ratio)
        snap.ls_updated_at = now
        return snap

    def refresh_price_overlay_if_needed(self, *, force: bool = False) -> None:
        """Lightweight price-only refresh for Flask requests.

        This never calls Coinalyze and never rebuilds heavy snapshots.
        """
        now_ts = time.time()
        if not force and self.last_price_update and (now_ts - self.last_price_update) < self.price_interval:
            return
        if not self.snapshots:
            self.bootstrap_from_cache()
        preferred = self.price_router.next_tick_provider()
        for sym in self.symbols:
            snap = self.snapshots.get(sym) or SymbolSnapshot(symbol=sym, updated_at='')
            try:
                snap.price = self.price_router.price(sym, preferred=preferred)
                ts = datetime.now(timezone.utc).isoformat()
                snap.price_updated_at = ts
                snap.updated_at = ts
                self.snapshots[sym] = snap
            except Exception as exc:  # noqa: BLE001
                self.log.warning('price overlay failed for %s: %s', sym, exc)
        self.last_price_update = time.time()
    def refresh_heavy_cycle(self, coinalyze_collector=None) -> dict:
        """One-shot heavy cycle for Cron.

        Fetch Coinalyze, build dashboard-ready snapshots from SQLite, persist
        them, and return a summary. This method does not start any background
        loop and does not fetch live prices.
        """
        collector = coinalyze_collector
        if collector is None:
            raise RuntimeError('Coinalyze collector is required for heavy cycle')
        if not self.coinalyze_store:
            raise RuntimeError('Coinalyze store is required for heavy cycle')
        started = time.time()
        previous = dict(self.snapshots)
        result = collector.refresh_once()
        rows = self.coinalyze_store.latest_by_symbols(self.symbols)
        by_symbol = {str(r.get('symbol')).upper(): r for r in rows}
        built = 0
        for sym in self.symbols:
            row = by_symbol.get(sym.upper())
            if not row:
                continue
            snap = self._snapshot_from_coinalyze_row(sym.upper(), row, previous.get(sym))
            self._attach_cvd_15m_trend(sym, snap, record=True)
            self.snapshots[sym] = snap
            self.store.insert(snap)
            built += 1
        self._maybe_record_market_monitor_snapshot()
        now_ts = time.time()
        self.last_ls_update = now_ts
        return {
            'ok': built > 0,
            'status': 'success' if built > 0 and result.get('ok') else 'partial_success' if built > 0 else 'failed',
            'rows_saved': int(result.get('rows_saved') or 0),
            'snapshots_built': built,
            'duration_ms': int((time.time() - started) * 1000),
            'coinalyze': result,
        }

    def refresh_full(self):
        for sym in self.symbols:
            try:
                s = self.builder.build_full(sym)
                self._attach_next_funding(sym, s)
                self._attach_cvd_15m_trend(sym, s, record=True)
                self.snapshots[sym] = s
                self.store.insert(s)
            except Exception as e:
                self.log.warning('full refresh failed for %s: %s', sym, e)
        self._maybe_record_market_monitor_snapshot()
        self.last_ls_update = time.time()
        self.last_price_update = self.last_ls_update

    def refresh_prices(self):
        self.refresh_price_overlay_if_needed(force=True)

    def _attach_cvd_15m_trend(self, symbol: str, snapshot: SymbolSnapshot, *, record: bool):
        """Attach CVD 15m comparison to a snapshot without changing trading logic.

        The comparison is per-symbol, so BTC, ETH, SOL, DOGE and XRP are each
        compared against their own historical CVD value instead of using one
        shared raw threshold.
        """
        sym = str(symbol or '').upper()
        now_ts = time.time()
        cvd = _safe_float(getattr(snapshot, 'cvd', None))

        history = self._cvd_history[sym]
        cutoff = now_ts - max(self.cvd_trend_window_sec * 4, 3600)
        while history and history[0][0] < cutoff:
            history.popleft()

        previous_cvd = self._cvd_value_at_or_before(sym, now_ts - self.cvd_trend_window_sec)
        delta = None
        if cvd is not None and previous_cvd is not None:
            delta = round(cvd - previous_cvd, 4)

        setattr(snapshot, 'cvd_15m_ago', previous_cvd)
        setattr(snapshot, 'cvd_delta_15m', delta)
        setattr(snapshot, 'cvd_trend', _classify_cvd_trend(delta))

        if record and cvd is not None:
            # Avoid duplicating identical full-refresh CVD samples at the same timestamp window.
            if not history or history[-1][1] != cvd:
                history.append((now_ts, cvd))

    def _cvd_value_at_or_before(self, symbol: str, target_ts: float):
        history = self._cvd_history.get(str(symbol or '').upper()) or []
        candidate = None
        for ts, value in history:
            if ts <= target_ts:
                candidate = value
            else:
                break
        return candidate


    def _ensure_market_monitor_schema(self) -> None:
        """Create the independent Market Monitor table if the main DB migration has not run yet."""
        try:
            db_file = Path(self.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS btc_radar_market_monitor_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        snapshot_hour TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        session TEXT,
                        symbol TEXT NOT NULL,
                        is_driver INTEGER DEFAULT 0,
                        price REAL,
                        price_change_1h_pct REAL,
                        price_change_4h_pct REAL,
                        price_change_24h_pct REAL,
                        btc_price REAL,
                        btc_change_1h_pct REAL,
                        btc_change_4h_pct REAL,
                        btc_change_24h_pct REAL,
                        reaction_ratio_1h REAL,
                        reaction_ratio_4h REAL,
                        reaction_ratio_24h REAL,
                        reaction_direction_1h TEXT,
                        ls_posit_long REAL,
                        ls_posit_short REAL,
                        ls_ratio_long REAL,
                        ls_ratio_short REAL,
                        ls_account_long REAL,
                        ls_account_short REAL,
                        funding REAL,
                        next_funding REAL,
                        oi REAL,
                        cvd REAL,
                        cvd_delta_15m REAL,
                        cvd_trend TEXT,
                        crowding_side TEXT,
                        agreement_with_btc TEXT,
                        btc_link_strength TEXT,
                        session_phase TEXT,
                        hypothesis_tags TEXT,
                        raw_json TEXT,
                        UNIQUE(snapshot_hour, symbol)
                    )
                    """
                )

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS btc_radar_market_daily_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        day TEXT NOT NULL UNIQUE,
                        generated_at TEXT NOT NULL,
                        snapshot_hours INTEGER DEFAULT 0,
                        sessions_json TEXT,
                        btc_day_change_pct REAL,
                        story TEXT,
                        summary_json TEXT,
                        timeline_json TEXT,
                        hypothesis_json TEXT,
                        raw_json TEXT
                    )
                    """
                )
                # Existing databases created by V1 need additive migrations.
                existing = {r[1] for r in conn.execute('PRAGMA table_info(btc_radar_market_monitor_snapshots)').fetchall()}
                extra_cols = {
                    'price_change_4h_pct': 'REAL',
                    'price_change_24h_pct': 'REAL',
                    'btc_change_4h_pct': 'REAL',
                    'btc_change_24h_pct': 'REAL',
                    'reaction_ratio_4h': 'REAL',
                    'reaction_ratio_24h': 'REAL',
                    'reaction_direction_1h': 'TEXT',
                    'btc_link_strength': 'TEXT',
                    'session_phase': 'TEXT',
                    'hypothesis_tags': 'TEXT',
                }
                for col, typ in extra_cols.items():
                    if col not in existing:
                        conn.execute(f'ALTER TABLE btc_radar_market_monitor_snapshots ADD COLUMN {col} {typ}')
                conn.commit()
        except Exception as e:
            self.log.debug('market monitor schema init failed: %s', e)

    def _market_monitor_symbols(self) -> list[str]:
        configured = self.market_monitor_cfg.get('symbols') or []
        if configured:
            symbols = [str(x).upper() for x in configured]
        else:
            symbols = [self.cfg['symbols']['driver']] + list(self.cfg.get('symbols', {}).get('followers', []))
        out = []
        for sym in symbols:
            if sym and sym not in out:
                out.append(sym)
        return out

    def _session_label(self, dt: datetime | None = None) -> str:
        """Return active trading session labels using KSA session definitions."""
        dt = dt or datetime.now(timezone.utc)
        ksa = dt.astimezone(timezone(timedelta(hours=3)))
        hour = ksa.hour + ksa.minute / 60.0
        sessions = self.market_monitor_cfg.get('sessions_ksa') or {
            'tokyo': [3, 12],
            'london': [11, 20],
            'new_york': [16, 1],
        }

        active = []
        for name, window in sessions.items():
            try:
                start, end = float(window[0]), float(window[1])
            except Exception:
                continue
            if start <= end:
                ok = start <= hour < end
            else:
                ok = hour >= start or hour < end
            if ok:
                active.append(str(name).replace('_', ' ').title())

        return ' + '.join(active) if active else 'Off Session'

    def _session_phase_label(self, dt: datetime | None = None) -> str:
        """Describe where the current time sits relative to major KSA sessions."""
        dt = dt or datetime.now(timezone.utc)
        ksa = dt.astimezone(timezone(timedelta(hours=3)))
        minute_of_day = ksa.hour * 60 + ksa.minute
        opens = {
            'Tokyo Open': 3 * 60,
            'London Open': 11 * 60,
            'New York Open': 16 * 60,
        }
        for label, open_min in opens.items():
            diff = minute_of_day - open_min
            if 0 <= diff < 60:
                return f'{label} +{diff}m'
            if -60 <= diff < 0:
                return f'{label} {diff}m'
        session = self._session_label(dt)
        return session

    def _funding_sign_label(self, value) -> str:
        v = _safe_float(value)
        if v is None:
            return 'UNKNOWN'
        if v > 0:
            return 'POSITIVE'
        if v < 0:
            return 'NEGATIVE'
        return 'NEUTRAL'

    def _crowding_side(self, snapshot) -> str:
        long_ls = _safe_float(getattr(snapshot, 'ls_posit_long', None)) if snapshot else None
        short_ls = _safe_float(getattr(snapshot, 'ls_posit_short', None)) if snapshot else None
        threshold = float(self.market_monitor_cfg.get('crowding_threshold', 65.0))
        if long_ls is None or short_ls is None:
            return 'UNKNOWN'
        if long_ls >= threshold:
            return 'LONG_CROWDED'
        if short_ls >= threshold:
            return 'SHORT_CROWDED'
        if long_ls > short_ls:
            return 'LONG_LEAN'
        if short_ls > long_ls:
            return 'SHORT_LEAN'
        return 'NEUTRAL'

    def _snapshot_row(self, symbol: str, snapshot, btc_snapshot=None) -> dict:
        self._attach_next_funding(symbol, snapshot) if snapshot is not None else None
        price = _safe_float(getattr(snapshot, 'price', None)) if snapshot else None
        btc_price = _safe_float(getattr(btc_snapshot, 'price', None)) if btc_snapshot else None

        db_current_funding, db_next_funding = self._latest_coinalyze_funding_pair(symbol)
        snapshot_current_funding = _funding_value(snapshot, 'funding')
        snapshot_next_funding = _funding_value(snapshot, 'next_funding', 'next_funding_rate', 'predicted_funding_rate', 'predicted_funding')
        current_funding = db_current_funding if db_current_funding is not None else snapshot_current_funding
        next_funding = db_next_funding if db_next_funding is not None else snapshot_next_funding

        return {
            'symbol': str(symbol or '').upper(),
            'price': price,
            'ls_posit_long': _safe_float(getattr(snapshot, 'ls_posit_long', None)) if snapshot else None,
            'ls_posit_short': _safe_float(getattr(snapshot, 'ls_posit_short', None)) if snapshot else None,
            'ls_ratio_long': _safe_float(getattr(snapshot, 'ls_ratio_long', None)) if snapshot else None,
            'ls_ratio_short': _safe_float(getattr(snapshot, 'ls_ratio_short', None)) if snapshot else None,
            'ls_account_long': _safe_float(getattr(snapshot, 'ls_account_long', None)) if snapshot else None,
            'ls_account_short': _safe_float(getattr(snapshot, 'ls_account_short', None)) if snapshot else None,
            'funding': current_funding,
            'next_funding': next_funding,
            'oi': _safe_float(getattr(snapshot, 'oi', None)) if snapshot else None,
            'vwap': _safe_float(getattr(snapshot, 'vwap', None)) if snapshot else None,
            'cvd': _safe_float(getattr(snapshot, 'cvd', None)) if snapshot else None,
            'cvd_delta_15m': _safe_float(getattr(snapshot, 'cvd_delta_15m', None)) if snapshot else None,
            'cvd_trend': getattr(snapshot, 'cvd_trend', None) if snapshot else None,
            'crowding_side': self._crowding_side(snapshot),
            'funding_sign': self._funding_sign_label(current_funding),
            'next_funding_sign': self._funding_sign_label(next_funding),
            'btc_price': btc_price,
        }

    def _latest_hour_record(self, symbol: str, before_iso: str | None = None) -> dict | None:
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                if before_iso:
                    row = conn.execute(
                        """
                        SELECT * FROM btc_radar_market_monitor_snapshots
                        WHERE symbol = ? AND snapshot_hour <= ?
                        ORDER BY snapshot_hour DESC
                        LIMIT 1
                        """,
                        (symbol, before_iso),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT * FROM btc_radar_market_monitor_snapshots
                        WHERE symbol = ?
                        ORDER BY snapshot_hour DESC
                        LIMIT 1
                        """,
                        (symbol,),
                    ).fetchone()
                return dict(row) if row else None
        except Exception:
            return None

    def _percent_change(self, current, previous):
        cur = _safe_float(current)
        prev = _safe_float(previous)
        if cur is None or prev in (None, 0):
            return None
        return round(((cur - prev) / prev) * 100.0, 4)

    def _reaction_ratio(self, follower_change, btc_change):
        f = _safe_float(follower_change)
        b = _safe_float(btc_change)
        if f is None or b in (None, 0):
            return None
        return round(abs(f) / abs(b), 3)

    def _reaction_direction(self, follower_change, btc_change) -> str:
        f = _safe_float(follower_change)
        b = _safe_float(btc_change)
        if f is None or b is None or abs(f) < 0.0001 or abs(b) < 0.0001:
            return 'WAITING'
        return 'SAME' if (f > 0 and b > 0) or (f < 0 and b < 0) else 'INVERSE'

    def _btc_link_strength(self, row: dict) -> str:
        if row.get('is_driver'):
            return 'DRIVER'
        direction = row.get('reaction_direction_1h')
        ratio = _safe_float(row.get('reaction_ratio_1h'))
        if direction == 'INVERSE':
            return 'INVERSE'
        if direction != 'SAME' or ratio is None:
            return 'WAITING'
        if ratio >= 1.75:
            return 'STRONG'
        if ratio >= 0.75:
            return 'MEDIUM'
        return 'WEAK'

    def _market_monitor_rows(self) -> list[dict]:
        driver = str(self.cfg.get('symbols', {}).get('driver', 'BTCUSDT')).upper()
        btc_snapshot = self.snapshots.get(driver)
        now = datetime.now(timezone.utc)
        before_1h = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0).isoformat()
        before_4h = (now - timedelta(hours=4)).replace(minute=0, second=0, microsecond=0).isoformat()
        before_24h = (now - timedelta(hours=24)).replace(minute=0, second=0, microsecond=0).isoformat()
        btc_prev_1h = self._latest_hour_record(driver, before_1h)
        btc_prev_4h = self._latest_hour_record(driver, before_4h)
        btc_prev_24h = self._latest_hour_record(driver, before_24h)
        btc_current_price = _safe_float(getattr(btc_snapshot, 'price', None)) if btc_snapshot else None
        btc_change_1h = self._percent_change(btc_current_price, btc_prev_1h.get('price') if btc_prev_1h else None)
        btc_change_4h = self._percent_change(btc_current_price, btc_prev_4h.get('price') if btc_prev_4h else None)
        btc_change_24h = self._percent_change(btc_current_price, btc_prev_24h.get('price') if btc_prev_24h else None)

        rows = []
        btc_side = self._crowding_side(btc_snapshot)
        for symbol in self._market_monitor_symbols():
            snapshot = self.snapshots.get(symbol)
            row = self._snapshot_row(symbol, snapshot, btc_snapshot)
            prev_1h = self._latest_hour_record(symbol, before_1h)
            prev_4h = self._latest_hour_record(symbol, before_4h)
            prev_24h = self._latest_hour_record(symbol, before_24h)
            row['price_change_1h_pct'] = self._percent_change(row.get('price'), prev_1h.get('price') if prev_1h else None)
            row['price_change_4h_pct'] = self._percent_change(row.get('price'), prev_4h.get('price') if prev_4h else None)
            row['price_change_24h_pct'] = self._percent_change(row.get('price'), prev_24h.get('price') if prev_24h else None)
            row['btc_change_1h_pct'] = btc_change_1h
            row['btc_change_4h_pct'] = btc_change_4h
            row['btc_change_24h_pct'] = btc_change_24h
            row['reaction_ratio_1h'] = self._reaction_ratio(row.get('price_change_1h_pct'), btc_change_1h)
            row['reaction_ratio_4h'] = self._reaction_ratio(row.get('price_change_4h_pct'), btc_change_4h)
            row['reaction_ratio_24h'] = self._reaction_ratio(row.get('price_change_24h_pct'), btc_change_24h)
            row['reaction_direction_1h'] = 'DRIVER' if symbol == driver else self._reaction_direction(row.get('price_change_1h_pct'), btc_change_1h)
            row['is_driver'] = 1 if symbol == driver else 0
            row['agreement_with_btc'] = 'DRIVER' if symbol == driver else ('AGREE' if row.get('crowding_side') == btc_side else 'DIVERGE')
            row['btc_link_strength'] = self._btc_link_strength(row)
            row['session_phase'] = self._session_phase_label(now)
            row['hypothesis_tags'] = self._row_hypothesis_tags(row, btc_side)
            rows.append(row)
        return rows

    def _row_hypothesis_tags(self, row: dict, btc_side: str) -> list[str]:
        tags: list[str] = []
        side = str(row.get('crowding_side') or '')
        if side.startswith('LONG'):
            tags.append('LONG_BIAS')
        if side == 'LONG_CROWDED':
            tags.append('LONG_CROWDED')
        if side.startswith('SHORT'):
            tags.append('SHORT_BIAS')
        if row.get('funding_sign') != row.get('next_funding_sign'):
            tags.append('FUNDING_TRANSITION')
        if side.startswith('LONG') and row.get('funding_sign') == 'NEGATIVE':
            tags.append('LONG_FUNDING_DIVERGENCE')
        if not row.get('is_driver') and row.get('crowding_side') != btc_side:
            tags.append('BTC_DIVERGENCE')
        if (row.get('reaction_ratio_1h') or 0) >= 1.75:
            tags.append('FAST_REACTOR')
        return tags

    def _market_monitor_summary(self, rows: list[dict]) -> dict:
        followers = [r for r in rows if not r.get('is_driver')]
        long_like = sum(1 for r in followers if str(r.get('crowding_side')) in ('LONG_CROWDED', 'LONG_LEAN'))
        short_like = sum(1 for r in followers if str(r.get('crowding_side')) in ('SHORT_CROWDED', 'SHORT_LEAN'))
        long_crowded = sum(1 for r in followers if r.get('crowding_side') == 'LONG_CROWDED')
        short_crowded = sum(1 for r in followers if r.get('crowding_side') == 'SHORT_CROWDED')
        neutral = sum(1 for r in followers if r.get('crowding_side') == 'NEUTRAL')
        funding_pos = sum(1 for r in followers if r.get('funding_sign') == 'POSITIVE')
        funding_neg = sum(1 for r in followers if r.get('funding_sign') == 'NEGATIVE')
        next_pos = sum(1 for r in followers if r.get('next_funding_sign') == 'POSITIVE')
        next_neg = sum(1 for r in followers if r.get('next_funding_sign') == 'NEGATIVE')
        total = max(1, len(followers))
        avg_long = round(sum(_safe_float(r.get('ls_posit_long')) or 0 for r in followers) / total, 2) if followers else None
        avg_short = round(sum(_safe_float(r.get('ls_posit_short')) or 0 for r in followers) / total, 2) if followers else None
        fastest = sorted(
            [r for r in followers if r.get('reaction_ratio_1h') is not None],
            key=lambda x: x.get('reaction_ratio_1h') or 0,
            reverse=True,
        )[:3]
        inverse = [r for r in followers if r.get('reaction_direction_1h') == 'INVERSE']

        return {
            'followers_count': len(followers),
            'long_like_count': long_like,
            'short_like_count': short_like,
            'neutral_count': neutral,
            'long_crowded_count': long_crowded,
            'short_crowded_count': short_crowded,
            'current_funding_positive': funding_pos,
            'current_funding_negative': funding_neg,
            'next_funding_positive': next_pos,
            'next_funding_negative': next_neg,
            'avg_ls_posit_long': avg_long,
            'avg_ls_posit_short': avg_short,
            'market_long_crowding_index': round((long_crowded / total) * 100, 2) if followers else 0,
            'market_short_crowding_index': round((short_crowded / total) * 100, 2) if followers else 0,
            'fastest_reactors_1h': [
                {'symbol': r.get('symbol'), 'ratio': r.get('reaction_ratio_1h'), 'change': r.get('price_change_1h_pct')}
                for r in fastest
            ],
            'inverse_reactors_1h': [r.get('symbol') for r in inverse],
        }

    def _hypothesis_stats(self, hypothesis_id: str) -> dict:
        """Count how often a hypothesis tag appeared in saved hourly snapshots."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT snapshot_hour, raw_json
                    FROM btc_radar_market_monitor_snapshots
                    ORDER BY snapshot_hour DESC
                    LIMIT 720
                    """
                ).fetchall()
        except Exception:
            return {'observed': 0, 'triggered': 0, 'confirmed': 0, 'rejected': 0, 'accuracy': None, 'last_seen': None}

        observed = 0
        last_seen = None
        for r in rows:
            try:
                payload = json.loads(r['raw_json'] or '{}')
            except Exception:
                payload = {}
            tags = payload.get('hypothesis_tags') or []
            if hypothesis_id in tags:
                observed += 1
                if last_seen is None:
                    last_seen = r['snapshot_hour']
        return {'observed': observed, 'triggered': observed, 'confirmed': 0, 'rejected': 0, 'accuracy': None, 'last_seen': last_seen}

    def _market_monitor_hypotheses(self, rows: list[dict], summary: dict) -> list[dict]:
        followers = [r for r in rows if not r.get('is_driver')]
        btc = next((r for r in rows if r.get('is_driver')), None)
        h001_active = summary.get('long_like_count', 0) > summary.get('short_like_count', 0)
        h002_active = bool(btc and btc.get('crowding_side') != 'LONG_CROWDED' and summary.get('long_crowded_count', 0) >= 1)
        divergence = sum(1 for r in followers if str(r.get('crowding_side')).startswith('LONG') and r.get('funding_sign') == 'NEGATIVE')
        h003_active = divergence > 0
        fast_count = sum(1 for r in followers if (r.get('reaction_ratio_1h') or 0) >= 1.75)

        items = [
            {
                'id': 'H001',
                'name': 'Followers long crowding dominates',
                'status': 'ACTIVE' if h001_active else 'WAITING',
                'evidence': f"Long-like {summary.get('long_like_count', 0)}/{len(followers)} vs Short-like {summary.get('short_like_count', 0)}/{len(followers)}",
            },
            {
                'id': 'H002',
                'name': 'BTC driver / followers stronger crowding',
                'status': 'ACTIVE' if h002_active else 'WAITING',
                'evidence': f"BTC {btc.get('crowding_side') if btc else 'UNKNOWN'} / Followers long crowded {summary.get('long_crowded_count', 0)}",
            },
            {
                'id': 'H003',
                'name': 'Long crowding with negative funding divergence',
                'status': 'ACTIVE' if h003_active else 'WAITING',
                'evidence': f"{divergence} followers show long crowding/lean while current funding is negative",
            },
            {
                'id': 'H004',
                'name': 'Fast follower reaction to BTC move',
                'status': 'ACTIVE' if fast_count else 'WAITING',
                'evidence': f"{fast_count} followers are moving >= 1.75x BTC over 1h",
            },
        ]
        for item in items:
            stats = self._hypothesis_stats(item['id'])
            item['observed'] = stats.get('observed', 0)
            item['triggered'] = stats.get('triggered', stats.get('observed', 0))
            item['confirmed'] = stats.get('confirmed', 0)
            item['rejected'] = stats.get('rejected', 0)
            item['accuracy'] = stats.get('accuracy')
            item['last_seen'] = stats.get('last_seen')
        return items

    def _market_story(self, rows: list[dict], summary: dict) -> str:
        btc = next((r for r in rows if r.get('is_driver')), None)
        followers = [r for r in rows if not r.get('is_driver')]
        parts = []
        if btc:
            btc_change = btc.get('price_change_1h_pct')
            change_txt = f" 1H {btc_change:+.2f}%" if btc_change is not None else ""
            parts.append(f"BTC is {btc.get('crowding_side', 'UNKNOWN').replace('_', ' ').lower()}{change_txt}.")
        parts.append(
            f"Followers show {summary.get('long_like_count', 0)} long-like, "
            f"{summary.get('short_like_count', 0)} short-like, and {summary.get('neutral_count', 0)} neutral."
        )
        parts.append(
            f"Funding now is {summary.get('current_funding_positive', 0)} positive / "
            f"{summary.get('current_funding_negative', 0)} negative; next is "
            f"{summary.get('next_funding_positive', 0)} positive / {summary.get('next_funding_negative', 0)} negative."
        )
        crowded = [r for r in followers if r.get('crowding_side') == 'LONG_CROWDED']
        if crowded:
            parts.append('Long crowding is concentrated in ' + ', '.join(r['symbol'].replace('USDT','') for r in crowded) + '.')
        fastest = summary.get('fastest_reactors_1h') or []
        if fastest:
            names = ', '.join(f"{x['symbol'].replace('USDT','')} {x['ratio']}x" for x in fastest if x.get('symbol'))
            parts.append(f"Fastest 1H BTC reactions: {names}.")
        inverse = summary.get('inverse_reactors_1h') or []
        if inverse:
            parts.append('Inverse 1H movers: ' + ', '.join(str(x).replace('USDT','') for x in inverse) + '.')
        active_tags = []
        if summary.get('long_like_count', 0) > summary.get('short_like_count', 0):
            active_tags.append('H001')
        if any(str(r.get('crowding_side')).startswith('LONG') and r.get('funding_sign') == 'NEGATIVE' for r in followers):
            active_tags.append('H003')
        if active_tags:
            parts.append('Active hypotheses: ' + ', '.join(active_tags) + '.')
        return ' '.join(parts)



    def _daily_market_story(self, day: str, day_items: list[dict], card: dict) -> str:
        """Build a compact daily story from saved hourly Market Monitor rows."""
        btc_change = card.get('btc_day_change_pct')
        btc_txt = f"BTC changed {btc_change:+.2f}%" if btc_change is not None else "BTC daily change is still collecting"
        followers = [r for r in day_items if not r.get('is_driver')]
        crowded = [r for r in followers if r.get('crowding_side') == 'LONG_CROWDED']
        long_like = card.get('long_like_count', 0)
        short_like = card.get('short_like_count', 0)
        funding_txt = (
            f"Funding now: {card.get('funding_now_positive', 0)} positive / {card.get('funding_now_negative', 0)} negative; "
            f"next: {card.get('funding_next_positive', 0)} positive / {card.get('funding_next_negative', 0)} negative."
        )
        fastest = card.get('fastest_1h') or []
        fastest_txt = ''
        if fastest:
            names = ', '.join(f"{str(x.get('symbol','')).replace('USDT','')} {x.get('ratio')}x" for x in fastest if x.get('symbol'))
            fastest_txt = f" Fastest BTC reactions: {names}."
        crowd_txt = ''
        if crowded:
            names = ', '.join(sorted({str(r.get('symbol','')).replace('USDT','') for r in crowded if r.get('symbol')}))
            crowd_txt = f" Long crowding concentrated in {names}."
        tags = card.get('hypothesis_tags') or {}
        tag_txt = ''
        if tags:
            top = ', '.join(f"{k}({v})" for k, v in sorted(tags.items(), key=lambda kv: kv[1], reverse=True)[:4])
            tag_txt = f" Hypotheses observed: {top}."
        sessions = ', '.join(card.get('sessions') or []) or 'no session data'
        return f"{day}: {btc_txt}. Followers bias {long_like} long-like vs {short_like} short-like across {sessions}. {funding_txt}{crowd_txt}{fastest_txt}{tag_txt}"

    def _daily_timeline(self, day_items: list[dict]) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for row in day_items:
            grouped.setdefault(row.get('snapshot_hour'), []).append(row)
        out = []
        for hour in sorted(grouped.keys()):
            rows = grouped[hour]
            btc = next((r for r in rows if r.get('is_driver')), None)
            followers = [r for r in rows if not r.get('is_driver')]
            fastest = sorted(
                [r for r in followers if r.get('reaction_ratio_1h') is not None],
                key=lambda x: _safe_float(x.get('reaction_ratio_1h')) or 0,
                reverse=True,
            )[:3]
            out.append({
                'hour': hour,
                'session': rows[0].get('session') if rows else '--',
                'btc_change_1h_pct': btc.get('price_change_1h_pct') if btc else None,
                'long_like': sum(1 for r in followers if str(r.get('crowding_side')) in ('LONG_CROWDED','LONG_LEAN')),
                'short_like': sum(1 for r in followers if str(r.get('crowding_side')) in ('SHORT_CROWDED','SHORT_LEAN')),
                'fastest': [{'symbol': r.get('symbol'), 'ratio': r.get('reaction_ratio_1h'), 'change': r.get('price_change_1h_pct')} for r in fastest],
            })
        return out

    def _upsert_daily_market_report(self, card: dict) -> None:
        """Persist a clean daily summary table separate from trade/snapshot data."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO btc_radar_market_daily_reports (
                        day, generated_at, snapshot_hours, sessions_json, btc_day_change_pct,
                        story, summary_json, timeline_json, hypothesis_json, raw_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(day) DO UPDATE SET
                        generated_at=excluded.generated_at,
                        snapshot_hours=excluded.snapshot_hours,
                        sessions_json=excluded.sessions_json,
                        btc_day_change_pct=excluded.btc_day_change_pct,
                        story=excluded.story,
                        summary_json=excluded.summary_json,
                        timeline_json=excluded.timeline_json,
                        hypothesis_json=excluded.hypothesis_json,
                        raw_json=excluded.raw_json
                    """,
                    (
                        card.get('day'),
                        datetime.now(timezone.utc).isoformat(),
                        int(card.get('snapshot_hours') or 0),
                        json.dumps(card.get('sessions') or [], ensure_ascii=False),
                        card.get('btc_day_change_pct'),
                        card.get('story'),
                        json.dumps(card.get('summary') or {}, ensure_ascii=False),
                        json.dumps(card.get('timeline') or [], ensure_ascii=False),
                        json.dumps(card.get('hypothesis_tags') or {}, ensure_ascii=False),
                        json.dumps(card, ensure_ascii=False),
                    ),
                )
                conn.commit()
        except Exception as e:
            self.log.debug('daily market report save failed: %s', e)

    def _daily_market_monitor_cards(self, days: int = 3) -> list[dict]:
        """Build collapsible daily cards from independent Market Monitor snapshots.

        Each card summarizes one calendar day and includes the 24h snapshot rows
        for expand/collapse in the dashboard. This is read-only research data.
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                day_rows = conn.execute(
                    """
                    SELECT substr(snapshot_hour, 1, 10) AS day
                    FROM btc_radar_market_monitor_snapshots
                    GROUP BY day
                    ORDER BY day DESC
                    LIMIT ?
                    """,
                    (int(days),),
                ).fetchall()
                day_keys = [r['day'] for r in day_rows if r['day']]
                if not day_keys:
                    return []
                placeholders = ','.join(['?'] * len(day_keys))
                rows = conn.execute(
                    f"""
                    SELECT *
                    FROM btc_radar_market_monitor_snapshots
                    WHERE substr(snapshot_hour, 1, 10) IN ({placeholders})
                    ORDER BY snapshot_hour ASC, symbol ASC
                    """,
                    day_keys,
                ).fetchall()
        except Exception:
            return []

        grouped: dict[str, list[dict]] = {day: [] for day in day_keys}
        for r in rows:
            item = dict(r)
            grouped.setdefault(str(item.get('snapshot_hour') or '')[:10], []).append(item)

        cards: list[dict] = []
        for day in day_keys:
            day_items = grouped.get(day, [])
            hours = sorted({r.get('snapshot_hour') for r in day_items if r.get('snapshot_hour')})
            btc_rows = [r for r in day_items if r.get('is_driver')]
            followers = [r for r in day_items if not r.get('is_driver')]

            first_btc = btc_rows[0] if btc_rows else None
            last_btc = btc_rows[-1] if btc_rows else None
            btc_day_change = self._percent_change(
                last_btc.get('price') if last_btc else None,
                first_btc.get('price') if first_btc else None,
            )

            long_like = sum(1 for r in followers if str(r.get('crowding_side')) in ('LONG_CROWDED', 'LONG_LEAN'))
            short_like = sum(1 for r in followers if str(r.get('crowding_side')) in ('SHORT_CROWDED', 'SHORT_LEAN'))
            long_crowded = sum(1 for r in followers if r.get('crowding_side') == 'LONG_CROWDED')
            short_crowded = sum(1 for r in followers if r.get('crowding_side') == 'SHORT_CROWDED')

            funding_pos = sum(1 for r in followers if self._funding_sign_label(r.get('funding')) == 'POSITIVE')
            funding_neg = sum(1 for r in followers if self._funding_sign_label(r.get('funding')) == 'NEGATIVE')
            next_pos = sum(1 for r in followers if self._funding_sign_label(r.get('next_funding')) == 'POSITIVE')
            next_neg = sum(1 for r in followers if self._funding_sign_label(r.get('next_funding')) == 'NEGATIVE')

            fastest_rows = sorted(
                [r for r in followers if r.get('reaction_ratio_1h') is not None],
                key=lambda x: _safe_float(x.get('reaction_ratio_1h')) or 0,
                reverse=True,
            )[:3]

            tags: dict[str, int] = {}
            sessions = sorted({r.get('session') for r in day_items if r.get('session')})
            for r in day_items:
                raw_tags = r.get('hypothesis_tags')
                parsed = []
                if isinstance(raw_tags, str) and raw_tags:
                    try:
                        parsed = json.loads(raw_tags)
                    except Exception:
                        parsed = [x.strip() for x in raw_tags.split(',') if x.strip()]
                for tag in parsed:
                    tags[str(tag)] = tags.get(str(tag), 0) + 1

            card = {
                'day': day,
                'snapshot_hours': len(hours),
                'rows_count': len(day_items),
                'sessions': sessions,
                'btc_day_change_pct': btc_day_change,
                'long_like_count': long_like,
                'short_like_count': short_like,
                'long_crowded_count': long_crowded,
                'short_crowded_count': short_crowded,
                'funding_now_positive': funding_pos,
                'funding_now_negative': funding_neg,
                'funding_next_positive': next_pos,
                'funding_next_negative': next_neg,
                'fastest_1h': [
                    {
                        'symbol': r.get('symbol'),
                        'ratio': r.get('reaction_ratio_1h'),
                        'change': r.get('price_change_1h_pct'),
                    }
                    for r in fastest_rows
                ],
                'hypothesis_tags': tags,
                'timeline': self._daily_timeline(day_items),
                'summary': {
                    'btc_day_change_pct': btc_day_change,
                    'long_like_count': long_like,
                    'short_like_count': short_like,
                    'long_crowded_count': long_crowded,
                    'short_crowded_count': short_crowded,
                    'funding_now_positive': funding_pos,
                    'funding_now_negative': funding_neg,
                    'funding_next_positive': next_pos,
                    'funding_next_negative': next_neg,
                },
                'rows': day_items,
            }
            card['story'] = self._daily_market_story(day, day_items, card)
            self._upsert_daily_market_report(card)
            cards.append(card)
        return cards

    def _market_timeline(self, limit_hours: int = 12) -> list[dict]:
        snapshots = self._recent_market_monitor_snapshots(limit_hours * max(1, len(self._market_monitor_symbols())))
        grouped: dict[str, list[dict]] = {}
        for row in snapshots:
            grouped.setdefault(row.get('snapshot_hour'), []).append(row)
        out = []
        for hour in sorted(grouped.keys(), reverse=True)[:limit_hours]:
            rows = grouped[hour]
            btc = next((r for r in rows if r.get('is_driver')), None)
            followers = [r for r in rows if not r.get('is_driver')]
            fastest = sorted(
                [r for r in followers if r.get('reaction_ratio_1h') is not None],
                key=lambda x: x.get('reaction_ratio_1h') or 0,
                reverse=True,
            )[:3]
            out.append({
                'hour': hour,
                'session': rows[0].get('session') if rows else '--',
                'btc_change_1h_pct': btc.get('price_change_1h_pct') if btc else None,
                'btc_crowding': btc.get('crowding_side') if btc else None,
                'long_like': sum(1 for r in followers if str(r.get('crowding_side')) in ('LONG_CROWDED','LONG_LEAN')),
                'short_like': sum(1 for r in followers if str(r.get('crowding_side')) in ('SHORT_CROWDED','SHORT_LEAN')),
                'fastest': [{'symbol': r.get('symbol'), 'ratio': r.get('reaction_ratio_1h'), 'change': r.get('price_change_1h_pct')} for r in fastest],
            })
        return out

    def _snapshot_groups(self, limit_hours: int = 12) -> list[dict]:
        snapshots = self._recent_market_monitor_snapshots(limit_hours * max(1, len(self._market_monitor_symbols())))
        grouped: dict[str, list[dict]] = {}
        for row in snapshots:
            grouped.setdefault(row.get('snapshot_hour'), []).append(row)
        return [
            {
                'hour': hour,
                'session': (rows[0].get('session') if rows else '--'),
                'rows': rows,
            }
            for hour, rows in sorted(grouped.items(), reverse=True)[:limit_hours]
        ]

    def _maybe_record_market_monitor_snapshot(self) -> None:
        if not self.market_monitor_enabled:
            return
        now = datetime.now(timezone.utc)
        hour = now.replace(minute=0, second=0, microsecond=0).isoformat()
        if self._last_market_monitor_snapshot_hour == hour:
            return
        self._record_market_monitor_snapshot(hour, now)
        self._last_market_monitor_snapshot_hour = hour

    def _record_market_monitor_snapshot(self, hour_iso: str, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        session = self._session_label(now)
        rows = self._market_monitor_rows()
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                for row in rows:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO btc_radar_market_monitor_snapshots (
                            snapshot_hour, recorded_at, session, symbol, is_driver,
                            price, price_change_1h_pct, price_change_4h_pct, price_change_24h_pct,
                            btc_price, btc_change_1h_pct, btc_change_4h_pct, btc_change_24h_pct,
                            reaction_ratio_1h, reaction_ratio_4h, reaction_ratio_24h, reaction_direction_1h,
                            ls_posit_long, ls_posit_short, ls_ratio_long, ls_ratio_short,
                            ls_account_long, ls_account_short, funding, next_funding, oi,
                            cvd, cvd_delta_15m, cvd_trend, crowding_side, agreement_with_btc,
                            btc_link_strength, session_phase, hypothesis_tags, raw_json
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            hour_iso,
                            now.isoformat(),
                            session,
                            row.get('symbol'),
                            int(row.get('is_driver') or 0),
                            row.get('price'),
                            row.get('price_change_1h_pct'),
                            row.get('price_change_4h_pct'),
                            row.get('price_change_24h_pct'),
                            row.get('btc_price'),
                            row.get('btc_change_1h_pct'),
                            row.get('btc_change_4h_pct'),
                            row.get('btc_change_24h_pct'),
                            row.get('reaction_ratio_1h'),
                            row.get('reaction_ratio_4h'),
                            row.get('reaction_ratio_24h'),
                            row.get('reaction_direction_1h'),
                            row.get('ls_posit_long'),
                            row.get('ls_posit_short'),
                            row.get('ls_ratio_long'),
                            row.get('ls_ratio_short'),
                            row.get('ls_account_long'),
                            row.get('ls_account_short'),
                            row.get('funding'),
                            row.get('next_funding'),
                            row.get('oi'),
                            row.get('cvd'),
                            row.get('cvd_delta_15m'),
                            row.get('cvd_trend'),
                            row.get('crowding_side'),
                            row.get('agreement_with_btc'),
                            row.get('btc_link_strength'),
                            row.get('session_phase'),
                            json.dumps(row.get('hypothesis_tags') or [], ensure_ascii=False),
                            json.dumps(row, ensure_ascii=False),
                        ),
                    )
                conn.commit()
        except Exception as e:
            self.log.debug('market monitor snapshot save failed: %s', e)

    def _recent_market_monitor_snapshots(self, limit: int = 24) -> list[dict]:
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT * FROM btc_radar_market_monitor_snapshots
                    ORDER BY snapshot_hour DESC, symbol ASC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def market_monitor_state(self) -> dict:
        """Return the independent Market Monitor / Intelligence Lab state."""
        rows = self._market_monitor_rows()
        summary = self._market_monitor_summary(rows)
        now = datetime.now(timezone.utc)
        return {
            'version': 'market_monitor_v1_5',
            'generated_at': now.isoformat(),
            'session': self._session_label(now),
            'snapshot_interval_minutes': int(self.market_monitor_interval_sec / 60),
            'symbols': self._market_monitor_symbols(),
            'summary': summary,
            'rows': rows,
            'hypotheses': self._market_monitor_hypotheses(rows, summary),
            'story': self._market_story(rows, summary),
            'timeline': self._market_timeline(24),
            'snapshot_groups': self._snapshot_groups(24),
            'recent_snapshots': self._recent_market_monitor_snapshots(24 * max(1, len(self._market_monitor_symbols()))),
            'daily_cards': self._daily_market_monitor_cards(3),
        }


    def followers_consensus(self) -> dict:
        """Compute Followers Consensus as a passive research layer.

        V1 intentionally excludes VWAP. A follower contributes 25 points only
        when LS_POSIT and current+next funding agree strongly in the same side.
        This does not change BTC Score, Follow Score, recommendation, entry, or exit logic.
        """
        cfg = self.cfg.get('followers_consensus', {}) if isinstance(self.cfg, dict) else {}
        threshold_ls = float(cfg.get('ls_posit_threshold', 65.0))
        threshold_funding = float(cfg.get('funding_threshold', 0.00005))
        followers = [str(x).upper() for x in self.cfg.get('symbols', {}).get('followers', [])]

        rows = []
        for sym in followers:
            snapshot = self.snapshots.get(sym)
            if snapshot is not None:
                self._attach_next_funding(sym, snapshot)
            rows.append(_symbol_consensus(sym, snapshot, threshold_ls, threshold_funding))

        short_score = int(sum(r['short_score'] for r in rows))
        long_score = int(sum(r['long_score'] for r in rows))
        positive_agreements = sum(1 for r in rows if str(r.get('funding_agreement')) in ('POSITIVE_STRONG', 'POSITIVE_WEAK'))
        negative_agreements = sum(1 for r in rows if str(r.get('funding_agreement')) in ('NEGATIVE_STRONG', 'NEGATIVE_WEAK'))
        transitions = sum(1 for r in rows if str(r.get('funding_agreement')) in ('POS_TO_NEG', 'NEG_TO_POS'))
        strong_agreements = sum(1 for r in rows if str(r.get('funding_agreement')) in ('POSITIVE_STRONG', 'NEGATIVE_STRONG'))

        return {
            'version': 'followers_consensus_v1',
            'thresholds': {
                'ls_posit': threshold_ls,
                'funding': threshold_funding,
                'vwap_enabled': False,
            },
            'short': {
                'score': short_score,
                'state': _score_state(short_score),
            },
            'long': {
                'score': long_score,
                'state': _score_state(long_score),
            },
            'funding_summary': {
                'positive_agreements': positive_agreements,
                'negative_agreements': negative_agreements,
                'strong_agreements': strong_agreements,
                'transitions': transitions,
                'unknown': sum(1 for r in rows if str(r.get('funding_agreement')) == 'UNKNOWN'),
            },
            'symbols': rows,
        }

    def status(self) -> dict:
        now_ts = time.time()
        has_heavy = any(
            getattr(s, 'funding', None) is not None or getattr(s, 'oi', None) is not None or getattr(s, 'ls_updated_at', None)
            for s in self.snapshots.values()
        )
        return {
            'binance': 'Disabled',
            'price_feed': 'Live' if self.last_price_update else 'Waiting',
            'ls_feed': 'Live' if has_heavy else 'Waiting',
            'last_price_age_sec': int(now_ts - self.last_price_update) if self.last_price_update else None,
            'last_ls_age_sec': int(now_ts - self.last_ls_update) if self.last_ls_update else None,
            'ls_refresh_sec': self.ls_interval,
            'ls_countdown_sec': max(0, int(self.ls_interval - (now_ts - self.last_ls_update))) if self.last_ls_update else self.ls_interval,
            'mock_data': bool(self.cfg.get('runtime', {}).get('mock_data', False)),
            'data_engine': {
                'price_ok': bool(self.last_price_update),
                'heavy_ok': bool(has_heavy),
                'last_price_provider': next(iter(self.price_router.last_price_provider.values()), None) if self.price_router.last_price_provider else None,
                'router': self.price_router.status(),
            },
        }
