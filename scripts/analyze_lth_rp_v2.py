#!/usr/bin/env python3
"""Analyze LTH RP proxy v2 - SMA-smoothed realized price."""
import pandas as pd
import numpy as np

df = pd.read_csv('/home/z/my-project/cache/binance_btc_prices.csv', parse_dates=['date'])
mvrv = pd.read_csv('/home/z/my-project/cache/coinmetrics_mvrv.csv', parse_dates=['date'])
master = df.merge(mvrv, on='date', how='inner').sort_values('date').reset_index(drop=True)
master = master.dropna(subset=['mvrv'])

master['realized_price'] = master['price_usd'] / master['mvrv']

# Method 1: k=0.65 constant (Price/LTH_RP = MVRV/0.65)
master['lth_k65'] = master['realized_price'] * 0.65
master['ratio_k65'] = master['price_usd'] / master['lth_k65']

# Method 2: 180-day SMA of realized price (sticky LTH cost basis)
master['lth_sma180'] = master['realized_price'].rolling(180, min_periods=60).mean()
master['ratio_sma180'] = master['price_usd'] / master['lth_sma180']

# Method 3: 90-day EMA of realized price
master['lth_ema90'] = master['realized_price'].ewm(span=90, min_periods=30, adjust=False).mean()
master['ratio_ema90'] = master['price_usd'] / master['lth_ema90']

print('=== Comparing LTH RP Proxies ===')
print(f'\nMethod 1 (k=0.65 constant): ratio = MVRV / 0.65')
print(f'  Mean: {master["ratio_k65"].mean():.2f}, Range: {master["ratio_k65"].min():.2f} - {master["ratio_k65"].max():.2f}')
print(f'  P5: {master["ratio_k65"].quantile(0.05):.2f}, P95: {master["ratio_k65"].quantile(0.95):.2f}')

print(f'\nMethod 2 (180d SMA of RP): ratio = Price / SMA180(RP)')
print(f'  Mean: {master["ratio_sma180"].mean():.2f}, Range: {master["ratio_sma180"].min():.2f} - {master["ratio_sma180"].max():.2f}')
print(f'  P5: {master["ratio_sma180"].quantile(0.05):.2f}, P95: {master["ratio_sma180"].quantile(0.95):.2f}')

print(f'\nMethod 3 (90d EMA of RP): ratio = Price / EMA90(RP)')
print(f'  Mean: {master["ratio_ema90"].mean():.2f}, Range: {master["ratio_ema90"].min():.2f} - {master["ratio_ema90"].max():.2f}')
print(f'  P5: {master["ratio_ema90"].quantile(0.05):.2f}, P95: {master["ratio_ema90"].quantile(0.95):.2f}')

# Check correlation between methods
print(f'\n=== Correlation Matrix ===')
print(master[['mvrv', 'ratio_k65', 'ratio_sma180', 'ratio_ema90']].corr().round(3))

# The key test: does ratio_sma180 give DIFFERENT signals than MVRV?
# i.e., are there days where one is high but the other isn't?
master_valid = master.dropna(subset=['ratio_sma180'])
high_mvrv_low_sma = master_valid[(master_valid['mvrv'] > 2.5) & (master_valid['ratio_sma180'] < 2.5)]
low_mvrv_high_sma = master_valid[(master_valid['mvrv'] < 2.0) & (master_valid['ratio_sma180'] > 3.0)]
print(f'\n=== Divergence Analysis ===')
print(f'High MVRV(>2.5) but Low SMA180 ratio(<2.5): {len(high_mvrv_low_sma)} days')
print(f'Low MVRV(<2.0) but High SMA180 ratio(>3.0): {len(low_mvrv_high_sma)} days')

# 3-year specific
three_yr = master_valid.tail(int(3 * 365.25))
print(f'\n=== 3-Year Window ({three_yr["date"].min().date()} to {three_yr["date"].max().date()}) ===')
print(f'ratio_sma180 range: {three_yr["ratio_sma180"].min():.2f} - {three_yr["ratio_sma180"].max():.2f}')
print(f'Days ratio_sma180 > 2.0: {(three_yr["ratio_sma180"] > 2.0).sum()}')
print(f'Days ratio_sma180 > 2.5: {(three_yr["ratio_sma180"] > 2.5).sum()}')
print(f'Days ratio_sma180 > 3.0: {(three_yr["ratio_sma180"] > 3.0).sum()}')
print(f'Days ratio_sma180 < 1.2: {(three_yr["ratio_sma180"] < 1.2).sum()}')
print(f'Days ratio_sma180 < 1.0: {(three_yr["ratio_sma180"] < 1.0).sum()}')

# Key test: does price drop below SMA180 realized price (strong buy signal)?
below_rp = three_yr[three_yr['ratio_sma180'] < 1.1]
print(f'\nDays Price < 1.1 * SMA180_RP (near/below LTH cost): {len(below_rp)}')
if len(below_rp) > 0:
    for _, r in below_rp.iterrows():
        print(f'  {r["date"].date()} | Price: ${r["price_usd"]:,.0f} | RP_sma180: ${r["lth_sma180"]:,.0f} | MVRV: {r["mvrv"]:.2f} | ratio: {r["ratio_sma180"]:.3f}')
