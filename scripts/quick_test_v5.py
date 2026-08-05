#!/usr/bin/env python3
"""Quick v5 vs v1 vs v4 comparison."""
import sys
sys.path.insert(0, 'scripts')
from smart_dca.data_pipeline import build_master_dataframe
from smart_dca.backtest_engine import backtest_strategy
from smart_dca.strategies.style_phoenix import strategy_style_phoenix
from smart_dca.strategies.style_phoenix_v4 import strategy_style_phoenix_v4
from smart_dca.strategies.style_phoenix_v5 import strategy_style_phoenix_v5

master = build_master_dataframe(years=5)

for years in [3, 5]:
    label = f'{years}-Year'
    if years == 3:
        test_df = master.tail(int(3 * 365.25)).reset_index(drop=True)
    else:
        test_df = master.copy()
    
    print()
    print('=' * 95)
    print(f'  {label.upper()} BACKTEST')
    print('=' * 95)
    print(f'{"Strategy":<14} {"Portfolio":>12} {"True ROI":>9} {"DD%":>7} {"Calmar":>7} {"BTC":>10} {"Sells":>6} {"Sell P/L":>9} {"Avg Sell THB":>14}')
    print('-' * 95)
    
    for name, func in [('Phoenix v1', strategy_style_phoenix),
                          ('Phoenix v4', strategy_style_phoenix_v4),
                          ('Phoenix v5', strategy_style_phoenix_v5)]:
        sf = func(test_df)
        r, _ = backtest_strategy(test_df, sf, name)
        spr = f'{r["sell_profit_ratio"]:.2f}x' if r['sell_profit_ratio'] > 0 else '-'
        asp = f'{r["avg_sell_price_thb"]:,.0f}' if r['avg_sell_price_thb'] > 0 else '-'
        print(f'{name:<14} {r["final_value"]:>12,.0f} {r["true_roi_pct"]:>8.1f}% {r["max_drawdown_pct"]:>6.1f}% {r["calmar_ratio"]:>7.2f} {r["total_btc"]:>10.6f} {r["sell_count"]:>6} {spr:>9} {asp:>14}')
    
    print()

print('=' * 95)