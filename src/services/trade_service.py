from __future__ import annotations
import json
from ..models import RadarSignal, classify_cvd_pressure, classify_cvd_trend
from ..storage.trades import TradeStore


class TradeService:
    def __init__(self, trade_store: TradeStore, market_service):
        self.store = trade_store
        self.market = market_service

    def open_trade(self, symbol: str, direction: str, size_usd: float, signal: RadarSignal | None = None, followers: list[dict] | None = None, symbol_states: dict | None = None):
        snap = self.market.snapshots.get(symbol)
        if not snap or snap.price is None:
            raise ValueError(f'No live price for {symbol}')
        metadata = self._build_decision_metadata(symbol, direction.upper(), signal, followers or [], symbol_states or {})
        self.store.open_trade(symbol, direction.upper(), float(size_usd), float(snap.price), metadata)

    def close_trade(self, trade_id: int, exit_reason: str | None = None):
        t = self.store.get_trade(trade_id)
        if not t: raise ValueError('Trade not found')
        snap = self.market.snapshots.get(t['symbol'])
        if not snap or snap.price is None:
            raise ValueError(f'No live price for {t["symbol"]}')
        close_metadata = self._build_close_metadata(t['symbol'])
        return self.store.close_trade(trade_id, float(snap.price), exit_reason, close_metadata)

    def sync_pnl(self):
        prices = {k: v.price for k, v in self.market.snapshots.items() if v.price is not None}
        self.store.update_open_prices(prices)
        return self.apply_auto_guard()

    def apply_auto_guard(self) -> list[dict]:
        cfg = self.market.cfg.get('auto_guard', {}) if hasattr(self.market, 'cfg') else {}
        if not bool(cfg.get('enabled', False)):
            return []

        tp = float(cfg.get('take_profit_pct', 10.0))
        sl = float(cfg.get('stop_loss_pct', -10.0))

        closed: list[dict] = []
        for t in self.store.open_trades():
            pnl_pct = float(t.get('pnl_pct') or 0.0)
            reason = None
            if pnl_pct >= tp:
                reason = 'TP_10_PERCENT'
            elif pnl_pct <= sl:
                reason = 'SL_10_PERCENT'

            if not reason:
                continue

            snap = self.market.snapshots.get(t['symbol'])
            if not snap or snap.price is None:
                continue

            close_metadata = self._build_close_metadata(t['symbol'])
            ok = self.store.close_trade(int(t['id']), float(snap.price), reason, close_metadata)
            if ok:
                closed.append({
                    'id': t['id'],
                    'symbol': t['symbol'],
                    'direction': t['direction'],
                    'reason': reason,
                    'pnl_pct': pnl_pct,
                })

        return closed

    def _build_close_metadata(self, symbol: str) -> dict:
        driver = self.market.cfg['symbols']['driver']
        btc = self.market.snapshots.get(driver)
        follower_snap = self.market.snapshots.get(symbol)
        return {
            'btc_cvd_at_close': _num(getattr(btc, 'cvd', None)) if btc else None,
            'btc_cvd_pressure_at_close': getattr(btc, 'cvd_pressure', None) if btc else None,
            'btc_cvd_delta_15m_at_close': _num(getattr(btc, 'cvd_delta_15m', None)) if btc else None,
            'btc_cvd_trend_at_close': getattr(btc, 'cvd_trend', None) if btc else None,
            'follower_cvd_at_close': _num(getattr(follower_snap, 'cvd', None)) if follower_snap else None,
            'follower_cvd_pressure_at_close': getattr(follower_snap, 'cvd_pressure', None) if follower_snap else None,
            'follower_cvd_delta_15m_at_close': _num(getattr(follower_snap, 'cvd_delta_15m', None)) if follower_snap else None,
            'follower_cvd_trend_at_close': getattr(follower_snap, 'cvd_trend', None) if follower_snap else None,
        }

    def _cvd_meta(self, snap, prefix: str) -> dict:
        if not snap:
            return {
                f'{prefix}_cvd_at_entry': None,
                f'{prefix}_cvd_pressure_at_entry': None,
                f'{prefix}_cvd_15m_ago_at_entry': None,
                f'{prefix}_cvd_delta_15m_at_entry': None,
                f'{prefix}_cvd_trend_at_entry': None,
            }
        cvd = _num(getattr(snap, 'cvd', None))
        prev = _num(getattr(snap, 'cvd_15m_ago', None))
        return {
            f'{prefix}_cvd_at_entry': cvd,
            f'{prefix}_cvd_pressure_at_entry': getattr(snap, 'cvd_pressure', None) or classify_cvd_pressure(cvd),
            f'{prefix}_cvd_15m_ago_at_entry': prev,
            f'{prefix}_cvd_delta_15m_at_entry': _num(getattr(snap, 'cvd_delta_15m', None)),
            f'{prefix}_cvd_trend_at_entry': getattr(snap, 'cvd_trend', None) or classify_cvd_trend(cvd, prev),
        }


    def _followers_consensus_meta(self) -> tuple[dict | None, dict]:
        consensus = None
        if hasattr(self.market, 'followers_consensus'):
            try:
                consensus = self.market.followers_consensus()
            except Exception:
                consensus = None
        if not consensus:
            return None, {
                'followers_consensus_short_score_at_entry': None,
                'followers_consensus_short_state_at_entry': None,
                'followers_consensus_long_score_at_entry': None,
                'followers_consensus_long_state_at_entry': None,
                'followers_consensus_positive_funding_count_at_entry': None,
                'followers_consensus_negative_funding_count_at_entry': None,
                'followers_consensus_transition_count_at_entry': None,
                'followers_consensus_strong_agreement_count_at_entry': None,
                'followers_consensus_json': None,
            }
        summary = consensus.get('funding_summary') or {}
        meta = {
            'followers_consensus_short_score_at_entry': _num((consensus.get('short') or {}).get('score')),
            'followers_consensus_short_state_at_entry': (consensus.get('short') or {}).get('state'),
            'followers_consensus_long_score_at_entry': _num((consensus.get('long') or {}).get('score')),
            'followers_consensus_long_state_at_entry': (consensus.get('long') or {}).get('state'),
            'followers_consensus_positive_funding_count_at_entry': _int(summary.get('positive_agreements')),
            'followers_consensus_negative_funding_count_at_entry': _int(summary.get('negative_agreements')),
            'followers_consensus_transition_count_at_entry': _int(summary.get('transitions')),
            'followers_consensus_strong_agreement_count_at_entry': _int(summary.get('strong_agreements')),
            'followers_consensus_json': json.dumps(consensus, ensure_ascii=False, separators=(',', ':')),
        }
        return consensus, meta

    def _build_decision_metadata(self, symbol: str, direction: str, signal: RadarSignal | None, followers: list[dict], symbol_states: dict | None = None) -> dict:
        """Build a permanent Decision Snapshot for a manually opened trade.

        This is the research fingerprint of the trade. It intentionally stores
        both a compact column set for reports and a full JSON payload for
        future replay/diagnosis without changing any trading rule.
        """
        driver = str(self.market.cfg['symbols']['driver']).upper()
        symbol = str(symbol).upper()
        btc = self.market.snapshots.get(driver)
        follower_snap = self.market.snapshots.get(symbol)
        follower_row = next((f for f in followers if str(f.get('symbol') or '').upper() == symbol), {})
        symbol_states = symbol_states or {}
        btc_state = symbol_states.get(driver, {}) if isinstance(symbol_states, dict) else {}
        follower_state = symbol_states.get(symbol, {}) if isinstance(symbol_states, dict) else {}

        score = _num(signal.score) if signal else _num(btc_state.get('score'))
        spread = _num(signal.spread) if signal else _num(btc_state.get('spread'))
        state = signal.state if signal else (btc_state.get('state') or 'UNKNOWN')
        recommendation = signal.recommendation if signal else (btc_state.get('recommendation') or 'UNKNOWN')
        long_votes = _int(getattr(signal, 'long_votes', None)) if signal else _int(btc_state.get('long_votes'))
        short_votes = _int(getattr(signal, 'short_votes', None)) if signal else _int(btc_state.get('short_votes'))
        dominant_votes = _dominant_votes(long_votes, short_votes)

        follow_score = _num(follower_row.get('follow_score'))
        btc_health_status = btc_state.get('status')
        btc_health_score = _num(btc_state.get('health_score'))
        btc_preferred_direction = btc_state.get('preferred_direction')
        follower_health_status = follower_state.get('status')
        follower_health_score = _num(follower_state.get('health_score'))
        follower_preferred_direction = follower_state.get('preferred_direction')

        btc_ls_posit_long = _snap_num(btc, 'ls_posit_long')
        btc_ls_ratio_long = _snap_num(btc, 'ls_ratio_long')
        btc_ls_account_long = _snap_num(btc, 'ls_account_long')
        follower_ls_posit_long = _snap_num(follower_snap, 'ls_posit_long')
        follower_ls_ratio_long = _snap_num(follower_snap, 'ls_ratio_long')
        follower_ls_account_long = _snap_num(follower_snap, 'ls_account_long')

        follower_long_votes = _int(follower_state.get('long_votes'))
        follower_short_votes = _int(follower_state.get('short_votes'))
        follower_dominant_votes = _dominant_votes(follower_long_votes, follower_short_votes)

        strength = self._judgment_strength(spread, follow_score)
        judgment = self._format_judgment(strength, direction, state, spread, btc_ls_posit_long, follow_score)

        btc_payload = self._symbol_snapshot_payload(
            symbol=driver,
            snap=btc,
            state=btc_state,
            role='driver',
            signal_state=state,
            recommendation=recommendation,
            score=score,
            spread=spread,
            long_votes=long_votes,
            short_votes=short_votes,
            dominant_votes=dominant_votes,
            long_score=_num(btc_state.get('long_score')),
            short_score=_num(btc_state.get('short_score')),
            narrative=btc_state.get('narrative'),
        )
        follower_payload = self._symbol_snapshot_payload(
            symbol=symbol,
            snap=follower_snap,
            state=follower_state,
            role='follower',
            follow_score=follow_score,
            spread=_num(follower_state.get('spread')),
            long_votes=follower_long_votes,
            short_votes=follower_short_votes,
            dominant_votes=follower_dominant_votes,
            long_score=_num(follower_state.get('long_score')),
            short_score=_num(follower_state.get('short_score')),
            narrative=follower_state.get('narrative'),
        )

        followers_consensus, followers_consensus_meta = self._followers_consensus_meta()

        snapshot = {
            'version': 'decision_snapshot_v2',
            'trade': {
                'symbol': symbol,
                'direction': direction,
                'size_mode': 'manual',
            },
            'btc': btc_payload,
            'follower': follower_payload,
            'followers_consensus': followers_consensus,
            'alignment': {
                'btc_preferred_direction': btc_preferred_direction,
                'follower_preferred_direction': follower_preferred_direction,
                'trade_direction': direction,
                'btc_aligned': _aligned(direction, btc_preferred_direction),
                'follower_aligned': _aligned(direction, follower_preferred_direction),
            },
            'research_flags': {
                'display_only': True,
                'does_not_change_signal': True,
                'purpose': 'entry_snapshot_validation',
            },
        }

        return {
            'decision_judgment': judgment,
            'decision_snapshot_json': json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')),
            'entry_snapshot_version': 'decision_snapshot_v2',
            'btc_state_at_entry': state,
            'btc_recommendation_at_entry': recommendation,
            'btc_score_at_entry': score,
            'btc_spread_at_entry': spread,
            'btc_long_votes_at_entry': long_votes,
            'btc_short_votes_at_entry': short_votes,
            'btc_dominant_votes_at_entry': dominant_votes,
            'btc_long_score_at_entry': _num(btc_state.get('long_score')),
            'btc_short_score_at_entry': _num(btc_state.get('short_score')),
            'btc_narrative_at_entry': btc_state.get('narrative'),
            'btc_price_at_entry': _snap_num(btc, 'price'),
            'btc_ls_posit_long_at_entry': btc_ls_posit_long,
            'btc_ls_posit_short_at_entry': _snap_num(btc, 'ls_posit_short'),
            'btc_ls_ratio_long_at_entry': btc_ls_ratio_long,
            'btc_ls_ratio_short_at_entry': _snap_num(btc, 'ls_ratio_short'),
            'btc_ls_account_long_at_entry': btc_ls_account_long,
            'btc_ls_account_short_at_entry': _snap_num(btc, 'ls_account_short'),
            'btc_funding_at_entry': _snap_num(btc, 'funding'),
            'btc_oi_at_entry': _snap_num(btc, 'oi'),
            'btc_vwap_at_entry': _snap_num(btc, 'vwap'),
            'btc_health_status_at_entry': btc_health_status,
            'btc_health_score_at_entry': btc_health_score,
            'btc_preferred_direction_at_entry': btc_preferred_direction,
            'follow_score_at_entry': follow_score,
            'follower_price_at_entry': _snap_num(follower_snap, 'price'),
            'follower_ls_posit_long_at_entry': follower_ls_posit_long,
            'follower_ls_posit_short_at_entry': _snap_num(follower_snap, 'ls_posit_short'),
            'follower_ls_ratio_long_at_entry': follower_ls_ratio_long,
            'follower_ls_ratio_short_at_entry': _snap_num(follower_snap, 'ls_ratio_short'),
            'follower_ls_account_long_at_entry': follower_ls_account_long,
            'follower_ls_account_short_at_entry': _snap_num(follower_snap, 'ls_account_short'),
            'follower_funding_at_entry': _snap_num(follower_snap, 'funding'),
            'follower_oi_at_entry': _snap_num(follower_snap, 'oi'),
            'follower_vwap_at_entry': _snap_num(follower_snap, 'vwap'),
            'follower_health_status_at_entry': follower_health_status,
            'follower_health_score_at_entry': follower_health_score,
            'follower_preferred_direction_at_entry': follower_preferred_direction,
            'follower_spread_at_entry': _num(follower_state.get('spread')),
            'follower_long_votes_at_entry': follower_long_votes,
            'follower_short_votes_at_entry': follower_short_votes,
            'follower_dominant_votes_at_entry': follower_dominant_votes,
            'follower_long_score_at_entry': _num(follower_state.get('long_score')),
            'follower_short_score_at_entry': _num(follower_state.get('short_score')),
            'follower_narrative_at_entry': follower_state.get('narrative'),
            **followers_consensus_meta,
            **self._cvd_meta(btc, 'btc'),
            **self._cvd_meta(follower_snap, 'follower'),
        }

    def _symbol_snapshot_payload(
        self,
        *,
        symbol: str,
        snap,
        state: dict | None,
        role: str,
        signal_state: str | None = None,
        recommendation: str | None = None,
        score: float | None = None,
        follow_score: float | None = None,
        spread: float | None = None,
        long_votes: int | None = None,
        short_votes: int | None = None,
        dominant_votes: int | None = None,
        long_score: float | None = None,
        short_score: float | None = None,
        narrative: str | None = None,
    ) -> dict:
        state = state or {}
        cvd = _snap_num(snap, 'cvd')
        cvd_15m_ago = _snap_num(snap, 'cvd_15m_ago')
        return {
            'symbol': symbol,
            'role': role,
            'state': signal_state,
            'recommendation': recommendation,
            'score': score,
            'follow_score': follow_score,
            'spread': spread,
            'spread_regime': _spread_regime(spread),
            'votes': {
                'long': long_votes,
                'short': short_votes,
                'dominant': dominant_votes,
            },
            'scores': {
                'long': long_score,
                'short': short_score,
            },
            'narrative': narrative,
            'market': {
                'price': _snap_num(snap, 'price'),
                'funding': _snap_num(snap, 'funding'),
                'oi': _snap_num(snap, 'oi'),
                'vwap': _snap_num(snap, 'vwap'),
            },
            'ls': {
                'posit_long': _snap_num(snap, 'ls_posit_long'),
                'posit_short': _snap_num(snap, 'ls_posit_short'),
                'ratio_long': _snap_num(snap, 'ls_ratio_long'),
                'ratio_short': _snap_num(snap, 'ls_ratio_short'),
                'account_long': _snap_num(snap, 'ls_account_long'),
                'account_short': _snap_num(snap, 'ls_account_short'),
            },
            'cvd': {
                'value': cvd,
                'pressure': getattr(snap, 'cvd_pressure', None) or classify_cvd_pressure(cvd),
                'previous_15m': cvd_15m_ago,
                'delta_15m': _snap_num(snap, 'cvd_delta_15m'),
                'trend': getattr(snap, 'cvd_trend', None) or classify_cvd_trend(cvd, cvd_15m_ago),
            },
            'health': {
                'status': state.get('status'),
                'score': _num(state.get('health_score')),
                'preferred_direction': state.get('preferred_direction'),
            },
            'timestamps': {
                'price_updated_at': getattr(snap, 'price_updated_at', None) if snap else None,
                'ls_updated_at': getattr(snap, 'ls_updated_at', None) if snap else None,
                'updated_at': getattr(snap, 'updated_at', None) if snap else None,
            },
        }

    def _judgment_strength(self, spread: float | None, follow_score: float | None) -> str:
        spread = spread or 0.0
        follow_score = follow_score or 0.0
        if spread >= 30 and follow_score >= 70:
            return 'STRONG'
        if spread >= 20 and follow_score >= 65:
            return 'GOOD'
        if spread >= 10:
            return 'WATCH'
        return 'WEAK'

    def _format_judgment(self, strength: str, direction: str, state: str, spread: float | None, btc_ls_posit: float | None, follow_score: float | None) -> str:
        parts = [f'{strength} {direction}', state]
        if spread is not None:
            parts.append(f'Spread {spread:.1f}%')
        if btc_ls_posit is not None:
            parts.append(f'BTC LS_POSIT {btc_ls_posit:.1f}%')
        if follow_score is not None:
            parts.append(f'Follow {follow_score:.1f}')
        return ' | '.join(parts)


def _snap_num(snap, attr: str):
    return _num(getattr(snap, attr, None)) if snap else None


def _int(value):
    try:
        if value is None:
            return None
        return int(float(value))
    except Exception:
        return None


def _dominant_votes(long_votes, short_votes):
    vals = [v for v in (long_votes, short_votes) if v is not None]
    return max(vals) if vals else None


def _aligned(direction: str | None, preferred: str | None) -> bool | None:
    if not direction or not preferred:
        return None
    d = str(direction).upper()
    p = str(preferred).upper()
    if p in ('WAIT', 'WATCH', 'NEUTRAL', 'UNKNOWN'):
        return None
    return d in p


def _spread_regime(value):
    n = _num(value)
    if n is None:
        return 'NA'
    if n >= 30:
        return 'EXTREME_30_PLUS'
    if n >= 20:
        return 'HIGH_20_30'
    if n >= 10:
        return 'MID_10_20'
    return 'LOW_0_10'


def _num(value):
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except Exception:
        return None
