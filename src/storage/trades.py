from __future__ import annotations
from datetime import datetime, timezone
from .database import Database


def now() -> str: return datetime.now(timezone.utc).isoformat()


def _delta(current, previous):
    try:
        if current is None or previous is None:
            return None
        return round(float(current) - float(previous), 4)
    except Exception:
        return None


_ENTRY_META_COLUMNS = [
    'decision_judgment',
    'decision_snapshot_json',
    'entry_snapshot_version',
    'btc_state_at_entry',
    'btc_recommendation_at_entry',
    'btc_score_at_entry',
    'btc_spread_at_entry',
    'btc_long_votes_at_entry',
    'btc_short_votes_at_entry',
    'btc_dominant_votes_at_entry',
    'btc_long_score_at_entry',
    'btc_short_score_at_entry',
    'btc_narrative_at_entry',
    'btc_price_at_entry',
    'btc_ls_posit_long_at_entry',
    'btc_ls_posit_short_at_entry',
    'btc_ls_ratio_long_at_entry',
    'btc_ls_ratio_short_at_entry',
    'btc_ls_account_long_at_entry',
    'btc_ls_account_short_at_entry',
    'btc_funding_at_entry',
    'btc_oi_at_entry',
    'btc_vwap_at_entry',
    'btc_health_status_at_entry',
    'btc_health_score_at_entry',
    'btc_preferred_direction_at_entry',
    'follow_score_at_entry',
    'follower_price_at_entry',
    'follower_ls_posit_long_at_entry',
    'follower_ls_posit_short_at_entry',
    'follower_ls_ratio_long_at_entry',
    'follower_ls_ratio_short_at_entry',
    'follower_ls_account_long_at_entry',
    'follower_ls_account_short_at_entry',
    'follower_funding_at_entry',
    'follower_oi_at_entry',
    'follower_vwap_at_entry',
    'follower_health_status_at_entry',
    'follower_health_score_at_entry',
    'follower_preferred_direction_at_entry',
    'follower_spread_at_entry',
    'follower_long_votes_at_entry',
    'follower_short_votes_at_entry',
    'follower_dominant_votes_at_entry',
    'follower_long_score_at_entry',
    'follower_short_score_at_entry',
    'follower_narrative_at_entry',
    'followers_consensus_short_score_at_entry',
    'followers_consensus_short_state_at_entry',
    'followers_consensus_long_score_at_entry',
    'followers_consensus_long_state_at_entry',
    'followers_consensus_positive_funding_count_at_entry',
    'followers_consensus_negative_funding_count_at_entry',
    'followers_consensus_transition_count_at_entry',
    'followers_consensus_strong_agreement_count_at_entry',
    'followers_consensus_json',
    'btc_cvd_at_entry',
    'btc_cvd_15m_ago_at_entry',
    'btc_cvd_delta_15m_at_entry',
    'btc_cvd_trend_at_entry',
    'follower_cvd_at_entry',
    'follower_cvd_15m_ago_at_entry',
    'follower_cvd_delta_15m_at_entry',
    'follower_cvd_trend_at_entry',
]

_CLOSE_META_COLUMNS = [
    'btc_cvd_at_close',
    'btc_cvd_delta_15m_at_close',
    'btc_cvd_trend_at_close',
    'btc_cvd_delta_entry_to_close',
    'follower_cvd_at_close',
    'follower_cvd_delta_15m_at_close',
    'follower_cvd_trend_at_close',
    'follower_cvd_delta_entry_to_close',
]

