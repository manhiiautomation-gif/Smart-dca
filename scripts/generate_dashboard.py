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
from live_bot import config as cfg


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


def fmt_btc(n, decimals=8):
    """Format BTC with smart decimal places (U6)."""
    if n is None or n == 0:
        return '0 BTC'
    if abs(n) >= 1:
        return f'{n:.4f} BTC'
    if abs(n) >= 0.001:
        return f'{n:.6f} BTC'
    return f'{n:.8f} BTC'


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
    exchange_name = state.get('last_exchange_name', '')
    # Derive currency from exchange name (more reliable than stale state)
    _EXCHANGE_CURRENCY = {'BITKUB': 'THB', 'BINANCE': 'USDT'}
    currency = _EXCHANGE_CURRENCY.get(exchange_name, state.get('last_exchange_currency', 'USDT'))

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

    # --- Investment control metrics ---
    net_btc = total_btc_bought - total_btc_sold
    avg_buy_price = (invested / net_btc) if net_btc > 0 else 0
    unrealized_pnl = (current_price - avg_buy_price) * btc_bal if avg_buy_price > 0 else 0
    unrealized_pnl_pct = (unrealized_pnl / invested * 100) if invested > 0 else 0
    avg_buy_size = (invested / buy_count) if buy_count > 0 else 0

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

    # 24h / since-last-trade change
    change_pct = None
    change_abs = None
    change_label = '24h Change'
    if len(portfolio_series) >= 2:
        prev_val = portfolio_series[-2]['value']
        if prev_val > 0:
            change_abs = portfolio - prev_val
            change_pct = (change_abs / prev_val) * 100
            from datetime import datetime as dt
            try:
                last_dt = dt.strptime(portfolio_series[-2]['date'], '%Y-%m-%d %H:%M')
                now_dt = dt.now()
                diff_days = (now_dt - last_dt).total_seconds() / 86400
                if diff_days > 2:
                    change_label = 'Since Last Trade'
            except Exception:
                pass

    # Kill switch status
    # H3: L1 (BOT_ENABLED env var) IS available at dashboard gen time
    # because generate_dashboard.py runs inside the same GitHub Actions job.
    l1_ok = os.environ.get('BOT_ENABLED', 'true').lower() == 'true'
    bot_alive = l1_ok and ks_status['l2_enabled']
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
    sopr_source = indicators.get('sopr_source', 'proxy')
    sma200 = indicators.get('sma_200')
    sma365 = indicators.get('sma_365')
    sell_score = indicators.get('sell_score', 0)
    path_taken = indicators.get('path_taken', 'none')
    in_bear = indicators.get('in_bear', False)
    cooldown = indicators.get('cooldown', 0)
    ath = indicators.get('ath', 0)

    # U2: Empty state detection
    is_empty = (buy_count == 0 and sell_count == 0 and invested == 0)

    # U11: Next expected run time (cron: '10 17 * * *' UTC = 00:10 THB)
    from datetime import timezone, timedelta
    tz_thai = timezone(timedelta(hours=7))
    now_thai = datetime.now(tz_thai)
    # Next 00:10 THB
    next_run_date = now_thai.replace(hour=0, minute=10, second=0, microsecond=0)
    if now_thai.hour >= 0 and now_thai.minute >= 10 and now_thai.hour < 24:
        next_run_date += timedelta(days=1)
    next_run_str = next_run_date.strftime('%H:%M')
    next_run_day = next_run_date.strftime('%d %b')

    # U5: Max drawdown conditional color
    if max_dd == 0:
        max_dd_class = 'dim'
    elif max_dd < 0.05:
        max_dd_class = 'yellow'
    else:
        max_dd_class = 'red'

    # Next expected action
    next_action = ''
    next_action_class = 'neutral'
    if cooldown > 0:
        next_action = f'COOLDOWN — ขายแล้ว รอ {cooldown} วัน'
        next_action_class = 'yellow'
    elif sell_score >= 50:
        next_action = f'SELL WATCHING — score {sell_score}/100 (need 50+ to trigger)'
        next_action_class = 'red'
    elif mvrv is not None and mvrv < 1.0:
        next_action = 'BUY EXPECTED — MVRV accumulation zone'
        next_action_class = 'green'
    elif rsi_val is not None and rsi_val < 35:
        next_action = 'BUY LIKELY — RSI oversold zone'
        next_action_class = 'green'
    elif in_bear and mvrv is not None and mvrv < 1.5:
        next_action = 'BUY EXPECTED — Bear + low MVRV = good accumulation'
        next_action_class = 'green'
    elif sell_score >= 30:
        next_action = f'HOLD — sell score rising ({sell_score}/100), watching'
        next_action_class = 'yellow'
    else:
        next_action = 'HOLD — ไม่มีสัญญาณชัดเจน รอรอบถัดไป'
        next_action_class = 'blue'

    # Build HTML
    # Load demo portfolio data if exists
    demo_html = ''
    demo_state_path = os.path.join(PROJECT_ROOT, 'demo_state.json')
    demo_report_path = os.path.join(PROJECT_ROOT, 'demo_report.json')
    if os.path.exists(demo_state_path):
        try:
            with open(demo_state_path, 'r') as f:
                ds = json.load(f)
            ds_runs = ds.get('run_count', 0)
            ds_btc = ds.get('btc', 0)
            ds_cash = ds.get('cash', 0)
            ds_price = ds.get('last_price', 0)
            ds_portfolio = ds_btc * ds_price + ds_cash
            ds_initial = ds.get('initial_cash', 10000)
            ds_roi = ((ds_portfolio - ds_initial) / ds_initial * 100) if ds_initial > 0 else 0
            ds_peak = ds.get('peak_value', 0)
            ds_max_dd = ds.get('max_drawdown', 0)
            ds_fees = ds.get('cumulative_fees', 0)
            ds_slip = ds.get('cumulative_slippage', 0)
            ds_buys = ds.get('buy_count', 0)
            ds_sells = ds.get('sell_count', 0)
            ds_val = ds.get('validation', {})
            ds_created = ds.get('created_at', '')

            # Load report if exists
            ds_ready = False
            ds_recommendation = ''
            checklist_html = ''
            if os.path.exists(demo_report_path):
                try:
                    with open(demo_report_path, 'r') as f:
                        dr = json.load(f)
                    ds_ready = dr.get('go_live_ready', False)
                    ds_recommendation = dr.get('recommendation', '')
                    checks = dr.get('go_live_checklist', [])
                    for c in checks:
                        icon = '<span style="color:var(--green)">&#10003;</span>' if c['passed'] else '<span style="color:var(--red)">&#10007;</span>'
                        checklist_html += f'<div style="display:flex;gap:8px;align-items:center;margin:4px 0;font-size:12px;"><span>{icon}</span><span>{c["name"]}</span><span style="color:var(--text-dim)">{c["detail"]}</span></div>'
                except Exception:
                    pass

            ready_class = 'green' if ds_ready else ('yellow' if ds_runs >= 7 else 'red')
            ready_text = 'READY' if ds_ready else ('IN PROGRESS' if ds_runs >= 7 else 'TOO EARLY')
            roi_class_d = 'green' if ds_roi > 0 else ('red' if ds_roi < 0 else 'neutral')

            demo_html = f'''
    <!-- Demo Portfolio -->
    <div class="card" style="margin-bottom:16px;border-left:3px solid var(--blue);">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
            Demo Portfolio Simulation
            <span class="tag {ready_class}">{ready_text}</span>
        </div>
        <div class="ind-grid">
            <div class="ind-item">
                <span class="label">Runs</span>
                <span class="val">{ds_runs} / 14</span>
            </div>
            <div class="ind-item">
                <span class="label">Portfolio</span>
                <span class="val">{fmt_num(ds_portfolio)}</span>
            </div>
            <div class="ind-item">
                <span class="label">ROI</span>
                <span class="val {roi_class_d}">{ds_roi:+.2f}%</span>
            </div>
            <div class="ind-item">
                <span class="label">BTC</span>
                <span class="val">{ds_btc:.8f}</span>
            </div>
            <div class="ind-item">
                <span class="label">Cash</span>
                <span class="val">{fmt_num(ds_cash)}</span>
            </div>
            <div class="ind-item">
                <span class="label">Buys / Sells</span>
                <span class="val"><span class="green">{ds_buys}</span> / <span class="red">{ds_sells}</span></span>
            </div>
            <div class="ind-item">
                <span class="label">Peak</span>
                <span class="val">{fmt_num(ds_peak)}</span>
            </div>
            <div class="ind-item">
                <span class="label">Max DD</span>
                <span class="val">{ds_max_dd*100:.2f}%</span>
            </div>
            <div class="ind-item">
                <span class="label">Fees</span>
                <span class="val yellow">{fmt_num(ds_fees)}</span>
            </div>
            <div class="ind-item">
                <span class="label">Slippage</span>
                <span class="val">{fmt_num(ds_slip, 4)}</span>
            </div>
        </div>
        {'<div style="margin-top:12px;"><div class="card-title" style="font-size:12px;">Go-Live Checklist</div>' + checklist_html + '</div>' if checklist_html else ''}
        {f'<div style="margin-top:8px;font-size:11px;color:var(--text-dim);">{ds_recommendation}</div>' if ds_recommendation else ''}
    </div>'''
        except Exception as e:
            print(f'[DASHBOARD] Demo section error: {e}')
            demo_html = ''

    # ── Config settings for dashboard display ──
    # Show effective values (after THB→local conversion)
    cfg_items = [
        ('Exchange', cfg.EXCHANGE.upper()),
        ('Currency', cfg.CURRENCY),
        ('USD/THB Rate', f'{cfg.USD_THB_RATE:.3f}'),
        ('Daily DCA Budget', f'{cfg.DAILY_BUDGET_THB:,.0f} THB = {cfg.get_daily_budget():.2f} {cfg.CURRENCY}'),
        ('Max Buy/Trade', f'{cfg.MAX_BUY_THB:,.0f} THB = {cfg.get_max_buy():.2f} {cfg.CURRENCY}'),
        ('Max DCA Buys/Day', str(cfg.MAX_DCA_BUYS_PER_DAY)),
        ('Reserve Floor', f'{cfg.get_reserve_floor():.2f} {cfg.CURRENCY}'),
        ('Max Reserve Inject', f'{cfg.get_max_reserve_injection():.2f} {cfg.CURRENCY}'),
        ('Max Boosted Inject', f'{cfg.get_max_reserve_boosted():.2f} {cfg.CURRENCY}'),
        ('Boost Multiplier', f'{cfg.RESERVE_BOOST_MULTIPLIER}x'),
        ('Boost Price Ratio', f'{cfg.RESERVE_BOOST_PRICE_RATIO}x realized'),
        ('Low Balance Alert', f'< {cfg.LOW_BALANCE_DAYS} days remaining'),
        ('Buy Fee', f'{cfg.BUY_FEE_PCT*100:.2f}%'),
        ('Sell Fee', f'{cfg.SELL_FEE_PCT*100:.2f}%'),
    ]
    cfg_grid_rows = ''
    for label, val in cfg_items:
        cfg_grid_rows += f'<div class="ind-item"><span class="label">{label}</span><span class="val">{val}</span></div>\n'

    config_html = f'''
    <!-- U10: Config Section (collapsible) -->
    <div class="card" style="margin-bottom:16px;border-left:3px solid var(--purple);">
        <div class="collapsible-header" onclick="this.classList.toggle('open');this.nextElementSibling.classList.toggle('open');">
            <div class="card-title" style="margin-bottom:0;">Configuration (Active)</div>
            <div style="display:flex;align-items:center;gap:8px;">
                <button class="ctrl-btn" onclick="event.stopPropagation();toggleHelp()" style="padding:4px 12px;font-size:0.7rem;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    วิธีตั้งค่า
                </button>
                <span class="chevron">&#9660;</span>
            </div>
        </div>
        <div class="collapsible-body">
            <div class="ind-grid" style="margin-top:12px;">
                {cfg_grid_rows}
            </div>
        </div>
    </div>

    <!-- Help Modal -->
    <div class="confirm-overlay" id="helpOverlay" style="z-index:10000;">
        <div class="confirm-box" style="max-width:520px;">
            <h3 style="margin-bottom:12px;">วิธีตั้งค่า Config</h3>
            <div style="font-size:0.82rem;color:var(--text-dim);line-height:1.7;">
                <p style="margin-bottom:10px;">ตั้งค่าผ่าน <b style="color:var(--text);">GitHub Secrets</b> ใน repo Settings → Secrets and variables → Actions</p>
                <table style="width:100%;font-size:0.78rem;margin-bottom:12px;">
                    <tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px 0;">Secret Name</th><th style="text-align:left;padding:4px 0;">ค่าเริ่มต้น</th><th style="text-align:left;padding:4px 0;">อธิบาย</th></tr>
                    <tr><td style="padding:4px 0;font-family:monospace;">DAILY_BUDGET_THB</td><td>100</td><td>งบ DCA ต่อรอบ (THB)</td></tr>
                    <tr><td style="padding:4px 0;font-family:monospace;">MAX_BUY_THB</td><td>1000</td><td>ซื้อสูงสุด/trade (THB)</td></tr>
                    <tr><td style="padding:4px 0;font-family:monospace;">MAX_DCA_BUYS_PER_DAY</td><td>1</td><td>ซื้อ DCA สูงสุด/วัน</td></tr>
                    <tr><td style="padding:4px 0;font-family:monospace;">RESERVE_FLOOR</td><td>auto</td><td>จำนวนเงิน reserve ขั้นต่ำ (สกุลเงินเดียวกับ exchange)</td></tr>
                    <tr><td style="padding:4px 0;font-family:monospace;">MAX_RESERVE_INJECTION</td><td>auto</td><td>ฉีด reserve สูงสุด/ครั้ง</td></tr>
                    <tr><td style="padding:4px 0;font-family:monospace;">RESERVE_BOOST_MULTIPLIER</td><td>1.8</td><td>boost x เมื่อราคา < realized</td></tr>
                    <tr><td style="padding:4px 0;font-family:monospace;">RESERVE_BOOST_PRICE_RATIO</td><td>1.05</td><td>เงื่อนไข boost: price < realized x นี้</td></tr>
                    <tr><td style="padding:4px 0;font-family:monospace;">LOW_BALANCE_DAYS</td><td>7</td><td>แจ้งเตือนเมื่อเงินเหลือไม่พอ N รอบ</td></tr>
                    <tr><td style="padding:4px 0;font-family:monospace;">USD_THB_RATE</td><td>33.426</td><td>อัตราแลกเปลี่ยน (สำหรับ Binance→USDT)</td></tr>
                </table>
                <p style="color:var(--yellow);"><b>หมายเหตุ:</b> ค่า DCA (DAILY_BUDGET_THB, MAX_BUY_THB) ระบุเป็น THB เสมอ ระบบจะ auto-convert เป็นสกุลเงินของ exchange ให้</p>
                <p style="margin-top:8px;">ตั้งค่าผ่าน <b style="color:var(--text);">Manual Trigger</b> ใน Actions ได้ด้วย (ช่อง budget)</p>
            </div>
            <div class="confirm-actions">
                <button class="ctrl-btn" onclick="toggleHelp()">ปิด</button>
            </div>
        </div>
    </div>
    '''

    html = build_html(
        bot_alive=bot_alive, l1_ok=l1_ok, l2_ok=l2_ok,
        ks_reason=ks_reason, ks_time=ks_time, ks_by=ks_by,
        portfolio=portfolio, invested=invested, roi=roi,
        peak=peak, max_dd=max_dd, current_price=current_price,
        btc_bal=btc_bal, cash_bal=cash_bal, currency=currency,
        exchange_name=exchange_name,
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
        sopr_source=sopr_source,
        sma200=sma200, sma365=sma365, ath=ath,
        sell_score=sell_score, path_taken=path_taken,
        in_bear=in_bear, cooldown=cooldown,
        portfolio_series=portfolio_series,
        recent_trades=recent_trades,
        last_trade_date=last_trade_date,
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        demo_html=demo_html,
        config_html=config_html,
        avg_buy_price=avg_buy_price,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        avg_buy_size=avg_buy_size,
        change_pct=change_pct,
        change_abs=change_abs,
        change_label=change_label,
        next_action=next_action,
        next_action_class=next_action_class,
        is_empty=is_empty,
        next_run_str=next_run_str,
        next_run_day=next_run_day,
        max_dd_class=max_dd_class,
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
    exchange_name = kw.get('exchange_name', '')
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
    sopr_source = kw.get('sopr_source', 'proxy')
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
    demo_html = kw.get('demo_html', '')
    config_html = kw.get('config_html', '')
    avg_buy_price = kw.get('avg_buy_price', 0)
    unrealized_pnl = kw.get('unrealized_pnl', 0)
    unrealized_pnl_pct = kw.get('unrealized_pnl_pct', 0)
    avg_buy_size = kw.get('avg_buy_size', 0)
    change_pct = kw.get('change_pct')
    change_abs = kw.get('change_abs')
    change_label = kw.get('change_label', '24h Change')
    next_action = kw.get('next_action', '')
    next_action_class = kw.get('next_action_class', 'neutral')
    is_empty = kw.get('is_empty', False)
    next_run_str = kw.get('next_run_str', '00:10')
    next_run_day = kw.get('next_run_day', '')
    max_dd_class = kw.get('max_dd_class', 'dim')
    upnl_class = 'green' if unrealized_pnl > 0 else ('red' if unrealized_pnl < 0 else 'neutral')
    chg_class = 'green' if (change_pct or 0) > 0 else ('red' if (change_pct or 0) < 0 else 'neutral')

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

    # U3: DRY RUN banner (large, prominent)
    dry_banner_html = '''
    <div class="dry-run-banner">
        <span class="banner-icon">&#9888;</span>
        <div>
            <div>โหมดทดสอบ (TEST MODE) — ไม่มีการซื้อขายจริง</div>
            <div class="banner-text">ระบบจำลองผลลัพธ์เท่านั้น เงินและ BTC ไม่เคลื่อนไหวจริง</div>
        </div>
    </div>''' if dry_run else ''

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
            <td class="num-mono">{fmt_btc(t['btc'])}</td>
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
    <meta http-equiv="refresh" content="300">  <!-- Auto refresh every 5 min -->
    <title>Phoenix v5.1 Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        :root {{
            --bg: #0d1117;
            --card: #161b22;
            --border: #30363d;
            --text: #e6edf3;
            --text-dim: #9da5ae;
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
            body {{ padding: 10px; }}
            .card {{ padding: 12px; border-radius: 10px; }}
            .grid {{ gap: 10px; margin-bottom: 10px; }}
            .header {{ padding: 10px 0; margin-bottom: 10px; }}
            h1 {{ font-size: 1.25rem; }}
            .metric-value {{ font-size: 1.2rem; }}
            .metric-value.hero {{ font-size: 1.5rem; }}
            .ind-grid {{ gap: 4px; }}
            .ind-item {{ padding: 5px 8px; }}
            .ind-item .label {{ font-size: 0.72rem; }}
            .ind-item .val {{ font-size: 0.78rem; }}
            .ctrl-panel {{ gap: 6px; }}
            .ctrl-btn {{ padding: 6px 12px; font-size: 0.75rem; }}
            table {{ font-size: 0.78rem; }}
            th, td {{ padding: 5px 6px; }}
            .chart-container {{ height: 220px; }}
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

        /* U3: DRY RUN Banner */
        .dry-run-banner {{
            background: linear-gradient(135deg, rgba(210,153,34,0.15), rgba(210,153,34,0.05));
            border: 1px solid var(--yellow);
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 0.85rem;
            color: var(--yellow);
            font-weight: 600;
        }}
        .dry-run-banner .banner-icon {{ font-size: 1.3rem; flex-shrink: 0; }}
        .dry-run-banner .banner-text {{ color: var(--text); font-weight: 400; font-size: 0.8rem; }}

        /* U8: Hero metric */
        .metric-value.hero {{ font-size: 1.8rem; }}
        .num-mono {{ font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace; }}

        /* U9: Freshness badge */
        .freshness {{ font-size: 0.72rem; color: var(--text-dim); margin-left: 8px; font-weight: 400; }}

        /* U10: Collapsible */
        .collapsible-header {{ cursor: pointer; user-select: none; display: flex; justify-content: space-between; align-items: center; }}
        .collapsible-header .chevron {{ transition: transform 0.2s; font-size: 0.7rem; }}
        .collapsible-header.open .chevron {{ transform: rotate(180deg); }}
        .collapsible-body {{ max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }}
        .collapsible-body.open {{ max-height: 800px; }}

        /* U2: Onboarding hero */
        .onboarding-hero {{
            text-align: center;
            padding: 40px 20px;
            border: 1px dashed var(--border);
            border-radius: 12px;
            margin-bottom: 16px;
        }}
        .onboarding-hero .onboard-icon {{ font-size: 2.5rem; margin-bottom: 12px; opacity: 0.7; }}
        .onboarding-hero .onboard-title {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 6px; }}
        .onboarding-hero .onboard-desc {{ font-size: 0.85rem; color: var(--text-dim); max-width: 360px; margin: 0 auto; line-height: 1.6; }}

        /* Sopr source tag */
        .tag.sopr-src {{ font-size: 0.65rem; vertical-align: middle; margin-left: 4px; opacity: 0.7; }}
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
    <!-- Token Input Modal -->
    <div class="confirm-overlay" id="tokenOverlay" style="z-index:10001;">
        <div class="confirm-box" style="max-width:520px;">
            <h3 style="margin-bottom:8px;">GitHub PAT Token</h3>
            <p style="margin-bottom:12px;font-size:0.82rem;color:var(--text-dim);line-height:1.6;">
                ปุ่ม Update / Kill / Resume ต้องใช้ GitHub Personal Access Token (PAT)<br>
                <b style="color:var(--text);">สร้างที่:</b> <a href="https://github.com/settings/tokens" target="_blank" style="color:var(--blue);">github.com/settings/tokens</a><br>
                <b style="color:var(--text);">Permission:</b> <code style="background:var(--bg);padding:2px 6px;border-radius:4px;font-size:0.78rem;">actions:write</code><br>
                <span style="color:var(--yellow);">Token เก็บใน browser เท่านั้น ไม่ส่งออกไปที่อื่น</span>
            </p>
            <input type="password" id="tokenInput" placeholder="ghp_xxxxxxxxxxxx" autocomplete="off" style="font-family:monospace;font-size:0.85rem;">
            <div class="confirm-actions">
                <button class="ctrl-btn" onclick="closeTokenModal()">ยกเลิก</button>
                <button class="ctrl-btn resume" id="tokenSubmitBtn" onclick="submitToken()">บันทึก Token</button>
            </div>
        </div>
    </div>
    <!-- U3: DRY RUN Banner -->
    {dry_banner_html}

    <!-- Header -->
    <div class="header">
        <div class="header-left">
            <h1>Phoenix v5.1</h1>
            <!-- U9: Freshness badge -->
            <span class="freshness" id="freshness"></span>
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
            <a href="https://github.com/manhiiautomation-gif/Smart-dca/actions" target="_blank" class="ctrl-btn" style="text-decoration:none;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                Logs
            </a>
            <span id="tokenStatus" style="margin-left:auto;font-size:0.7rem;color:var(--text-dim);cursor:pointer;" onclick="openTokenModal()" title="คลิกเพื่อตั้ง/เปลี่ยน Token"></span>
        </div>
    </div>

    <!-- U2: Onboarding Hero (shown only when empty state) -->
    {('''<div class="onboarding-hero">
        <div class="onboard-icon">&#128200;</div>
        <div class="onboard-title">ยินดีต้อนรับสู่ Phoenix DCA Bot</div>
        <div class="onboard-desc">
            ระบบพร้อมทำงานแล้ว — การซื้อครั้งแรกจะเกิดขึ้นอัตโนมัติเมื่อถึงเวลา DCA<br>
            <small>รันถัดไป: <b>''' + next_run_str + ' น.</b> (' + next_run_day + ')</small>' + ('<br><span style="color:var(--yellow);">&#9888; ขณะนี้อยู่ในโหมดทดสอบ</span>' if dry_run else '') + '''
        </div>
    </div>''') if is_empty else ''}

    <!-- Row 1: Portfolio + Kill Switch -->
    <div class="grid grid-2">
        <!-- Portfolio Summary -->
        <div class="card">
            <div class="card-title">Portfolio Summary</div>
            <div class="metric">
                <div class="metric-label">Portfolio Value</div>
                <div class="metric-value hero {roi_class} num-mono">{fmt_num(portfolio)} <small style="font-size:0.7em;opacity:0.7;">{currency}</small></div>
            </div>
            {('<div class="metric" style="margin-top:-4px;"><div class="metric-label">' + change_label + '</div><div class="metric-value ' + chg_class + '" style="font-size:0.95rem;">' + fmt_num(change_abs, 2) + ' ' + currency + ' (' + f'{change_pct:+.2f}' + '%)</div></div>') if change_pct is not None else ''}
            <div class="metric">
                <div class="metric-label">BTC Holdings</div>
                <div class="metric-value blue num-mono">{fmt_btc(btc_bal)}</div>
                <div class="metric-sub">{fmt_num(btc_bal * current_price)} {currency}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Cash Balance</div>
                <div class="metric-value">{fmt_num(cash_bal)} {currency}</div>
            </div>
            {('<div class="metric" style="margin-top:-4px;"><div class="metric-label">Avg Buy Price</div><div class="metric-value dim" style="font-size:0.95rem;">' + fmt_num(avg_buy_price) + ' ' + currency + '</div></div>') if avg_buy_price > 0 else ''}
            {('<div class="metric" style="margin-top:-4px;"><div class="metric-label">Unrealized P&L</div><div class="metric-value ' + upnl_class + '" style="font-size:0.95rem;">' + fmt_num(unrealized_pnl) + ' ' + currency + ' (' + f'{unrealized_pnl_pct:+.1f}' + '%)</div></div>') if avg_buy_price > 0 else ''}
            {('<div class="metric" style="margin-top:-4px;"><div class="metric-label">Avg Buy Size</div><div class="metric-value dim" style="font-size:0.95rem;">' + fmt_num(avg_buy_size) + ' ' + currency + '/trade</div></div>') if avg_buy_size > 0 else ''}
            <div class="grid grid-2" style="margin-top:12px; gap:8px;">
                <div class="metric">
                    <div class="metric-label">ROI (ตลอดกาล)</div>
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
                    <div class="metric-value {max_dd_class}">{fmt_pct(max_dd)}</div>
                </div>
            </div>
        </div>

        <!-- System Status + Kill Switch -->
        <div class="card">
            <div class="card-title">System Status</div>
            <div class="ind-grid">
                <div class="ind-item">
                    <span class="label">สวิตช์หยุดฉุกเฉิน L1</span>
                    <span class="val">{l1_html}</span>
                </div>
                <div class="ind-item">
                    <span class="label">สวิตช์หยุดฉุกเฉิน L2</span>
                    <span class="val">{l2_html}</span>
                </div>
                <div class="ind-item">
                    <span class="label">Exchange</span>
                    <span class="val">{exchange_name or currency.upper()}</span>
                </div>
                <div class="ind-item">
                    <span class="label">รันล่าสุด</span>
                    <span class="val">{last_run}</span>
                </div>
                <div class="ind-item">
                    <span class="label">จำนวนรัน (ตลอดกาล)</span>
                    <span class="val">{run_count}</span>
                </div>
                <div class="ind-item">
                    <span class="label">ราคา BTC ตอนนี้</span>
                    <span class="val num-mono">{fmt_num(current_price)} {currency}</span>
                </div>
                <!-- U11: Next Run -->
                <div class="ind-item">
                    <span class="label">รันถัดไป</span>
                    <span class="val blue">{next_run_str} น.</span>
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
                    <span class="label">MVRV Z-Score</span>
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
                    <span class="val">{fmt_num(sopr, 3)} <small class="tag neutral sopr-src">{('โปรดักซี่' if sopr_source == 'proxy' else sopr_source)}</small></span>
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
            <div style="margin-top:12px;padding:10px;border-radius:8px;background:var(--{next_action_class}-bg, rgba(139,148,158,0.1));border:1px solid var(--{next_action_class}, var(--border));">
                <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px;">NEXT EXPECTED ACTION</div>
                <div style="font-size:13px;font-weight:600;color:var(--{next_action_class}, var(--text));">{next_action}</div>
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
                        <span class="label">BTC ซื้อรวม</span>
                        <span class="val num-mono">{fmt_btc(total_btc_bought)}</span>
                    </div>
                    <div class="ind-item">
                        <span class="label">BTC ขายรวม</span>
                        <span class="val num-mono">{fmt_btc(total_btc_sold)}</span>
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

    {config_html}
    {demo_html}

    <!-- Footer -->
    <div class="footer">
        Phoenix v5.1 DCA Bot | Generated: {now_str} | Auto-refresh: 5 min | <a href="https://github.com/manhiiautomation-gif/Smart-dca" target="_blank" style="color:var(--blue);text-decoration:none;">GitHub</a>
    </div>

    <script>
    (function() {{
        // GitHub Actions direct dispatch (replaces Netlify serverless function)
        var REPO = 'manhiiautomation-gif/Smart-dca';
        var API_BASE = 'https://api.github.com/repos/' + REPO + '/actions/workflows';
        var WORKFLOWS = {{
            update: 'dashboard-trigger.yml',
            kill: 'dashboard-trigger.yml',
            resume: 'dashboard-trigger.yml'
        }};

        // ── Token management (custom modal, no prompt()) ──
        var _pendingTokenCallback = null;

        function getGitHubToken() {{
            var params = new URLSearchParams(window.location.search);
            var token = params.get('token');
            if (!token) {{
                try {{ token = localStorage.getItem('gh_pat'); }} catch(e) {{}}
            }}
            return token || null;
        }}

        function setGitHubToken(token) {{
            try {{ localStorage.setItem('gh_pat', token); }} catch(e) {{}}
            updateTokenStatus();
        }}

        function removeGitHubToken() {{
            try {{ localStorage.removeItem('gh_pat'); }} catch(e) {{}}
            updateTokenStatus();
        }}

        function updateTokenStatus() {{
            var el = document.getElementById('tokenStatus');
            if (!el) return;
            var token = getGitHubToken();
            if (token) {{
                var masked = token.slice(0, 6) + '...' + token.slice(-4);
                el.innerHTML = '<span style="color:var(--green);">&#9679;</span> Token: ' + masked;
                el.title = 'คลิกเพื่อเปลี่ยน Token';
            }} else {{
                el.innerHTML = '<span style="color:var(--red);">&#9679;</span> ไม่มี Token';
                el.title = 'คลิกเพื่อตั้งค่า Token';
            }}
        }}

        window.openTokenModal = function(pendingCallback) {{
            _pendingTokenCallback = pendingCallback || null;
            var overlay = document.getElementById('tokenOverlay');
            var input = document.getElementById('tokenInput');
            var existing = getGitHubToken();
            input.value = existing || '';
            overlay.classList.add('active');
            setTimeout(function() {{ input.focus(); }}, 100);
        }};

        window.closeTokenModal = function() {{
            document.getElementById('tokenOverlay').classList.remove('active');
            if (_pendingTokenCallback) {{
                _pendingTokenCallback(null);
                _pendingTokenCallback = null;
            }}
        }};

        window.submitToken = function() {{
            var input = document.getElementById('tokenInput');
            var val = input.value.trim();
            if (!val) {{
                showToast('กรุณาใส่ Token', 'error');
                return;
            }}
            setGitHubToken(val);
            closeTokenModal();
            showToast('Token บันทึกแล้ว', 'success');
            if (_pendingTokenCallback) {{
                var cb = _pendingTokenCallback;
                _pendingTokenCallback = null;
                cb(val);
            }}
        }};

        // Allow Enter key in token input
        var tokenInputEl = document.getElementById('tokenInput');
        if (tokenInputEl) {{
            tokenInputEl.addEventListener('keydown', function(e) {{
                if (e.key === 'Enter') submitToken();
                if (e.key === 'Escape') closeTokenModal();
            }});
        }}
        var tokenOverlayEl = document.getElementById('tokenOverlay');
        if (tokenOverlayEl) {{
            tokenOverlayEl.addEventListener('click', function(e) {{
                if (e.target === this) closeTokenModal();
            }});
        }}

        function requireToken(callback) {{
            var token = getGitHubToken();
            if (token) {{
                callback(token);
                return;
            }}
            openTokenModal(function(submittedToken) {{
                if (submittedToken) {{
                    callback(submittedToken);
                }} else {{
                    showToast('ต้องมี Token ก่อนกดปุ่ม', 'error');
                }}
            }});
        }}

        // ── Toast & Loading ──
        function showToast(msg, type) {{
            var c = document.getElementById('toasts');
            var t = document.createElement('div');
            t.className = 'toast ' + (type || 'info');
            t.textContent = msg;
            c.appendChild(t);
            setTimeout(function() {{ t.remove(); }}, 5000);
        }}

        function setLoading(btn, on) {{
            if (on) btn.classList.add('loading'); else btn.classList.remove('loading');
            btn.disabled = on;
        }}

        function dispatchWorkflow(workflowFile, inputs, token) {{
            return fetch(API_BASE + '/' + workflowFile + '/dispatches', {{
                method: 'POST',
                headers: {{
                    'Authorization': 'Bearer ' + token,
                    'Accept': 'application/vnd.github.v3+json',
                    'Content-Type': 'application/json'
                }},
                body: JSON.stringify({{ ref: 'main', inputs: inputs }})
            }});
        }}

        // ── Actions ──
        window.doUpdate = function() {{
            var btn = document.getElementById('btnUpdate');
            requireToken(function(token) {{
                setLoading(btn, true);
                dispatchWorkflow('dashboard-trigger.yml', {{ action: 'update' }}, token)
                .then(function(r) {{
                    if (r.status === 204) {{
                        showToast('ส่งคำสั่ง Update แล้ว! รอ ~2 นาที แล้วรีเฟรชหน้า', 'success');
                    }} else {{
                        return r.json().then(function(d) {{
                            throw new Error(d.message || 'HTTP ' + r.status);
                        }});
                    }}
                }})
                .catch(function(e) {{ showToast('Error: ' + e.message, 'error'); }})
                .finally(function() {{ setTimeout(function() {{ setLoading(btn, false); }}, 3000); }});
            }});
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
                msg.innerHTML = '\u26a0\ufe0f ก่อน Kill:<br>' +
                    '\u2022 กำลังถือ: <b>' + {fmt_num(btc_bal)} + ' BTC</b> (~' + {fmt_num(btc_bal * current_price)} + ' {currency})<br>' +
                    '\u2022 ถ้าราคาเปลี่ยน จะไม่มี auto-sell<br>' +
                    '\u2022 ต้อง Resume ด้วยมือเท่านั้น';
                input.value = '';
                input.placeholder = 'Reason (optional)';
                input.style.display = 'block';
                okBtn.textContent = 'Kill';
                okBtn.className = 'ctrl-btn kill';
                confirmCallback = function() {{
                    requireToken(function(token) {{
                        var btn = document.getElementById('btnKill');
                        setLoading(btn, true);
                        dispatchWorkflow('dashboard-trigger.yml', {{ action: 'kill', reason: input.value || 'Manual kill from dashboard' }}, token)
                        .then(function(r) {{
                            if (r.status === 204) showToast('Kill switch activated!', 'success');
                            else throw new Error('HTTP ' + r.status);
                        }})
                        .catch(function(e) {{ showToast('Error: ' + e.message, 'error'); }})
                        .finally(function() {{ setTimeout(function() {{ setLoading(btn, false); }}, 3000); }});
                    }});
                }};
            }} else {{
                title.textContent = 'Resume Bot?';
                msg.textContent = 'Bot \u0e08\u0e30\u0e01\u0e25\u0e31\u0e1a\u0e21\u0e32\u0e17\u0e33\u0e07\u0e32\u0e19\u0e1b\u0e01\u0e15\u0e34';
                input.style.display = 'none';
                okBtn.textContent = 'Resume';
                okBtn.className = 'ctrl-btn resume';
                confirmCallback = function() {{
                    requireToken(function(token) {{
                        var btn = document.getElementById('btnKill');
                        setLoading(btn, true);
                        dispatchWorkflow('dashboard-trigger.yml', {{ action: 'resume' }}, token)
                        .then(function(r) {{
                            if (r.status === 204) showToast('Bot resumed!', 'success');
                            else throw new Error('HTTP ' + r.status);
                        }})
                        .catch(function(e) {{ showToast('Error: ' + e.message, 'error'); }})
                        .finally(function() {{ setTimeout(function() {{ setLoading(btn, false); }}, 3000); }});
                    }});
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
            if (e.key === 'Escape') {{ closeConfirm(); toggleHelp(); }}
        }});
        // Help modal
        window.toggleHelp = function() {{
            var o = document.getElementById('helpOverlay');
            if (o) o.classList.toggle('active');
        }};
        var helpO = document.getElementById('helpOverlay');
        if (helpO) helpO.addEventListener('click', function(e) {{
            if (e.target === this) toggleHelp();
        }});
        // Init token status on page load
        updateTokenStatus();

        // U9: Freshness badge — shows relative time since generation
        (function() {{
            var genTime = new Date('{now_str}');
            var el = document.getElementById('freshness');
            if (!el || isNaN(genTime)) return;
            function update() {{
                var diff = Math.floor((Date.now() - genTime) / 60000);
                if (diff < 1) el.textContent = 'อัปเดตเมื่อสักครู่';
                else if (diff < 60) el.textContent = 'อัปเดต ' + diff + ' นาทีก่อน';
                else {{ var h = Math.floor(diff/60); var m = diff % 60; el.textContent = 'อัปเดต ' + h + ' ชม. ' + m + ' นาทีก่อน'; }}
            }}
            update();
            setInterval(update, 30000);
        }})();
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
                    '<div style="text-align:center;color:var(--text-dim);padding:60px 20px;">' +
                    '<div style="font-size:2rem;opacity:0.4;margin-bottom:8px;">&#128200;</div>' +
                    '<div style="font-size:0.9rem;">กราฟจะปรากฏหลังการซื้อขายครั้งแรก</div>' +
                    '<div style="font-size:0.78rem;margin-top:4px;">การซื้อ DCA อัตโนมัติจะเริ่มต้นเมื่อถึงเวลาที่กำหนด</div></div>';
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
