#!/usr/bin/env python3
"""
Dashboard HTML Generator
Reads state.json (authoritative) for summary metrics and trade_log.json for
trade history. Dry-run trades are excluded from the main metrics and history
table; state.json is the single source of truth for current bot status.
"""
import json
import os
from datetime import datetime


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADE_LOG_PATH = os.path.join(PROJECT_ROOT, "trade_log.json")
STATE_PATH = os.path.join(PROJECT_ROOT, "live_bot", "state.json")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "dashboard.html")


def load_trade_log():
    with open(TRADE_LOG_PATH, "r") as f:
        return json.load(f)


def load_state():
    with open(STATE_PATH, "r") as f:
        return json.load(f)


def build_dashboard_html():
    trades = load_trade_log()
    state = load_state()

    # FIX: Use state.json as the single source of truth for all summary metrics.
    # state.json is updated by the engine on every live trade / cycle.
    total_trades = state.get("total_trades", 0)
    total_volume = state.get("total_volume", 0.0)
    last_exchange = state.get("last_exchange_name", "") or "N/A"
    is_live = state.get("is_live", False)
    cycles_completed = state.get("cycles_completed", 0)
    win_trades = state.get("win_trades", 0)
    loss_trades = state.get("loss_trades", 0)
    last_cycle_time = state.get("last_cycle_time", "")

    # FIX: Only show live (non-dry-run) trades in the history table.
    # Dry-run trades are historical test data and should not appear as current activity.
    live_trades = [t for t in trades if not t.get("dry_run", True)]

    trade_rows = ""
    for t in live_trades:
        trade_rows += f"""
        <tr>
            <td>{t['timestamp']}</td>
            <td>{t['symbol']}</td>
            <td>{t['side']}</td>
            <td>{t['amount']}</td>
            <td>{t['price']}</td>
            <td>{t['exchange']}</td>
            <td>Live</td>
        </tr>"""
    if not live_trades:
        trade_rows = '<tr><td colspan="7" style="text-align:center; color:#888;">No live trades yet</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Trading Bot Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #1a1a2e; color: #eee; }}
        h1 {{ color: #0f3460; }}
        .card {{ background: #16213e; border-radius: 8px; padding: 20px; margin: 10px 0; }}
        .metric {{ font-size: 2em; color: #e94560; }}
        .label {{ color: #888; font-size: 0.9em; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px 12px; border-bottom: 1px solid #333; text-align: left; }}
        th {{ background: #0f3460; }}
        .status {{ padding: 4px 10px; border-radius: 4px; font-weight: bold; }}
        .live {{ background: #28a745; color: white; }}
        .dry {{ background: #dc3545; color: white; }}
    </style>
</head>
<body>
    <h1>Trading Bot Dashboard</h1>
    <div style="display: flex; gap: 15px; flex-wrap: wrap;">
        <div class="card">
            <div class="label">Total Trades</div>
            <div class="metric">{total_trades}</div>
        </div>
        <div class="card">
            <div class="label">Total Volume ($)</div>
            <div class="metric">{total_volume:,.2f}</div>
        </div>
        <div class="card">
            <div class="label">Exchange</div>
            <div class="metric">{last_exchange}</div>
        </div>
        <div class="card">
            <div class="label">Mode</div>
            <div class="metric">{'<span class="status live">LIVE</span>' if is_live else '<span class="status dry">DRY RUN</span>'}</div>
        </div>
        <div class="card">
            <div class="label">Cycles Completed</div>
            <div class="metric">{cycles_completed}</div>
        </div>
        <div class="card">
            <div class="label">Win / Loss</div>
            <div class="metric">{win_trades} / {loss_trades}</div>
        </div>
    </div>
    <div class="card" style="margin-top:10px;">        
        <div class="label">Last Cycle: {last_cycle_time or 'N/A'}</div>
    </div>
    <div class="card" style="margin-top: 20px;">
        <h2>Trade History</h2>
        <table>
            <thead>
                <tr>
                    <th>Time</th><th>Symbol</th><th>Side</th><th>Amount</th><th>Price</th><th>Exchange</th><th>Mode</th>
                </tr>
            </thead>
            <tbody>{trade_rows}</tbody>
        </table>
    </div>
    <p style="color:#666; margin-top:20px;">Generated: {datetime.now().isoformat()}</p>
</body>
</html>"""
    return html


def main():
    html = build_dashboard_html()
    with open(OUTPUT_PATH, "w") as f:
        f.write(html)
    print(f"Dashboard written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
