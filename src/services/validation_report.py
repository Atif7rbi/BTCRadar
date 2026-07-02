from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable


REQUIRED_METADATA = [
    'entry_snapshot_version',
    'decision_snapshot_json',
    'btc_spread_at_entry',
    'btc_state_at_entry',
    'btc_recommendation_at_entry',
    'btc_score_at_entry',
    'btc_long_votes_at_entry',
    'btc_short_votes_at_entry',
    'btc_ls_posit_long_at_entry',
    'btc_ls_posit_short_at_entry',
    'btc_ls_ratio_long_at_entry',
    'btc_ls_ratio_short_at_entry',
    'btc_ls_account_long_at_entry',
    'btc_ls_account_short_at_entry',
    'btc_funding_at_entry',
    'btc_oi_at_entry',
    'btc_health_status_at_entry',
    'btc_health_score_at_entry',
    'btc_preferred_direction_at_entry',
    'follow_score_at_entry',
    'follower_ls_posit_long_at_entry',
    'follower_ls_posit_short_at_entry',
    'follower_ls_ratio_long_at_entry',
    'follower_ls_ratio_short_at_entry',
    'follower_ls_account_long_at_entry',
    'follower_ls_account_short_at_entry',
    'follower_funding_at_entry',
    'follower_oi_at_entry',
    'follower_health_status_at_entry',
    'follower_health_score_at_entry',
    'follower_preferred_direction_at_entry',
    'btc_cvd_trend_at_entry',
    'btc_cvd_delta_15m_at_entry',
    'follower_cvd_trend_at_entry',
    'follower_cvd_delta_15m_at_entry',
]


def generate_validation_report(db, options: dict | None = None) -> dict:
    options = options or {}
    rows = _closed_trade_rows(db, options)
    return ValidationReport(rows, options).to_dict()


