from __future__ import annotations

from datetime import datetime, timezone
import json
from statistics import mean
from .database import Database


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CoinalyzeStore:
    def __init__(self, db: Database):
        self.db = db

    def upsert_point(self, row: dict) -> None:
        symbol = row.get('symbol')
        ts = row.get('ts')
        if not symbol or ts is None:
            return

        payload = {
            'symbol': str(symbol).upper(),
            'coinalyze_symbol': row.get('coinalyze_symbol'),
            'ts': int(ts),
            'interval': row.get('interval') or '1hour',
            'oi': row.get('oi'),
            'funding_rate': row.get('funding_rate'),
            'predicted_funding_rate': row.get('predicted_funding_rate'),
            'ls_ratio': row.get('ls_ratio'),
            'ls_long': row.get('ls_long'),
            'ls_short': row.get('ls_short'),
            'long_liquidations': row.get('long_liquidations'),
            'short_liquidations': row.get('short_liquidations'),
            'raw_json': json.dumps(row.get('raw_json') or {}, ensure_ascii=False),
            'created_at': now(),
        }

        cols = list(payload.keys())
        placeholders = ','.join(['?'] * len(cols))
        update_cols = [c for c in cols if c not in ('symbol', 'ts')]
        update_sql = ','.join([f'{c}=COALESCE(excluded.{c},{c})' for c in update_cols])

        sql = f'''
        INSERT INTO btc_radar_coinalyze_history ({','.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(symbol, ts) DO UPDATE SET {update_sql}
        '''

        with self.db.connect() as con:
            con.execute(sql, [payload[c] for c in cols])

    def latest_by_symbols(self, symbols: list[str]) -> list[dict]:
        symbols = [s.upper() for s in symbols]
        if not symbols:
            return []
        q = ','.join(['?'] * len(symbols))
        sql = f'''
        SELECT h.*
        FROM btc_radar_coinalyze_history h
        JOIN (
            SELECT symbol, MAX(ts) AS max_ts
            FROM btc_radar_coinalyze_history
            WHERE symbol IN ({q})
            GROUP BY symbol
        ) m ON h.symbol=m.symbol AND h.ts=m.max_ts
        ORDER BY CASE h.symbol
        {''.join([f" WHEN '{s}' THEN {i}" for i, s in enumerate(symbols)])}
        ELSE 999 END
        '''
        with self.db.connect() as con:
            return [dict(r) for r in con.execute(sql, symbols).fetchall()]

    def history(self, symbol: str, limit: int = 48) -> list[dict]:
        with self.db.connect() as con:
            rows = [dict(r) for r in con.execute('''
                SELECT * FROM btc_radar_coinalyze_history
                WHERE symbol=?
                ORDER BY ts DESC
                LIMIT ?
            ''', (symbol.upper(), int(limit))).fetchall()]
        rows.reverse()
        return rows

    def trend_summary(self, symbols: list[str], lookback: int = 30) -> dict:
        out: dict[str, dict] = {}
        for symbol in symbols:
            rows = self.history(symbol, lookback)
            latest = rows[-1] if rows else None
            previous_1h = rows[-2] if len(rows) >= 2 else None
            previous_4h = rows[-5] if len(rows) >= 5 else None

            trend = {
                'ls_ratio_1h': self._delta(latest, previous_1h, 'ls_ratio'),
                'ls_ratio_4h': self._delta(latest, previous_4h, 'ls_ratio'),
                'funding_1h': self._delta(latest, previous_1h, 'funding_rate'),
                'funding_4h': self._delta(latest, previous_4h, 'funding_rate'),
                'oi_1h': self._delta(latest, previous_1h, 'oi'),
                'oi_4h': self._delta(latest, previous_4h, 'oi'),
                'oi_1h_pct': self._pct_delta(latest, previous_1h, 'oi'),
                'oi_4h_pct': self._pct_delta(latest, previous_4h, 'oi'),
                'long_liq_1h': self._delta(latest, previous_1h, 'long_liquidations'),
                'short_liq_1h': self._delta(latest, previous_1h, 'short_liquidations'),
            }

            analysis = self._analyze_pressure(rows, latest, trend)

            out[symbol.upper()] = {
                'symbol': symbol.upper(),
                'latest': latest,
                'history': rows,
                'trend': trend,
                'analysis': analysis,
            }
        return out

    def _analyze_pressure(self, rows: list[dict], latest: dict | None, trend: dict) -> dict:
        if not latest:
            return {
                'funding_trend': 'NO DATA',
                'oi_trend': 'NO DATA',
                'liquidation_trend': 'NO DATA',
                'crowding_state': 'NO DATA',
                'entry_timing': 'WAITING',
                'verdict': 'WAITING FOR DATA',
                'dominant_liquidation': 'NONE',
                'pain_score': 0,
                'confidence_score': 0,
                'notes': ['No Coinalyze data stored yet.'],
            }

        funding = self._num(latest.get('funding_rate'))
        oi_1h_pct = self._optional_num(trend.get('oi_1h_pct'))
        oi_4h_pct = self._optional_num(trend.get('oi_4h_pct'))
        funding_1h = self._optional_num(trend.get('funding_1h'))
        funding_4h = self._optional_num(trend.get('funding_4h'))
        long_liq = max(0.0, self._num(latest.get('long_liquidations')))
        short_liq = max(0.0, self._num(latest.get('short_liquidations')))
        total_liq = long_liq + short_liq

        prior_rows = rows[-6:-1] if len(rows) > 1 else []
        prior_totals = [
            max(0.0, self._num(r.get('long_liquidations'))) + max(0.0, self._num(r.get('short_liquidations')))
            for r in prior_rows
        ]
        avg_prior_liq = mean(prior_totals) if prior_totals else 0.0
        spike_ratio = round(total_liq / avg_prior_liq, 3) if avg_prior_liq > 0 else (999.0 if total_liq > 0 else 0.0)

        dominant = 'NONE'
        if long_liq > short_liq * 1.5 and long_liq > 0:
            dominant = 'LONG LIQ'
        elif short_liq > long_liq * 1.5 and short_liq > 0:
            dominant = 'SHORT LIQ'
        elif total_liq > 0:
            dominant = 'MIXED'

        funding_trend = self._trend_label(funding_1h, 0.0001, 'RISING', 'FALLING', 'FLAT')
        if funding_4h is not None and abs(funding_4h) > abs(funding_1h or 0) and abs(funding_4h) >= 0.0003:
            funding_trend = 'RISING 4H' if funding_4h > 0 else 'FALLING 4H'

        oi_trend = self._trend_label(oi_1h_pct, 0.2, 'RISING', 'FALLING', 'FLAT')
        if oi_4h_pct is not None and abs(oi_4h_pct) >= 1.0 and abs(oi_4h_pct) > abs(oi_1h_pct or 0):
            oi_trend = 'RISING 4H' if oi_4h_pct > 0 else 'FALLING 4H'

        if spike_ratio >= 3:
            liq_trend = 'SPIKE'
        elif spike_ratio >= 1.5:
            liq_trend = 'ELEVATED'
        elif total_liq > 0:
            liq_trend = 'NORMAL'
        else:
            liq_trend = 'NONE'

        notes: list[str] = []
        score = 0.0
        score += min(abs(oi_1h_pct or 0) * 6, 25)
        score += min(abs(oi_4h_pct or 0) * 3, 20)
        score += min(abs(funding or 0) * 1200, 20)
        score += 25 if liq_trend == 'SPIKE' else 12 if liq_trend == 'ELEVATED' else 4 if liq_trend == 'NORMAL' else 0
        if dominant in ('LONG LIQ', 'SHORT LIQ'):
            score += 10
        pain_score = int(max(0, min(round(score), 100)))

        if oi_trend.startswith('RISING') and liq_trend in ('NONE', 'NORMAL'):
            crowding_state = 'BUILDING'
            entry_timing = 'EARLY' if pain_score < 55 else 'DEVELOPING'
            verdict = 'CROWDING BUILDING'
            notes.append('OI is rising while liquidation pressure is still controlled.')
        elif oi_trend.startswith('RISING') and liq_trend in ('ELEVATED', 'SPIKE'):
            crowding_state = 'EXPANDING WITH PAIN'
            entry_timing = 'DEVELOPING'
            verdict = 'ACTIVE PRESSURE'
            notes.append('OI is rising while liquidation activity is elevated.')
        elif oi_trend.startswith('FALLING') and liq_trend in ('ELEVATED', 'SPIKE'):
            crowding_state = 'UNWINDING'
            entry_timing = 'AFTER FLUSH'
            verdict = 'PAIN EVENT LIKELY HAPPENED'
            notes.append('OI is falling while liquidations are elevated. The pain event may already be underway or completed.')
        elif oi_trend.startswith('FALLING'):
            crowding_state = 'COOLING'
            entry_timing = 'LATE'
            verdict = 'PRESSURE COOLING'
            notes.append('OI is falling. New entries may be late unless BTC crowding remains strong.')
        else:
            crowding_state = 'NEUTRAL'
            entry_timing = 'WAIT'
            verdict = 'NO CLEAR EDGE'
            notes.append('No strong pressure trend detected yet.')

        if dominant == 'LONG LIQ':
            notes.append('Long liquidation pressure is dominant.')
        elif dominant == 'SHORT LIQ':
            notes.append('Short liquidation pressure is dominant.')

        if funding > 0:
            notes.append('Funding is positive, meaning longs are paying shorts.')
        elif funding < 0:
            notes.append('Funding is negative, meaning shorts are paying longs.')

        confidence_score = min(
            100,
            max(
                0,
                pain_score
                + (10 if entry_timing in ('EARLY', 'DEVELOPING') else -10 if entry_timing in ('LATE', 'AFTER FLUSH') else 0),
            ),
        )

        return {
            'funding_trend': funding_trend,
            'oi_trend': oi_trend,
            'liquidation_trend': liq_trend,
            'crowding_state': crowding_state,
            'entry_timing': entry_timing,
            'verdict': verdict,
            'dominant_liquidation': dominant,
            'pain_score': pain_score,
            'confidence_score': confidence_score,
            'liquidation_spike_ratio': spike_ratio,
            'notes': notes,
        }

    @staticmethod
    def _delta(a: dict | None, b: dict | None, key: str) -> float | None:
        if not a or not b or a.get(key) is None or b.get(key) is None:
            return None
        try:
            return round(float(a.get(key)) - float(b.get(key)), 6)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _pct_delta(a: dict | None, b: dict | None, key: str) -> float | None:
        if not a or not b or a.get(key) is None or b.get(key) in (None, 0):
            return None
        try:
            old = float(b.get(key))
            if old == 0:
                return None
            return round(((float(a.get(key)) - old) / abs(old)) * 100, 4)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def _num(v, default: float = 0.0) -> float:
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _optional_num(v) -> float | None:
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _trend_label(v: float | None, threshold: float, up: str, down: str, flat: str) -> str:
        if v is None:
            return 'NO DATA'
        if v > threshold:
            return up
        if v < -threshold:
            return down
        return flat
