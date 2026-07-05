from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collectors.okx_provider import OKXProvider, OKX_SYMBOLS


DB_CANDIDATES = [
    ROOT / "data" / "btcradar.db",
    ROOT / "data" / "btc_radar.db",
    ROOT / "btcradar.db",
]


def db_path() -> Path:
    for p in DB_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit("DB not found")


def table_columns(con, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


def latest_row(con, symbol: str) -> dict:
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM btc_radar_snapshots WHERE symbol=? ORDER BY id DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    return dict(row) if row else {}


def insert_snapshot(con, cols: set[str], values: dict) -> None:
    payload = {k: v for k, v in values.items() if k in cols}
    fields = ", ".join(payload.keys())
    qs = ", ".join(["?"] * len(payload))
    con.execute(
        f"INSERT INTO btc_radar_snapshots ({fields}) VALUES ({qs})",
        list(payload.values()),
    )


def main() -> int:
    provider = OKXProvider(timeout=10, period="5m")
    db = db_path()
    now = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(db) as con:
        cols = table_columns(con, "btc_radar_snapshots")

        for symbol in OKX_SYMBOLS:
            prev = latest_row(con, symbol)
            ls = provider.get_ls_snapshot(symbol)

            funding = provider.get_funding_rate(symbol)
            oi = provider.get_open_interest(symbol)
            try:
                buy_vol, sell_vol, flow_delta = provider.get_taker_flow(symbol)
            except Exception as exc:
                print(f"OKX taker flow skipped for {symbol}: {exc}")
                buy_vol, sell_vol, flow_delta = None, None, None

            values = dict(prev)
            values.pop("id", None)

            # Price fields are owned by the 5-second Flask price overlay, not Cron.
            for k in ("price", "mark_price", "last_price", "price_updated_at"):
                values.pop(k, None)

            values.update({
                "symbol": symbol,
                "ls_posit_long": ls.ls_posit.long_pct,
                "ls_posit_short": ls.ls_posit.short_pct,
                "ls_ratio_long": ls.ls_ratio.long_pct,
                "ls_ratio_short": ls.ls_ratio.short_pct,
                "ls_account_long": ls.ls_account.long_pct,
                "ls_account_short": ls.ls_account.short_pct,
                "funding": funding,
                "oi": oi,
                "cvd_buy_vol": buy_vol,
                "cvd_sell_vol": sell_vol,
                "cvd": flow_delta,
                "updated_at": now,
                "ls_updated_at": now,
                "created_at": now,
            })

            insert_snapshot(con, cols, values)

        con.commit()

    print(f"OKX runtime refresh done db={db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
