#!/usr/bin/env python3
'''Generate Phoenix v5.1 Dashboard HTML.

Reads state.json, trade_log.json, kill_switch.json → produces dashboard.html
Deployed to Netlify for password-protected viewing.
'''

import json
import os
import sys
from datetime import datetime, date

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from live_bot.kill_switch import get_full_status
from live_bot.state import load_state, load_trade_log


def fmt_num(n, decimals=2):
    """Format number with commas."""
    if n is None:
        return '—'
    if abs(n) >= 1_000_000:
        return f'{n:,.{decimals}f}'
    if abs(n) >= 100:
        return f'{n:,.{decimals}f}'
    return f'{n:.{decimals}f}'


def fmt_pct(n):
    """Format percentage."""
    if n is None:
        return '—'
    return f'{n * 100:.1f}%'


def color_for_value(val, thresholds):
    """Return color class based on thresholds.
    thresholds: [(threshold, color_class), ...] ascending order.
    """
    if val is None:
        return 'neutral'
    for threshold, color in thresholds:
        if val < threshold:
            return color
    return thresholds[-1][1]


def mvrv_color(mvrv):
    if mvrv is None:
        return 'neutral'
    if mvrv < 1.0:
        return 'green'
    if mvrv < 2.0:
        return 'blue'
    if mvrv < 3.0:
        return 'yellow'
    return 'red'


def rsi_color(rsi):
    if rsi is None:
        return 'neutral'
    if rsi < 30:
        return 'green'
    if rsi < 70:
        return 'blue'
    return 'red'


def generate_dashboard(state_path='live_bot/state.json',
                       trade_log_path='trade_log.json',
                       kill_switch_path='kill_switch.json',
                       output_path='dashboard/dist/index.html'):
    """Generate complete dashboard HTML."""
    # Load data
    state = load_state(state_path)
    trade_log = load_trade_log(trade_log_path)
    ks_status = get_full_status(kill_switch_path)
    indicators = state.get('last_indicators', {})
    currency = state.get('last_exchange_currency', 'USDT')

    # Computed values from state (for portfolio snapshot)
    portfolio = state.get('last_portfolio_value', 0)
    current_price = state.get('last_price', 0)
    btc_bal = state.get('last_btc_balance', 0)
    cash_bal = state.get('last_cash_balance', 0)
    last_run = state.get('last_run_date', '—')
    run_count = state.get('run_count', 0)
    dry_run = state.get('last_dry_run', False)
    peak = state.get('peak_value', 0)
    max_dd = state.get('max_drawdown', 0)

    # Trade statistics — computed from trade_log (source of truth)
    tl_buys = [t for t in trade_log if t['type'] == 'buy']
    tl_sells = [t for t in trade_log if t['type'] == 'sell']
    buy_count = len(tl_buys)
    sell_count = len(tl_sells)
    total_btc_bought = sum(t['btc'] for t in tl_buys)
    total_btc_sold = sum(t['btc'] for t in tl_sells)
    invested = sum(t['amount'] for t in tl_buys)
    total_sell_proceeds = sum(t['amount'] for t in tl_sells)
    total_fees = sum(t.get('fee', 0) for t in trade_log)
    total_reserve = sum(t.get('reserve', 0) for t in tl_buys)
    last_trade_date = trade_log[-1]['date'] if trade_log else '—'
    roi = ((portfolio - invested) / invested * 100) if invested > 0 else 0.0

    # Time series for chart — value BTC at current price for accurate P&L
    portfolio_series = []
    if trade_log and current_price > 0:
        running_btc = 0.0
        net_cash_out = 0.0
        for trade in trade_log:
            if trade['type'] == 'buy':
                running_btc += trade['btc']
                net_cash_out += trade['amount'] + trade.get('fee', 0)
            else:
                running_btc -= trade['btc']
                net_cash_out -= trade['amount'] - trade.get('fee', 0)
            # Value BTC at current price (realistic P&L)
            pv = running_btc * current_price - net_cash_out
            portfolio_series.append({
                'date': trade['date'],
                'value': round(pv, 2),
                'type': trade['type']
            })
        # Add current snapshot point
        if portfolio > 0 and (not portfolio_series or portfolio_series[-1]['date'] != last_run):
            portfolio_series.append({
                'date': last_run,
                'value': round(portfolio, 2),
                'type': 'current'
            })

    # Recent trades (last 10)
    recent_trades = trade_log[-10:][::-1]  # newest first

    # Kill switch status
    bot_alive = ks_status['is_alive']
    l1_ok = ks_status['l1_enabled']
    l2_ok = ks_status['l2_enabled']
    ks_reason = ks_status.get('l2_reason', '')
    ks_time = ks_status.get('l2_activated_at', '')
    ks_by = ks_status.get('l2_activated_by', '')

    # Indicators
    mvrv = indicators.get('mvrv')
    mvrv_pct = indicators.get('mvrv_pct', 0)
    mvrv_z = indicators.get('mvrv_z', 0)
    rsi_val = indicators.get('rsi')
    macd_h = indicators.get('macd_h')
    nupl = indicators.get('nupl', 0)
    sopr = indicators.get('sopr', 0)
    sma200 = indicators.get('sma_200')
    sma365 = indicators.get('sma_365')
    sell_score = indicators.get('sell_score', 0)
    path_taken = indicators.get('path_taken', 'none')
    in_bear = indicators.get('in_bear', False)
    cooldown = indicators.get('cooldown', 0)
    ath = indicators.get('ath', 0)

    # Build HTML
    html = build_html(
        bot_alive=bot_alive, l1_ok=l1_ok, l2_ok=l2_ok,
        ks_reason=ks_reason, ks_time=ks_time, ks_by=ks_by,
        portfolio=portfolio, invested=invested, roi=roi,
        peak=peak, max_dd=max_dd, current_price=current_price,
        btc_bal=btc_bal, cash_bal=cash_bal, currency=currency,
        last_run=last_run, run_count=run_count, dry_run=dry_run,
        total_fees=total_fees,
        buy_count=buy_count,
        sell_count=sell_count,
        total_sell_proceeds=total_sell_proceeds,
        total_btc_bought=total_btc_bought,
        total_btc_sold=total_btc_sold,
        total_reserve=total_reserve,
        mvrv=mvrv, mvrv_pct=mvrv_pct, mvrv_z=mvrv_z,
        rsi_val=rsi_val, macd_h=macd_h, nupl=nupl, sopr=sopr,
        sma200=sma200, sma365=sma365, ath=ath,
        sell_score=sell_score, path_taken=path_taken,
        in_bear=in_bear, cooldown=cooldown,
        portfolio_series=portfolio_series,
        recent_trades=recent_trades,
        last_trade_date=last_trade_date,
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )

    # Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'[DASHBOARD] Generated {output_path} ({len(html):,} bytes)')
    return output_path


