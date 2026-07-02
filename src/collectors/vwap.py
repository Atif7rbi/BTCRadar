from __future__ import annotations


def calculate_vwap(klines: list[list]) -> float | None:
    total_pv = 0.0
    total_v = 0.0
    for k in klines:
        high = float(k[2]); low = float(k[3]); close = float(k[4]); vol = float(k[5])
        typical = (high + low + close) / 3
        total_pv += typical * vol
        total_v += vol
    if total_v <= 0:
        return None
    return total_pv / total_v
