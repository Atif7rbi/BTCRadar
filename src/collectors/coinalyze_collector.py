from __future__ import annotations

from datetime import datetime, timezone, timedelta
import threading
import time
import requests

from ..config_loader import env
from ..logger import get_logger
from ..storage.coinalyze import CoinalyzeStore


class CoinalyzeCollector:
    BASE_URL = "https://api.coinalyze.net/v1"

    def __init__(self, cfg: dict, store: CoinalyzeStore):
        self.cfg = cfg
        self.store = store
        self.log = get_logger("BTCRadar.Coinalyze")

        self.settings = cfg.get("coinalyze", {}) or {}
        self.enabled = bool(self.settings.get("enabled", True))
        self.refresh_minutes = int(self.settings.get("refresh_minutes", 60))
        self.interval = str(self.settings.get("interval", "1hour"))
        self.timeout = (int(self.settings.get("connect_timeout_sec", 5)), int(self.settings.get("timeout_sec", 12)))
        self.api_key = env("COINALYZE_API_KEY")

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self.last_refresh_at: str | None = None
        self.last_error: str | None = None
        self.last_rows_saved = 0

        driver = cfg.get("symbols", {}).get("driver", "BTCUSDT")
        followers = cfg.get("symbols", {}).get("followers", []) or []

        self.symbols = [driver] + [s for s in followers if s != driver]
        self.symbol_map = self._build_symbol_map(self.symbols)

    def _build_symbol_map(self, symbols: list[str]) -> dict[str, str]:
        configured = self.settings.get("symbol_map") or {}
        out: dict[str, str] = {}

        for symbol in symbols:
            symbol = symbol.upper()
            out[symbol] = configured.get(symbol, f"{symbol}_PERP.A")

        return out

    def start(self) -> None:
        if not self.enabled:
            self.log.info("Coinalyze collector disabled")
            return

        if not self.api_key:
            self.last_error = "Missing COINALYZE_API_KEY in .env"
            self.log.warning(self.last_error)
            return

        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._loop,
            name="coinalyze-collector",
            daemon=True,
        )
        self._thread.start()

        self.log.info(
            "Coinalyze collector started refresh_minutes=%s symbols=%s",
            self.refresh_minutes,
            self.symbol_map,
        )

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "configured": bool(self.api_key),
            "refresh_minutes": self.refresh_minutes,
            "last_refresh_at": self.last_refresh_at,
            "last_error": self.last_error,
            "last_rows_saved": self.last_rows_saved,
            "symbols": self.symbol_map,
        }

    def _loop(self) -> None:
        time.sleep(3)

        while not self._stop.is_set():
            try:
                self.refresh_once()
            except Exception as e:
                self.last_error = str(e)
                self.log.exception("Coinalyze refresh failed")

            self._stop.wait(max(60, self.refresh_minutes * 60))

    def refresh_once(self) -> dict:
        """Run one complete Coinalyze refresh and persist rows.

        Designed to be safe for Cron/CLI. Each endpoint is isolated, so one
        failing Coinalyze endpoint does not prevent all other data from being
        saved. Logs are written to the normal application logger/stdout path.
        """
        if not self.api_key:
            raise RuntimeError("Missing COINALYZE_API_KEY in .env")

        started = time.time()
        now_ts = int(datetime.now(timezone.utc).timestamp())
        from_ts = int((datetime.now(timezone.utc) - timedelta(hours=30)).timestamp())
        symbols_param = ",".join(self.symbol_map.values())

        snapshots: dict[tuple[str, int], dict] = {}
        endpoint_results: list[dict] = []

        endpoints = [
            ("open-interest-history", self._parse_oi_history),
            ("funding-rate-history", self._parse_funding_history),
            ("predicted-funding-rate-history", self._parse_predicted_funding_history),
            ("long-short-ratio-history", self._parse_ls_history),
            ("liquidation-history", self._parse_liquidation_history),
        ]

        self.log.info("Coinalyze refresh start symbols=%s", symbols_param)

        for endpoint, parser in endpoints:
            ep_started = time.time()
            rows_seen = 0
            try:
                self.log.info("Coinalyze fetch_start endpoint=%s symbols=%s", endpoint, symbols_param)
                data = self._get(
                    f"/{endpoint}",
                    {
                        "symbols": symbols_param,
                        "interval": self.interval,
                        "from": from_ts,
                        "to": now_ts,
                    },
                )

                for row in parser(data):
                    symbol = row.get("symbol")
                    ts = row.get("ts")
                    if not symbol or ts is None:
                        continue
                    key = (str(symbol), int(ts))
                    base = snapshots.setdefault(
                        key,
                        {
                            "symbol": str(symbol),
                            "coinalyze_symbol": row.get("coinalyze_symbol"),
                            "ts": int(ts),
                            "interval": self.interval,
                            "raw_json": {},
                        },
                    )
                    safe_row = {k: v for k, v in row.items() if v is not None and k != "raw_json"}
                    base.update(safe_row)
                    if not isinstance(base.get("raw_json"), dict):
                        base["raw_json"] = {}
                    raw = row.get("raw_json")
                    base["raw_json"][endpoint] = dict(raw) if isinstance(raw, dict) else {}
                    rows_seen += 1

                duration_ms = int((time.time() - ep_started) * 1000)
                self.log.info("Coinalyze fetch_ok endpoint=%s rows=%s duration_ms=%s", endpoint, rows_seen, duration_ms)
                endpoint_results.append({"endpoint": endpoint, "ok": True, "rows": rows_seen, "duration_ms": duration_ms})
            except Exception as exc:  # noqa: BLE001 - isolate endpoint failures
                duration_ms = int((time.time() - ep_started) * 1000)
                msg = f"{type(exc).__name__}: {exc}"
                self.log.exception("Coinalyze fetch_error endpoint=%s duration_ms=%s error=%s", endpoint, duration_ms, msg)
                endpoint_results.append({"endpoint": endpoint, "ok": False, "rows": 0, "duration_ms": duration_ms, "error": msg})
                continue

        saved = 0
        save_started = time.time()
        for row in snapshots.values():
            self.store.upsert_point(row)
            saved += 1

        self.last_refresh_at = datetime.now(timezone.utc).isoformat()
        failed = [x for x in endpoint_results if not x.get('ok')]
        self.last_error = '; '.join(x.get('error', '') for x in failed) if failed else None
        self.last_rows_saved = saved
        status = 'failed' if saved == 0 else 'partial_success' if failed else 'success'
        duration_ms = int((time.time() - started) * 1000)
        self.log.info(
            "Coinalyze refresh_done status=%s rows_saved=%s duration_ms=%s save_ms=%s",
            status, saved, duration_ms, int((time.time() - save_started) * 1000),
        )

        return {
            "ok": saved > 0,
            "status": status,
            "rows_saved": saved,
            "refreshed_at": self.last_refresh_at,
            "duration_ms": duration_ms,
            "endpoints": endpoint_results,
            "error": self.last_error,
        }

    def _get(self, path: str, params: dict) -> list | dict:
        url = self.BASE_URL + path

        response = requests.get(
            url,
            params=params,
            headers={"api_key": self.api_key or ""},
            timeout=self.timeout,
        )

        if response.status_code == 429:
            raise RuntimeError("Coinalyze rate limit reached")

        if not response.ok:
            raise RuntimeError(
                f"Coinalyze API error {response.status_code}: {response.text[:300]}"
            )

        return response.json()

    def _symbol_from_coinalyze(self, coinalyze_symbol: str) -> str:
        for local, remote in self.symbol_map.items():
            if remote == coinalyze_symbol:
                return local

        return coinalyze_symbol.split("_PERP")[0].upper()

    def _iter_history(self, data):
        if isinstance(data, dict):
            data = [data]

        for item in data or []:
            remote_symbol = item.get("symbol") or item.get("s")

            if not remote_symbol:
                continue

            local_symbol = self._symbol_from_coinalyze(str(remote_symbol))
            history = item.get("history") or item.get("data") or []

            for point in history:
                ts = point.get("t") or point.get("time") or point.get("timestamp")

                if ts is None:
                    continue

                yield local_symbol, remote_symbol, int(ts), point

    @staticmethod
    def _last_number(point: dict, keys: list[str]) -> float | None:
        for key in keys:
            if key in point and point.get(key) is not None:
                try:
                    return float(point.get(key))
                except (TypeError, ValueError):
                    return None

        return None

    def _parse_oi_history(self, data):
        for symbol, remote, ts, point in self._iter_history(data):
            yield {
                "symbol": symbol,
                "coinalyze_symbol": remote,
                "ts": ts,
                "oi": self._last_number(point, ["c", "close", "oi", "value"]),
                "raw_json": point,
            }

    def _parse_funding_history(self, data):
        for symbol, remote, ts, point in self._iter_history(data):
            yield {
                "symbol": symbol,
                "coinalyze_symbol": remote,
                "ts": ts,
                "funding_rate": self._last_number(
                    point,
                    ["c", "close", "funding_rate", "value"],
                ),
                "raw_json": point,
            }

    def _parse_predicted_funding_history(self, data):
        for symbol, remote, ts, point in self._iter_history(data):
            yield {
                "symbol": symbol,
                "coinalyze_symbol": remote,
                "ts": ts,
                "predicted_funding_rate": self._last_number(
                    point,
                    ["c", "close", "predicted_funding_rate", "value"],
                ),
                "raw_json": point,
            }

    def _parse_ls_history(self, data):
        for symbol, remote, ts, point in self._iter_history(data):
            # Coinalyze long-short history documents points as: t, r, l, s.
            ratio = self._last_number(
                point,
                ["r", "c", "close", "ratio", "long_short_ratio", "value"],
            )
            ls_long = self._last_number(point, ["l", "long", "long_percent", "long_percentage"])
            ls_short = self._last_number(point, ["s", "short", "short_percent", "short_percentage"])

            if (ls_long is None or ls_short is None) and ratio is not None and ratio >= 0:
                ls_long = round((ratio / (1 + ratio)) * 100, 4) if ratio > 0 else 0.0
                ls_short = round(100 - ls_long, 4)

            yield {
                "symbol": symbol,
                "coinalyze_symbol": remote,
                "ts": ts,
                "ls_ratio": ratio,
                "ls_long": ls_long,
                "ls_short": ls_short,
                "raw_json": point,
            }

    def _parse_liquidation_history(self, data):
        for symbol, remote, ts, point in self._iter_history(data):
            yield {
                "symbol": symbol,
                "coinalyze_symbol": remote,
                "ts": ts,
                "long_liquidations": self._last_number(
                    point,
                    ["l", "long", "long_liquidations"],
                ),
                "short_liquidations": self._last_number(
                    point,
                    ["s", "short", "short_liquidations"],
                ),
                "raw_json": point,
            }
