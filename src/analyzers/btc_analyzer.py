from __future__ import annotations
from ..models import SymbolSnapshot, RadarSignal, utc_now


def _pair(long_v: float | None, short_v: float | None) -> tuple[float, float]:
    l = float(long_v or 50.0)
    s = float(short_v if short_v is not None else 100.0 - l)
    return l, s


class BTCAnalyzer:
    def __init__(self, cfg: dict):
        st = cfg.get('strategy', {})
        self.weights = st.get('weights', {'ls_posit': .45, 'ls_ratio': .35, 'ls_account': .20})
        th = st.get('thresholds', {})
        self.min_score = float(th.get('min_score', 15.0))
        self.min_spread = float(th.get('min_spread', 3.0))
        self.min_votes = int(th.get('min_votes', 2))

    def analyze(self, btc: SymbolSnapshot) -> RadarSignal:
        items = [
            ('ls_posit', *_pair(btc.ls_posit_long, btc.ls_posit_short)),
            ('ls_ratio', *_pair(btc.ls_ratio_long, btc.ls_ratio_short)),
            ('ls_account', *_pair(btc.ls_account_long, btc.ls_account_short)),
        ]
        long_score = 0.0; short_score = 0.0; lv = 0; sv = 0
        for key, l, s in items:
            w = float(self.weights.get(key, 0.0))
            long_score += l * w
            short_score += s * w
            if l > s: lv += 1
            elif s > l: sv += 1
        spread = abs(long_score - short_score)
        score = max(long_score, short_score)
        if long_score > short_score and lv >= self.min_votes and spread >= self.min_spread:
            state, rec = 'BTC_LONG_CROWDED', 'SHORT FOLLOWERS'
        elif short_score > long_score and sv >= self.min_votes and spread >= self.min_spread:
            state, rec = 'BTC_SHORT_CROWDED', 'LONG FOLLOWERS'
        else:
            state, rec = 'BTC_NEUTRAL', 'WAIT'
        return RadarSignal(state, rec, round(score, 2), round(spread, 2), lv, sv, utc_now())