_COLUMN_TYPES = {
    'entry_snapshot_version': 'TEXT',
    'btc_long_votes_at_entry': 'INTEGER',
    'btc_short_votes_at_entry': 'INTEGER',
    'btc_dominant_votes_at_entry': 'INTEGER',
    'btc_long_score_at_entry': 'REAL',
    'btc_short_score_at_entry': 'REAL',
    'btc_narrative_at_entry': 'TEXT',
    'btc_price_at_entry': 'REAL',
    'btc_ls_posit_short_at_entry': 'REAL',
    'btc_ls_ratio_short_at_entry': 'REAL',
    'btc_ls_account_short_at_entry': 'REAL',
    'btc_funding_at_entry': 'REAL',
    'btc_oi_at_entry': 'REAL',
    'btc_vwap_at_entry': 'REAL',
    'btc_health_status_at_entry': 'TEXT',
    'btc_health_score_at_entry': 'REAL',
    'btc_preferred_direction_at_entry': 'TEXT',
    'follower_price_at_entry': 'REAL',
    'follower_ls_posit_long_at_entry': 'REAL',
    'follower_ls_posit_short_at_entry': 'REAL',
    'follower_ls_ratio_long_at_entry': 'REAL',
    'follower_ls_ratio_short_at_entry': 'REAL',
    'follower_ls_account_long_at_entry': 'REAL',
    'follower_ls_account_short_at_entry': 'REAL',
    'follower_funding_at_entry': 'REAL',
    'follower_oi_at_entry': 'REAL',
    'follower_vwap_at_entry': 'REAL',
    'follower_health_status_at_entry': 'TEXT',
    'follower_health_score_at_entry': 'REAL',
    'follower_preferred_direction_at_entry': 'TEXT',
    'follower_spread_at_entry': 'REAL',
    'follower_long_votes_at_entry': 'INTEGER',
    'follower_short_votes_at_entry': 'INTEGER',
    'follower_dominant_votes_at_entry': 'INTEGER',
    'follower_long_score_at_entry': 'REAL',
    'follower_short_score_at_entry': 'REAL',
    'follower_narrative_at_entry': 'TEXT',
    'followers_consensus_short_score_at_entry': 'REAL',
    'followers_consensus_short_state_at_entry': 'TEXT',
    'followers_consensus_long_score_at_entry': 'REAL',
    'followers_consensus_long_state_at_entry': 'TEXT',
    'followers_consensus_positive_funding_count_at_entry': 'INTEGER',
    'followers_consensus_negative_funding_count_at_entry': 'INTEGER',
    'followers_consensus_transition_count_at_entry': 'INTEGER',
    'followers_consensus_strong_agreement_count_at_entry': 'INTEGER',
    'followers_consensus_json': 'TEXT',
    'btc_cvd_at_entry': 'REAL',
    'btc_cvd_15m_ago_at_entry': 'REAL',
    'btc_cvd_delta_15m_at_entry': 'REAL',
    'btc_cvd_trend_at_entry': 'TEXT',
    'follower_cvd_at_entry': 'REAL',
    'follower_cvd_15m_ago_at_entry': 'REAL',
    'follower_cvd_delta_15m_at_entry': 'REAL',
    'follower_cvd_trend_at_entry': 'TEXT',
    'btc_cvd_at_close': 'REAL',
    'btc_cvd_delta_15m_at_close': 'REAL',
    'btc_cvd_trend_at_close': 'TEXT',
    'btc_cvd_delta_entry_to_close': 'REAL',
    'follower_cvd_at_close': 'REAL',
    'follower_cvd_delta_15m_at_close': 'REAL',
    'follower_cvd_trend_at_close': 'TEXT',
    'follower_cvd_delta_entry_to_close': 'REAL',
    'exit_reason': 'TEXT',
    'auto_guard_reason': 'TEXT',
}


