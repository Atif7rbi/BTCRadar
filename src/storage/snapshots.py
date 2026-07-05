from __future__ import annotations
from ..models import SymbolSnapshot
from .database import Database


class SnapshotStore:
    def __init__(self, db: Database): self.db = db

    def insert(self, s: SymbolSnapshot):
        with self.db.connect() as con:
            con.execute('''INSERT INTO btc_radar_snapshots
            (symbol, price, mark_price, last_price, ls_posit_long, ls_posit_short, ls_ratio_long, ls_ratio_short,
             ls_account_long, ls_account_short, funding, oi, vwap, cvd, cvd_buy_vol, cvd_sell_vol,
             price_updated_at, ls_updated_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (s.symbol, s.price, s.mark_price, s.last_price, s.ls_posit_long, s.ls_posit_short, s.ls_ratio_long, s.ls_ratio_short,
             s.ls_account_long, s.ls_account_short, s.funding, s.oi, s.vwap, s.cvd, s.cvd_buy_vol, s.cvd_sell_vol,
             s.price_updated_at, s.ls_updated_at, s.updated_at))

    def latest(self, symbol: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute('SELECT * FROM btc_radar_snapshots WHERE symbol=? ORDER BY id DESC LIMIT 1', (symbol,)).fetchone()
            return dict(row) if row else None


    def latest_all(self, symbols: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for symbol in symbols:
            row = self.latest(symbol)
            if row:
                out[str(symbol).upper()] = row
        return out
