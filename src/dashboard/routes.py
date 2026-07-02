from __future__ import annotations
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, jsonify, request
from ..analyzers.btc_monitor import BTCMonitor
from ..services.validation_report import generate_validation_report


def create_dashboard(market, signal_service, trade_service, trade_store, cfg: dict, coinalyze_store=None, coinalyze_collector=None, alert_service=None, trade_lifecycle=None, job_status_store=None) -> Blueprint:
    bp = Blueprint('dashboard', __name__, template_folder='templates', static_folder='static')
    driver = cfg['symbols']['driver']
    followers_symbols = cfg['symbols'].get('followers', [])
    btc_monitor = BTCMonitor(cfg)

    def snap_to_ui(s):
        if not s: return None
        return s.to_dict()

    def follower_rows(sig):
        followers = []
        for sym in followers_symbols:
            snap = market.snapshots.get(sym)
            if snap:
                d = snap.to_dict(); d['_snapshot'] = snap; followers.append(d)
        return signal_service.score_followers(followers, sig)

    def btc_exit_monitor(symbol_states: dict):
        btc_state = (symbol_states or {}).get(driver, {})
        return btc_monitor.exit_card(btc_state)

    def _current_symbol_states() -> dict:
        monitor_symbols = [driver] + [s for s in followers_symbols if s != driver]
        coinalyze_summary = {}
        if coinalyze_store:
            try:
                coinalyze_summary = coinalyze_store.trend_summary(monitor_symbols, 30)
            except Exception:
                coinalyze_summary = {}
        monitor_snapshots = {
            symbol: market.snapshots.get(symbol)
            for symbol in monitor_symbols
            if market.snapshots.get(symbol)
        }
        return btc_monitor.evaluate_all(monitor_snapshots, coinalyze_summary)

    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def _period_start(period: str | None, custom_start: str | None = None) -> str | None:
        period = (period or 'all').lower()
        if period == '7d':
            return (_utc_now() - timedelta(days=7)).isoformat()
        if period == '30d':
            return (_utc_now() - timedelta(days=30)).isoformat()
        if period == '90d':
            return (_utc_now() - timedelta(days=90)).isoformat()
        if period == 'custom' and custom_start:
            # Accept YYYY-MM-DD from the UI and compare against ISO strings.
            return f'{custom_start}T00:00:00+00:00'
        return None

    def _rows_for_report(options: dict) -> list[dict]:
        period = options.get('period', 'all')
        start = _period_start(period, options.get('custom_start'))
        symbols = options.get('symbols') or []
        symbols = [str(s).upper() for s in symbols if s and str(s).upper() != 'ALL']

        sql = 'SELECT * FROM btc_radar_closed_trades WHERE 1=1'
        params: list[object] = []
        if start:
            sql += ' AND closed_at >= ?'
            params.append(start)
        if symbols:
            sql += ' AND symbol IN (%s)' % ','.join(['?'] * len(symbols))
            params.extend(symbols)
        sql += ' ORDER BY closed_at ASC, id ASC'

        with trade_store.db.connect() as con:
            return [dict(r) for r in con.execute(sql, params).fetchall()]

    def _num(v, default: float = 0.0) -> float:
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    def _pct(n: float, d: float) -> float:
        return round((n / d * 100), 2) if d else 0.0

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    def _format_duration(seconds) -> str:
        try:
            sec = int(float(seconds or 0))
        except (TypeError, ValueError):
            sec = 0
        if sec <= 0:
            return '--'
        minutes = sec // 60
        if minutes < 60:
            return f'{max(1, minutes)}m'
        hours = minutes // 60
        rem_m = minutes % 60
        if hours < 24:
            return f'{hours}h {rem_m}m' if rem_m else f'{hours}h'
        days = hours // 24
        rem_h = hours % 24
        return f'{days}d {rem_h}h' if rem_h else f'{days}d'

    def _avg_duration_text(rows: list[dict]) -> str:
        vals = [_num(r.get('duration_sec')) for r in rows if _num(r.get('duration_sec')) > 0]
        return _format_duration(sum(vals) / len(vals)) if vals else '--'

    def _health_label(raw) -> str:
        s = str(raw or '').upper().strip()
        if not s:
            return 'Legacy / Missing'
        if s in ('SAFE+', 'SAFE', 'WARNING', 'EXIT'):
            return s
        return s

    def _btc_health_label(r: dict) -> str:
        return _health_label(r.get('btc_health_status_at_entry'))

    def _follower_health_label(r: dict) -> str:
        return _health_label(r.get('follower_health_status_at_entry'))

    def _matrix_label(r: dict) -> str:
        return f'{_btc_health_label(r)} × {_follower_health_label(r)}'

    def _duration_label(r: dict) -> str:
        sec = _num(r.get('duration_sec'))
        if sec <= 0:
            return 'Legacy / Missing'
        minutes = sec / 60
        if minutes < 15:
            return '< 15m'
        if minutes < 60:
            return '15m-1h'
        if minutes < 240:
            return '1h-4h'
        if minutes < 1440:
            return '4h-24h'
        return '1d+'

    def _funding_label(r: dict) -> str:
        f = r.get('follower_funding_at_entry')
        if f is None:
            return 'Legacy / Missing'
        v = _num(f)
        if v <= -0.02:
            return 'Funding <= -0.02%'
        if v < -0.005:
            return 'Funding -0.005% to -0.02%'
        if v < 0:
            return 'Funding Slight Negative'
        if v == 0:
            return 'Funding Neutral'
        if v < 0.005:
            return 'Funding Slight Positive'
        if v < 0.02:
            return 'Funding +0.005% to +0.02%'
        return 'Funding >= +0.02%'

    def _performance_summary(rows: list[dict], initial_equity: float) -> dict:
        total = len(rows)
        wins = [r for r in rows if _num(r.get('pnl_usd')) > 0]
        losses = [r for r in rows if _num(r.get('pnl_usd')) <= 0]
        gross_profit = round(sum(_num(r.get('pnl_usd')) for r in wins), 4)
        gross_loss = round(sum(_num(r.get('pnl_usd')) for r in losses), 4)
        net_pnl = round(gross_profit + gross_loss, 4)
        profit_factor = round(gross_profit / abs(gross_loss), 3) if gross_loss < 0 else (gross_profit if gross_profit else 0.0)
        return {
            'trades': total,
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': _pct(len(wins), total),
            'net_pnl': net_pnl,
            'equity': round(initial_equity + net_pnl, 4),
            'equity_pct': _pct(net_pnl, initial_equity),
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': profit_factor,
            'avg_winner_pct': _avg([_num(r.get('pnl_pct')) for r in wins]),
            'avg_loser_pct': _avg([_num(r.get('pnl_pct')) for r in losses]),
            'avg_trade_pct': _avg([_num(r.get('pnl_pct')) for r in rows]),
            'avg_duration': _avg_duration_text(rows),
        }

    def _bucket_stats(rows: list[dict], key_fn, label_order: list[str] | None = None) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for r in rows:
            label = key_fn(r)
            groups.setdefault(label, []).append(r)
        labels = label_order or sorted(groups.keys())
        out = []
        for label in labels:
            rs = groups.get(label, [])
            total = len(rs)
            wins = sum(1 for r in rs if _num(r.get('pnl_usd')) > 0)
            net_pnl = round(sum(_num(r.get('pnl_usd')) for r in rs), 4)
            out.append({
                'label': label,
                'trades': total,
                'wins': wins,
                'losses': max(0, total - wins),
                'win_rate': _pct(wins, total),
                'net_pnl': net_pnl,
                'avg_pnl_pct': _avg([_num(r.get('pnl_pct')) for r in rs]),
                'avg_duration': _avg_duration_text(rs),
            })
        return out

    def _spread_label(r: dict) -> str:
        spread = r.get('btc_spread_at_entry')
        if spread is None:
            return 'Legacy / Missing'
        s = _num(spread)
        if s < 20:
            return 'Spread < 20'
        if s < 30:
            return 'Spread 20-30'
        return 'Spread 30+'

    def _judgment_label(r: dict) -> str:
        j = (r.get('decision_judgment') or '').strip()
        if not j:
            return 'Legacy / Missing'
        return j.split('|')[0].strip() or 'Unknown'

    def _equity_curve(rows: list[dict], initial_equity: float) -> list[dict]:
        equity = float(initial_equity)
        points = [{'index': 0, 'label': 'Start', 'equity': round(equity, 4), 'pnl': 0.0}]
        for i, r in enumerate(rows, start=1):
            pnl = _num(r.get('pnl_usd'))
            equity += pnl
            points.append({
                'index': i,
                'label': r.get('closed_at') or f'Trade {i}',
                'trade_id': r.get('trade_id'),
                'symbol': r.get('symbol'),
                'equity': round(equity, 4),
                'pnl': pnl,
            })
        return points

    def _conclusions(report: dict) -> list[str]:
        notes = []
        perf = report.get('performance', {})
        if perf.get('trades', 0) < 20:
            notes.append('Sample size is still small. Use this report as an early read, not a final verdict.')
        elif perf.get('win_rate', 0) >= 60 and perf.get('profit_factor', 0) >= 1.5:
            notes.append('Performance shows a positive edge in the selected period.')
        else:
            notes.append('Performance needs more validation before automation decisions.')

        spread_rows = report.get('spread_analysis', [])
        s30 = next((x for x in spread_rows if x.get('label') == 'Spread 30+'), None)
        if s30 and s30.get('trades', 0) >= 5:
            if s30.get('win_rate', 0) >= 65:
                notes.append('Spread 30+ is currently the strongest crowding zone.')
            elif s30.get('win_rate', 0) < 50:
                notes.append('Spread 30+ did not validate yet; avoid assuming it is automatically strong.')
        return notes

    def _generate_report(options: dict) -> dict:
        rows = _rows_for_report(options)
        initial_equity = float(cfg.get('account', {}).get('initial_equity_usd', 1000.0))
        sections = options.get('sections') or [
            'performance', 'spread', 'judgment', 'symbol', 'equity',
            'duration', 'btc_health', 'follower_health', 'health_matrix', 'funding'
        ]

        report = {
            'generated_at': _utc_now().isoformat(),
            'period': options.get('period', 'all'),
            'symbols': options.get('symbols') or ['ALL'],
            'sections': sections,
            'trade_count': len(rows),
            'performance': _performance_summary(rows, initial_equity),
        }

        if 'spread' in sections:
            report['spread_analysis'] = _bucket_stats(
                rows,
                _spread_label,
                ['Spread < 20', 'Spread 20-30', 'Spread 30+', 'Legacy / Missing'],
            )
        if 'judgment' in sections:
            report['judgment_analysis'] = _bucket_stats(rows, _judgment_label)
        if 'symbol' in sections:
            report['symbol_analysis'] = _bucket_stats(rows, lambda r: r.get('symbol') or 'Unknown')
        if 'duration' in sections:
            report['duration_analysis'] = _bucket_stats(
                rows,
                _duration_label,
                ['< 15m', '15m-1h', '1h-4h', '4h-24h', '1d+', 'Legacy / Missing'],
            )
        if 'btc_health' in sections:
            report['btc_health_analysis'] = _bucket_stats(
                rows,
                _btc_health_label,
                ['SAFE+', 'SAFE', 'WARNING', 'EXIT', 'Legacy / Missing'],
            )
        if 'follower_health' in sections:
            report['follower_health_analysis'] = _bucket_stats(
                rows,
                _follower_health_label,
                ['SAFE+', 'SAFE', 'WARNING', 'EXIT', 'Legacy / Missing'],
            )
        if 'health_matrix' in sections:
            matrix_order = [
                'SAFE+ × SAFE+', 'SAFE+ × SAFE', 'SAFE+ × WARNING', 'SAFE+ × EXIT',
                'SAFE × SAFE+', 'SAFE × SAFE', 'SAFE × WARNING', 'SAFE × EXIT',
                'WARNING × SAFE+', 'WARNING × SAFE', 'WARNING × WARNING', 'WARNING × EXIT',
                'EXIT × SAFE+', 'EXIT × SAFE', 'EXIT × WARNING', 'EXIT × EXIT',
                'Legacy / Missing × Legacy / Missing',
            ]
            report['health_matrix'] = _bucket_stats(rows, _matrix_label, matrix_order)
        if 'funding' in sections:
            report['funding_analysis'] = _bucket_stats(
                rows,
                _funding_label,
                [
                    'Funding <= -0.02%',
                    'Funding -0.005% to -0.02%',
                    'Funding Slight Negative',
                    'Funding Neutral',
                    'Funding Slight Positive',
                    'Funding +0.005% to +0.02%',
                    'Funding >= +0.02%',
                    'Legacy / Missing',
                ],
            )
        if 'equity' in sections:
            report['equity_curve'] = _equity_curve(rows, initial_equity)

        report['conclusions'] = _conclusions(report)
        return report

    @bp.route('/')
    def index():
        return render_template('index.html', cfg=cfg, driver=driver, followers=followers_symbols)

    @bp.route('/api/state')
    def api_state():
        # Read-only Dashboard path: load saved snapshots and overlay fast price only.
        # This never triggers Coinalyze or any heavy refresh.
        try:
            market.bootstrap_from_cache()
            market.refresh_price_overlay_if_needed()
        except Exception:
            pass
        sig = signal_service.analyze(market.snapshots)
        btc_snap = market.snapshots.get(driver)
        btc = snap_to_ui(btc_snap)
        followers = follower_rows(sig)
        auto_guard_closed = trade_service.sync_pnl() or []

        symbol_states = _current_symbol_states()

        if trade_lifecycle and auto_guard_closed:
            for closed in auto_guard_closed:
                try:
                    trade = trade_store.get_trade(int(closed.get('id')))
                    if trade:
                        trade_lifecycle.record_close(
                            trade,
                            symbol_states=symbol_states,
                            driver=driver,
                            reason=closed.get('reason') or 'AUTO_GUARD'
                        )
                except Exception:
                    pass

        open_trades = trade_store.open_trades()
        for trade in open_trades:
            trade['monitor_alert'] = btc_monitor.evaluate_trade(trade, symbol_states, driver)

        lifecycle_events = []
        if trade_lifecycle:
            try:
                lifecycle_events = trade_lifecycle.process_open_trades(
                    symbol_states=symbol_states,
                    open_trades=open_trades,
                    driver=driver,
                )
            except Exception:
                lifecycle_events = []

        alerts_sent = []
        if alert_service:
            try:
                alerts_sent = alert_service.process(
                    symbol_states=symbol_states,
                    followers=followers,
                    open_trades=open_trades,
                    driver=driver,
                )
            except Exception:
                alerts_sent = []

        followers_consensus = market.followers_consensus() if hasattr(market, 'followers_consensus') else None

        return jsonify({
            'btc': btc,
            'signal': sig.to_dict() if sig else None,
            'followers': followers,
            'followers_consensus': followers_consensus,
            'symbol_states': symbol_states,
            'open_trades': open_trades,
            'closed_trades': trade_store.closed_trades(50),
            'performance': trade_store.stats(float(cfg.get('account', {}).get('initial_equity_usd', 1000.0))),
            'spread_trend': signal_service.spread_trend(),
            'btc_exit_monitor': btc_exit_monitor(symbol_states),
            'alerts_sent': alerts_sent,
            'lifecycle_events': lifecycle_events,
            'auto_guard_closed': auto_guard_closed,
            'status': market.status(),
        })

    @bp.route('/api/market-monitor')
    def market_monitor_state():
        if not hasattr(market, 'market_monitor_state'):
            return jsonify({'ok': False, 'error': 'Market Monitor is not available'}), 404
        return jsonify(market.market_monitor_state())

    @bp.route('/api/reports/generate', methods=['POST'])
    def generate_report():
        options = request.get_json(force=True) or {}
        return jsonify(_generate_report(options))

    @bp.route('/api/reports/validation')
    def validation_report():
        options = {
            'period': request.args.get('period', 'all'),
            'custom_start': request.args.get('custom_start'),
            'symbols': request.args.get('symbols', 'ALL'),
        }
        return jsonify(generate_validation_report(trade_store.db, options))




    @bp.route('/api/lifecycle/trades')
    def lifecycle_trades():
        if not trade_lifecycle:
            return jsonify({'trades': []})
        status = request.args.get('status', 'all')
        return jsonify({'trades': trade_lifecycle.trade_options(status)})

    @bp.route('/api/lifecycle/trades/<int:trade_id>')
    def lifecycle_trade_detail(trade_id: int):
        if not trade_lifecycle:
            return jsonify({'trade': None, 'events': [], 'summary': {}})
        return jsonify(trade_lifecycle.summary_for_trade(trade_id))


    @bp.route('/api/coinalyze/state')
    def coinalyze_state():
        symbols = [driver] + [s for s in followers_symbols if s != driver]
        status = coinalyze_collector.status() if coinalyze_collector else {
            'enabled': False,
            'configured': False,
            'last_error': 'Coinalyze collector is not initialized',
        }
        if job_status_store:
            try:
                status['cron'] = job_status_store.latest('coinalyze_heavy_refresh')
            except Exception:
                status['cron'] = None
        if not coinalyze_store:
            return jsonify({'status': status, 'rows': []})

        summary = coinalyze_store.trend_summary(symbols, 30)
        rows = []
        for symbol in symbols:
            item = summary.get(symbol, {})
            rows.append({
                'symbol': symbol,
                'latest': item.get('latest') or {},
                'trend': item.get('trend') or {},
                'analysis': item.get('analysis') or {},
            })

        return jsonify({
            'status': status,
            'rows': rows,
        })

    @bp.route('/api/coinalyze/refresh', methods=['POST'])
    def coinalyze_refresh():
        latest = None
        recent = []
        if job_status_store:
            try:
                latest = job_status_store.latest('coinalyze_heavy_refresh')
                recent = job_status_store.recent('coinalyze_heavy_refresh', 10)
            except Exception:
                pass
        return jsonify({
            'ok': False,
            'disabled': True,
            'message': 'Coinalyze refresh is owned by cPanel Cron on hosting. Manual web refresh is disabled to prevent Passenger timeouts.',
            'latest': latest,
            'recent': recent,
        }), 202

    @bp.route('/api/jobs/status')
    def jobs_status():
        if not job_status_store:
            return jsonify({'jobs': [], 'latest': None})
        job_name = request.args.get('job') or None
        return jsonify({
            'latest': job_status_store.latest(job_name or 'coinalyze_heavy_refresh') if job_name or True else None,
            'jobs': job_status_store.recent(job_name, int(request.args.get('limit', 20))),
        })

    @bp.route('/api/trades/open', methods=['POST'])
    def open_trade():
        data = request.get_json(force=True)
        sig = signal_service.analyze(market.snapshots)
        followers = follower_rows(sig)
        symbol_states = _current_symbol_states()
        trade_service.open_trade(data['symbol'], data['direction'], float(data.get('size_usd') or 100), sig, followers, symbol_states)
        return jsonify({'ok': True})

    @bp.route('/api/trades/<int:trade_id>/close', methods=['POST'])
    def close_trade(trade_id: int):
        trade_service.close_trade(trade_id, 'MANUAL_CLOSE')
        if trade_lifecycle:
            try:
                symbol_states = _current_symbol_states()
                trade = trade_store.get_trade(trade_id)
                if trade:
                    trade_lifecycle.record_close(trade, symbol_states=symbol_states, driver=driver)
            except Exception:
                pass
        return jsonify({'ok': True})

    return bp
