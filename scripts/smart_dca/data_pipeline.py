"""Data Pipeline — Real data fetching with CSV cache, technical indicators, master DF.

Sources:
  - Binance Spot API (BTC/USDT daily klines) — primary price data
  - CoinMetrics Community API (CapMVRVCur) — primary on-chain MVRV
  - BGeometrics API (sopr) — fallback SOPR, rate-limited
  - Derived: NUPL = 1 - 1/MVRV, SOPR proxy = Price/EMA30, MVRV proxy = Price/SMA365
"""

import os
import time
import numpy as np
import pandas as pd
import requests
from datetime import datetime, timedelta

from .config import USD_THB_RATE, CACHE_DIR, CACHE_MAX_AGE_HOURS


def _cache_path(name):
    return os.path.join(CACHE_DIR, f'{name}.csv')


def _load_cache(name):
    path = _cache_path(name)
    if os.path.exists(path):
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        if age_hours < CACHE_MAX_AGE_HOURS:
            df = pd.read_csv(path, parse_dates=['date'])
            df['date'] = df['date'].dt.date
            print(f'[CACHE] Loaded {name} from disk ({len(df)} rows, {age_hours:.1f}h old)')
            return df
        else:
            print(f'[CACHE] {name} cache expired ({age_hours:.1f}h old), re-fetching...')
    return None


def _save_cache(name, df):
    path = _cache_path(name)
    df.to_csv(path, index=False)
    print(f'[CACHE] Saved {name} to disk ({len(df)} rows)')


def fetch_binance_btc_price(days=2000):
    """Fetch REAL BTC daily close prices from Binance Spot API (klines)."""
    cached = _load_cache('binance_btc_prices')
    if cached is not None:
        return cached

    try:
        print('[DATA] Fetching REAL BTC prices from Binance API...')
        limit = 1000
        url1 = (f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT"
               f"&interval=1d&limit={limit}")
        resp1 = requests.get(url1, timeout=15)
        if resp1.status_code != 200:
            print(f'[DATA] Binance returned status {resp1.status_code}.')
            return None
        candles1 = resp1.json()
        if not candles1:
            return None

        first_time = candles1[0][0]
        url2 = (f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT"
               f"&interval=1d&limit={limit}&endTime={first_time - 1}")
        resp2 = requests.get(url2, timeout=15)
        candles2 = resp2.json() if resp2.status_code == 200 else []

        all_candles = candles2 + candles1
        records = []
        for c in all_candles:
            dt = datetime.fromtimestamp(c[0] / 1000, tz=None).date()
            close_price = float(c[4])
            records.append({'date': dt, 'price_usd': close_price})

        df = pd.DataFrame(records).drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)
        print(f'[DATA] Binance returned {len(df)} days of REAL price data.')
        print(f'        Period: {df["date"].iloc[0]} to {df["date"].iloc[-1]}')
        _save_cache('binance_btc_prices', df)
        return df
    except Exception as e:
        print(f'[DATA] Binance fetch failed: {e}.')
        return None


def fetch_coinmetrics_mvrv(start_date, end_date):
    """Fetch REAL MVRV from CoinMetrics Community API (FREE, no API key needed)."""
    cache_key = 'coinmetrics_mvrv'
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    try:
        print(f'[DATA] Fetching REAL MVRV from CoinMetrics Community API...')
        all_records = []
        current_start = start_date.strftime('%Y-%m-%dT00:00:00Z')
        end_str = end_date.strftime('%Y-%m-%dT23:59:59Z')

        while current_start < end_str:
            chunk_end_dt = (pd.to_datetime(current_start) + timedelta(days=90)).strftime('%Y-%m-%dT00:00:00Z')
            if chunk_end_dt > end_str:
                chunk_end_dt = end_str

            url = 'https://community-api.coinmetrics.io/v4/timeseries/asset-metrics'
            params = {
                'assets': 'btc',
                'metrics': 'CapMVRVCur',
                'frequency': '1d',
                'start_time': current_start,
                'end_time': chunk_end_dt,
            }
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code != 200:
                print(f'[DATA] CoinMetrics HTTP {resp.status_code}: {resp.text[:200]}')
                if not all_records:
                    return None
                break

            data = resp.json().get('data', [])
            for item in data:
                dt = pd.to_datetime(item['time']).date()
                val = float(item['CapMVRVCur'])
                if val > 0:
                    all_records.append({'date': dt, 'mvrv': val})

            print(f'[DATA]   {current_start[:10]} to {chunk_end_dt[:10]}: {len(data)} rows')
            current_start = chunk_end_dt
            time.sleep(0.2)

        if not all_records:
            return None

        df = pd.DataFrame(all_records).drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)
        print(f'[DATA] CoinMetrics MVRV: {len(df)} records ({df["date"].iloc[0]} to {df["date"].iloc[-1]})')
        print(f'        MVRV range: {df["mvrv"].min():.3f} - {df["mvrv"].max():.3f}')
        _save_cache(cache_key, df)
        return df
    except Exception as e:
        print(f'[DATA] CoinMetrics MVRV fetch failed: {e}')
        return None


