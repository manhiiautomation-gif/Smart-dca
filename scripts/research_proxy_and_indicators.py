"""Research: MVRV Proxy Improvement + New Indicator Discovery."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from smart_dca.data_pipeline import build_master_dataframe, _cache_path, _load_cache, fetch_coinmetrics_mvrv
from datetime import datetime

print('='*70)
print('  PART 1: MVRV PROXY COMPARISON')
print('='*70)

master = build_master_dataframe(years=5)
price = master['price_usd'].values
mvrv_real = master['mvrv'].values
dates = master['date'].values

# Current proxy
sma_365 = pd.Series(price).rolling(365, min_periods=1).mean().values
proxy_sma = price / sma_365

# Proxy variant 1: EMA(365)
ema_365 = pd.Series(price).ewm(span=365, adjust=False).mean().values
proxy_ema365 = price / ema_365

# Proxy variant 2: EMA(730)
ema_730 = pd.Series(price).ewm(span=730, adjust=False).mean().values
proxy_ema730 = price / ema_730

# Proxy variant 3: Weighted combo
proxy_combo = 0.5 * proxy_sma + 0.5 * proxy_ema730

# Regression calibration: fit real = a*proxy_sma + b on first 1000 days
valid = ~np.isnan(mvrv_real)
X = proxy_sma[valid][:1000]
Y = mvrv_real[valid][:1000]
mask = ~np.isnan(X) & ~np.isnan(Y)
if mask.sum() > 100:
    coeffs = np.polyfit(X[mask], Y[mask], 1)
    proxy_regress = np.polyval(coeffs, proxy_sma)
    print(f'  Regression: real_MVRV = {coeffs[0]:.4f} * proxy_SMA365 + {coeffs[1]:.4f}')
else:
    proxy_regress = proxy_sma

# Compare at MVRV > 2.5 (critical zone)
high_mvrv = mvrv_real > 2.5
print(f'\n  Correlation with REAL MVRV (all days):')
for name, proxy in [('SMA365 (current)', proxy_sma), ('EMA365', proxy_ema365),
                       ('EMA730', proxy_ema730), ('Combo', proxy_combo), ('Regression', proxy_regress)]:
    v = valid & ~np.isnan(proxy)
    corr = np.corrcoef(mvrv_real[v], proxy[v])[0,1]
    mae = np.mean(np.abs(mvrv_real[v] - proxy[v]))
    print(f'    {name:<18} corr={corr:.4f}  MAE={mae:.3f}')

print(f'\n  At MVRV > 2.5 (critical sell zone):')
for name, proxy in [('SMA365 (current)', proxy_sma), ('EMA365', proxy_ema365),
                       ('EMA730', proxy_ema730), ('Combo', proxy_combo), ('Regression', proxy_regress)]:
    zone = valid & high_mvrv & ~np.isnan(proxy)
    if zone.sum() > 0:
        corr = np.corrcoef(mvrv_real[zone], proxy[zone])[0,1]
        mean_real = np.mean(mvrv_real[zone])
        mean_proxy = np.mean(proxy[zone])
        print(f'    {name:<18} corr={corr:.4f}  real_mean={mean_real:.2f}  proxy_mean={mean_proxy:.2f}  bias={mean_proxy-mean_real:+.3f}')

# Find how well each proxy detects tops (> 2.5 threshold)
print(f'\n  Top Detection Rate (proxy > 2.5 when real > 2.5):')
for name, proxy in [('SMA365', proxy_sma), ('EMA365', proxy_ema365),
                       ('EMA730', proxy_ema730), ('Regression', proxy_regress)]:
    real_top = mvrv_real > 2.5
    proxy_top = proxy > 2.5
    tp = (real_top & proxy_top & valid).sum()
    fn = (real_top & ~proxy_top & valid).sum()  # missed tops
    fp = (~real_top & proxy_top & valid).sum()  # false tops
    recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    print(f'    {name:<18} Recall={recall:.0f}%  Precision={precision:.0f}%  (TP={tp}, FN={fn}, FP={fp})')

# Threshold analysis: what proxy value best corresponds to MVRV 2.5?
print(f'\n  Optimal Proxy Threshold for MVRV = 2.5:')
for name, proxy in [('SMA365', proxy_sma), ('EMA730', proxy_ema730), ('Regression', proxy_regress)]:
    v = valid & ~np.isnan(proxy)
    from sklearn.metrics import roc_curve, auc
    try:
        fpr, tpr, thresholds = roc_curve((mvrv_real[v] > 2.5).astype(int), proxy[v])
        # Find threshold closest to 2.5
        target_idx = np.argmin(np.abs(thresholds - 2.5))
        # Find threshold where sensitivity + specificity is max
        j_stat = tpr - fpr
        best_idx = np.argmax(j_stat)
        print(f'    {name:<18} Best threshold={thresholds[best_idx]:.4f} (AUC={auc(fpr, tpr):.3f})')
    except:
        print(f'    {name:<18} sklearn not available, skipping')


print('\n' + '='*70)
print('  PART 2: NEW INDICATOR ANALYSIS')
print('='*70)

# Indicator 1: Pi Cycle Top
sma_111 = pd.Series(price).rolling(111, min_periods=50).mean().values
sma_350 = pd.Series(price).rolling(350, min_periods=100).mean().values
pi_cycle = sma_111 * 2 / sma_350
pi_signal = price / pi_cycle  # > 1 = price above pi cycle top

print(f'\n  Pi Cycle Top Indicator (SMA111*2 / SMA350):')
print(f'    Current pi_cycle value: {pi_cycle[-1]:,.0f}')
print(f'    Current BTC price:    {price[-1]:,.0f}')
print(f'    Ratio (Price/Pi):      {pi_signal[-1]:.3f}')
print(f'    Price crossed above Pi: {np.sum(price[1000:] > pi_cycle[1000:])} days (out of {len(price)-1000})')

# Indicator 2: MVRV Z-Score (rolling 365d)
mvrv_series = pd.Series(mvrv_real)
mvrv_mean = mvrv_series.rolling(365, min_periods=100).mean().values
mvrv_std = mvrv_series.rolling(365, min_periods=100).std().values
mvrv_zscore = np.where(mvrv_std > 0, (mvrv_real - mvrv_mean) / mvrv_std, 0)

print(f'\n  MVRV Z-Score (365d rolling):')
print(f'    Current Z-Score: {mvrv_zscore[-1]:.2f}')
print(f'    Historical range: {np.nanmin(mvrv_zscore[200:]):.2f} to {np.nanmax(mvrv_zscore[200:]):.2f}')
print(f'    Days Z > 5 (danger): {(np.nan_to_num(mvrv_zscore) > 5).sum()}')
print(f'    Days Z > 7 (extreme): {(np.nan_to_num(mvrv_zscore) > 7).sum()}')

# Indicator 3: 2-Year MA Multiple (Price/SMA730)
ma_730 = pd.Series(price).rolling(730, min_periods=200).mean().values
ma_multiple = price / ma_730

print(f'\n  2-Year MA Multiple (Price / SMA730):')
print(f'    Current multiple: {ma_multiple[-1]:.2f}')
print(f'    Historical range: {np.nanmin(ma_multiple[400:]):.2f} to {np.nanmax(ma_multiple[400:]):.2f}')
print(f'    Days > 3.0: {(np.nan_to_num(ma_multiple) > 3.0).sum()}')
print(f'    Days > 3.5: {(np.nan_to_num(ma_multiple) > 3.5).sum()}')

# Indicator 4: Active Addresses momentum
if 'AdrActCnt' not in master.columns:
    print(f'\n  Active Addresses: Not in master_df, skipping')
else:
    adr = master['AdrActCnt'].values
    adr_ma = pd.Series(adr).rolling(30, min_periods=10).mean().values
    adr_momentum = (adr - adr_ma) / np.where(adr_ma > 0, adr_ma, 1) * 100
    print(f'\n  Active Addresses Momentum (vs 30d MA):')
    print(f'    Current: {adr_momentum[-1]:.1f}%')

# CoinMetrics MVRV history: how far back does it go?
print(f'\n  CoinMetrics MVRV History Check:')
print(f'    Our cache starts: {master["date"].iloc[0]}')
print(f'    Testing earlier dates...')
from smart_dca.config import CACHE_DIR
import requests, time
for year_start in ['2015', '2016', '2017', '2018', '2019']:
    url = 'https://community-api.coinmetrics.io/v4/timeseries/asset-metrics'
    params = {
        'assets': 'btc', 'metrics': 'CapMVRVCur',
        'start_time': f'{year_start}-01-01T00:00:00Z',
        'end_time': f'{year_start}-01-03T00:00:00Z',
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            if data:
                print(f'    {year_start}: OK ({len(data)} days)')
            else:
                print(f'    {year_start}: No data')
        else:
            print(f'    {year_start}: HTTP {resp.status_code}')
    except Exception as e:
        print(f'    {year_start}: Error')
    time.sleep(0.3)

print('\n' + '='*70)
print('  RESEARCH COMPLETE')
print('='*70)
