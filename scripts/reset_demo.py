#!/usr/bin/env python3
"""Reset demo portfolio data to clean state."""

import json

# Reset demo_state.json with clean binance/USDT state
clean_state = {
    'scenario': 'default',
    'initial_cash': 10000.0,
    'currency': 'USDT',
    'exchange': 'binance',
    'created_at': '2026-08-11T00:00:00',
    'last_run_date': '',
    'run_count': 0,
    'cash': 10000.0,
    'btc': 0.0,
    'sell_proceeds_reserve': 0.0,
    'total_invested': 0.0,
    'total_sell_proceeds': 0.0,
    'total_btc_bought': 0.0,
    'total_btc_sold': 0.0,
    'buy_count': 0,
    'sell_count': 0,
    'cumulative_fees': 0.0,
    'cumulative_slippage': 0.0,
    'peak_value': 0.0,
    'max_drawdown': 0.0,
    'cooldown': 0,
    'currency_locked': True,
    'history': [],
    'last_decision': None,
    'last_price': 0.0,
    'last_indicators': {},
    'validation': {
        'total_runs': 0,
        'buy_signals': 0,
        'sell_signals': 0,
        'actual_buys': 0,
        'actual_sells': 0,
        'skipped_buys_reason': {},
        'skipped_sells_reason': {},
        'avg_buy_slippage_pct': 0.0,
        'avg_sell_slippage_pct': 0.0,
    },
}

with open('demo_state.json', 'w') as f:
    json.dump(clean_state, f, indent=2)

with open('demo_trades.json', 'w') as f:
    json.dump([], f, indent=2)

with open('demo_report.json', 'w') as f:
    json.dump({}, f, indent=2)

print('Demo data reset complete.')
print('  demo_state.json: currency=USDT, exchange=binance, cash=10000.0')
print('  demo_trades.json: []')
print('  demo_report.json: {}')
