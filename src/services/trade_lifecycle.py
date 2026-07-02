from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import math


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None:
            return default
        n = float(v)
        if math.isnan(n):
            return default
        return round(n, 6)
    except Exception:
        return default


def _tier(state: dict | None) -> str:
    if not state:
        return 'WAITING'
    status = str(state.get('status') or '').upper()
    score = _num(state.get('health_score'), 0) or 0
    if 'EXIT' in status or score < 50:
        return 'EXIT'
    if 'WARNING' in status or score < 70:
        return 'WARNING'
    if score >= 90:
        return 'SAFE+'
    return 'SAFE'


def _score(state: dict | None) -> float | None:
    return _num((state or {}).get('health_score'))


def _short(symbol: str) -> str:
    return str(symbol or '').upper().replace('USDT', '')


def _snap_value(snap: Any, attr: str) -> float | None:
    return _num(getattr(snap, attr, None)) if snap else None




def _followers_consensus(market) -> dict | None:
    if market is None or not hasattr(market, 'followers_consensus'):
        return None
    try:
        return market.followers_consensus()
    except Exception:
        return None

def _sign(v: Any) -> str:
    n = _num(v)
    if n is None:
        return 'NA'
    if n > 0:
        return 'POS'
    if n < 0:
        return 'NEG'
    return 'ZERO'


def _fmt_delta(v: float | None) -> str:
    if v is None:
        return '--'
    sign = '+' if v > 0 else ''
    return f'{sign}{round(v, 4)}'


def _spread_regime(v: Any) -> str:
    n = _num(v)
    if n is None:
        return 'NA'
    if n >= 30:
        return 'EXTREME_30_PLUS'
    if n >= 20:
        return 'HIGH_20_30'
    if n >= 10:
        return 'MID_10_20'
    return 'LOW_0_10'


def _dominant_votes(state: dict | None) -> int | None:
    if not state:
        return None
    lv = _num(state.get('long_votes'))
    sv = _num(state.get('short_votes'))
    vals = [v for v in (lv, sv) if v is not None]
    return int(max(vals)) if vals else None


def _direction_for_trade(direction: str, pnl_delta: float | None) -> str:
    if pnl_delta is None:
        return 'neutral'
    if pnl_delta > 0:
        return 'in_favor'
    if pnl_delta < 0:
        return 'against'
    return 'neutral'