class TradeStore:
    def __init__(self, db: Database):
        self.db = db
        self._ensure_report_columns()

    def _ensure_report_columns(self):
        """Add report/monitor columns safely for existing BTCRadar databases."""
        tables = ['btc_radar_manual_trades', 'btc_radar_closed_trades']
        with self.db.connect() as con:
            for table in tables:
                existing = {row['name'] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
                for name, col_type in _COLUMN_TYPES.items():
                    if name not in existing:
                        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")

    def open_trade(self, symbol: str, direction: str, size_usd: float, entry_price: float, metadata: dict | None = None):
        """Open a manual research trade and persist the entry snapshot metadata."""
        meta = metadata or {}
        row = {
            'symbol': symbol,
            'direction': direction,
            'size_usd': size_usd,
            'entry_price': entry_price,
            'current_price': entry_price,
            'status': 'OPEN',
            'opened_at': now(),
        }
        for key in _ENTRY_META_COLUMNS:
            row[key] = meta.get(key)
        for key in _CLOSE_META_COLUMNS:
            row[key] = None

        columns = list(row.keys())
        placeholders = ','.join(['?'] * len(columns))
        sql = f"INSERT INTO btc_radar_manual_trades ({','.join(columns)}) VALUES ({placeholders})"
        with self.db.connect() as con:
            con.execute(sql, tuple(row[c] for c in columns))

    def close_trade(self, trade_id: int, exit_price: float, exit_reason: str | None = None, close_metadata: dict | None = None):
        t = self.get_trade(trade_id)
        if not t:
            return False
        close_meta = close_metadata or {}
        pnl_usd, pnl_pct = self._pnl(t, exit_price)
        closed_at = now()
        opened = datetime.fromisoformat(t['opened_at'])
        closed = datetime.fromisoformat(closed_at)
        duration = int((closed - opened).total_seconds())

        btc_cvd_close = close_meta.get('btc_cvd_at_close')
        follower_cvd_close = close_meta.get('follower_cvd_at_close')
        btc_delta_entry_to_close = _delta(btc_cvd_close, t.get('btc_cvd_at_entry'))
        follower_delta_entry_to_close = _delta(follower_cvd_close, t.get('follower_cvd_at_entry'))

        update_fields = {
            'status': 'CLOSED',
            'exit_price': exit_price,
            'current_price': exit_price,
            'pnl_usd': pnl_usd,
            'pnl_pct': pnl_pct,
            'closed_at': closed_at,
            'exit_reason': exit_reason,
            'auto_guard_reason': exit_reason,
            'btc_cvd_at_close': btc_cvd_close,
            'btc_cvd_delta_15m_at_close': close_meta.get('btc_cvd_delta_15m_at_close'),
            'btc_cvd_trend_at_close': close_meta.get('btc_cvd_trend_at_close'),
            'btc_cvd_delta_entry_to_close': btc_delta_entry_to_close,
            'follower_cvd_at_close': follower_cvd_close,
            'follower_cvd_delta_15m_at_close': close_meta.get('follower_cvd_delta_15m_at_close'),
            'follower_cvd_trend_at_close': close_meta.get('follower_cvd_trend_at_close'),
            'follower_cvd_delta_entry_to_close': follower_delta_entry_to_close,
        }

        closed_row = {
            'trade_id': trade_id,
            'symbol': t['symbol'],
            'direction': t['direction'],
            'size_usd': t['size_usd'],
            'entry_price': t['entry_price'],
            'exit_price': exit_price,
            'pnl_usd': pnl_usd,
            'pnl_pct': pnl_pct,
            'opened_at': t['opened_at'],
            'closed_at': closed_at,
            'duration_sec': duration,
            'exit_reason': exit_reason,
            'auto_guard_reason': exit_reason,
        }
        for key in _ENTRY_META_COLUMNS:
            closed_row[key] = t.get(key)
        for key in _CLOSE_META_COLUMNS:
            closed_row[key] = update_fields.get(key)

        set_clause = ', '.join([f'{k}=?' for k in update_fields])
        columns = list(closed_row.keys())
        placeholders = ','.join(['?'] * len(columns))
        sql = f"INSERT INTO btc_radar_closed_trades ({','.join(columns)}) VALUES ({placeholders})"

        with self.db.connect() as con:
            con.execute(
                f"UPDATE btc_radar_manual_trades SET {set_clause} WHERE id=?",
                tuple(update_fields.values()) + (trade_id,),
            )
            con.execute(sql, tuple(closed_row[c] for c in columns))
        return True

    def update_open_prices(self, price_map: dict[str, float]):
        with self.db.connect() as con:
            rows = con.execute("SELECT * FROM btc_radar_manual_trades WHERE status='OPEN'").fetchall()
            for r in rows:
                t = dict(r); price = price_map.get(t['symbol'])
                if price is None: continue
                pnl_usd, pnl_pct = self._pnl(t, price)
                con.execute('UPDATE btc_radar_manual_trades SET current_price=?, pnl_usd=?, pnl_pct=? WHERE id=?', (price, pnl_usd, pnl_pct, t['id']))

    def _pnl(self, t: dict, price: float) -> tuple[float, float]:
        entry = float(t['entry_price']); size = float(t.get('size_usd') or 0)
        if entry <= 0: return 0.0, 0.0
        pct = ((price - entry) / entry) * 100
        if t['direction'].upper() == 'SHORT': pct *= -1
        return round(size * pct / 100, 4), round(pct, 4)

    def get_trade(self, trade_id: int) -> dict | None:
        with self.db.connect() as con:
            row = con.execute('SELECT * FROM btc_radar_manual_trades WHERE id=?', (trade_id,)).fetchone()
            return dict(row) if row else None

    def open_trades(self):
        with self.db.connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM btc_radar_manual_trades WHERE status='OPEN' ORDER BY id DESC").fetchall()]

    def closed_trades(self, limit: int = 50):
        with self.db.connect() as con:
            return [dict(r) for r in con.execute('SELECT * FROM btc_radar_closed_trades ORDER BY id DESC LIMIT ?', (limit,)).fetchall()]

    def stats(self, initial_equity: float = 1000.0):
        with self.db.connect() as con:
            open_rows = [dict(r) for r in con.execute("SELECT * FROM btc_radar_manual_trades WHERE status='OPEN'").fetchall()]
            closed_rows = [dict(r) for r in con.execute("SELECT * FROM btc_radar_closed_trades").fetchall()]

        open_pnl = round(sum(float(r.get('pnl_usd') or 0) for r in open_rows), 4)
        realized_pnl = round(sum(float(r.get('pnl_usd') or 0) for r in closed_rows), 4)
        total_closed = len(closed_rows)
        wins = sum(1 for r in closed_rows if float(r.get('pnl_usd') or 0) > 0)
        win_rate = round((wins / total_closed * 100), 2) if total_closed else 0.0
        equity = round(float(initial_equity) + realized_pnl + open_pnl, 4)
        equity_pct = round(((equity - float(initial_equity)) / float(initial_equity) * 100), 4) if initial_equity else 0.0

        return {
            'initial_equity': float(initial_equity),
            'equity': equity,
            'equity_pct': equity_pct,
            'realized_pnl': realized_pnl,
            'total_trades': total_closed,
            'wins': wins,
            'losses': max(0, total_closed - wins),
            'win_rate': win_rate,
            'open_positions': len(open_rows),
            'open_pnl': open_pnl,
        }
