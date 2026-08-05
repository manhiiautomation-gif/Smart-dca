#!/usr/bin/env python3
"""Quick comparison: Phoenix v5.1 vs Standard DCA."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from smart_dca.data_pipeline import build_master_dataframe
from smart_dca.backtest_engine import backtest_strategy
from smart_dca.strategies.standard_dca import strategy_standard_dca
from smart_dca.strategies.style_phoenix_v5_1 import strategy_style_phoenix_v5_1

master = build_master_dataframe(years=5)

r_dca, d_dca = backtest_strategy(master, strategy_standard_dca, 'Standard DCA')
s51 = strategy_style_phoenix_v5_1(master)
r_51, d_51 = backtest_strategy(master, s51, 'Phoenix v5.1')

print('=' * 65)
print('  {:<28} {:>12} {:>12} {:>10}'.format('Metric', 'DCA', 'v5.1', 'Diff'))
print('=' * 65)

metrics = [
    ('Final Value (THB)', 'final_value', ',.0f'),
    ('Net Profit (THB)', 'net_profit', ',.0f'),
    ('ROI (%)', 'roi_pct', '.1f'),
    ('True ROI (%)', 'true_roi_pct', '.1f'),
    ('Max Drawdown (%)', 'max_drawdown_pct', '.1f'),
    ('Calmar Ratio', 'calmar_ratio', '.2f'),
    ('Total BTC', 'total_btc', '.8f'),
    ('BTC Sold (%)', 'btc_sell_pct', '.1f'),
    ('Avg Cost (THB/BTC)', 'avg_cost_thb', ',.0f'),
    ('Cash Reserve (THB)', 'cash_reserve', ',.0f'),
    ('Sell Count', 'sell_count', 'd'),
    ('Total Fees (THB)', 'total_fees_paid', ',.0f'),
    ('Days in DD (%)', 'days_in_drawdown_pct', '.1f'),
    ('Net Capital In', 'net_capital', ',.0f'),
]

for name, key, fmt in metrics:
    dv = r_dca[key]
    v = r_51[key]
    diff = v - dv
    sign = '+' if diff > 0 else ''
    print('  {:<28} {:>12} {:>12} {:>10}'.format(
        name, format(dv, fmt), format(v, fmt), sign + format(diff, fmt)))

extra_profit = r_51['net_profit'] - r_dca['net_profit']
pct_better = (extra_profit / abs(r_dca['net_profit']) * 100) if r_dca['net_profit'] != 0 else 0

print()
print('  v5.1 extra profit: {:+,} THB ({:+.1f}%)'.format(int(extra_profit), pct_better))
print('  BTC end price: ${:,.0f}'.format(master.iloc[-1]['price_usd']))