def fetch_bgeometrics_metric(metric_name, token='7NqNRwWhyc'):
    """Fetch REAL on-chain metric from BGeometrics API (FALLBACK only)."""
    cache_key = f'bgeometrics_{metric_name}'
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    url = f'https://api.bgeometrics.com/v1/{metric_name}?token={token}'
    for attempt in range(3):
        try:
            if attempt > 0:
                wait = 10 * attempt
                print(f'[DATA] BGeometrics {metric_name}: retry in {wait}s (attempt {attempt+1}/3)')
                time.sleep(wait)
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            if resp.status_code == 429:
                print(f'[DATA] BGeometrics {metric_name}: HTTP 429 rate-limit (attempt {attempt+1}/3)')
                continue
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, list) or len(data) == 0:
                return None
            records = []
            for item in data:
                date_str = item.get('d')
                metric_val = item.get(metric_name)
                if date_str and metric_val is not None:
                    dt = pd.to_datetime(date_str).date()
                    records.append({'date': dt, metric_name: float(metric_val)})
            if not records:
                return None
            df = pd.DataFrame(records).drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)
            print(f'[DATA] BGeometrics {metric_name}: {len(df)} records '
                  f'({df["date"].iloc[0]} to {df["date"].iloc[-1]})')
            _save_cache(cache_key, df)
            return df
        except Exception as e:
            if attempt == 2:
                return None
    return None


