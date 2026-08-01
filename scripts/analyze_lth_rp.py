#!/usr/bin/env python3
"""Analyze LTH Realized Price proxy calibration."""
import pandas as pd
import numpy as np

df = pd.read_csv('/home/z/my-project/cache/binance_btc_prices.csv', parse_dates=['date'])
mvrv = pd.read_csv('/home/z/my-project/cache/coinmetrics_mvrv.csv', parse_dates=['date'])
master = df.merge(mvrv, on='date', how='inner').sort_values('date')
master = master.dropna(subset=['mvrv'])

master['realized_price'] = master['price_usd'] / master['mvrv']

# LTH RP proxy: k=0.65 constant
master['lth_rp'] = master['realized_price'] * 0.65
master['price_to_lth'] = master['price_usd'] / master['lth_rp']

print('=== MVRV Distribution ===')
print(master['mvrv'].describe())

print('\n=== Price/LTH_RP (k=0.65) ===')
print(master['price_to_lth'].describe())

print('\n=== Percentile analysis ===')
for pct in [5, 10, 25, 50, 75, 90, 95, 99]:
    val = master['price_to_lth'].quantile(pct / 100)
    subset = master[master['price_to_lth'] <= val]
    if len(subset) > 0:
        last = subset.iloc[-1]
        print(f'  P{pct:2d}: ratio={val:.2f}, MVRV={last["mvrv"]:.2f}, Price=${last["price_usd"]:,.0f}, Date={last["date"].date()}')

print('\n=== Days where Price/LTH_RP > 3.0 ===')
high = master[master['price_to_lth'] > 3.0]
print(f'Count: {len(high)} / {len(master)} days ({len(high)/len(master)*100:.1f}%)')
if len(high) > 0:
    print(f'Date range: {high["date"].min().date()} to {high["date"].max().date()}')
    print(f'Avg MVRV: {high["mvrv"].mean():.2f}, Avg Price: ${high["price_usd"].mean():,.0f}')

print('\n=== Days where Price/LTH_RP > 4.0 ===')
high4 = master[master['price_to_lth'] > 4.0]
print(f'Count: {len(high4)} / {len(master)} days ({len(high4)/len(master)*100:.1f}%)')

print('\n=== Days where Price/LTH_RP < 1.3 (near LTH cost) ===')
low = master[master['price_to_lth'] < 1.3]
print(f'Count: {len(low)} / {len(master)} days ({len(low)/len(master)*100:.1f}%)')
if len(low) > 0:
    print(f'Date range: {low["date"].min().date()} to {low["date"].max().date()}')
    print(f'Avg MVRV: {low["mvrv"].mean():.2f}, Avg Price: ${low["price_usd"].mean():,.0f}')

# Check 3-year window specifically
three_yr = master.tail(int(3 * 365.25))
print(f'\n=== 3-Year Window: {three_yr["date"].min().date()} to {three_yr["date"].max().date()} ({len(three_yr)} days) ===')
print(f'MVRV range: {three_yr["mvrv"].min():.2f} - {three_yr["mvrv"].max():.2f}')
print(f'Price/LTH_RP range: {three_yr["price_to_lth"].min():.2f} - {three_yr["price_to_lth"].max():.2f}')
print(f'Days with Price/LTH_RP > 3.0: {(three_yr["price_to_lth"] > 3.0).sum()}')
print(f'Days with Price/LTH_RP > 4.0: {(three_yr["price_to_lth"] > 4.0).sum()}')
print(f'Days with Price/LTH_RP < 1.3: {(three_yr["price_to_lth"] < 1.3).sum()}')
