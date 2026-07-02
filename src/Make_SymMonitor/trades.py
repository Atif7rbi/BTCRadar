from __future__ import annotations
from datetime import datetime, timezone
from .database import Database


def now() -> str: return datetime.now(timezone.utc).isoformat()


_META_COLUMNS = [
    'decision_judgment',
    'decision_snapshot_json',
    'btc_state_at_entry',
    'btc_recommendation_at_entry',
    'btc_score_at_entry',
    'btc_spread_at_entry',
    'btc_ls_posit_long_at_entry',
    'btc_ls_ratio_long_at_entry',
    'btc_ls_account_long_at_entry',
    'follow_score_at_entry',
    'btc_health_status_at_entry',
    'btc_health_score_at_entry',
    'btc_preferred_direction_at_entry',
    'btc_funding_at_entry',
    'follower_health_status_at_entry',
    'follower_health_score_at_entry',
    'follower_preferred_direction_at_entry',
    'follower_funding_at_entry',
]


class TradeStore:
    def __init__(self, db: Database):
        self.db = db
        self._ensure_report_columns()

    def _ensure_report_columns(self):
        """Add report/monitor columns safely for existing BTCRadar databases."""
        columns = {
            'btc_health_status_at_entry': 'TEXT',
            'btc_health_score_at_entry': 'REAL',
            'btc_preferred_direction_at_entry': 'TEXT',
            'btc_funding_at_entry': 'REAL',
            'follower_health_status_at_entry': 'TEXT',
            'follower_health_score_at_entry': 'REAL',
            'follower_preferred_direction_at_entry': 'TEXT',
            'follower_funding_at_entry': 'REAL',
        }
        tables = ['btc_radar_manual_trades', 'btc_radar_closed_trades']
        with self.db.connect() as con:
            for table in tables:
                existing = {row['name'] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
                for name, col_type in columns.items():
                    if name not in existing:
                        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


    def open_trade(self, symbol: str, direction: str, size_usd: float, entry_price: float, metadata: dict | None = None):
        meta = metadata or {}
        with self.db.connect() as con:
            con.execute('''INSERT INTO btc_radar_manual_trades
            (symbol, direction, size_usd, entry_price, current_price, status, opened_at,
             decision_judgment, decision_snapshot_json, btc_state_at_entry, btc_recommendation_at_entry,
             btc_score_at_entry, btc_spread_at_entry, btc_ls_posit_long_at_entry, btc_ls_ratio_long_at_entry,
             btc_ls_account_long_at_entry, follow_score_at_entry,
             btc_health_status_at_entry, btc_health_score_at_entry, btc_preferred_direction_at_entry, btc_funding_at_entry,
             follower_health_status_at_entry, follower_health_score_at_entry, follower_preferred_direction_at_entry, follower_funding_at_entry)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                symbol,
                direction,
                size_usd,
                entry_price,
                entry_price,
                'OPEN',
                now(),
                meta.get('decision_judgment'),
                meta.get('decision_snapshot_json'),
                meta.get('btc_state_at_entry'),
                meta.get('btc_recommendation_at_entry'),
                meta.get('btc_score_at_entry'),
                meta.get('btc_spread_at_entry'),
                meta.get('btc_ls_posit_long_at_entry'),
                meta.get('btc_ls_ratio_long_at_entry'),
                meta.get('btc_ls_account_long_at_entry'),
                meta.get('follow_score_at_entry'),
                meta.get('btc_health_status_at_entry'),
                meta.get('btc_health_score_at_entry'),
                meta.get('btc_preferred_direction_at_entry'),
                meta.get('btc_funding_at_entry'),
                meta.get('follower_health_status_at_entry'),
                meta.get('follower_health_score_at_entry'),
                meta.get('follower_preferred_direction_at_entry'),
                meta.get('follower_funding_at_entry'),
            ))

    def close_trade(self, trade_id: int, exit_price: float):
        t = self.get_trade(trade_id)
        if not t: return False
        pnl_usd, pnl_pct = self._pnl(t, exit_price)
        closed_at = now()
        opened = datetime.fromisoformat(t['opened_at'])
        closed = datetime.fromisoformat(closed_at)
        duration = int((closed - opened).total_seconds())
        with self.db.connect() as con:
            con.execute('''UPDATE btc_radar_manual_trades SET status='CLOSED', exit_price=?, current_price=?, pnl_usd=?, pnl_pct=?, closed_at=? WHERE id=?''',
                        (exit_price, exit_price, pnl_usd, pnl_pct, closed_at, trade_id))
            con.execute('''INSERT INTO btc_radar_closed_trades
            (trade_id, symbol, direction, size_usd, entry_price, exit_price, pnl_usd, pnl_pct, opened_at, closed_at, duration_sec,
             decision_judgment, decision_snapshot_json, btc_state_at_entry, btc_recommendation_at_entry,
             btc_score_at_entry, btc_spread_at_entry, btc_ls_posit_long_at_entry, btc_ls_ratio_long_at_entry,
             btc_ls_account_long_at_entry, follow_score_at_entry,
             btc_health_status_at_entry, btc_health_score_at_entry, btc_preferred_direction_at_entry, btc_funding_at_entry,
             follower_health_status_at_entry, follower_health_score_at_entry, follower_preferred_direction_at_entry, follower_funding_at_entry)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (trade_id, t['symbol'], t['direction'], t['size_usd'], t['entry_price'], exit_price, pnl_usd, pnl_pct,
             t['opened_at'], closed_at, duration,
             t.get('decision_judgment'), t.get('decision_snapshot_json'), t.get('btc_state_at_entry'), t.get('btc_recommendation_at_entry'),
             t.get('btc_score_at_entry'), t.get('btc_spread_at_entry'), t.get('btc_ls_posit_long_at_entry'), t.get('btc_ls_ratio_long_at_entry'),
             t.get('btc_ls_account_long_at_entry'), t.get('follow_score_at_entry'),
             t.get('btc_health_status_at_entry'), t.get('btc_health_score_at_entry'), t.get('btc_preferred_direction_at_entry'), t.get('btc_funding_at_entry'),
             t.get('follower_health_status_at_entry'), t.get('follower_health_score_at_entry'), t.get('follower_preferred_direction_at_entry'), t.get('follower_funding_at_entry')))
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
