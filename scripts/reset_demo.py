#!/usr/bin/env python3
"""Reset demo portfolio data to clean state.

Usage:
    python scripts/reset_demo.py                # binance/USDT
    python scripts/reset_demo.py --exchange bitkub  # bitkub/THB
    python scripts/reset_demo.py --exchange bitkub --cash 50000
"""

import argparse
import json
import sys
import os

# Add project root for live_bot import
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

parser = argparse.ArgumentParser(description='Reset demo portfolio')
parser.add_argument('--exchange', '-e', default='binance',
                    choices=['binance', 'bitkub'],
                    help='Exchange (default: binance)')
parser.add_argument('--cash', '-c', type=float, default=10000.0,
                    help='Initial cash (default: 10000)')
parser.add_argument('--scenario', '-s', default='default',
                    help='Scenario name (default: default)')
args = parser.parse_args()

# Determine currency from exchange
currency = 'USDT' if args.exchange == 'binance' else 'THB'

# Use the proper init_demo to ensure consistency
clean_state = {
    'scenario': args.scenario,
    'initial_cash': args.cash,
    'currency': currency,
    'exchange': args.exchange,
    'created_at': '',
    'last_run_date': '',
    'run_count': 0,
    'cash': args.cash,
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

import datetime
clean_state['created_at'] = datetime.datetime.now().isoformat()

# Use scenario-based paths if not default
if args.scenario == 'default':
    state_path = os.path.join(PROJECT_ROOT, 'demo_state.json')
    trades_path = os.path.join(PROJECT_ROOT, 'demo_trades.json')
    report_path = os.path.join(PROJECT_ROOT, 'demo_report.json')
else:
    state_path = os.path.join(PROJECT_ROOT, f'demo_state_{args.scenario}.json')
    trades_path = os.path.join(PROJECT_ROOT, f'demo_trades_{args.scenario}.json')
    report_path = os.path.join(PROJECT_ROOT, f'demo_report_{args.scenario}.json')

with open(state_path, 'w') as f:
    json.dump(clean_state, f, indent=2)

with open(trades_path, 'w') as f:
    json.dump([], f, indent=2)

with open(report_path, 'w') as f:
    json.dump({}, f, indent=2)

print(f'Demo data reset complete.')
print(f'  State:  {state_path}')
print(f'  Exchange: {args.exchange.upper()} / {currency}')
print(f'  Cash:  {args.cash:,.2f} {currency}')
print(f'  Scenario: {args.scenario}')
