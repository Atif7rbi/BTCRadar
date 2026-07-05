from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


def classify_cvd_pressure(cvd: Optional[float]) -> str:
    """Research-only CVD pressure label. It must not affect trading decisions."""
    if cvd is None:
        return 'UNKNOWN'
    try:
        value = float(cvd)
    except Exception:
        return 'UNKNOWN'
    if value >= 30:
        return 'STRONG_BUY'
    if value >= 10:
        return 'BUY'
    if value <= -30:
        return 'STRONG_SELL'
    if value <= -10:
        return 'SELL'
    return 'NEUTRAL'


def classify_cvd_trend(current: Optional[float], previous: Optional[float]) -> str:
    """Research-only 15m CVD trend label based on current - previous."""
    if current is None or previous is None:
        return 'UNKNOWN'
    try:
        cur = float(current)
        prev = float(previous)
    except Exception:
        return 'UNKNOWN'
    delta = cur - prev
    if abs(delta) < 10:
        return 'STABLE'
    if cur >= 0 and delta > 0:
        return 'BUY_GROWING'
    if cur >= 0 and delta < 0:
        return 'BUY_WEAKENING'
    if cur < 0 and delta < 0:
        return 'SELL_GROWING'
    if cur < 0 and delta > 0:
        return 'SELL_FADING'
    return 'STABLE'


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SymbolSnapshot:
    symbol: str

    # Compatibility field (will be removed later)
    price: Optional[float] = None

    # New price architecture
    mark_price: Optional[float] = None
    last_price: Optional[float] = None
    ls_posit_long: Optional[float] = None
    ls_posit_short: Optional[float] = None
    ls_ratio_long: Optional[float] = None
    ls_ratio_short: Optional[float] = None
    ls_account_long: Optional[float] = None
    ls_account_short: Optional[float] = None
    funding: Optional[float] = None
    oi: Optional[float] = None
    vwap: Optional[float] = None
    cvd: Optional[float] = None
    cvd_15m_ago: Optional[float] = None
    cvd_delta_15m: Optional[float] = None
    cvd_pressure: Optional[str] = None
    cvd_trend: Optional[str] = None
    cvd_buy_vol: Optional[float] = None
    cvd_sell_vol: Optional[float] = None
    price_updated_at: Optional[str] = None
    ls_updated_at: Optional[str] = None
    updated_at: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RadarSignal:
    state: str
    recommendation: str
    score: float
    spread: float
    long_votes: int
    short_votes: int
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)