class ValidationReport:
    """Validation-only report for closed trades.

    This layer measures the current closed trade sample. It intentionally does
    not change strategy rules, BTC narrative, follow scoring, or UI behavior.
    """

    def __init__(self, rows: list[dict], options: dict | None = None):
        self.rows = rows
        self.options = options or {}

    def to_dict(self) -> dict:
        summary = self._summary(self.rows)
        sample_quality = self._sample_quality(self.rows)
        risk_flags = self._risk_flags(self.rows, sample_quality)
        return {
            'generated_at': _utc_now(),
            'report_type': 'validation_v1',
            'scope': {
                'source': 'btc_radar_closed_trades',
                'period': self.options.get('period', 'all'),
                'symbols': self.options.get('symbols') or ['ALL'],
            },
            'summary': summary,
            'sample_quality': sample_quality,
            'entry_validation': self._entry_validation(),
            'alignment_validation': self._alignment_validation(),
            'funding_validation': self._funding_validation(),
            'cvd_validation': self._cvd_validation(),
            'exit_validation': self._exit_validation(),
            'symbol_validation': self._symbol_validation(),
            'risk_flags': risk_flags,
            'conclusions': self._conclusions(summary, sample_quality, risk_flags),
            'next_data_needed': self._next_data_needed(),
        }

    def _summary(self, rows: list[dict]) -> dict:
        total = len(rows)
        wins = [r for r in rows if _num(r.get('pnl_usd')) > 0]
        losses = [r for r in rows if _num(r.get('pnl_usd')) <= 0]
        gross_profit = round(sum(_num(r.get('pnl_usd')) for r in wins), 4)
        gross_loss = round(sum(_num(r.get('pnl_usd')) for r in losses), 4)
        net_pnl = round(gross_profit + gross_loss, 4)
        profit_factor = round(gross_profit / abs(gross_loss), 3) if gross_loss < 0 else None
        return {
            'sample_size': total,
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': _pct(len(wins), total),
            'net_pnl_usd': net_pnl,
            'gross_profit_usd': gross_profit,
            'gross_loss_usd': gross_loss,
            'profit_factor': profit_factor,
            'avg_pnl_pct': _avg([_num(r.get('pnl_pct')) for r in rows]),
            'avg_winner_pct': _avg([_num(r.get('pnl_pct')) for r in wins]),
            'avg_loser_pct': _avg([_num(r.get('pnl_pct')) for r in losses]),
            'avg_duration_sec': _avg([_num(r.get('duration_sec')) for r in rows if _num(r.get('duration_sec')) > 0]),
        }

    def _sample_quality(self, rows: list[dict]) -> dict:
        total = len(rows)
        missing_by_field = {
            field: sum(1 for r in rows if _missing(r.get(field)))
            for field in REQUIRED_METADATA
        }
        rows_with_missing = sum(
            1 for r in rows
            if any(_missing(r.get(field)) for field in REQUIRED_METADATA)
        )
        completeness = 0.0
        if total and REQUIRED_METADATA:
            present = (total * len(REQUIRED_METADATA)) - sum(missing_by_field.values())
            completeness = round((present / (total * len(REQUIRED_METADATA))) * 100, 2)
        return {
            'sample_size': total,
            'low_sample': total < 30,
            'minimum_recommended_sample': 30,
            'metadata_completeness_pct': completeness,
            'rows_with_missing_metadata': rows_with_missing,
            'missing_metadata_by_field': missing_by_field,
            'legacy_trade_count': rows_with_missing,
            'can_prove_edge': False,
            'edge_limitation': 'Closed manual trades can validate the recorded sample, but cannot prove full strategy edge without opportunity-set and forward-return data.',
        }

    def _entry_validation(self) -> dict:
        return {
            'btc_spread_buckets': _bucket_stats(
                self.rows,
                _btc_spread_bucket,
                ['Spread < 10', 'Spread 10-20', 'Spread 20-30', 'Spread 30+', 'Legacy / Missing'],
            ),
            'btc_state': _bucket_stats(self.rows, lambda r: _label(r.get('btc_state_at_entry'))),
            'btc_recommendation': _bucket_stats(self.rows, lambda r: _label(r.get('btc_recommendation_at_entry'))),
            'follow_score_buckets': _bucket_stats(
                self.rows,
                _follow_score_bucket,
                ['Follow < 50', 'Follow 50-65', 'Follow 65-70', 'Follow 70+', 'Legacy / Missing'],
            ),
        }

    def _alignment_validation(self) -> dict:
        return {
            'trade_direction_alignment': _bucket_stats(
                self.rows,
                _direction_alignment,
                ['BTC+Follower aligned', 'BTC aligned only', 'Follower aligned only', 'Not aligned', 'WAIT / Missing'],
            ),
            'health_matrix': _bucket_stats(self.rows, _health_matrix_label),
            'btc_health': _bucket_stats(self.rows, lambda r: _health_label(r.get('btc_health_status_at_entry'))),
            'follower_health': _bucket_stats(self.rows, lambda r: _health_label(r.get('follower_health_status_at_entry'))),
        }

    def _funding_validation(self) -> dict:
        return {
            'btc_funding_buckets': _bucket_stats(self.rows, lambda r: _funding_bucket(r.get('btc_funding_at_entry'))),
            'follower_funding_buckets': _bucket_stats(self.rows, lambda r: _funding_bucket(r.get('follower_funding_at_entry'))),
            'follower_funding_by_direction': _bucket_stats(self.rows, _funding_direction_label),
        }

    def _cvd_validation(self) -> dict:
        return {
            'btc_cvd_trend_at_entry': _bucket_stats(self.rows, lambda r: _label(r.get('btc_cvd_trend_at_entry'))),
            'follower_cvd_trend_at_entry': _bucket_stats(self.rows, lambda r: _label(r.get('follower_cvd_trend_at_entry'))),
            'btc_cvd_entry_to_close': _bucket_stats(self.rows, lambda r: _delta_bucket(r.get('btc_cvd_delta_entry_to_close'))),
            'follower_cvd_entry_to_close': _bucket_stats(self.rows, lambda r: _delta_bucket(r.get('follower_cvd_delta_entry_to_close'))),
            'cvd_trade_alignment': _bucket_stats(
                self.rows,
                _cvd_trade_alignment,
                ['CVD with trade', 'CVD against trade', 'CVD neutral', 'Legacy / Missing'],
            ),
        }

    def _exit_validation(self) -> dict:
        return {
            'exit_reason': _bucket_stats(self.rows, lambda r: _label(r.get('exit_reason') or r.get('auto_guard_reason'))),
            'duration_buckets': _bucket_stats(
                self.rows,
                _duration_bucket,
                ['< 15m', '15m-1h', '1h-4h', '4h-24h', '1d+', 'Legacy / Missing'],
            ),
        }

    def _symbol_validation(self) -> dict:
        return {
            'by_symbol': _bucket_stats(self.rows, lambda r: _label(r.get('symbol'))),
            'by_symbol_direction': _bucket_stats(self.rows, lambda r: f'{_label(r.get("symbol"))} {_label(r.get("direction"))}'),
        }

    def _risk_flags(self, rows: list[dict], sample_quality: dict) -> list[dict]:
        flags = [
            {
                'code': 'SELECTION_BIAS_RISK',
                'active': True,
                'message': 'Report uses closed trades only; non-traded opportunities are not included.',
            },
            {
                'code': 'NO_COST_MODEL',
                'active': True,
                'message': 'Fees, slippage, and spread costs are not modeled in this report.',
            },
            {
                'code': 'NO_OPPORTUNITY_SET',
                'active': True,
                'message': 'BTCRadar opportunities that were not manually traded are not recorded here.',
            },
            {
                'code': 'LOW_SAMPLE',
                'active': bool(sample_quality.get('low_sample')),
                'message': f"Sample size is {len(rows)}; use at least {sample_quality.get('minimum_recommended_sample')} closed trades before treating buckets as reliable.",
            },
            {
                'code': 'MISSING_METADATA',
                'active': bool(sample_quality.get('rows_with_missing_metadata')),
                'message': f"{sample_quality.get('rows_with_missing_metadata')} closed trades have missing validation metadata.",
            },
            {
                'code': 'LEGACY_TRADES',
                'active': bool(sample_quality.get('legacy_trade_count')),
                'message': 'Some trades were opened before all validation metadata existed or have incomplete metadata.',
            },
        ]
        return flags

    def _conclusions(self, summary: dict, sample_quality: dict, risk_flags: list[dict]) -> list[str]:
        conclusions = []
        if not summary.get('sample_size'):
            return ['No closed trades are available for validation yet.']

        active = {f['code'] for f in risk_flags if f.get('active')}
        conclusions.append('Validation V1 measures the current closed-trade sample only; it does not prove full strategy edge.')
        if 'LOW_SAMPLE' in active:
            conclusions.append('Sample size is low, so bucket win rates can change materially with a few additional trades.')
        if 'MISSING_METADATA' in active:
            conclusions.append('Some rows have missing entry/close metadata; Legacy / Missing buckets should not be interpreted as strategy behavior.')
        if summary.get('net_pnl_usd', 0) > 0:
            conclusions.append('The recorded sample is net positive before fees/slippage, but cost modeling and opportunity-set validation are still missing.')
        elif summary.get('net_pnl_usd', 0) < 0:
            conclusions.append('The recorded sample is net negative before fees/slippage; inspect losing buckets before any strategy expansion.')
        else:
            conclusions.append('The recorded sample is approximately flat before fees/slippage.')
        return conclusions

    def _next_data_needed(self) -> list[str]:
        return [
            'Record every BTCRadar opportunity, including setups that were not manually traded.',
            'Store forward returns after each opportunity at 15m, 30m, 1h, 4h, and 24h.',
            'Add MFE and MAE for each trade/opportunity.',
            'Add fee, slippage, and spread cost assumptions.',
            'Tag market regime so validation can separate trend/range and high/low volatility periods.',
            'Increase closed-trade sample size before treating any bucket as reliable.',
        ]


