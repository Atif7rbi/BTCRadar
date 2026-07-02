from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_text(v: Any, fallback: str = '--') -> str:
    if v is None or v == '':
        return fallback
    return str(v)


def _clamp(v: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, v))


@dataclass
class SymbolMonitorState:
    symbol: str
    status: str
    narrative: str
    preferred_direction: str
    health_score: float
    crowding_score: float
    pressure_score: float
    reversal_risk: float
    long_score: float
    short_score: float
    spread: float
    long_votes: int
    short_votes: int
    reasons: list[str]
    warnings: list[str]
    coinalyze: dict
    breakdown: dict

    def to_dict(self) -> dict:
        return asdict(self)


class BTCMonitor:
    """
    BTCRadar Monitor v1.

    Research mode:
    - Evaluates BTC and each follower independently.
    - Combines BTC + traded-symbol only for open-trade alerts.
    - Does not execute closes.
    """

    def __init__(self, cfg: dict):
        st = cfg.get('strategy', {})
        self.weights = st.get('weights', {'ls_posit': .45, 'ls_ratio': .35, 'ls_account': .20})
        th = st.get('thresholds', {})
        self.min_spread = float(th.get('min_spread', 3.0))
        self.min_votes = int(th.get('min_votes', 2))
        monitor_cfg = cfg.get('btc_monitor', {})
        self.safe_score = float(monitor_cfg.get('safe_score', 65.0))
        self.exit_score = float(monitor_cfg.get('exit_score', 45.0))
        self.exit_risk = float(monitor_cfg.get('exit_risk', 65.0))

    def evaluate_all(self, snapshots: dict, coinalyze_summary: dict | None = None) -> dict[str, dict]:
        coinalyze_summary = coinalyze_summary or {}
        states: dict[str, dict] = {}

        for symbol, snap in snapshots.items():
            item = coinalyze_summary.get(symbol.upper(), {}) if isinstance(coinalyze_summary, dict) else {}
            state = self.evaluate_symbol(snap, item)
            states[symbol.upper()] = state.to_dict()

        return states

    def evaluate_symbol(self, snap, coinalyze_item: dict | None = None) -> SymbolMonitorState:
        symbol = str(getattr(snap, 'symbol', '') or '').upper()
        coinalyze_item = coinalyze_item or {}
        analysis = coinalyze_item.get('analysis') or {}
        trend = coinalyze_item.get('trend') or {}

        pairs = [
            ('ls_posit', self._pair(getattr(snap, 'ls_posit_long', None), getattr(snap, 'ls_posit_short', None))),
            ('ls_ratio', self._pair(getattr(snap, 'ls_ratio_long', None), getattr(snap, 'ls_ratio_short', None))),
            ('ls_account', self._pair(getattr(snap, 'ls_account_long', None), getattr(snap, 'ls_account_short', None))),
        ]

        long_score = 0.0
        short_score = 0.0
        long_votes = 0
        short_votes = 0

        for key, (long_v, short_v) in pairs:
            w = float(self.weights.get(key, 0.0))
            long_score += long_v * w
            short_score += short_v * w
            if long_v > short_v:
                long_votes += 1
            elif short_v > long_v:
                short_votes += 1

        spread = abs(long_score - short_score)

        if long_score > short_score and long_votes >= self.min_votes and spread >= self.min_spread:
            narrative = 'LONG_CROWDED'
            preferred_direction = 'SHORT'
        elif short_score > long_score and short_votes >= self.min_votes and spread >= self.min_spread:
            narrative = 'SHORT_CROWDED'
            preferred_direction = 'LONG'
        else:
            narrative = 'NEUTRAL'
            preferred_direction = 'WAIT'

        crowding_score = self._crowding_score(narrative, max(long_score, short_score), spread, long_votes, short_votes)
        pressure_score, pressure_reasons, pressure_warnings = self._pressure_score(narrative, analysis, trend)
        reversal_risk, risk_reasons = self._reversal_risk(narrative, spread, analysis, trend)

        health_score = _clamp((crowding_score * 0.50) + (pressure_score * 0.35) + ((100.0 - reversal_risk) * 0.15))

        reasons: list[str] = []
        warnings: list[str] = []

        if narrative == 'LONG_CROWDED':
            reasons.append('Symbol long crowding is dominant; preferred pressure direction is SHORT.')
        elif narrative == 'SHORT_CROWDED':
            reasons.append('Symbol short crowding is dominant; preferred pressure direction is LONG.')
        else:
            warnings.append('No clear LS crowding narrative.')

        if spread >= 30:
            reasons.append(f'Crowding spread is extreme ({spread:.1f}).')
        elif spread >= 20:
            reasons.append(f'Crowding spread is high ({spread:.1f}).')
        elif spread >= self.min_spread:
            reasons.append(f'Crowding spread is active ({spread:.1f}).')
        else:
            warnings.append(f'Crowding spread is weak ({spread:.1f}).')

        reasons.extend(pressure_reasons)
        warnings.extend(pressure_warnings)
        warnings.extend(risk_reasons)

        strong_crowding = crowding_score >= 70 and spread >= 20 and max(long_votes, short_votes) >= self.min_votes
        extreme_reversal = reversal_risk >= 85 and pressure_score <= 20
        confirmed_exit = (
            health_score < self.exit_score
            and reversal_risk >= self.exit_risk
            and (not strong_crowding or extreme_reversal)
        )

        if narrative == 'NEUTRAL':
            status = 'WARNING'
        elif health_score >= self.safe_score and reversal_risk < self.exit_risk:
            status = 'SAFE'
        elif confirmed_exit or extreme_reversal:
            status = 'EXIT'
        else:
            status = 'WARNING'

        return SymbolMonitorState(
            symbol=symbol,
            status=status,
            narrative=narrative,
            preferred_direction=preferred_direction,
            health_score=round(health_score, 2),
            crowding_score=round(crowding_score, 2),
            pressure_score=round(pressure_score, 2),
            reversal_risk=round(reversal_risk, 2),
            long_score=round(long_score, 2),
            short_score=round(short_score, 2),
            spread=round(spread, 2),
            long_votes=long_votes,
            short_votes=short_votes,
            reasons=reasons[:6],
            warnings=warnings[:6],
            coinalyze={
                'oi_trend': _safe_text(analysis.get('oi_trend')),
                'liquidation_trend': _safe_text(analysis.get('liquidation_trend')),
                'dominant_liquidation': _safe_text(analysis.get('dominant_liquidation')),
                'verdict': _safe_text(analysis.get('verdict')),
                'pain_score': _num(analysis.get('pain_score')),
                'oi_1h_pct': trend.get('oi_1h_pct'),
                'oi_4h_pct': trend.get('oi_4h_pct'),
            },
            breakdown={
                'health_formula': 'crowding*0.50 + pressure*0.35 + (100-risk)*0.15',
                'crowding_score': round(crowding_score, 2),
                'pressure_score': round(pressure_score, 2),
                'reversal_risk': round(reversal_risk, 2),
                'risk_inverse': round(100.0 - reversal_risk, 2),
                'crowding_component': round(crowding_score * 0.50, 2),
                'pressure_component': round(pressure_score * 0.35, 2),
                'risk_component': round((100.0 - reversal_risk) * 0.15, 2),
                'health_score': round(health_score, 2),
                'long_score': round(long_score, 2),
                'short_score': round(short_score, 2),
                'spread': round(spread, 2),
                'long_votes': long_votes,
                'short_votes': short_votes,
                'narrative': narrative,
                'preferred_direction': preferred_direction,
                'strong_crowding': strong_crowding,
                'extreme_reversal': extreme_reversal,
                'confirmed_exit': confirmed_exit,
                'inputs': {
                    'oi_trend': _safe_text(analysis.get('oi_trend')),
                    'liquidation_trend': _safe_text(analysis.get('liquidation_trend')),
                    'dominant_liquidation': _safe_text(analysis.get('dominant_liquidation')),
                    'verdict': _safe_text(analysis.get('verdict')),
                    'oi_1h_pct': trend.get('oi_1h_pct'),
                    'oi_4h_pct': trend.get('oi_4h_pct'),
                },
            },
        )

    def evaluate_trade(self, trade: dict, symbol_states: dict[str, dict], btc_symbol: str = 'BTCUSDT') -> dict:
        symbol = str(trade.get('symbol') or '').upper()
        direction = str(trade.get('direction') or '').upper()

        btc_state = symbol_states.get(btc_symbol.upper(), {})
        symbol_state = symbol_states.get(symbol, {})

        btc_status = btc_state.get('status', 'WAITING')
        symbol_status = symbol_state.get('status', 'WAITING')
        symbol_preferred = str(symbol_state.get('preferred_direction') or 'WAIT').upper()
        btc_preferred = str(btc_state.get('preferred_direction') or 'WAIT').upper()

        if not symbol_state:
            return {
                'status': 'WAITING',
                'btc_status': btc_status,
                'symbol_status': 'WAITING',
                'action': 'WAIT',
                'confidence': 0,
                'reason': 'Symbol monitor state is not available yet.',
                'reasons': ['Symbol monitor state is not available yet.'],
            }

        reasons: list[str] = []
        direction_supported_by_symbol = symbol_preferred == direction
        direction_supported_by_btc = btc_preferred == direction

        if direction_supported_by_symbol:
            reasons.append(f'{symbol.replace("USDT","")} monitor still supports {direction}.')
        else:
            reasons.append(f'{symbol.replace("USDT","")} monitor no longer supports {direction}.')

        if direction_supported_by_btc:
            reasons.append(f'BTC monitor still supports {direction} followers.')
        else:
            reasons.append(f'BTC monitor does not strongly support {direction} followers now.')

        if btc_status == 'EXIT' and symbol_status == 'EXIT':
            status = 'EXIT ALERT'
            action = 'EXIT_NOW'
            confidence = 95
        elif symbol_status == 'EXIT' and not direction_supported_by_symbol:
            status = 'EXIT ALERT'
            action = 'EXIT_NOW'
            confidence = 85
        elif btc_status == 'SAFE' and symbol_status == 'SAFE' and direction_supported_by_symbol and direction_supported_by_btc:
            status = 'HOLD'
            action = 'HOLD'
            confidence = 90
        elif btc_status == 'WARNING' or symbol_status == 'WARNING':
            status = 'WATCH'
            action = 'WATCH'
            confidence = 65
        elif btc_status == 'EXIT' or symbol_status == 'EXIT':
            status = 'WARNING'
            action = 'WATCH_CLOSELY'
            confidence = 75
        else:
            status = 'WATCH'
            action = 'WATCH'
            confidence = 55

        return {
            'status': status,
            'btc_status': btc_status,
            'symbol_status': symbol_status,
            'action': action,
            'confidence': confidence,
            'reason': ' | '.join(reasons),
            'reasons': reasons,
            'btc_health_score': btc_state.get('health_score'),
            'symbol_health_score': symbol_state.get('health_score'),
            'btc_reversal_risk': btc_state.get('reversal_risk'),
            'symbol_reversal_risk': symbol_state.get('reversal_risk'),
        }

    def exit_card(self, btc_state: dict | None) -> dict:
        btc_state = btc_state or {}
        return {
            'status': btc_state.get('status', 'WAITING'),
            'rule': 'Narrative Health Monitor v1 (research mode)',
            'btc_ls_posit': None,
            'threshold': None,
            'distance': None,
            'state': btc_state.get('narrative', 'UNKNOWN'),
            'health_score': btc_state.get('health_score'),
            'reversal_risk': btc_state.get('reversal_risk'),
            'reasons': btc_state.get('reasons', []),
            'warnings': btc_state.get('warnings', []),
        }

    @staticmethod
    def _pair(long_v: Any, short_v: Any) -> tuple[float, float]:
        long_f = _num(long_v, 50.0)
        short_f = _num(short_v, 100.0 - long_f)
        return long_f, short_f

    def _crowding_score(self, narrative: str, dominant_score: float, spread: float, long_votes: int, short_votes: int) -> float:
        if narrative == 'NEUTRAL':
            return 25.0

        vote_count = max(long_votes, short_votes)
        vote_score = min(vote_count / 3.0, 1.0) * 25.0
        dominant_component = _clamp((dominant_score - 50.0) * 2.0, 0.0, 35.0)
        spread_component = _clamp(spread * 1.5, 0.0, 40.0)
        return _clamp(vote_score + dominant_component + spread_component)

    def _pressure_score(self, narrative: str, analysis: dict, trend: dict) -> tuple[float, list[str], list[str]]:
        if narrative == 'NEUTRAL':
            return 35.0, [], ['Pressure layer is weaker because symbol narrative is neutral.']

        score = 45.0
        reasons: list[str] = []
        warnings: list[str] = []

        oi_trend = _safe_text(analysis.get('oi_trend'), 'NO DATA').upper()
        liq_trend = _safe_text(analysis.get('liquidation_trend'), 'NO DATA').upper()
        dominant = _safe_text(analysis.get('dominant_liquidation'), 'NONE').upper()
        verdict = _safe_text(analysis.get('verdict'), 'NO CLEAR EDGE').upper()

        if 'RISING' in oi_trend:
            score += 18
            reasons.append('OI is rising; new positioning fuel is entering.')
        elif 'FALLING' in oi_trend:
            score -= 12
            warnings.append('OI is falling; positioning fuel may be leaving.')

        expected_dominant = 'LONG LIQ' if narrative == 'LONG_CROWDED' else 'SHORT LIQ'
        opposite_dominant = 'SHORT LIQ' if narrative == 'LONG_CROWDED' else 'LONG LIQ'

        if dominant == expected_dominant:
            score += 20
            reasons.append(f'{dominant} is dominant; pain is aligned with the crowding narrative.')
        elif dominant == opposite_dominant:
            score -= 12
            warnings.append(f'{dominant} is dominant; liquidation pressure is not aligned yet.')
        elif dominant == 'MIXED':
            score -= 5
            warnings.append('Liquidation pressure is mixed.')

        if liq_trend in ('SPIKE', 'ELEVATED'):
            score += 7
            reasons.append(f'Liquidation trend is {liq_trend.lower()}.')

        if 'CROWDING BUILDING' in verdict or 'ACTIVE PRESSURE' in verdict:
            score += 10
            reasons.append(f'Verdict supports active pressure: {verdict}.')
        elif 'COOLING' in verdict or 'HAPPENED' in verdict:
            score -= 10
            warnings.append(f'Verdict is cautious: {verdict}.')
        elif 'NO CLEAR' in verdict:
            score -= 4
            warnings.append(f'Verdict is unclear, not confirmed exit: {verdict}.')

        return _clamp(score), reasons, warnings

    def _reversal_risk(self, narrative: str, spread: float, analysis: dict, trend: dict) -> tuple[float, list[str]]:
        if narrative == 'NEUTRAL':
            return 65.0, ['Neutral narrative raises reversal/uncertainty risk.']

        risk = 25.0
        warnings: list[str] = []

        oi_trend = _safe_text(analysis.get('oi_trend'), 'NO DATA').upper()
        dominant = _safe_text(analysis.get('dominant_liquidation'), 'NONE').upper()
        verdict = _safe_text(analysis.get('verdict'), 'NO CLEAR EDGE').upper()
        oi_1h_pct = _num(trend.get('oi_1h_pct'), 0.0)

        if spread < 10:
            risk += 22
            warnings.append('Crowding spread is weak; narrative may be fading.')
        elif spread < 20:
            risk += 8
            warnings.append('Crowding spread is moderate, not strong.')

        if 'FALLING' in oi_trend and oi_1h_pct <= -0.2:
            risk += 18
            warnings.append('OI is falling enough to raise reversal risk.')

        expected_dominant = 'LONG LIQ' if narrative == 'LONG_CROWDED' else 'SHORT LIQ'
        opposite_dominant = 'SHORT LIQ' if narrative == 'LONG_CROWDED' else 'LONG LIQ'

        if dominant == opposite_dominant:
            risk += 15
            warnings.append('Dominant liquidation is opposite to the expected pain side; treat as warning until crowding weakens.')
        elif dominant not in (expected_dominant, 'NONE', 'MIXED'):
            risk += 10

        if 'PRESSURE COOLING' in verdict:
            risk += 18
            warnings.append('Coinalyze verdict says pressure is cooling.')
        elif 'NO CLEAR EDGE' in verdict:
            risk += 7
            warnings.append('Coinalyze verdict is unclear; risk is elevated but not confirmed exit.')
        elif 'PAIN EVENT LIKELY HAPPENED' in verdict:
            risk += 12
            warnings.append('Pain event may already have happened.')

        return _clamp(risk), warnings
