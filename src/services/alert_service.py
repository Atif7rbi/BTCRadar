from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from ..alerts.telegram_alerts import TelegramAlerter


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat()


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _short(symbol: str) -> str:
    return str(symbol or '').upper().replace('USDT', '')


def _health_tier(state: dict | None) -> str:
    if not state:
        return 'WAITING'
    status = str(state.get('status') or '').upper()
    score = _num(state.get('health_score'))
    if 'EXIT' in status or score < 50:
        return 'EXIT'
    if 'WARNING' in status or score < 70:
        return 'WARNING'
    if score >= 90:
        return 'SAFE+'
    return 'SAFE'


def _fmt_score(v: Any) -> str:
    try:
        return str(int(round(float(v))))
    except Exception:
        return '--'


def _state_icon(tier: str) -> str:
    t = str(tier or '').upper()
    if t == 'EXIT':
        return '🔴'
    if t == 'WARNING':
        return '🟡'
    if t in ('SAFE', 'SAFE+'):
        return '🟢'
    return '⚪'


def _fmt_pnl_pct(v: Any) -> str:
    try:
        n = float(v)
        return f'{n:+.2f}%'
    except Exception:
        return '--'


def _fmt_pnl_usd(v: Any) -> str:
    try:
        n = float(v)
        return f'{n:+.2f} USD'
    except Exception:
        return '--'


def _fmt_funding_decimal(v: Any) -> str:
    if v is None:
        return '--'
    try:
        return f'{float(v) * 100:.4f}%'
    except Exception:
        return '--'


def _preferred(state: dict | None) -> str:
    return str((state or {}).get('preferred_direction') or 'WAIT').upper()


def _reason_line(state: dict | None) -> str:
    if not state:
        return 'No monitor state.'
    reasons = state.get('reasons') or []
    if isinstance(reasons, list) and reasons:
        return ' | '.join(str(x) for x in reasons[:3])
    return str(state.get('narrative') or '--')


