#!/usr/bin/env python3
"""Diagnose Omega's avg cost spike behavior."""
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

    print(f'\n{"=" * 80}')
    print(f'  {years}-YEAR OMEGA AVG COST DIAGNOSTIC')
    print(f'{"=" * 80}')

    # Find where avg cost spikes
    omega = daily_omega.copy()
    omega['avg_cost_change'] = omega['avg_cost'].diff()

    # Top 10 biggest avg cost increases
    top_increases = omega.nlargest(10, 'avg_cost_change')
    print(f'\nTop 10 biggest AVG COST increases:')
    for _, r in top_increases.iterrows():
        print(f'  {r["date"]} | AvgCost: {r["avg_cost"]:,.0f} (delta +{r["avg_cost_change"]:+,.0f}) | '
              f'Price: {r["price_thb"]:,.0f} | BTC: {r["btc"]:.6f} | Cash: {r["cash_reserve"]:,.0f} | '
              f'Invested: {r["total_invested"]:,.0f}')

    # Find periods where avg cost > 2x the previous avg
    omega['cost_ratio'] = omega['avg_cost'] / omega['avg_cost'].shift(1)
    spikes = omega[omega['cost_ratio'] > 1.5].head(20)
    if len(spikes) > 0:
        print(f'\nDays where avg cost jumped >50% from previous day:')
        for _, r in spikes.iterrows():
            idx = omega.index.get_loc(r.name)
            prev = omega.iloc[idx - 1] if idx > 0 else None
            if prev is not None:
                prev_cost = prev['avg_cost']
                print(f'  {r["date"].date()} | Cost: {prev_cost:,.0f} -> {r["avg_cost"]:,.0f} ({r["cost_ratio"]:.2f}x) | '
                      f'Price: {prev["price_thb"]:,.0f} -> {r["price_thb"]:,.0f} | '
                      f'BTC: {prev["btc"]:.6f} -> {r["btc"]:.6f}')

    # Compare Omega vs Beta avg cost over time at key points
    print(f'\nAvg Cost comparison at key dates:')
    sample_dates = [0, len(omega)//4, len(omega)//2, 3*len(omega)//4, len(omega)-1]
    for i in sample_dates:
        o = omega.iloc[i]
        b = daily_beta.iloc[i]
        c = daily_c.iloc[i]
        print(f'  {o["date"].date()} | Omega: {o["avg_cost"]:,.0f} | Beta: {b["avg_cost"]:,.0f} | C: {c["avg_cost"]:,.0f} | '
              f'Price: {o["price_thb"]:,.0f}')

    # Find where Omega's avg cost exceeds C's avg cost (shouldn't happen often)
    merged = omega.merge(daily_beta[['date', 'avg_cost']], on='date', suffixes=('_omega', '_beta'))
    merged = merged.merge(daily_c[['date', 'avg_cost']], on='date')
    merged.rename(columns={'avg_cost': 'avg_cost_c'}, inplace=True)
    
    omega_higher = merged[merged['avg_cost_omega'] > merged['avg_cost_c'] * 1.1]
    if len(omega_higher) > 0:
        print(f'\nDays where Omega avg cost > C avg cost by >10% ({len(omega_higher)} days):')
        # Show first and last 5
        for _, r in pd.concat([omega_higher.head(5), omega_higher.tail(5)]).iterrows():
            print(f'  {r["date"].date()} | Omega: {r["avg_cost_omega"]:,.0f} | C: {r["avg_cost_c"]:,.0f} | '
                  f'Ratio: {r["avg_cost_omega"]/r["avg_cost_c"]:.2f}x | Price: ${r["price_thb"]/USD_THB_RATE:,.0f}')

    # Check: is Omega buying at high prices from reserve?
    print(f'\n--- Reserve deployment analysis ---')
    # Days where cash_reserve decreased significantly (reserve being deployed)
    omega['cash_change'] = omega['cash_reserve'].diff()
    big_deploys = omega[omega['cash_change'] < -1000].sort_values('cash_change')
    print(f'Days with reserve deploy >1,000 THB: {len(big_deploys)}')
    if len(big_deploys) > 0:
        print(f'\nTop 10 largest reserve deployments:')
        for _, r in big_deploys.head(10).iterrows():
            idx = omega.index.get_loc(r.name)
            prev = omega.iloc[idx - 1] if idx > 0 else None
            mvrv_row = test_df.iloc[idx] if idx < len(test_df) else None
            mvrv_val = mvrv_row['mvrv'] if mvrv_row is not None else 'N/A'
            rp_val = mvrv_row['realized_price'] if mvrv_row is not None else 'N/A'
            print(f'  {r["date"].date()} | Deploy: {r["cash_change"]:+,.0f} THB | '
                  f'Cash: {prev["cash_reserve"] if prev is not None else 0:,.0f} -> {r["cash_reserve"]:,.0f} | '
                  f'Price: ${r["price_thb"]/USD_THB_RATE:,.0f} | MVRV: {mvrv_val}')

    # Final summary
    print(f'\n--- Final State ---')
    o = omega.iloc[-1]
    b = daily_beta.iloc[-1]
    c = daily_c.iloc[-1]
    print(f'  Omega: AvgCost={o["avg_cost"]:,.0f} BTC={o["btc"]:.6f} Cash={o["cash_reserve"]:,.0f} Invested={o["total_invested"]:,.0f}')
    print(f'  Beta:  AvgCost={b["avg_cost"]:,.0f} BTC={b["btc"]:.6f} Cash={b["cash_reserve"]:,.0f} Invested={b["total_invested"]:,.0f}')
    print(f'  C:     AvgCost={c["avg_cost"]:,.0f} BTC={c["btc"]:.6f} Cash={c["cash_reserve"]:,.0f} Invested={c["total_invested"]:,.0f}')

    # The key metric: what's the average BUY PRICE when deploying from reserve?
    # Track total_invested - total that would have been invested by C's rules
    # Reserve deploys happen when MVRV < 1.3
    # Check avg price during deploy days vs non-deploy days
    deploy_days = omega[omega['cash_change'] < -100]
    non_deploy_days = omega[omega['cash_change'] >= -100]
    if len(deploy_days) > 0:
        print(f'\n  Deploy days avg price:     ${deploy_days["price_thb"].mean()/USD_THB_RATE:,.0f}')
        print(f'  Non-deploy days avg price: ${non_deploy_days["price_thb"].mean()/USD_THB_RATE:,.0f}')
        print(f'  Overall avg price:         ${omega["price_thb"].mean()/USD_THB_RATE:,.0f}')
