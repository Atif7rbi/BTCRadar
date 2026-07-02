from __future__ import annotations
from datetime import datetime, timedelta, timezone
from ..models import RadarSignal, SymbolSnapshot
from .database import Database


class SignalStore:
    def __init__(self, db: Database): self.db = db

    def insert(self, sig: RadarSignal):
        with self.db.connect() as con:
            con.execute('''INSERT INTO btc_radar_signals
            (state, recommendation, score, spread, long_votes, short_votes, created_at)
            VALUES (?,?,?,?,?,?,?)''', (sig.state, sig.recommendation, sig.score, sig.spread, sig.long_votes, sig.short_votes, sig.created_at))

    def insert_spread_history(self, sig: RadarSignal, btc: SymbolSnapshot):
        with self.db.connect() as con:
            con.execute('''INSERT INTO btc_radar_spread_history
            (state, recommendation, score, spread, btc_ls_posit_long, btc_ls_ratio_long, btc_ls_account_long, ls_updated_at, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)''', (
                sig.state,
                sig.recommendation,
                sig.score,
                sig.spread,
                btc.ls_posit_long,
                btc.ls_ratio_long,
                btc.ls_account_long,
                btc.ls_updated_at,
                sig.created_at,
            ))

    def spread_trend(self) -> dict:
        with self.db.connect() as con:
            latest = con.execute('SELECT * FROM btc_radar_spread_history ORDER BY id DESC LIMIT 1').fetchone()
            if not latest:
                return {'now': None, 'one_hour': None, 'four_hour': None, 'direction': 'WAITING'}
            latest_d = dict(latest)
            latest_dt = _parse_dt(latest_d.get('created_at'))
            one_hour = self._closest_before(con, latest_dt - timedelta(hours=1)) if latest_dt else None
            four_hour = self._closest_before(con, latest_dt - timedelta(hours=4)) if latest_dt else None

        now_spread = _num(latest_d.get('spread'))
        h1_spread = _num(one_hour.get('spread')) if one_hour else None
        h4_spread = _num(four_hour.get('spread')) if four_hour else None
        direction = 'FLAT'
        ref = h1_spread if h1_spread is not None else h4_spread
        if ref is None or now_spread is None:
            direction = 'WAITING'
        elif now_spread >= ref + 2:
            direction = 'RISING'
        elif now_spread <= ref - 2:
            direction = 'FALLING'
        return {
            'now': now_spread,
            'one_hour': h1_spread,
            'four_hour': h4_spread,
            'direction': direction,
            'state': latest_d.get('state'),
            'updated_at': latest_d.get('created_at'),
        }

    def _closest_before(self, con, target_dt: datetime) -> dict | None:
        row = con.execute(
            'SELECT * FROM btc_radar_spread_history WHERE created_at <= ? ORDER BY created_at DESC LIMIT 1',
            (target_dt.isoformat(),),
        ).fetchone()
        return dict(row) if row else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except Exception:
        return None
