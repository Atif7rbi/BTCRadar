from __future__ import annotations
from ..models import SymbolSnapshot, RadarSignal


def _avg_long(s: SymbolSnapshot) -> float:
    vals = [s.ls_posit_long, s.ls_ratio_long, s.ls_account_long]
    vals = [float(v) for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else 50.0


class FollowerScorer:
    def __init__(self, cfg: dict):
        fc = cfg.get('follow_score', {})
        self.enabled = bool(fc.get('enabled', True))
        self.sort_enabled = bool(fc.get('sort_followers', True))

    def score(self, follower: SymbolSnapshot, signal: RadarSignal) -> float:
        long_avg = _avg_long(follower)
        short_avg = 100.0 - long_avg
        # If BTC long crowded -> target SHORT followers, so follower long crowding is useful fuel.
        if signal.recommendation.startswith('SHORT'):
            raw = long_avg
        elif signal.recommendation.startswith('LONG'):
            raw = short_avg
        else:
            raw = 50.0
        # Light boost from agreement among the 3 LS views only. OI/CVD are read-only for now.
        return round(max(0.0, min(100.0, raw)), 1)

    def enrich_and_sort(self, followers: list[dict], signal: RadarSignal) -> list[dict]:
        for item in followers:
            snap = item.get('_snapshot')
            item['follow_score'] = self.score(snap, signal) if snap else 0.0
        if self.sort_enabled:
            followers.sort(key=lambda x: x.get('follow_score', 0), reverse=True)
        for item in followers:
            item.pop('_snapshot', None)
        return followers