def compute_technical_indicators(df):
    """Add EMA20, RSI(14), SMA365, SMA200, MACD(12,26,9), realized_price, lth_realized_price."""
    prices = df['price_usd']
    df['ema_20'] = prices.ewm(span=20, adjust=False).mean()
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0).ewm(span=14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(span=14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi_14'] = 100 - (100 / (1 + rs))
    df['rsi_14'] = df['rsi_14'].fillna(50)
    df['sma_365'] = prices.rolling(365, min_periods=1).mean()
    df['sma_200'] = prices.rolling(200, min_periods=50).mean()
    # MACD (12, 26, 9)
    ema12 = prices.ewm(span=12, adjust=False).mean()
    ema26 = prices.ewm(span=26, adjust=False).mean()
    df['macd_line'] = ema12 - ema26
    df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd_line'] - df['macd_signal']
    # Realized Price = Price / MVRV
    df['realized_price'] = df['price_usd'] / df['mvrv'].clip(lower=0.01)
    # LTH Realized Price proxy: 180-day SMA of Realized Price
    df['lth_realized_price'] = df['realized_price'].rolling(180, min_periods=60).mean()
    df['price_to_lth_rp'] = df['price_usd'] / df['lth_realized_price'].clip(lower=1)
    return df


def build_master_dataframe(years=5):
    """Main data pipeline: fetch real data (with CSV cache), merge into master DF."""

    # Step 1: BTC Price from Binance
    price_df = fetch_binance_btc_price(days=2000)
    if price_df is None or len(price_df) < 365:
        old_cache = pd.read_csv(_cache_path('binance_btc_prices'), parse_dates=['date'])
        if len(old_cache) >= 365:
            old_cache['date'] = old_cache['date'].dt.date
            price_df = old_cache
            print('[DATA] Using expired cache as fallback for prices.')
        else:
            raise RuntimeError('[DATA] Binance FAILED and no usable cache.')

    # Step 2: On-Chain Metrics
    data_start = price_df['date'].iloc[0]
    data_end = price_df['date'].iloc[-1]

    print(f'\n[DATA] === ON-CHAIN DATA PIPELINE ===')
    print(f'        Primary source: CoinMetrics Community API (CapMVRVCur)')
    print(f'        NUPL: Derived from MVRV (NUPL = 1 - 1/MVRV)')
    print(f'        SOPR: BGeometrics fallback -> Proxy (Price/EMA30)')

    mvrv_df = fetch_coinmetrics_mvrv(data_start, data_end)

    time.sleep(2)
    sopr_df = fetch_bgeometrics_metric('sopr')

    # Merge on-chain data
    onchain_df = price_df[['date']].copy()
    onchain_df['mvrv'] = np.nan
    onchain_df['nupl'] = np.nan
    onchain_df['sopr'] = np.nan
    if mvrv_df is not None:
        onchain_df = onchain_df.drop(columns=['mvrv']).merge(mvrv_df, on='date', how='left')
    if sopr_df is not None:
        onchain_df = onchain_df.drop(columns=['sopr']).merge(sopr_df, on='date', how='left')

    master = price_df.merge(onchain_df, on='date', how='left')
    master = master.sort_values('date').reset_index(drop=True)

    # Forward-fill missing on-chain (up to 2 days)
    for col in ['mvrv', 'nupl', 'sopr']:
        master[col] = master[col].ffill(limit=2)

    # Proxy fallback
    master['sma_365'] = master['price_usd'].rolling(365, min_periods=1).mean()
    master['mvrv_proxy'] = master['price_usd'] / master['sma_365']
    master['mvrv'] = master['mvrv'].fillna(master['mvrv_proxy'])

    # NUPL derived from MVRV
    master['nupl_real'] = 1.0 - (1.0 / master['mvrv'])
    nupl_proxy = (master['price_usd'] - master['sma_365']) / master['price_usd']
    master['nupl'] = master['nupl'].fillna(master['nupl_real'])
    master['nupl'] = master['nupl'].fillna(nupl_proxy)
    master.drop(columns=['nupl_real'], inplace=True)

    # SOPR proxy: Price/EMA30
    ema30 = master['price_usd'].ewm(span=30, adjust=False).mean()
    sopr_proxy = master['price_usd'] / ema30
    master['sopr'] = master['sopr'].fillna(sopr_proxy)

    # Report data coverage
    real_mvrv_count = len(mvrv_df) if mvrv_df is not None else 0
    real_sopr_count = len(sopr_df) if sopr_df is not None else 0

    print(f'\n[DATA] === DATA SOURCE SUMMARY ===')
    print(f'        Price:  Binance REAL ({len(master)} days)')
    print(f'        MVRV:   CoinMetrics REAL ({real_mvrv_count}d) + Proxy ({max(0, len(master)-real_mvrv_count)}d)')
    print(f'        NUPL:   Derived from MVRV ({real_mvrv_count}d) + Proxy ({max(0, len(master)-real_mvrv_count)}d)')
    print(f'        SOPR:   BGeometrics REAL ({real_sopr_count}d) + Proxy ({max(0, len(master)-real_sopr_count)}d)')
    print(f'        Cache dir: {CACHE_DIR}/')
    print(f'        Cache TTL : {CACHE_MAX_AGE_HOURS}h (7 days)')
    print(f'        To force re-fetch: rm {CACHE_DIR}/*.csv')

    if real_mvrv_count > 0 and mvrv_df is not None:
        print(f'\n        [OK] REAL MVRV range: {mvrv_df["mvrv"].min():.3f} - {mvrv_df["mvrv"].max():.3f}')
        print(f'             Days with MVRV > 2.5: {(mvrv_df["mvrv"] > 2.5).sum()}')
        print(f'             Days with MVRV > 3.0: {(mvrv_df["mvrv"] > 3.0).sum()}')
    else:
        print(f'\n  [!] WARNING: MVRV uses PROXY (CoinMetrics failed).')

    if real_sopr_count == 0:
        print(f'        [i] SOPR uses Proxy (Price/EMA30) — BGeometrics rate-limited.')

    # Technical indicators
    master = compute_technical_indicators(master)
    master['price_thb'] = master['price_usd'] * USD_THB_RATE

    print(f'\n[DATA] Master DataFrame: {len(master)} rows, {master["date"].min()} to {master["date"].max()}')
    return master
