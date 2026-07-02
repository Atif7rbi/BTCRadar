from __future__ import annotations
from ..analyzers.btc_analyzer import BTCAnalyzer
from ..analyzers.follower_scorer import FollowerScorer
from ..storage.signals import SignalStore


class SignalService:
    def __init__(self, cfg: dict, signal_store: SignalStore):
        self.cfg = cfg
        self.driver = cfg['symbols']['driver']
        self.analyzer = BTCAnalyzer(cfg)
        self.scorer = FollowerScorer(cfg)
        self.store = signal_store
        self.last_signal = None
        self.last_spread_ls_updated_at = None

    def analyze(self, snapshots: dict):
        btc = snapshots.get(self.driver)
        if not btc:
            return None
        sig = self.analyzer.analyze(btc)
        # Store only when changed or first run to avoid DB spam every UI poll.
        if not self.last_signal or sig.state != self.last_signal.state or sig.recommendation != self.last_signal.recommendation:
            self.store.insert(sig)
        # Spread history follows the LS refresh cycle, not the 1-second UI refresh.
        if btc.ls_updated_at and btc.ls_updated_at != self.last_spread_ls_updated_at:
            self.store.insert_spread_history(sig, btc)
            self.last_spread_ls_updated_at = btc.ls_updated_at
        self.last_signal = sig
        return sig

    def score_followers(self, followers: list[dict], signal):
        if not signal: return followers
        return self.scorer.enrich_and_sort(followers, signal)

    def spread_trend(self) -> dict:
        return self.store.spread_trend()
