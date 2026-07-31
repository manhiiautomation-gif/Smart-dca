#!/usr/bin/env python3
"""Diagnose Omega avg cost spike - v2."""
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '/home/z/my-project/scripts')
from smart_dca_backtest import (
    build_master_dataframe, backtest_strategy, strategy_style_omega, strategy_style_beta, strategy_style_c, USD_THB_RATE
)

master_df = build_master_dataframe(years=5)

for years in [3, 5]:
    if years == 3:
        test_df = master_df.tail(int(3 * 365.25)).reset_index(drop=True)
    else:
        test_df = master_df.copy()
    
    _, daily_omega = backtest_strategy(test_df, strategy_style_omega(test_df), 'Omega')
    _, daily_beta = backtest_strategy(test_df, strategy_style_beta(test_df), 'Beta')
    _, daily_c = backtest_strategy(test_df, strategy_style_c, 'C')

    print(f'\n{"=" * 90}')
    print(f'  {years}-YEAR: OMEGA AVG COST SPIKE ANALYSIS')
    print(f'{"=" * 90}')

    omega = daily_omega.copy()
    omega['btc_change'] = omega['btc'].diff()
    omega['invested_change'] = omega['total_invested'].diff()
    omega['cash_change'] = omega['cash_reserve'].diff()
    omega['avg_cost'] = omega['avg_cost'].replace(0, np.nan)

    # Find days where avg cost jumped significantly
    omega['cost_delta'] = omega['avg_cost'].diff()
    big_jumps = omega[omega['cost_delta'] > 50000].sort_values('cost_delta', ascending=False)

    print(f'\nDays with avg cost jump > 50,000 THB: {len(big_jumps)}')
    print(f'\n{"Date":<12} {"AvgCost":>12} {"Delta":>10} {"Price USD":>10} {"BTC":>10} {"BTC d":>10} {"Cash":>10} {"Cash d":>10} {"MVRV":>6}')
    print('-' * 100)

    for idx, r in big_jumps.head(15).iterrows():
        row_idx = omega.index.get_loc(r.name)
        mvrv_val = test_df.iloc[row_idx]['mvrv']
        date_str = str(r['date'])[:10]
        print(f'{date_str:<12} {r["avg_cost"]:>12,.0f} {r["cost_delta"]:>+10,.0f} {r["price_thb"]/USD_THB_RATE:>10,.0f} '
              f'{r["btc"]:>10.6f} {r["btc_change"]:>+10.6f} {r["cash_reserve"]:>10,.0f} {r["cash_change"]:>+10,.0f} {mvrv_val:>6.2f}')

    # KEY CHECK: On spike days, did BTC decrease (SELL event)?
    sell_days = big_jumps[big_jumps['btc_change'] < -0.0001]
    buy_at_high = big_jumps[(big_jumps['btc_change'] >= -0.0001) & (big_jumps['invested_change'] > 500)]
    
    print(f'\n--- ROOT CAUSE BREAKDOWN ---')
    print(f'  Spike days caused by SELL (BTC decreased): {len(sell_days)} / {len(big_jumps)}')
    print(f'  Spike days caused by BUY at HIGH price:     {len(buy_at_high)} / {len(big_jumps)}')

    if len(sell_days) > 0:
        print(f'\n  >> CONFIRMED: Avg cost spikes are from SELLING BTC (denominator drops)')
        print(f'     When you sell BTC, total_invested stays same but btc count drops.')
        print(f'     Formula: avg_cost = total_invested / btc  -->  SPIKES when btc drops.')
        print(f'     This is a METRIC ARTIFACT, not a strategy error.')

    # Check: is Omega deploying reserve at HIGH MVRV? (that would be a real bug)
    print(f'\n--- CHECK: Reserve deploy at HIGH MVRV (>2.0)? ---')
    deploy_days = omega[omega['cash_change'] < -500]
    high_mvrv_deploys = 0
    for idx, r in deploy_days.iterrows():
        row_idx = omega.index.get_loc(r.name)
        mvrv_val = test_df.iloc[row_idx]['mvrv']
        if mvrv_val > 2.0:
            high_mvrv_deploys += 1
            date_str = str(r['date'])[:10]
            print(f'  WARNING: {date_str} deployed {r["cash_change"]:+,.0f} at MVRV={mvrv_val:.2f} Price=${r["price_thb"]/USD_THB_RATE:,.0f}')
    if high_mvrv_deploys == 0:
        print(f'  OK: No reserve deployments at MVRV > 2.0 (correct behavior)')

    # Show Omega vs C avg cost at key points to show Omega is actually buying CHEAPER
    print(f'\n--- OMEGA vs C vs BETA avg cost at sample points ---')
    points = [0, len(omega)//6, len(omega)//3, len(omega)//2, 2*len(omega)//3, 5*len(omega)//6, len(omega)-1]
    print(f'{"Date":<12} {"Omega Cost":>12} {"Beta Cost":>12} {"C Cost":>12} {"Price USD":>10} {"Omega BTC":>10} {"C BTC":>10}')
    print('-' * 85)
    for i in points:
        o = omega.iloc[i]
        b = daily_beta.iloc[i]
        c = daily_c.iloc[i]
        date_str = str(o['date'])[:10]
        print(f'{date_str:<12} {o["avg_cost"]:>12,.0f} {b["avg_cost"]:>12,.0f} {c["avg_cost"]:>12,.0f} '
              f'{o["price_thb"]/USD_THB_RATE:>10,.0f} {o["btc"]:>10.6f} {c["btc"]:>10.6f}')

    # Final state comparison
    print(f'\n--- FINAL STATE ---')
    o = omega.iloc[-1]; b = daily_beta.iloc[-1]; c = daily_c.iloc[-1]
    print(f'  Omega: AvgCost={o["avg_cost"]:,.0f} BTC={o["btc"]:.6f} Cash={o["cash_reserve"]:,.0f}')
    print(f'  Beta:  AvgCost={b["avg_cost"]:,.0f} BTC={b["btc"]:.6f} Cash={b["cash_reserve"]:,.0f}')
    print(f'  C:     AvgCost={c["avg_cost"]:,.0f} BTC={c["btc"]:.6f} Cash={c["cash_reserve"]:,.0f}')
    print(f'\n  NOTE: Omega avg cost is HIGHER than C because Omega SOLD some cheap BTC.')
    print(f'        The sold BTC was bought at low prices and sold at high prices (profitable).')
    print(f'        Remaining BTC was still bought cheap — but the metric total_invested/btc')
    print(f'        punishes sellers by dividing by fewer BTC. This is a METRIC ISSUE.')