class AlertService:
    """BTCRadar Telegram Alert Engine.

    P0 alerts:
    - Entry opportunity: BTC SAFE/SAFE+ + follower SAFE/SAFE+, no open trade.
    - A+ setup: BTC SAFE+ + follower SAFE+, no open trade.
    - Open trade warning: BTC or symbol WARNING, only if trade is open.
    - Open trade exit: BTC or symbol EXIT, only if trade is open.

    Optional:
    - Funding extreme alert.
    - Verdict change alert (stored state prevents first-run spam).
    """

    def __init__(self, cfg: dict, trade_store):
        self.cfg = cfg or {}
        self.trade_store = trade_store
        self.alert_cfg = self.cfg.get('alerts', {}) or {}
        self.enabled = bool(self.alert_cfg.get('enabled', True))
        self.cooldown_minutes = int(self.alert_cfg.get('cooldown_minutes', 60))
        self.funding_threshold_pct = float(self.alert_cfg.get('funding_extreme_pct', 0.02))
        self.telegram = TelegramAlerter(self.cfg)
        self._ensure_tables()

    def _ensure_tables(self):
        with self.trade_store.db.connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS btc_radar_alert_events (
                    alert_key TEXT PRIMARY KEY,
                    alert_type TEXT,
                    symbol TEXT,
                    state_hash TEXT,
                    sent_at TEXT,
                    message TEXT
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS btc_radar_alert_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT,
                    updated_at TEXT
                )
            """)

    def process(self, *, symbol_states: dict, followers: list[dict], open_trades: list[dict], driver: str = 'BTCUSDT') -> list[dict]:
        if not self.enabled or not self.telegram.enabled:
            return []

        sent: list[dict] = []
        symbol_states = symbol_states or {}
        followers = followers or []
        open_trades = open_trades or []

        open_by_symbol = {str(t.get('symbol') or '').upper(): t for t in open_trades}
        btc_state = symbol_states.get(driver.upper(), {})
        btc_tier = _health_tier(btc_state)
        btc_pref = _preferred(btc_state)

        for f in followers:
            symbol = str(f.get('symbol') or '').upper()
            if not symbol or symbol == driver.upper() or symbol in open_by_symbol:
                continue

            s_state = symbol_states.get(symbol, {})
            s_tier = _health_tier(s_state)
            s_pref = _preferred(s_state)
            aligned = btc_pref == s_pref and btc_pref in ('LONG', 'SHORT')

            if btc_tier in ('SAFE', 'SAFE+') and s_tier in ('SAFE', 'SAFE+') and aligned:
                is_aplus = btc_tier == 'SAFE+' and s_tier == 'SAFE+'
                alert_type = 'SAFE_PLUS_ENTRY' if is_aplus else 'ENTRY'
                title = '🔥 BTCRadar A+ Setup' if is_aplus else '🟢 BTCRadar Entry Watch'
                msg = self._entry_message(title, symbol, btc_state, s_state, f, btc_tier, s_tier, btc_pref)
                key = f'{alert_type}:{symbol}:{btc_pref}:{btc_tier}:{s_tier}'
                if self._send_once(key, alert_type, symbol, msg, f'{btc_tier}|{s_tier}|{btc_pref}'):
                    sent.append({'type': alert_type, 'symbol': symbol})

        for trade in open_trades:
            symbol = str(trade.get('symbol') or '').upper()
            if not symbol:
                continue
            s_state = symbol_states.get(symbol, {})
            s_tier = _health_tier(s_state)
            direction = str(trade.get('direction') or '').upper()
            trade_id = trade.get('id')

            current_trade_state = f'{btc_tier}|{s_tier}|{direction}'
            state_key = f'trade_alert_state:{trade_id}:{symbol}'
            previous_trade_state = self._get_state(state_key)

            if btc_tier == 'EXIT' or s_tier == 'EXIT':
                alert_type = 'EXIT'
                if previous_trade_state != current_trade_state:
                    msg = self._trade_message('🔴 EXIT SIGNAL', trade, btc_state, s_state, btc_tier, s_tier)
                    key = f'{alert_type}:{trade_id}:{symbol}'
                    if self._send_once(key, alert_type, symbol, msg, current_trade_state):
                        self._set_state(state_key, current_trade_state)
                        sent.append({'type': alert_type, 'symbol': symbol, 'trade_id': trade_id})
            elif btc_tier == 'WARNING' or s_tier == 'WARNING':
                alert_type = 'WARNING'
                if previous_trade_state != current_trade_state:
                    msg = self._trade_message('🟡 WARNING', trade, btc_state, s_state, btc_tier, s_tier)
                    key = f'{alert_type}:{trade_id}:{symbol}'
                    if self._send_once(key, alert_type, symbol, msg, current_trade_state):
                        self._set_state(state_key, current_trade_state)
                        sent.append({'type': alert_type, 'symbol': symbol, 'trade_id': trade_id})
            else:
                self._set_state(state_key, current_trade_state)

        if bool(self.alert_cfg.get('funding_extreme_enabled', True)):
            sent.extend(self._funding_extreme_alerts(symbol_states, followers, open_by_symbol))

        if bool(self.alert_cfg.get('verdict_change_enabled', False)):
            sent.extend(self._verdict_change_alerts(symbol_states))

        return sent

    def _entry_message(self, title: str, symbol: str, btc_state: dict, s_state: dict, follower_row: dict, btc_tier: str, s_tier: str, direction: str) -> str:
        funding = follower_row.get('funding')
        follow_score = follower_row.get('follow_score')
        short = _short(symbol)
        is_aplus = btc_tier == 'SAFE+' and s_tier == 'SAFE+'
        header = '🔥 A+ SETUP' if is_aplus else '🟢 ENTRY SETUP'
        return '\n'.join([
            header,
            '━━━━━━━━━━━━━━━━━━',
            '',
            f'{symbol} • {direction}',
            '',
            f'{_state_icon(btc_tier)} BTC      {btc_tier:<7} {_fmt_score(btc_state.get("health_score"))}',
            f'{_state_icon(s_tier)} {short:<8} {s_tier:<7} {_fmt_score(s_state.get("health_score"))}',
            '',
            f'📊 Follow   {_fmt_score(follow_score)}',
            f'💸 Funding  {_fmt_funding_decimal(funding)}',
            '',
            '━━━━━━━━━━━━━━━━━━',
            '🎯 DECISION: ENTER',
        ])

    def _trade_message(self, title: str, trade: dict, btc_state: dict, s_state: dict, btc_tier: str, s_tier: str) -> str:
        symbol = str(trade.get('symbol') or '').upper()
        short = _short(symbol)
        direction = str(trade.get('direction') or '').upper()
        pnl_pct = trade.get('pnl_pct')
        pnl_usd = trade.get('pnl_usd')
        is_exit = btc_tier == 'EXIT' or s_tier == 'EXIT'
        header = '🔴 EXIT SIGNAL' if is_exit else '🟡 WARNING'
        decision = 'CLOSE' if is_exit else 'MONITOR'
        money_label = '💵 Loss' if _num(pnl_usd) < 0 else '💵 Gain'

        return '\n'.join([
            header,
            '━━━━━━━━━━━━━━━━━━',
            '',
            f'Trade #{trade.get("id")}',
            f'{symbol} • {direction}',
            '',
            f'{_state_icon(btc_tier)} BTC      {btc_tier:<7} {_fmt_score(btc_state.get("health_score"))}',
            f'{_state_icon(s_tier)} {short:<8} {s_tier:<7} {_fmt_score(s_state.get("health_score"))}',
            '',
            f'💰 PnL      {_fmt_pnl_pct(pnl_pct)}',
            f'{money_label}     {_fmt_pnl_usd(pnl_usd)}',
            '',
            '━━━━━━━━━━━━━━━━━━',
            f'🎯 DECISION: {decision}',
        ])

    def _funding_extreme_alerts(self, symbol_states: dict, followers: list[dict], open_by_symbol: dict) -> list[dict]:
        sent = []
        for f in followers or []:
            symbol = str(f.get('symbol') or '').upper()
            if not symbol:
                continue
            funding = f.get('funding')
            try:
                funding_pct = float(funding) * 100
            except Exception:
                continue
            if abs(funding_pct) < self.funding_threshold_pct:
                continue
            state = symbol_states.get(symbol, {})
            tier = _health_tier(state)
            open_txt = 'YES' if symbol in open_by_symbol else 'NO'
            direction = _preferred(state)
            msg = '\n'.join([
                '⚡ FUNDING EXTREME',
                '━━━━━━━━━━━━━━━━━━',
                '',
                f'{symbol} • {direction}',
                '',
                f'{_state_icon(tier)} {_short(symbol):<8} {tier:<7} {_fmt_score(state.get("health_score"))}',
                '',
                f'💸 Funding  {funding_pct:.4f}%',
                f'📌 Open     {open_txt}',
                '',
                '━━━━━━━━━━━━━━━━━━',
                '🎯 DECISION: WATCH',
            ])
            bucket = 'NEG' if funding_pct < 0 else 'POS'
            key = f'FUNDING:{symbol}:{bucket}:{round(abs(funding_pct), 3)}'
            if self._send_once(key, 'FUNDING', symbol, msg, f'{bucket}|{tier}'):
                sent.append({'type': 'FUNDING', 'symbol': symbol})
        return sent

    def _verdict_change_alerts(self, symbol_states: dict) -> list[dict]:
        sent = []
        for symbol, state in (symbol_states or {}).items():
            coinalyze = state.get('coinalyze') or {}
            verdict = str(coinalyze.get('verdict') or '').upper().strip()
            if not verdict:
                continue

            state_key = f'verdict:{symbol}'
            previous = self._get_state(state_key)
            self._set_state(state_key, verdict)

            if previous is None or previous == verdict:
                continue

            msg = '\n'.join([
                '🧭 BTCRadar Verdict Change',
                '',
                f'Symbol: {symbol}',
                f'From: {previous}',
                f'To: {verdict}',
                f'Health: {_health_tier(state)} {_fmt_score(state.get("health_score"))}',
            ])
            key = f'VERDICT:{symbol}:{previous}->{verdict}'
            if self._send_once(key, 'VERDICT', symbol, msg, verdict):
                sent.append({'type': 'VERDICT', 'symbol': symbol})
        return sent

    def _send_once(self, alert_key: str, alert_type: str, symbol: str, message: str, state_hash: str) -> bool:
        now = _now()
        with self.trade_store.db.connect() as con:
            row = con.execute(
                'SELECT alert_key, state_hash, sent_at FROM btc_radar_alert_events WHERE alert_key=?',
                (alert_key,),
            ).fetchone()

            if row:
                previous_hash = row['state_hash']
                sent_at_raw = row['sent_at']
                try:
                    sent_at = datetime.fromisoformat(str(sent_at_raw).replace('Z', '+00:00'))
                except Exception:
                    sent_at = now - timedelta(days=365)
                if previous_hash == state_hash and (now - sent_at).total_seconds() < self.cooldown_minutes * 60:
                    return False

            ok = self.telegram.send(message)
            if not ok:
                return False

            con.execute(
                """
                INSERT OR REPLACE INTO btc_radar_alert_events
                (alert_key, alert_type, symbol, state_hash, sent_at, message)
                VALUES (?,?,?,?,?,?)
                """,
                (alert_key, alert_type, symbol, state_hash, _iso(now), message),
            )
        return True

    def _get_state(self, state_key: str) -> str | None:
        with self.trade_store.db.connect() as con:
            row = con.execute(
                'SELECT state_value FROM btc_radar_alert_state WHERE state_key=?',
                (state_key,),
            ).fetchone()
            return row['state_value'] if row else None

    def _set_state(self, state_key: str, state_value: str):
        with self.trade_store.db.connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO btc_radar_alert_state
                (state_key, state_value, updated_at)
                VALUES (?,?,?)
                """,
                (state_key, state_value, _iso()),
            )