def _closed_trade_rows(db, options: dict) -> list[dict]:
    period = str(options.get('period') or 'all').lower()
    custom_start = options.get('custom_start')
    start = _period_start(period, custom_start)
    symbols = options.get('symbols') or []
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(',')]
    symbols = [str(s).upper() for s in symbols if s and str(s).upper() != 'ALL']

    sql = 'SELECT * FROM btc_radar_closed_trades WHERE 1=1'
    params: list[Any] = []
    if start:
        sql += ' AND closed_at >= ?'
        params.append(start)
    if symbols:
        sql += ' AND symbol IN (%s)' % ','.join(['?'] * len(symbols))
        params.extend(symbols)
    sql += ' ORDER BY closed_at ASC, id ASC'

    with db.connect() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def _period_start(period: str, custom_start: str | None = None) -> str | None:
    now = datetime.now(timezone.utc)
    if period == '7d':
        return (now - timedelta(days=7)).isoformat()
    if period == '30d':
        return (now - timedelta(days=30)).isoformat()
    if period == '90d':
        return (now - timedelta(days=90)).isoformat()
    if period == 'custom' and custom_start:
        return f'{custom_start}T00:00:00+00:00'
    return None


def _bucket_stats(rows: list[dict], key_fn: Callable[[dict], str], label_order: list[str] | None = None) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(key_fn(row), []).append(row)
    labels = label_order or sorted(groups.keys())
    out = []
    for label in labels:
        group = groups.get(label, [])
        out.append(_stats_row(label, group))
    return out