def build_html(**kw) -> str:
    """Build the complete HTML dashboard string."""
    # Unpack all needed variables from kw
    bot_alive = kw['bot_alive']
    l1_ok = kw['l1_ok']
    l2_ok = kw['l2_ok']
    ks_reason = kw.get('ks_reason', '')
    ks_time = kw.get('ks_time', '')
    ks_by = kw.get('ks_by', '')
    portfolio = kw['portfolio']
    invested = kw['invested']
    roi = kw['roi']
    peak = kw['peak']
    max_dd = kw['max_dd']
    current_price = kw['current_price']
    btc_bal = kw['btc_bal']
    cash_bal = kw['cash_bal']
    currency = kw['currency']
    last_run = kw['last_run']
    run_count = kw['run_count']
    dry_run = kw['dry_run']
    total_fees = kw['total_fees']
    buy_count = kw['buy_count']
    sell_count = kw['sell_count']
    total_sell_proceeds = kw['total_sell_proceeds']
    total_btc_bought = kw['total_btc_bought']
    total_btc_sold = kw['total_btc_sold']
    total_reserve = kw['total_reserve']
    mvrv = kw['mvrv']
    mvrv_pct = kw['mvrv_pct']
    mvrv_z = kw['mvrv_z']
    rsi_val = kw['rsi_val']
    macd_h = kw['macd_h']
    nupl = kw['nupl']
    sopr = kw['sopr']
    sma200 = kw['sma200']
    sma365 = kw['sma365']
    ath = kw['ath']
    sell_score = kw['sell_score']
    path_taken = kw['path_taken']
    in_bear = kw['in_bear']
    cooldown = kw['cooldown']
    state = kw.get('state', {})
    recent_trades = kw['recent_trades']
    portfolio_series = kw['portfolio_series']
    now_str = kw['now']
    last_trade_date = kw.get('last_trade_date', '—')

    # Status badge
    if bot_alive:
        status_html = '''<div class="status-badge alive">
            <span class="pulse"></span> BOT ACTIVE
        </div>'''
    else:
        reason = kw.get('ks_reason', 'Unknown')
        status_html = f'''<div class="status-badge killed">
            KILLED: {reason}
        </div>'''

    # L1/L2 indicators
    l1_html = '<span class="tag green">ON</span>' if l1_ok else '<span class="tag red">OFF</span>'
    l2_html = '<span class="tag green">ON</span>' if l2_ok else '<span class="tag red">OFF</span>'

    # ROI color
    roi_class = 'green' if roi > 0 else ('red' if roi < 0 else 'neutral')

    # Dry run badge
    dry_html = '<span class="tag yellow">DRY RUN</span>' if dry_run else ''

    # MVRV zone
    if mvrv is not None:
        if mvrv < 1.0:
            mvrv_zone = 'Accumulation Zone'
            mvrv_zone_class = 'green'
        elif mvrv < 2.0:
            mvrv_zone = 'Normal'
            mvrv_zone_class = 'blue'
        elif mvrv < 3.0:
            mvrv_zone = 'Euphoria'
            mvrv_zone_class = 'yellow'
        else:
            mvrv_zone = 'Danger Zone'
            mvrv_zone_class = 'red'
    else:
        mvrv_zone = 'N/A'
        mvrv_zone_class = 'neutral'

    # Sell score bar
    ss = sell_score
    ss_color = 'green' if ss < 30 else ('yellow' if ss < 50 else 'red')
    ss_width = min(ss, 100)

    # Bear badge
    bear_html = '<span class="tag red">BEAR MARKET</span>' if in_bear else ''

    # Path badge
    path = path_taken
    if path in ('A', 'A-Ext', 'B'):
        path_class = 'yellow'
    elif path == 'killed':
        path_class = 'red'
    elif path.startswith('no-trade'):
        path_class = 'neutral'
    else:
        path_class = 'blue'

    # Recent trades table rows
    trade_rows = ''
    for t in recent_trades:
        ttype = t['type'].upper()
        tclass = 'buy' if t['type'] == 'buy' else 'sell'
        extra = ''
        if 'path' in t and t['path']:
            extra = f" | Path: {t['path']} (score: {t.get('score', 0)})"
        if 'reserve' in t and t['reserve'] > 0:
            extra += f" | Reserve: {t['reserve']:.0f}"
        trade_rows += f'''
        <tr class="{tclass}">
            <td>{t['date']}</td>
            <td class="{tclass}">{ttype}</td>
            <td>{fmt_num(t['amount'])} {currency}</td>
            <td>{t['btc']:.8f}</td>
            <td>{fmt_num(t['price'])}</td>
            <td>{fmt_num(t.get('fee', 0))}</td>
        </tr>'''
    if not trade_rows:
        trade_rows = '<tr><td colspan="6" class="empty">ยังไม่มี trades</td></tr>'

    # Chart data
    chart_dates = json.dumps([p['date'] for p in portfolio_series])
    chart_values = json.dumps([p['value'] for p in portfolio_series])
    chart_types = json.dumps([p['type'] for p in portfolio_series])

    # BTC price for reference line in chart (use trade_log from kw)
    # We already have the trade_log data in portfolio_series

    return f'''<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="86400">  <!-- Auto refresh daily -->
    <title>Phoenix v5.1 Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        :root {{
            --bg: #0d1117;
            --card: #161b22;
            --border: #30363d;
            --text: #e6edf3;
            --text-dim: #8b949e;
            --green: #3fb950;
            --green-bg: rgba(63,185,80,0.1);
            --red: #f85149;
            --red-bg: rgba(248,81,73,0.1);
            --blue: #58a6ff;
            --blue-bg: rgba(88,166,255,0.1);
            --yellow: #d29922;
            --yellow-bg: rgba(210,153,34,0.1);
            --purple: #bc8cff;
            --purple-bg: rgba(188,140,255,0.1);
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            padding: 16px;
            max-width: 960px;
            margin: 0 auto;
        }}
        h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
        h2 {{ font-size: 1.1rem; margin-bottom: 12px; color: var(--text-dim); }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 0;
            border-bottom: 1px solid var(--border);
            margin-bottom: 16px;
        }}
        .header-left h1 {{ display: inline; }}
        .header-right {{ display: flex; align-items: center; gap: 8px; }}
        .status-badge {{
            padding: 6px 14px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.85rem;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        .status-badge.alive {{ background: var(--green-bg); color: var(--green); border: 1px solid var(--green); }}
        .status-badge.killed {{ background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }}
        .pulse {{
            width: 8px; height: 8px;
            border-radius: 50%;
            background: var(--green);
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.3; }}
        }}
        .tag {{
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .tag.green {{ background: var(--green-bg); color: var(--green); }}
        .tag.red {{ background: var(--red-bg); color: var(--red); }}
        .tag.yellow {{ background: var(--yellow-bg); color: var(--yellow); }}
        .tag.blue {{ background: var(--blue-bg); color: var(--blue); }}
        .tag.neutral {{ background: rgba(139,148,158,0.1); color: var(--text-dim); }}
        .grid {{ display: grid; gap: 16px; margin-bottom: 16px; }}
        .grid-2 {{ grid-template-columns: 1fr 1fr; }}
        .grid-3 {{ grid-template-columns: 1fr 1fr 1fr; }}
        @media (max-width: 640px) {{
            .grid-2, .grid-3 {{ grid-template-columns: 1fr; }}
        }}
        .card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
        }}
        .card-title {{
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-dim);
            margin-bottom: 12px;
        }}
        .metric {{ margin-bottom: 10px; }}
        .metric-label {{ font-size: 0.8rem; color: var(--text-dim); }}
        .metric-value {{ font-size: 1.4rem; font-weight: 700; }}
        .metric-value.green {{ color: var(--green); }}
        .metric-value.red {{ color: var(--red); }}
        .metric-value.blue {{ color: var(--blue); }}
        .metric-value.yellow {{ color: var(--yellow); }}
        .metric-value.purple {{ color: var(--purple); }}
        .metric-value.dim {{ color: var(--text-dim); }}
        .metric-sub {{ font-size: 0.8rem; color: var(--text-dim); }}
        .ind-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
        .ind-item {{
            display: flex;
            justify-content: space-between;
            padding: 6px 10px;
            border-radius: 6px;
            background: rgba(255,255,255,0.02);
        }}
        .ind-item .label {{ font-size: 0.8rem; color: var(--text-dim); }}
        .ind-item .val {{ font-weight: 600; font-size: 0.85rem; }}
        .ind-item .val.green {{ color: var(--green); }}
        .ind-item .val.red {{ color: var(--red); }}
        .ind-item .val.blue {{ color: var(--blue); }}
        .ind-item .val.yellow {{ color: var(--yellow); }}
        .score-bar {{
            height: 24px;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            overflow: hidden;
            position: relative;
            margin-top: 8px;
        }}
        .score-fill {{
            height: 100%;
            border-radius: 12px;
            transition: width 0.3s;
            display: flex;
            align-items: center;
            padding-left: 10px;
            font-size: 0.75rem;
            font-weight: 700;
            color: white;
        }}
        .score-fill.green {{ background: var(--green); }}
        .score-fill.yellow {{ background: var(--yellow); }}
        .score-fill.red {{ background: var(--red); }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        th {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); color: var(--text-dim); font-size: 0.75rem; text-transform: uppercase; }}
        td {{ padding: 6px 10px; border-bottom: 1px solid rgba(48,54,61,0.5); }}
        tr.buy td:nth-child(2) {{ color: var(--green); font-weight: 600; }}
        tr.sell td:nth-child(2) {{ color: var(--red); font-weight: 600; }}
        td.empty {{ text-align: center; color: var(--text-dim); padding: 20px; }}
        .chart-container {{ width: 100%; height: 280px; }}
        .kill-detail {{ font-size: 0.8rem; color: var(--text-dim); margin-top: 6px; }}
        .footer {{
            text-align: center;
            color: var(--text-dim);
            font-size: 0.75rem;
            padding: 16px 0;
            border-top: 1px solid var(--border);
            margin-top: 16px;
        }}
        .mvrv-zone {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .mvrv-zone.green {{ background: var(--green-bg); color: var(--green); }}
        .mvrv-zone.blue {{ background: var(--blue-bg); color: var(--blue); }}
        .mvrv-zone.yellow {{ background: var(--yellow-bg); color: var(--yellow); }}
        .mvrv-zone.red {{ background: var(--red-bg); color: var(--red); }}
        .mvrv-zone.neutral {{ background: rgba(139,148,158,0.1); color: var(--text-dim); }}

        /* Control Panel */
        .ctrl-panel {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
        .ctrl-btn {{ padding: 7px 16px; border-radius: 8px; border: 1px solid var(--border); background: var(--card); color: var(--text); font-size: 0.8rem; font-weight: 600; cursor: pointer; transition: all 0.15s; display: inline-flex; align-items: center; gap: 6px; }}
        .ctrl-btn:hover:not(:disabled) {{ border-color: var(--blue); background: var(--blue-bg); }}
        .ctrl-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .ctrl-btn.kill {{ border-color: var(--red); color: var(--red); }}
        .ctrl-btn.kill:hover:not(:disabled) {{ background: var(--red-bg); }}
        .ctrl-btn.resume {{ border-color: var(--green); color: var(--green); }}
        .ctrl-btn.resume:hover:not(:disabled) {{ background: var(--green-bg); }}
        .ctrl-btn .spinner {{ width: 12px; height: 12px; border: 2px solid transparent; border-top-color: currentColor; border-radius: 50%; animation: spin 0.6s linear infinite; display: none; }}
        .ctrl-btn.loading .spinner {{ display: inline-block; }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .ctrl-settings {{ margin-left: auto; display: flex; align-items: center; gap: 6px; }}
        .ctrl-settings input {{ padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font-size: 0.75rem; width: 200px; }}
        .ctrl-settings input::placeholder {{ color: var(--text-dim); }}
        .ctrl-settings .save-btn {{ padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border); background: var(--card); color: var(--text-dim); font-size: 0.75rem; cursor: pointer; }}
        .ctrl-settings .save-btn:hover {{ border-color: var(--blue); }}
        .toast-container {{ position: fixed; top: 16px; right: 16px; z-index: 9999; }}
        .toast {{ padding: 10px 16px; border-radius: 8px; margin-bottom: 8px; font-size: 0.8rem; font-weight: 500; animation: slideIn 0.3s ease; max-width: 320px; }}
        .toast.success {{ background: var(--green-bg); color: var(--green); border: 1px solid var(--green); }}
        .toast.error {{ background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }}
        .toast.info {{ background: var(--blue-bg); color: var(--blue); border: 1px solid var(--blue); }}
        @keyframes slideIn {{ from {{ transform: translateX(100%); opacity: 0; }} to {{ transform: translateX(0); opacity: 1; }} }}
        .confirm-overlay {{ position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: none; align-items: center; justify-content: center; z-index: 9998; }}
        .confirm-overlay.active {{ display: flex; }}
        .confirm-box {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; max-width: 400px; width: 90%; }}
        .confirm-box h3 {{ margin-bottom: 8px; }}
        .confirm-box p {{ color: var(--text-dim); font-size: 0.85rem; margin-bottom: 16px; }}
        .confirm-box input {{ width: 100%; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font-size: 0.85rem; margin-bottom: 12px; }}
        .confirm-actions {{ display: flex; gap: 8px; justify-content: flex-end; }}
    </style>
</head>
<body>
    <div class="toast-container" id="toasts"></div>
    <div class="confirm-overlay" id="confirmOverlay">
        <div class="confirm-box">
            <h3 id="confirmTitle">Confirm</h3>
            <p id="confirmMsg"></p>
            <input type="text" id="confirmInput" placeholder="Reason (optional)">
            <div class="confirm-actions">
                <button class="ctrl-btn" onclick="closeConfirm()">Cancel</button>
                <button class="ctrl-btn kill" id="confirmOk">Confirm</button>
            </div>
        </div>
    </div>
    <!-- Header -->
    <div class="header">
        <div class="header-left">
            <h1>Phoenix v5.1</h1>
            {dry_html}
        </div>
        <div class="header-right">
            {status_html}
        </div>
    </div>

    <!-- Control Panel -->
    <div class="card" style="margin-bottom:16px;">
        <div class="ctrl-panel">
            <button class="ctrl-btn" id="btnUpdate" onclick="doUpdate()">
                <span class="spinner"></span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
                Update
            </button>
            <button class="ctrl-btn {'kill' if bot_alive else 'resume'}" id="btnKill" onclick="doKillSwitch()">
                <span class="spinner"></span>
                {'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg> Kill Bot' if bot_alive else '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> Resume Bot'}
            </button>
            <a href="https://github.com/manhiiautomation-gif/Smart-dca/actions/workflows/dashboard-trigger.yml" target="_blank" class="ctrl-btn" style="text-decoration:none;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                Logs
            </a>
            <div class="ctrl-settings">
                <input type="password" id="tokenInput" placeholder="GitHub PAT (saved in browser)" />
                <button class="save-btn" onclick="saveToken()">Save</button>
            </div>
        </div>
    </div>

    <!-- Row 1: Portfolio + Kill Switch -->
    <div class="grid grid-2">
        <!-- Portfolio Summary -->
        <div class="card">
            <div class="card-title">Portfolio Summary</div>
            <div class="metric">
                <div class="metric-label">Portfolio Value</div>
                <div class="metric-value {roi_class}">{fmt_num(portfolio)} {currency}</div>
            </div>
            <div class="metric">
                <div class="metric-label">BTC Holdings</div>
                <div class="metric-value blue">{btc_bal:.8f} BTC</div>
                <div class="metric-sub">{fmt_num(btc_bal * current_price)} {currency}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Cash Balance</div>
                <div class="metric-value">{fmt_num(cash_bal)} {currency}</div>
            </div>
            <div class="grid grid-2" style="margin-top:12px; gap:8px;">
                <div class="metric">
                    <div class="metric-label">ROI</div>
                    <div class="metric-value {roi_class}">{roi:+.1f}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Total Invested</div>
                    <div class="metric-value dim">{fmt_num(invested)} {currency}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Peak Value</div>
                    <div class="metric-value dim">{fmt_num(peak)}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Max Drawdown</div>
                    <div class="metric-value red">{fmt_pct(max_dd)}</div>
                </div>
            </div>
        </div>

        <!-- System Status + Kill Switch -->
        <div class="card">
            <div class="card-title">System Status</div>
            <div class="ind-grid">
                <div class="ind-item">
                    <span class="label">L1 Kill (env)</span>
                    <span class="val">{l1_html}</span>
                </div>
                <div class="ind-item">
                    <span class="label">L2 Kill (file)</span>
                    <span class="val">{l2_html}</span>
                </div>
                <div class="ind-item">
                    <span class="label">Exchange</span>
                    <span class="val">{currency.upper()}</span>
                </div>
                <div class="ind-item">
                    <span class="label">Last Run</span>
                    <span class="val">{last_run}</span>
                </div>
                <div class="ind-item">
                    <span class="label">Run Count</span>
                    <span class="val">{run_count}</span>
                </div>
                <div class="ind-item">
                    <span class="label">BTC Price</span>
                    <span class="val">{fmt_num(current_price)} {currency}</span>
                </div>
            </div>
            {('<div class="kill-detail" style="margin-top:12px; color:var(--red);">'
              + f'Reason: {ks_reason}<br>'
              + f'At: {ks_time}<br>'
              + f'By: {ks_by}'
              + '</div>') if not bot_alive else ''}
        </div>
    </div>

    <!-- Row 2: Indicators -->
    <div class="grid grid-2">
        <div class="card">
            <div class="card-title">Indicators</div>
            {bear_html}
            <div class="ind-grid" style="margin-top:8px;">
                <div class="ind-item">
                    <span class="label">MVRV</span>
                    <span class="val {mvrv_color(mvrv)}">{fmt_num(mvrv, 3)}</span>
                </div>
                <div class="ind-item">
                    <span class="label">MVRV Zone</span>
                    <span class="mvrv-zone {mvrv_zone_class}">{mvrv_zone}</span>
                </div>
                <div class="ind-item">
                    <span class="label">MVRV %ile</span>
                    <span class="val">{fmt_pct(mvrv_pct)}</span>
                </div>
                <div class="ind-item">
                    <span class="label">MVRV Z</span>
                    <span class="val">{fmt_num(mvrv_z, 2)}</span>
                </div>
                <div class="ind-item">
                    <span class="label">RSI (14)</span>
                    <span class="val {rsi_color(rsi_val)}">{fmt_num(rsi_val, 1)}</span>
                </div>
                <div class="ind-item">
                    <span class="label">MACD Hist</span>
                    <span class="val">{fmt_num(macd_h, 4)}</span>
                </div>
                <div class="ind-item">
                    <span class="label">NUPL</span>
                    <span class="val">{fmt_num(nupl, 3)}</span>
                </div>
                <div class="ind-item">
                    <span class="label">SOPR</span>
                    <span class="val">{fmt_num(sopr, 3)}</span>
                </div>
                <div class="ind-item">
                    <span class="label">SMA 200</span>
                    <span class="val">{fmt_num(sma200)}</span>
                </div>
                <div class="ind-item">
                    <span class="label">SMA 365</span>
                    <span class="val">{fmt_num(sma365)}</span>
                </div>
            </div>
        </div>

        <!-- Sell Logic -->
        <div class="card">
            <div class="card-title">Sell Logic</div>
            <div class="metric">
                <div class="metric-label">Sell Score <span class="tag {path_class}">Path: {path_taken}</span></div>
                <div class="score-bar">
                    <div class="score-fill {ss_color}" style="width:{ss_width}%">
                        {ss} / 100
                    </div>
                </div>
            </div>
            <div class="ind-grid" style="margin-top:12px;">
                <div class="ind-item">
                    <span class="label">Cooldown</span>
                    <span class="val">{cooldown} days</span>
                </div>
                <div class="ind-item">
                    <span class="label">ATH</span>
                    <span class="val">{fmt_num(ath)}</span>
                </div>
            </div>
            <div style="margin-top:16px;">
                <div class="card-title">Trade Statistics</div>
                <div class="ind-grid">
                    <div class="ind-item">
                        <span class="label">Total Buys</span>
                        <span class="val green">{buy_count}</span>
                    </div>
                    <div class="ind-item">
                        <span class="label">Total Sells</span>
                        <span class="val red">{sell_count}</span>
                    </div>
                    <div class="ind-item">
                        <span class="label">BTC Bought</span>
                        <span class="val">{total_btc_bought:.8f}</span>
                    </div>
                    <div class="ind-item">
                        <span class="label">BTC Sold</span>
                        <span class="val">{total_btc_sold:.8f}</span>
                    </div>
                    <div class="ind-item">
                        <span class="label">Sell Proceeds</span>
                        <span class="val">{fmt_num(total_sell_proceeds)}</span>
                    </div>
                    <div class="ind-item">
                        <span class="label">Reserve Used</span>
                        <span class="val">{fmt_num(total_reserve)}</span>
                    </div>
                    <div class="ind-item">
                        <span class="label">Total Fees</span>
                        <span class="val yellow">{fmt_num(total_fees)}</span>
                    </div>
                    <div class="ind-item">
                        <span class="label">Last Trade</span>
                        <span class="val">{last_trade_date}</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Row 3: Portfolio Chart -->
    <div class="card" style="margin-bottom:16px;">
        <div class="card-title">Portfolio Value Over Time</div>
        <div class="chart-container" id="chart"></div>
    </div>

    <!-- Row 4: Recent Trades -->
    <div class="card">
        <div class="card-title">Recent Trades (last 10)</div>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Amount ({currency})</th>
                    <th>BTC</th>
                    <th>Price</th>
                    <th>Fee</th>
                </tr>
            </thead>
            <tbody>
                {trade_rows}
            </tbody>
        </table>
    </div>

    <!-- Footer -->
    <div class="footer">
        Phoenix v5.1 DCA Bot | Generated: {now_str} | Updated daily
    </div>

    <script>
    (function() {{
        var REPO = 'manhiiautomation-gif/Smart-dca';
        var WORKFLOW = 'dashboard-trigger.yml';
        var API = 'https://api.github.com/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches';
        function getToken() {{ return localStorage.getItem('gh_pat') || ''; }}
        function setToken(t) {{ localStorage.setItem('gh_pat', t); }}
        var savedToken = getToken();
        if (savedToken) document.getElementById('tokenInput').value = '\u2022\u2022\u2022\u2022' + savedToken.slice(-4);
        window.saveToken = function() {{
            var input = document.getElementById('tokenInput');
            var val = input.value;
            if (val && !val.startsWith('\u2022')) {{
                setToken(val.trim());
                input.value = '\u2022\u2022\u2022\u2022' + val.trim().slice(-4);
                showToast('Token saved', 'success');
            }}
        }};
        function showToast(msg, type) {{
            var c = document.getElementById('toasts');
            var t = document.createElement('div');
            t.className = 'toast ' + (type || 'info');
            t.textContent = msg;
            c.appendChild(t);
            setTimeout(function() {{ t.remove(); }}, 4000);
        }}
        function setLoading(btn, on) {{
            if (on) btn.classList.add('loading'); else btn.classList.remove('loading');
            btn.disabled = on;
        }}
        function dispatch(action, reason) {{
            var token = getToken();
            if (!token) {{ showToast('Please enter GitHub PAT first', 'error'); return false; }}
            var body = {{ ref: 'main', inputs: {{ action: action }} }};
            if (reason) body.inputs.reason = reason;
            fetch(API, {{
                method: 'POST',
                headers: {{ 'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github.v3+json', 'Content-Type': 'application/json' }},
                body: JSON.stringify(body)
            }}).then(function(r) {{
                if (r.status === 204) return true;
                return r.json().then(function(e) {{ throw new Error(e.message || 'HTTP ' + r.status); }});
            }}).then(function() {{
                var labels = {{ update: 'Bot update + dashboard refresh started', kill: 'Kill switch activated', resume: 'Bot resumed' }};
                showToast(labels[action] || 'Action dispatched', 'success');
            }}).catch(function(e) {{ showToast('Error: ' + e.message, 'error'); }});
            return false;
        }}
        window.doUpdate = function() {{
            var btn = document.getElementById('btnUpdate');
            setLoading(btn, true);
            dispatch('update', '');
            setTimeout(function() {{ setLoading(btn, false); }}, 5000);
        }};
        var confirmCallback = null;
        window.doKillSwitch = function() {{
            var isAlive = {str(bot_alive).lower()};
            var overlay = document.getElementById('confirmOverlay');
            var input = document.getElementById('confirmInput');
            var okBtn = document.getElementById('confirmOk');
            var title = document.getElementById('confirmTitle');
            var msg = document.getElementById('confirmMsg');
            if (isAlive) {{
                title.textContent = 'Kill Bot?';
                msg.textContent = 'Bot \u0e08\u0e30\u0e2b\u0e22\u0e38\u0e14\u0e0b\u0e37\u0e49\u0e2d\u0e02\u0e32\u0e22\u0e17\u0e31\u0e19\u0e17\u0e35';
                input.value = '';
                input.placeholder = 'Reason (optional)';
                input.style.display = 'block';
                okBtn.textContent = 'Kill';
                okBtn.className = 'ctrl-btn kill';
                confirmCallback = function() {{
                    var btn = document.getElementById('btnKill');
                    setLoading(btn, true);
                    dispatch('kill', input.value || 'Manual kill from dashboard');
                    setTimeout(function() {{ setLoading(btn, false); }}, 5000);
                }};
            }} else {{
                title.textContent = 'Resume Bot?';
                msg.textContent = 'Bot \u0e08\u0e30\u0e01\u0e25\u0e31\u0e1a\u0e21\u0e32\u0e17\u0e33\u0e07\u0e32\u0e19\u0e1b\u0e01\u0e15\u0e34';
                input.style.display = 'none';
                okBtn.textContent = 'Resume';
                okBtn.className = 'ctrl-btn resume';
                confirmCallback = function() {{
                    var btn = document.getElementById('btnKill');
                    setLoading(btn, true);
                    dispatch('resume', '');
                    setTimeout(function() {{ setLoading(btn, false); }}, 5000);
                }};
            }}
            overlay.classList.add('active');
        }};
        window.closeConfirm = function() {{
            document.getElementById('confirmOverlay').classList.remove('active');
            confirmCallback = null;
        }};
        document.getElementById('confirmOk').addEventListener('click', function() {{
            if (confirmCallback) confirmCallback();
            closeConfirm();
        }});
        document.getElementById('confirmOverlay').addEventListener('click', function(e) {{
            if (e.target === this) closeConfirm();
        }});
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') closeConfirm();
        }});
    }})();
    </script>

    <!-- ECharts -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
    <script>
        (function() {{
            var dates = {chart_dates};
            var values = {chart_values};
            var types = {chart_types};

            if (dates.length === 0) {{
                document.getElementById('chart').innerHTML =
                    '<div style="text-align:center;color:var(--text-dim);padding:40px;">ยังไม่มีข้อมูลเพียงพอสำหรับกราฟ</div>';
                return;
            }}

            var buyDates = [], sellDates = [];
            var buyPoints = [], sellPoints = [];
            for (var i = 0; i < types.length; i++) {{
                if (types[i] === 'buy') {{ buyDates.push(dates[i]); buyPoints.push(values[i]); }}
                if (types[i] === 'sell') {{ sellDates.push(dates[i]); sellPoints.push(values[i]); }}
            }}

            var option = {{
                backgroundColor: 'transparent',
                tooltip: {{
                    trigger: 'axis',
                    backgroundColor: '#1c2128',
                    borderColor: '#30363d',
                    textStyle: {{ color: '#e6edf3', fontSize: 12 }}
                }},
                grid: {{ left: 60, right: 20, top: 20, bottom: 40 }},
                xAxis: {{
                    type: 'category',
                    data: dates,
                    axisLabel: {{ color: '#8b949e', fontSize: 10, rotate: 30 }},
                    axisLine: {{ lineStyle: {{ color: '#30363d' }} }}
                }},
                yAxis: {{
                    type: 'value',
                    axisLabel: {{ color: '#8b949e', fontSize: 10, formatter: function(v) {{ return v.toLocaleString(); }} }},
                    splitLine: {{ lineStyle: {{ color: '#21262d' }} }}
                }},
                series: [
                    {{
                        name: 'Portfolio',
                        type: 'line',
                        data: values,
                        smooth: true,
                        lineStyle: {{ color: '#58a6ff', width: 2 }},
                        areaStyle: {{
                            color: {{
                                type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                                colorStops: [
                                    {{ offset: 0, color: 'rgba(88,166,255,0.2)' }},
                                    {{ offset: 1, color: 'rgba(88,166,255,0.01)' }}
                                ]
                            }}
                        }},
                        itemStyle: {{ color: '#58a6ff' }}
                    }},
                    {{
                        name: 'Buy',
                        type: 'scatter',
                        data: buyPoints.length ? buyPoints.map(function(v, i) {{ return [buyDates[i], v]; }}) : [],
                        symbol: 'triangle',
                        symbolSize: 12,
                        itemStyle: {{ color: '#3fb950' }},
                        tooltip: {{ formatter: function(p) {{ return 'BUY<br>Value: ' + p.value[1].toLocaleString(); }} }}
                    }},
                    {{
                        name: 'Sell',
                        type: 'scatter',
                        data: sellPoints.length ? sellPoints.map(function(v, i) {{ return [sellDates[i], v]; }}) : [],
                        symbol: 'triangle',
                        symbolRotate: 180,
                        symbolSize: 12,
                        itemStyle: {{ color: '#f85149' }},
                        tooltip: {{ formatter: function(p) {{ return 'SELL<br>Value: ' + p.value[1].toLocaleString(); }} }}
                    }}
                ]
            }};

            var chart = echarts.init(document.getElementById('chart'));
            chart.setOption(option);
            window.addEventListener('resize', function() {{ chart.resize(); }});
        }})();
    </script>
</body>
</html>'''


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate Phoenix v5.1 Dashboard')
    parser.add_argument('--state', default='live_bot/state.json')
    parser.add_argument('--trade-log', default='trade_log.json')
    parser.add_argument('--kill-switch', default='kill_switch.json')
    parser.add_argument('--output', default='dashboard/dist/index.html')
    args = parser.parse_args()
    generate_dashboard(
        state_path=args.state,
        trade_log_path=args.trade_log,
        kill_switch_path=args.kill_switch,
        output_path=args.output,
    )