class TradeLifecycleService:
    """LifeCycle V2 — trade black-box recorder.

    Records complete event snapshots and explains what changed:
    - PnL bucket changes
    - BTC/Follower health state changes
    - BTC/Follower score moves
    - Pain moves
    - Funding sign/size changes
    - Verdict, entry timing, OI trend and liquidation trend changes

    This service is passive: it never opens or closes trades.
    """

    def __init__(self, trade_store, market_service, cfg: dict):
        self.trade_store = trade_store
        self.market = market_service
        self.cfg = cfg or {}

        lc_cfg = (self.cfg.get('trade_lifecycle') or {}) if isinstance(self.cfg, dict) else {}
        self.enabled = bool(lc_cfg.get('enabled', True))

        self.pnl_bucket_pct = float(lc_cfg.get('pnl_bucket_pct', 1.0))
        self.health_delta_threshold = float(lc_cfg.get('health_delta_threshold', 10.0))
        self.pain_delta_threshold = float(lc_cfg.get('pain_delta_threshold', 10.0))
        self.funding_delta_threshold = float(lc_cfg.get('funding_delta_threshold', 0.00005))
        self.ls_delta_threshold = float(lc_cfg.get('ls_delta_threshold', 3.0))
        self.spread_delta_threshold = float(lc_cfg.get('spread_delta_threshold', 5.0))
        self.votes_change_enabled = bool(lc_cfg.get('votes_change_enabled', True))
        self.spread_change_enabled = bool(lc_cfg.get('spread_change_enabled', True))

        self._ensure_tables()

    def _ensure_tables(self):
        base_columns = {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'trade_id': 'INTEGER NOT NULL',
            'symbol': 'TEXT',
            'direction': 'TEXT',
            'status': 'TEXT',
            'event_type': 'TEXT',
            'event_label': 'TEXT',
            'pnl_bucket': 'INTEGER',
            'pnl_pct': 'REAL',
            'pnl_usd': 'REAL',
            'current_price': 'REAL',
            'btc_health_status': 'TEXT',
            'btc_health_score': 'REAL',
            'btc_funding': 'REAL',
            'btc_ls_posit_long': 'REAL',
            'btc_ls_ratio_long': 'REAL',
            'btc_ls_account_long': 'REAL',
            'follower_health_status': 'TEXT',
            'follower_health_score': 'REAL',
            'follower_funding': 'REAL',
            'follower_ls_posit_long': 'REAL',
            'follower_ls_ratio_long': 'REAL',
            'follower_ls_account_long': 'REAL',
            'pain_score': 'REAL',
            'entry_timing': 'TEXT',
            'verdict': 'TEXT',
            'oi_trend': 'TEXT',
            'liq_trend': 'TEXT',
            'reason': 'TEXT',
            'snapshot_json': 'TEXT',
            'created_at': 'TEXT',
        }

        v2_columns = {
            'diff_json': 'TEXT',
            'change_summary': 'TEXT',
            'diagnosis_json': 'TEXT',
            'story_text': 'TEXT',
            'driver_label': 'TEXT',
            'severity': 'TEXT',
        }

        v3_columns = {
            'btc_spread': 'REAL',
            'btc_spread_regime': 'TEXT',
            'btc_long_votes': 'INTEGER',
            'btc_short_votes': 'INTEGER',
            'btc_dominant_votes': 'INTEGER',
            'btc_long_score': 'REAL',
            'btc_short_score': 'REAL',
            'btc_narrative': 'TEXT',
            'follower_spread': 'REAL',
            'follower_spread_regime': 'TEXT',
            'follower_long_votes': 'INTEGER',
            'follower_short_votes': 'INTEGER',
            'follower_dominant_votes': 'INTEGER',
            'follower_long_score': 'REAL',
            'follower_short_score': 'REAL',
            'follower_narrative': 'TEXT',
            'btc_cvd': 'REAL',
            'btc_cvd_15m_ago': 'REAL',
            'btc_cvd_delta_15m': 'REAL',
            'btc_cvd_trend': 'TEXT',
            'follower_cvd': 'REAL',
            'follower_cvd_15m_ago': 'REAL',
            'follower_cvd_delta_15m': 'REAL',
            'follower_cvd_trend': 'TEXT',
            'followers_consensus_short_score': 'REAL',
            'followers_consensus_short_state': 'TEXT',
            'followers_consensus_long_score': 'REAL',
            'followers_consensus_long_state': 'TEXT',
            'followers_consensus_positive_funding_count': 'INTEGER',
            'followers_consensus_negative_funding_count': 'INTEGER',
            'followers_consensus_transition_count': 'INTEGER',
            'followers_consensus_strong_agreement_count': 'INTEGER',
            'followers_consensus_json': 'TEXT',
        }

        with self.trade_store.db.connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS btc_radar_trade_lifecycle (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER NOT NULL,
                    symbol TEXT,
                    direction TEXT,
                    status TEXT,
                    event_type TEXT,
                    event_label TEXT,
                    pnl_bucket INTEGER,
                    pnl_pct REAL,
                    pnl_usd REAL,
                    current_price REAL,

                    btc_health_status TEXT,
                    btc_health_score REAL,
                    btc_funding REAL,
                    btc_ls_posit_long REAL,
                    btc_ls_ratio_long REAL,
                    btc_ls_account_long REAL,
                    btc_cvd REAL,
                    btc_cvd_15m_ago REAL,
                    btc_cvd_delta_15m REAL,
                    btc_cvd_trend TEXT,

                    follower_health_status TEXT,
                    follower_health_score REAL,
                    follower_funding REAL,
                    follower_ls_posit_long REAL,
                    follower_ls_ratio_long REAL,
                    follower_ls_account_long REAL,
                    follower_cvd REAL,
                    follower_cvd_15m_ago REAL,
                    follower_cvd_delta_15m REAL,
                    follower_cvd_trend TEXT,

                    pain_score REAL,
                    entry_timing TEXT,
                    verdict TEXT,
                    oi_trend TEXT,
                    liq_trend TEXT,

                    reason TEXT,
                    snapshot_json TEXT,
                    created_at TEXT
                )
            """)
            existing = {row['name'] for row in con.execute("PRAGMA table_info(btc_radar_trade_lifecycle)").fetchall()}
            for name, col_type in {**v2_columns, **v3_columns}.items():
                if name not in existing:
                    con.execute(f"ALTER TABLE btc_radar_trade_lifecycle ADD COLUMN {name} {col_type}")
            con.execute("CREATE INDEX IF NOT EXISTS idx_trade_lifecycle_trade_id ON btc_radar_trade_lifecycle(trade_id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_trade_lifecycle_created_at ON btc_radar_trade_lifecycle(created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_trade_lifecycle_event_type ON btc_radar_trade_lifecycle(event_type)")

    def process_open_trades(self, *, symbol_states: dict, open_trades: list[dict], driver: str = 'BTCUSDT') -> list[dict]:
        if not self.enabled:
            return []
        events: list[dict] = []
        for trade in open_trades or []:
            try:
                events.extend(self._process_trade(trade, symbol_states or {}, driver))
            except Exception:
                # LifeCycle must never break /api/state.
                continue
        return events

    def record_close(self, trade: dict, *, symbol_states: dict | None = None, driver: str = 'BTCUSDT', reason: str = 'Trade closed'):
        if not self.enabled or not trade:
            return
        try:
            previous = self._last_event(int(trade.get('id') or trade.get('trade_id')))
            snapshot = self._build_snapshot(trade, symbol_states or {}, driver)
            diff = self._diff(previous, snapshot) if previous else {}
            diagnosis = self._diagnose('CLOSE', trade, snapshot, previous, diff)
            self._insert_event(
                trade=trade,
                symbol_states=symbol_states or {},
                driver=driver,
                event_type='CLOSE',
                event_label='Closed',
                reason=reason,
                diff=diff,
                diagnosis=diagnosis,
            )
        except Exception:
            return

    def _process_trade(self, trade: dict, symbol_states: dict, driver: str) -> list[dict]:
        out: list[dict] = []
        trade_id = trade.get('id')
        symbol = str(trade.get('symbol') or '').upper()
        if not trade_id or not symbol:
            return out

        previous = self._last_event(int(trade_id))
        snapshot = self._build_snapshot(trade, symbol_states, driver)

        if previous is None:
            diagnosis = self._diagnose('ENTRY', trade, snapshot, None, {})
            self._insert_event(
                trade=trade,
                symbol_states=symbol_states,
                driver=driver,
                event_type='ENTRY',
                event_label='Entry',
                reason='Trade lifecycle started',
                diff={},
                diagnosis=diagnosis,
            )
            out.append({'trade_id': trade_id, 'event_type': 'ENTRY'})
            previous = self._last_event(int(trade_id))

        diff = self._diff(previous, snapshot)
        candidates = self._event_candidates(trade, previous, snapshot, diff)

        # Store only the most important event for this refresh cycle to avoid noise.
        if candidates:
            candidates.sort(key=lambda x: x.get('priority', 0), reverse=True)
            ev = candidates[0]
            diagnosis = self._diagnose(ev['event_type'], trade, snapshot, previous, diff)
            self._insert_event(
                trade=trade,
                symbol_states=symbol_states,
                driver=driver,
                event_type=ev['event_type'],
                event_label=ev['event_label'],
                reason=ev['reason'],
                pnl_bucket=ev.get('pnl_bucket'),
                diff=diff,
                diagnosis=diagnosis,
            )
            out.append({'trade_id': trade_id, 'event_type': ev['event_type'], 'label': ev['event_label']})

        return out

    def _build_snapshot(self, trade: dict, symbol_states: dict, driver: str) -> dict:
        symbol = str(trade.get('symbol') or '').upper()

        btc_state = symbol_states.get(driver.upper(), {}) if isinstance(symbol_states, dict) else {}
        follower_state = symbol_states.get(symbol, {}) if isinstance(symbol_states, dict) else {}
        coinalyze = follower_state.get('coinalyze') or {}

        btc_snap = self.market.snapshots.get(driver.upper()) if getattr(self.market, 'snapshots', None) else None
        follower_snap = self.market.snapshots.get(symbol) if getattr(self.market, 'snapshots', None) else None

        pnl_pct = _num(trade.get('pnl_pct'), 0) or 0
        pnl_bucket = int(math.floor(pnl_pct / self.pnl_bucket_pct)) if pnl_pct >= 0 else int(math.ceil(pnl_pct / self.pnl_bucket_pct))

        consensus = _followers_consensus(self.market)
        consensus_summary = (consensus or {}).get('funding_summary') or {}

        return {
            'trade_id': int(trade.get('id') or trade.get('trade_id')),
            'symbol': symbol,
            'direction': str(trade.get('direction') or '').upper(),
            'status': str(trade.get('status') or 'OPEN').upper(),
            'pnl_bucket': pnl_bucket,
            'pnl_pct': _num(trade.get('pnl_pct'), 0),
            'pnl_usd': _num(trade.get('pnl_usd'), 0),
            'current_price': _num(trade.get('current_price') or trade.get('exit_price') or trade.get('entry_price')),

            'btc_health_status': _tier(btc_state),
            'btc_health_score': _score(btc_state),
            'btc_funding': _snap_value(btc_snap, 'funding'),
            'btc_ls_posit_long': _snap_value(btc_snap, 'ls_posit_long'),
            'btc_ls_ratio_long': _snap_value(btc_snap, 'ls_ratio_long'),
            'btc_ls_account_long': _snap_value(btc_snap, 'ls_account_long'),
            'btc_spread': _num(btc_state.get('spread')),
            'btc_spread_regime': _spread_regime(btc_state.get('spread')),
            'btc_long_votes': int(_num(btc_state.get('long_votes'), 0) or 0),
            'btc_short_votes': int(_num(btc_state.get('short_votes'), 0) or 0),
            'btc_dominant_votes': _dominant_votes(btc_state),
            'btc_long_score': _num(btc_state.get('long_score')),
            'btc_short_score': _num(btc_state.get('short_score')),
            'btc_narrative': btc_state.get('narrative'),
            'btc_cvd': _snap_value(btc_snap, 'cvd'),
            'btc_cvd_15m_ago': _snap_value(btc_snap, 'cvd_15m_ago'),
            'btc_cvd_delta_15m': _snap_value(btc_snap, 'cvd_delta_15m'),
            'btc_cvd_trend': getattr(btc_snap, 'cvd_trend', None) if btc_snap else None,

            'follower_health_status': _tier(follower_state),
            'follower_health_score': _score(follower_state),
            'follower_funding': _snap_value(follower_snap, 'funding'),
            'follower_ls_posit_long': _snap_value(follower_snap, 'ls_posit_long'),
            'follower_ls_ratio_long': _snap_value(follower_snap, 'ls_ratio_long'),
            'follower_ls_account_long': _snap_value(follower_snap, 'ls_account_long'),
            'follower_spread': _num(follower_state.get('spread')),
            'follower_spread_regime': _spread_regime(follower_state.get('spread')),
            'follower_long_votes': int(_num(follower_state.get('long_votes'), 0) or 0),
            'follower_short_votes': int(_num(follower_state.get('short_votes'), 0) or 0),
            'follower_dominant_votes': _dominant_votes(follower_state),
            'follower_long_score': _num(follower_state.get('long_score')),
            'follower_short_score': _num(follower_state.get('short_score')),
            'follower_narrative': follower_state.get('narrative'),
            'follower_cvd': _snap_value(follower_snap, 'cvd'),
            'follower_cvd_15m_ago': _snap_value(follower_snap, 'cvd_15m_ago'),
            'follower_cvd_delta_15m': _snap_value(follower_snap, 'cvd_delta_15m'),
            'follower_cvd_trend': getattr(follower_snap, 'cvd_trend', None) if follower_snap else None,

            'followers_consensus_short_score': _num(((consensus or {}).get('short') or {}).get('score')),
            'followers_consensus_short_state': ((consensus or {}).get('short') or {}).get('state'),
            'followers_consensus_long_score': _num(((consensus or {}).get('long') or {}).get('score')),
            'followers_consensus_long_state': ((consensus or {}).get('long') or {}).get('state'),
            'followers_consensus_positive_funding_count': int(_num(consensus_summary.get('positive_agreements'), 0) or 0),
            'followers_consensus_negative_funding_count': int(_num(consensus_summary.get('negative_agreements'), 0) or 0),
            'followers_consensus_transition_count': int(_num(consensus_summary.get('transitions'), 0) or 0),
            'followers_consensus_strong_agreement_count': int(_num(consensus_summary.get('strong_agreements'), 0) or 0),
            'followers_consensus_json': json.dumps(consensus, ensure_ascii=False, separators=(',', ':')) if consensus else None,

            'pain_score': _num(coinalyze.get('pain_score')),
            'entry_timing': coinalyze.get('entry_timing'),
            'verdict': coinalyze.get('verdict'),
            'oi_trend': coinalyze.get('oi_trend'),
            'liq_trend': coinalyze.get('liquidation_trend'),

            'raw': {
                'trade': trade,
                'btc_state': btc_state,
                'follower_state': follower_state,
                'follower_coinalyze': coinalyze,
                'followers_consensus': consensus,
            }
        }

    def _diff(self, previous: dict | None, current: dict) -> dict:
        if not previous:
            return {}

        numeric_fields = [
            'pnl_pct',
            'pnl_usd',
            'current_price',
            'btc_health_score',
            'btc_funding',
            'btc_ls_posit_long',
            'btc_ls_ratio_long',
            'btc_ls_account_long',
            'btc_spread',
            'btc_long_votes',
            'btc_short_votes',
            'btc_dominant_votes',
            'btc_long_score',
            'btc_short_score',
            'btc_cvd',
            'btc_cvd_15m_ago',
            'btc_cvd_delta_15m',
            'follower_health_score',
            'follower_funding',
            'follower_ls_posit_long',
            'follower_ls_ratio_long',
            'follower_ls_account_long',
            'follower_spread',
            'follower_long_votes',
            'follower_short_votes',
            'follower_dominant_votes',
            'follower_long_score',
            'follower_short_score',
            'follower_cvd',
            'follower_cvd_15m_ago',
            'follower_cvd_delta_15m',
            'pain_score',
        ]
        text_fields = [
            'btc_health_status',
            'btc_spread_regime',
            'btc_narrative',
            'btc_cvd_trend',
            'follower_health_status',
            'follower_spread_regime',
            'follower_narrative',
            'follower_cvd_trend',
            'entry_timing',
            'verdict',
            'oi_trend',
            'liq_trend',
        ]

        changes: dict[str, dict] = {}

        for field in numeric_fields:
            prev = _num(previous.get(field))
            cur = _num(current.get(field))
            if prev is None or cur is None:
                continue
            delta = round(cur - prev, 6)
            if delta != 0:
                changes[field] = {'from': prev, 'to': cur, 'delta': delta}

        for field in text_fields:
            prev = previous.get(field)
            cur = current.get(field)
            if prev != cur:
                changes[field] = {'from': prev, 'to': cur, 'delta': None}

        # Explicit funding sign changes.
        prev_f = previous.get('follower_funding')
        cur_f = current.get('follower_funding')
        if _sign(prev_f) != _sign(cur_f):
            changes['follower_funding_sign'] = {'from': _sign(prev_f), 'to': _sign(cur_f), 'delta': None}

        return changes

    def _event_candidates(self, trade: dict, previous: dict, snapshot: dict, diff: dict) -> list[dict]:
        events = []

        # PnL bucket event.
        prev_bucket = previous.get('pnl_bucket')
        cur_bucket = snapshot.get('pnl_bucket')
        if prev_bucket is None or int(prev_bucket) != int(cur_bucket):
            if int(cur_bucket) != 0:
                pnl = snapshot.get('pnl_pct') or 0
                events.append({
                    'priority': 60,
                    'event_type': 'PNL_BUCKET',
                    'event_label': f'PnL {int(cur_bucket):+d}%',
                    'reason': 'Price moved in favor' if pnl > 0 else 'Price moved against position',
                    'pnl_bucket': int(cur_bucket),
                })

        if 'btc_health_status' in diff:
            events.append({
                'priority': 100,
                'event_type': 'BTC_STATE_CHANGE',
                'event_label': f"BTC {diff['btc_health_status']['from']} → {diff['btc_health_status']['to']}",
                'reason': self._reason_from_diff('BTC health state changed', diff),
            })

        if 'follower_health_status' in diff:
            events.append({
                'priority': 95,
                'event_type': 'FOLLOWER_STATE_CHANGE',
                'event_label': f"{_short(snapshot.get('symbol'))} {diff['follower_health_status']['from']} → {diff['follower_health_status']['to']}",
                'reason': self._reason_from_diff('Follower health state changed', diff),
            })

        if abs((diff.get('btc_health_score') or {}).get('delta') or 0) >= self.health_delta_threshold:
            delta = diff['btc_health_score']['delta']
            events.append({
                'priority': 80,
                'event_type': 'BTC_HEALTH_MOVE',
                'event_label': f'BTC Health {_fmt_delta(delta)}',
                'reason': self._reason_from_diff('BTC health moved strongly', diff),
            })

        if abs((diff.get('follower_health_score') or {}).get('delta') or 0) >= self.health_delta_threshold:
            delta = diff['follower_health_score']['delta']
            events.append({
                'priority': 78,
                'event_type': 'FOLLOWER_HEALTH_MOVE',
                'event_label': f'{_short(snapshot.get("symbol"))} Health {_fmt_delta(delta)}',
                'reason': self._reason_from_diff('Follower health moved strongly', diff),
            })

        if abs((diff.get('pain_score') or {}).get('delta') or 0) >= self.pain_delta_threshold:
            delta = diff['pain_score']['delta']
            events.append({
                'priority': 75,
                'event_type': 'PAIN_MOVE',
                'event_label': f'Pain {_fmt_delta(delta)}',
                'reason': self._reason_from_diff('Pain changed strongly', diff),
            })

        if 'verdict' in diff:
            events.append({
                'priority': 72,
                'event_type': 'VERDICT_CHANGE',
                'event_label': f"{diff['verdict']['from']} → {diff['verdict']['to']}",
                'reason': self._reason_from_diff('Coinalyze verdict changed', diff),
            })

        if 'entry_timing' in diff:
            events.append({
                'priority': 66,
                'event_type': 'ENTRY_TIMING_CHANGE',
                'event_label': f"{diff['entry_timing']['from']} → {diff['entry_timing']['to']}",
                'reason': self._reason_from_diff('Entry timing changed', diff),
            })

        if 'oi_trend' in diff:
            events.append({
                'priority': 64,
                'event_type': 'OI_TREND_CHANGE',
                'event_label': f"OI {diff['oi_trend']['from']} → {diff['oi_trend']['to']}",
                'reason': self._reason_from_diff('OI trend changed', diff),
            })

        if 'liq_trend' in diff:
            events.append({
                'priority': 63,
                'event_type': 'LIQ_TREND_CHANGE',
                'event_label': f"Liq {diff['liq_trend']['from']} → {diff['liq_trend']['to']}",
                'reason': self._reason_from_diff('Liquidation trend changed', diff),
            })

        if 'follower_funding_sign' in diff:
            events.append({
                'priority': 62,
                'event_type': 'FUNDING_SIGN_CHANGE',
                'event_label': f"Funding {diff['follower_funding_sign']['from']} → {diff['follower_funding_sign']['to']}",
                'reason': self._reason_from_diff('Funding sign changed', diff),
            })

        if abs((diff.get('follower_funding') or {}).get('delta') or 0) >= self.funding_delta_threshold:
            delta = diff['follower_funding']['delta']
            events.append({
                'priority': 50,
                'event_type': 'FUNDING_MOVE',
                'event_label': f'Funding {_fmt_delta(delta)}',
                'reason': self._reason_from_diff('Funding changed strongly', diff),
            })

        if self.votes_change_enabled and 'btc_dominant_votes' in diff:
            events.append({
                'priority': 74,
                'event_type': 'BTC_VOTES_CHANGE',
                'event_label': f"BTC Votes {diff['btc_dominant_votes']['from']} → {diff['btc_dominant_votes']['to']}",
                'reason': self._reason_from_diff('BTC votes changed', diff),
            })

        if self.votes_change_enabled and 'follower_dominant_votes' in diff:
            events.append({
                'priority': 73,
                'event_type': 'FOLLOWER_VOTES_CHANGE',
                'event_label': f"{_short(snapshot.get('symbol'))} Votes {diff['follower_dominant_votes']['from']} → {diff['follower_dominant_votes']['to']}",
                'reason': self._reason_from_diff('Follower votes changed', diff),
            })

        if self.spread_change_enabled and 'btc_spread_regime' in diff:
            events.append({
                'priority': 71,
                'event_type': 'BTC_SPREAD_REGIME_CHANGE',
                'event_label': f"BTC Spread {diff['btc_spread_regime']['from']} → {diff['btc_spread_regime']['to']}",
                'reason': self._reason_from_diff('BTC spread regime changed', diff),
            })

        if self.spread_change_enabled and 'follower_spread_regime' in diff:
            events.append({
                'priority': 70,
                'event_type': 'FOLLOWER_SPREAD_REGIME_CHANGE',
                'event_label': f"{_short(snapshot.get('symbol'))} Spread {diff['follower_spread_regime']['from']} → {diff['follower_spread_regime']['to']}",
                'reason': self._reason_from_diff('Follower spread regime changed', diff),
            })

        if self.spread_change_enabled and abs((diff.get('btc_spread') or {}).get('delta') or 0) >= self.spread_delta_threshold:
            delta = diff['btc_spread']['delta']
            events.append({
                'priority': 61,
                'event_type': 'BTC_SPREAD_MOVE',
                'event_label': f'BTC Spread {_fmt_delta(delta)}',
                'reason': self._reason_from_diff('BTC spread moved strongly', diff),
            })

        if self.spread_change_enabled and abs((diff.get('follower_spread') or {}).get('delta') or 0) >= self.spread_delta_threshold:
            delta = diff['follower_spread']['delta']
            events.append({
                'priority': 60,
                'event_type': 'FOLLOWER_SPREAD_MOVE',
                'event_label': f'{_short(snapshot.get("symbol"))} Spread {_fmt_delta(delta)}',
                'reason': self._reason_from_diff('Follower spread moved strongly', diff),
            })

        for field, label in [
            ('follower_ls_posit_long', 'LS_POSIT'),
            ('follower_ls_ratio_long', 'LS_RATIO'),
            ('follower_ls_account_long', 'LS_ACCOUNT'),
            ('btc_spread', 'BTC Spread'),
            ('follower_spread', 'Follower Spread'),
            ('btc_dominant_votes', 'BTC Votes'),
            ('follower_dominant_votes', 'Follower Votes'),
        ]:
            if abs((diff.get(field) or {}).get('delta') or 0) >= self.ls_delta_threshold:
                delta = diff[field]['delta']
                events.append({
                    'priority': 48,
                    'event_type': 'LS_MOVE',
                    'event_label': f'{label} {_fmt_delta(delta)}',
                    'reason': self._reason_from_diff(f'{label} moved strongly', diff),
                })

        return events

    def _reason_from_diff(self, base: str, diff: dict) -> str:
        parts = []

        for key, label in [
            ('btc_health_score', 'BTC health'),
            ('follower_health_score', 'Follower health'),
            ('pain_score', 'Pain'),
            ('follower_funding', 'Funding'),
            ('follower_ls_posit_long', 'LS_POSIT'),
            ('follower_ls_ratio_long', 'LS_RATIO'),
            ('follower_ls_account_long', 'LS_ACCOUNT'),
        ]:
            item = diff.get(key)
            if not item:
                continue
            delta = item.get('delta')
            if delta is None:
                continue
            if key in ('btc_health_score', 'follower_health_score', 'pain_score') and abs(delta) < 5:
                continue
            parts.append(f'{label} {item.get("from")} → {item.get("to")} ({_fmt_delta(delta)})')

        for key, label in [
            ('verdict', 'Verdict'),
            ('entry_timing', 'Timing'),
            ('oi_trend', 'OI'),
            ('liq_trend', 'Liq'),
            ('follower_funding_sign', 'Funding sign'),
            ('btc_spread_regime', 'BTC spread regime'),
            ('follower_spread_regime', 'Follower spread regime'),
            ('btc_narrative', 'BTC narrative'),
            ('follower_narrative', 'Follower narrative'),
        ]:
            item = diff.get(key)
            if item:
                parts.append(f'{label} {item.get("from")} → {item.get("to")}')

        if not parts:
            return base

        return base + ': ' + ' | '.join(parts[:5])

    def _diagnose(self, event_type: str, trade: dict, snapshot: dict, previous: dict | None, diff: dict) -> dict:
        pnl_delta = (diff.get('pnl_pct') or {}).get('delta')
        direction = str(snapshot.get('direction') or '').upper()
        symbol = snapshot.get('symbol')
        severity = 'INFO'
        if event_type in ('BTC_STATE_CHANGE', 'FOLLOWER_STATE_CHANGE', 'CLOSE'):
            severity = 'HIGH'
        elif event_type in ('PAIN_MOVE', 'VERDICT_CHANGE', 'BTC_HEALTH_MOVE', 'FOLLOWER_HEALTH_MOVE'):
            severity = 'MEDIUM'

        drivers = []
        risks = []
        supports = []

        follower_status = snapshot.get('follower_health_status')
        btc_status = snapshot.get('btc_health_status')
        pain = snapshot.get('pain_score')
        verdict = str(snapshot.get('verdict') or '').upper()
        funding = snapshot.get('follower_funding')
        ls_account = snapshot.get('follower_ls_account_long')
        ls_ratio = snapshot.get('follower_ls_ratio_long')
        follower_spread = snapshot.get('follower_spread')
        btc_spread = snapshot.get('btc_spread')
        follower_votes = snapshot.get('follower_dominant_votes')
        btc_votes = snapshot.get('btc_dominant_votes')

        if btc_status in ('SAFE', 'SAFE+'):
            supports.append(f'BTC is {btc_status}')
        elif btc_status in ('WARNING', 'EXIT'):
            risks.append(f'BTC is {btc_status}')

        if follower_status in ('SAFE', 'SAFE+'):
            supports.append(f'{_short(symbol)} is {follower_status}')
        elif follower_status in ('WARNING', 'EXIT'):
            risks.append(f'{_short(symbol)} is {follower_status}')

        if pain is not None:
            if pain >= 50:
                supports.append(f'Pain is elevated ({round(pain, 1)})')
            elif pain < 20:
                risks.append(f'Pain is weak ({round(pain, 1)})')

        if verdict:
            if 'BUILDING' in verdict or 'ACTIVE' in verdict:
                supports.append(f'Verdict supports pressure: {verdict}')
            elif 'NO CLEAR' in verdict or 'COOLING' in verdict or 'HAPPENED' in verdict:
                risks.append(f'Verdict weakens setup: {verdict}')

        if funding is not None:
            if direction == 'SHORT' and funding > 0:
                supports.append('Follower next funding is positive')
            elif direction == 'SHORT' and funding < 0:
                risks.append('Follower next funding is negative')
            elif direction == 'LONG' and funding < 0:
                supports.append('Follower next funding is negative')
            elif direction == 'LONG' and funding > 0:
                risks.append('Follower next funding is positive')

        if ls_account is not None and ls_account >= 70:
            supports.append(f'LS_ACCOUNT is crowded ({round(ls_account, 1)}%)')
        if ls_ratio is not None and ls_ratio >= 70:
            supports.append(f'LS_RATIO is crowded ({round(ls_ratio, 1)}%)')
        if follower_spread is not None and follower_spread >= 20:
            supports.append(f'Follower spread is strong ({round(follower_spread, 1)})')
        if btc_spread is not None and btc_spread >= 20:
            supports.append(f'BTC spread is strong ({round(btc_spread, 1)})')
        if follower_votes is not None and follower_votes >= 3:
            supports.append('Follower votes are fully aligned (3/3)')
        elif follower_votes is not None and follower_votes < 2:
            risks.append(f'Follower votes are weak ({follower_votes}/3)')
        if btc_votes is not None and btc_votes >= 3:
            supports.append('BTC votes are fully aligned (3/3)')
        elif btc_votes is not None and btc_votes < 2:
            risks.append(f'BTC votes are weak ({btc_votes}/3)')

        # Main driver = biggest absolute numeric change in this event.
        numeric_changes = {
            k: abs(v.get('delta') or 0)
            for k, v in diff.items()
            if isinstance(v, dict) and isinstance(v.get('delta'), (int, float))
        }
        if numeric_changes:
            main_change = max(numeric_changes, key=numeric_changes.get)
            drivers.append(main_change)

        if event_type == 'CLOSE':
            result = 'WIN' if (snapshot.get('pnl_pct') or 0) > 0 else 'LOSS'
        else:
            result = _direction_for_trade(direction, pnl_delta).upper()

        return {
            'event_type': event_type,
            'severity': severity,
            'result_context': result,
            'main_driver': drivers[0] if drivers else None,
            'supporting_factors': supports[:6],
            'risk_factors': risks[:6],
            'diff_keys': list(diff.keys())[:20],
        }

    def _insert_event(
        self,
        *,
        trade: dict,
        symbol_states: dict,
        driver: str,
        event_type: str,
        event_label: str,
        reason: str,
        pnl_bucket: int | None = None,
        diff: dict | None = None,
        diagnosis: dict | None = None,
    ):
        snapshot = self._build_snapshot(trade, symbol_states, driver)

        if pnl_bucket is not None:
            snapshot['pnl_bucket'] = pnl_bucket

        diff = diff or {}
        diagnosis = diagnosis or self._diagnose(event_type, trade, snapshot, None, diff)

        change_summary = self._change_summary(diff)
        story_text = self._story_line(event_label, snapshot, diff, diagnosis)
        severity = diagnosis.get('severity') or 'INFO'
        driver_label = diagnosis.get('main_driver') or event_type

        snapshot_json = json.dumps(snapshot.get('raw') or {}, ensure_ascii=False, separators=(',', ':'))
        diff_json = json.dumps(diff, ensure_ascii=False, separators=(',', ':'))
        diagnosis_json = json.dumps(diagnosis, ensure_ascii=False, separators=(',', ':'))

        with self.trade_store.db.connect() as con:
            con.execute(
                """
                INSERT INTO btc_radar_trade_lifecycle (
                    trade_id, symbol, direction, status, event_type, event_label, pnl_bucket,
                    pnl_pct, pnl_usd, current_price,
                    btc_health_status, btc_health_score, btc_funding, btc_ls_posit_long, btc_ls_ratio_long, btc_ls_account_long,
                    btc_spread, btc_spread_regime, btc_long_votes, btc_short_votes, btc_dominant_votes, btc_long_score, btc_short_score, btc_narrative,
                    btc_cvd, btc_cvd_15m_ago, btc_cvd_delta_15m, btc_cvd_trend,
                    follower_health_status, follower_health_score, follower_funding, follower_ls_posit_long, follower_ls_ratio_long, follower_ls_account_long,
                    follower_spread, follower_spread_regime, follower_long_votes, follower_short_votes, follower_dominant_votes, follower_long_score, follower_short_score, follower_narrative,
                    follower_cvd, follower_cvd_15m_ago, follower_cvd_delta_15m, follower_cvd_trend,
                    followers_consensus_short_score, followers_consensus_short_state, followers_consensus_long_score, followers_consensus_long_state,
                    followers_consensus_positive_funding_count, followers_consensus_negative_funding_count, followers_consensus_transition_count, followers_consensus_strong_agreement_count, followers_consensus_json,
                    pain_score, entry_timing, verdict, oi_trend, liq_trend,
                    reason, snapshot_json, created_at,
                    diff_json, change_summary, diagnosis_json, story_text, driver_label, severity
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    snapshot['trade_id'], snapshot['symbol'], snapshot['direction'], snapshot['status'], event_type, event_label, snapshot['pnl_bucket'],
                    snapshot['pnl_pct'], snapshot['pnl_usd'], snapshot['current_price'],
                    snapshot['btc_health_status'], snapshot['btc_health_score'], snapshot['btc_funding'], snapshot['btc_ls_posit_long'], snapshot['btc_ls_ratio_long'], snapshot['btc_ls_account_long'],
                    snapshot['btc_spread'], snapshot['btc_spread_regime'], snapshot['btc_long_votes'], snapshot['btc_short_votes'], snapshot['btc_dominant_votes'], snapshot['btc_long_score'], snapshot['btc_short_score'], snapshot['btc_narrative'],
                    snapshot['btc_cvd'], snapshot['btc_cvd_15m_ago'], snapshot['btc_cvd_delta_15m'], snapshot['btc_cvd_trend'],
                    snapshot['follower_health_status'], snapshot['follower_health_score'], snapshot['follower_funding'], snapshot['follower_ls_posit_long'], snapshot['follower_ls_ratio_long'], snapshot['follower_ls_account_long'],
                    snapshot['follower_spread'], snapshot['follower_spread_regime'], snapshot['follower_long_votes'], snapshot['follower_short_votes'], snapshot['follower_dominant_votes'], snapshot['follower_long_score'], snapshot['follower_short_score'], snapshot['follower_narrative'],
                    snapshot['follower_cvd'], snapshot['follower_cvd_15m_ago'], snapshot['follower_cvd_delta_15m'], snapshot['follower_cvd_trend'],
                    snapshot['followers_consensus_short_score'], snapshot['followers_consensus_short_state'], snapshot['followers_consensus_long_score'], snapshot['followers_consensus_long_state'],
                    snapshot['followers_consensus_positive_funding_count'], snapshot['followers_consensus_negative_funding_count'], snapshot['followers_consensus_transition_count'], snapshot['followers_consensus_strong_agreement_count'], snapshot['followers_consensus_json'],
                    snapshot['pain_score'], snapshot['entry_timing'], snapshot['verdict'], snapshot['oi_trend'], snapshot['liq_trend'],
                    reason, snapshot_json, _now(),
                    diff_json, change_summary, diagnosis_json, story_text, driver_label, severity,
                ),
            )

    def _change_summary(self, diff: dict) -> str:
        if not diff:
            return 'Initial snapshot'
        parts = []
        for key, item in diff.items():
            if not isinstance(item, dict):
                continue
            frm = item.get('from')
            to = item.get('to')
            delta = item.get('delta')
            if delta is None:
                parts.append(f'{key}: {frm} → {to}')
            else:
                parts.append(f'{key}: {frm} → {to} ({_fmt_delta(delta)})')
        return ' | '.join(parts[:8])

    def _story_line(self, event_label: str, snapshot: dict, diff: dict, diagnosis: dict) -> str:
        symbol = _short(snapshot.get('symbol'))
        pnl = snapshot.get('pnl_pct')
        btc = f"{snapshot.get('btc_health_status')} {snapshot.get('btc_health_score')}"
        follower = f"{snapshot.get('follower_health_status')} {snapshot.get('follower_health_score')}"
        main = diagnosis.get('main_driver')
        if main:
            return f'{event_label}: {symbol} PnL {round(pnl or 0, 2)}%, BTC {btc}, {symbol} {follower}. Main change: {main}.'
        return f'{event_label}: {symbol} PnL {round(pnl or 0, 2)}%, BTC {btc}, {symbol} {follower}.'

    def _last_event(self, trade_id: int) -> dict | None:
        with self.trade_store.db.connect() as con:
            row = con.execute(
                "SELECT * FROM btc_radar_trade_lifecycle WHERE trade_id=? ORDER BY id DESC LIMIT 1",
                (trade_id,),
            ).fetchone()
            return dict(row) if row else None

    def trade_options(self, status: str = 'all') -> list[dict]:
        status = str(status or 'all').lower()
        sql = """
            SELECT id, symbol, direction, size_usd, entry_price, current_price,
                   pnl_usd, pnl_pct, status, opened_at, closed_at, exit_price
            FROM btc_radar_manual_trades
            WHERE 1=1
        """
        if status == 'open':
            sql += " AND status='OPEN'"
        elif status == 'closed':
            sql += " AND status='CLOSED'"
        sql += " ORDER BY CASE WHEN status='OPEN' THEN 0 ELSE 1 END, id DESC"
        with self.trade_store.db.connect() as con:
            rows = [dict(r) for r in con.execute(sql).fetchall()]

        if status in ('all', 'closed'):
            with self.trade_store.db.connect() as con:
                closed = [dict(r) for r in con.execute("""
                    SELECT trade_id AS id, symbol, direction, size_usd, entry_price, exit_price AS current_price,
                           pnl_usd, pnl_pct, 'CLOSED' AS status, opened_at, closed_at, exit_price
                    FROM btc_radar_closed_trades
                    ORDER BY id DESC
                    LIMIT 100
                """).fetchall()]
            seen = {r.get('id') for r in rows}
            rows.extend([r for r in closed if r.get('id') not in seen])

        return rows

    def events_for_trade(self, trade_id: int) -> list[dict]:
        with self.trade_store.db.connect() as con:
            rows = [dict(r) for r in con.execute(
                "SELECT * FROM btc_radar_trade_lifecycle WHERE trade_id=? ORDER BY id ASC",
                (trade_id,),
            ).fetchall()]

        # Decode V2 JSON for API consumers while keeping original columns.
        for r in rows:
            for col in ('diff_json', 'diagnosis_json'):
                raw = r.get(col)
                key = col.replace('_json', '')
                try:
                    r[key] = json.loads(raw) if raw else {}
                except Exception:
                    r[key] = {}
        return rows

    def summary_for_trade(self, trade_id: int) -> dict:
        events = self.events_for_trade(trade_id)
        trade = None
        for t in self.trade_options('all'):
            if int(t.get('id') or 0) == int(trade_id):
                trade = t
                break

        best = max([_num(e.get('pnl_pct'), 0) or 0 for e in events], default=0)
        worst = min([_num(e.get('pnl_pct'), 0) or 0 for e in events], default=0)
        first = events[0] if events else {}
        last = events[-1] if events else {}

        diagnosis = self._trade_diagnosis(events, trade)
        story = self._trade_story(events)

        return {
            'trade': trade,
            'events': events,
            'summary': {
                'best_pnl_pct': best,
                'worst_pnl_pct': worst,
                'event_count': len(events),
                'entry': first,
                'latest': last,
                'btc_changed': bool(first and last and first.get('btc_health_status') != last.get('btc_health_status')),
                'follower_changed': bool(first and last and first.get('follower_health_status') != last.get('follower_health_status')),
                'verdict_changed': bool(first and last and first.get('verdict') != last.get('verdict')),
                'diagnosis': diagnosis,
                'story': story,
            }
        }

    def _trade_story(self, events: list[dict]) -> list[str]:
        if not events:
            return []
        story = []
        for e in events[:30]:
            line = e.get('story_text') or f"{e.get('event_label')}: PnL {e.get('pnl_pct')}%"
            story.append(line)
        return story

    def _trade_diagnosis(self, events: list[dict], trade: dict | None) -> dict:
        if not events:
            return {
                'primary_driver': None,
                'supporting_factors': [],
                'risk_factors': [],
                'conclusion': 'No lifecycle events recorded yet.',
            }

        first = events[0]
        last = events[-1]
        pnl = _num((trade or {}).get('pnl_pct'), _num(last.get('pnl_pct'), 0)) or 0

        support = []
        risks = []

        def changed(field, label):
            a = first.get(field)
            b = last.get(field)
            if a == b:
                return None
            return f'{label}: {a} → {b}'

        for item in [
            changed('btc_health_status', 'BTC state'),
            changed('follower_health_status', 'Follower state'),
            changed('verdict', 'Verdict'),
            changed('entry_timing', 'Entry timing'),
            changed('oi_trend', 'OI trend'),
            changed('liq_trend', 'Liq trend'),
        ]:
            if item:
                risks.append(item)

        for field, label in [
            ('btc_health_score', 'BTC health'),
            ('follower_health_score', 'Follower health'),
            ('pain_score', 'Pain'),
            ('follower_funding', 'Funding'),
            ('follower_ls_posit_long', 'LS_POSIT'),
            ('follower_ls_ratio_long', 'LS_RATIO'),
            ('follower_ls_account_long', 'LS_ACCOUNT'),
            ('btc_spread', 'BTC Spread'),
            ('follower_spread', 'Follower Spread'),
            ('btc_dominant_votes', 'BTC Votes'),
            ('follower_dominant_votes', 'Follower Votes'),
        ]:
            a = _num(first.get(field))
            b = _num(last.get(field))
            if a is None or b is None:
                continue
            delta = round(b - a, 4)
            if delta != 0:
                text = f'{label}: {a} → {b} ({_fmt_delta(delta)})'
                if field in ('follower_ls_ratio_long', 'follower_ls_account_long') and b >= 70:
                    support.append(text)
                elif field == 'pain_score' and delta < -10:
                    risks.append(text)
                elif field in ('btc_health_score', 'follower_health_score') and delta < -10:
                    risks.append(text)
                else:
                    support.append(text)

        event_types = [e.get('event_type') for e in events]
        primary = None
        if 'VERDICT_CHANGE' in event_types:
            primary = 'verdict_change'
        elif 'PAIN_MOVE' in event_types:
            primary = 'pain_move'
        elif 'FOLLOWER_STATE_CHANGE' in event_types:
            primary = 'follower_state_change'
        elif 'BTC_STATE_CHANGE' in event_types:
            primary = 'btc_state_change'
        elif 'PNL_BUCKET' in event_types:
            primary = 'price_pnl_movement'

        result = 'winning' if pnl > 0 else 'losing' if pnl < 0 else 'flat'
        conclusion = f'Trade is currently {result}. Main observed driver: {primary or "not enough data"}.'

        return {
            'primary_driver': primary,
            'supporting_factors': support[:8],
            'risk_factors': risks[:8],
            'conclusion': conclusion,
        }