def _stats_row(label: str, rows: list[dict]) -> dict:
    sample_size = len(rows)
    wins = sum(1 for r in rows if _num(r.get('pnl_usd')) > 0)
    gross_profit = round(sum(_num(r.get('pnl_usd')) for r in rows if _num(r.get('pnl_usd')) > 0), 4)
    gross_loss = round(sum(_num(r.get('pnl_usd')) for r in rows if _num(r.get('pnl_usd')) <= 0), 4)
    return {
        'label': label,
        'sample_size': sample_size,
        'wins': wins,
        'losses': max(0, sample_size - wins),
        'win_rate': _pct(wins, sample_size),
        'net_pnl_usd': round(gross_profit + gross_loss, 4),
        'avg_pnl_pct': _avg([_num(r.get('pnl_pct')) for r in rows]),
        'avg_duration_sec': _avg([_num(r.get('duration_sec')) for r in rows if _num(r.get('duration_sec')) > 0]),
    }


def _btc_spread_bucket(row: dict) -> str:
    spread = row.get('btc_spread_at_entry')
    if _missing(spread):
        return 'Legacy / Missing'
    value = _num(spread)
    if value < 10:
        return 'Spread < 10'
    if value < 20:
        return 'Spread 10-20'
    if value < 30:
        return 'Spread 20-30'
    return 'Spread 30+'


def _follow_score_bucket(row: dict) -> str:
    value = row.get('follow_score_at_entry')
    if _missing(value):
        return 'Legacy / Missing'
    score = _num(value)
    if score < 50:
        return 'Follow < 50'
    if score < 65:
        return 'Follow 50-65'
    if score < 70:
        return 'Follow 65-70'
    return 'Follow 70+'


def _direction_alignment(row: dict) -> str:
    direction = _text(row.get('direction'))
    btc_pref = _text(row.get('btc_preferred_direction_at_entry'))
    follower_pref = _text(row.get('follower_preferred_direction_at_entry'))
    if direction in ('', 'WAIT') or (btc_pref in ('', 'WAIT') and follower_pref in ('', 'WAIT')):
        return 'WAIT / Missing'
    btc_aligned = btc_pref == direction
    follower_aligned = follower_pref == direction
    if btc_aligned and follower_aligned:
        return 'BTC+Follower aligned'
    if btc_aligned:
        return 'BTC aligned only'
    if follower_aligned:
        return 'Follower aligned only'
    return 'Not aligned'


def _health_matrix_label(row: dict) -> str:
    return f'{_health_label(row.get("btc_health_status_at_entry"))} x {_health_label(row.get("follower_health_status_at_entry"))}'


def _funding_bucket(value: Any) -> str:
    if _missing(value):
        return 'Legacy / Missing'
    funding = _num(value)
    if funding <= -0.0002:
        return 'Funding <= -0.02%'
    if funding < -0.00005:
        return 'Funding -0.005% to -0.02%'
    if funding < 0:
        return 'Funding Slight Negative'
    if funding == 0:
        return 'Funding Neutral'
    if funding < 0.00005:
        return 'Funding Slight Positive'
    if funding < 0.0002:
        return 'Funding +0.005% to +0.02%'
    return 'Funding >= +0.02%'


def _funding_direction_label(row: dict) -> str:
    return f'{_label(row.get("direction"))} / {_funding_bucket(row.get("follower_funding_at_entry"))}'


def _delta_bucket(value: Any) -> str:
    if _missing(value):
        return 'Legacy / Missing'
    delta = _num(value)
    if delta > 0:
        return 'Positive delta'
    if delta < 0:
        return 'Negative delta'
    return 'Flat delta'


def _cvd_trade_alignment(row: dict) -> str:
    direction = _text(row.get('direction'))
    follower_delta = row.get('follower_cvd_delta_entry_to_close')
    if direction not in ('LONG', 'SHORT') or _missing(follower_delta):
        return 'Legacy / Missing'
    delta = _num(follower_delta)
    if delta == 0:
        return 'CVD neutral'
    if (direction == 'LONG' and delta > 0) or (direction == 'SHORT' and delta < 0):
        return 'CVD with trade'
    return 'CVD against trade'


def _duration_bucket(row: dict) -> str:
    value = row.get('duration_sec')
    if _missing(value) or _num(value) <= 0:
        return 'Legacy / Missing'
    minutes = _num(value) / 60
    if minutes < 15:
        return '< 15m'
    if minutes < 60:
        return '15m-1h'
    if minutes < 240:
        return '1h-4h'
    if minutes < 1440:
        return '4h-24h'
    return '1d+'


def _health_label(value: Any) -> str:
    text = _text(value)
    return text if text in ('SAFE+', 'SAFE', 'WARNING', 'EXIT') else 'Legacy / Missing'


def _label(value: Any) -> str:
    text = _text(value)
    return text if text else 'Legacy / Missing'


def _text(value: Any) -> str:
    return str(value or '').strip().upper()


def _missing(value: Any) -> bool:
    return value is None or value == ''


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _pct(numerator: float, denominator: float) -> float:
    return round((numerator / denominator) * 100, 2) if denominator else 0.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
