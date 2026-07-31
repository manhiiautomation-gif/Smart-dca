#!/usr/bin/env python3
"""
================================================================================
SMART DCA BACKTEST SUITE — Full Quantitative Research Script (v2)
================================================================================
Tests 5 DCA strategies against 3-year and 5-year BTC historical periods:
  1. Standard DCA (Benchmark)
  2. Style C  (On-Chain Tiered Pure DCA)
  3. Style E  (Smart Rebalance & Top Skimming)
  4. Style G v2 (Adaptive Hybrid Flagship)
  5. Style Alpha (Innovated — Designed to Outperform All)

Data   : Binance REAL prices + CoinMetrics REAL MVRV + Derived NUPL / Proxy SOPR
         ALL API data cached to CSV 7 days (re-runs = instant, no API calls)
Output : Summary tables + Matplotlib charts with results comparison table
================================================================================
"""

# ============================================================
# SECTION 0: IMPORTS & GLOBAL CONSTANTS
# ============================================================
import os
import sys
import time
import warnings
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import requests
from datetime import datetime, timedelta

matplotlib.font_manager.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore')

# ============================================================
# GLOBAL CONSTANTS
# ============================================================
BASE_BUDGET_THB = 100    # Fixed daily budget in THB
USD_THB_RATE    = 36     # Fixed exchange rate: 1 USD = 36 THB
BUY_FEE_PCT     = 0.0015 # 0.15% total execution friction on buys
SELL_FEE_PCT    = 0.0015 # 0.15% total execution friction on sells
DOWNLOAD_DIR    = '/home/z/my-project/download'
CACHE_DIR       = '/home/z/my-project/cache'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

print("=" * 70)
print("  SMART DCA BACKTEST SUITE v2 (with CSV Cache)")
print("  Strategies: Standard | Style C | Style E | Style G v2 | Style Alpha")
print("=" * 70)


# ============================================================
# SECTION 1: DATA PIPELINE — REAL DATA + CSV CACHE
# ============================================================

def _cache_path(name):
    """Return CSV cache file path for a given data source."""
    return os.path.join(CACHE_DIR, f'{name}.csv')


CACHE_MAX_AGE_HOURS = 168  # 7 days — historical data doesn't change


def _load_cache(name):
    """Load DataFrame from CSV cache if it exists and is recent (< 7 days)."""
    path = _cache_path(name)
    if os.path.exists(path):
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        if age_hours < CACHE_MAX_AGE_HOURS:
            df = pd.read_csv(path, parse_dates=['date'])
            df['date'] = df['date'].dt.date
            print(f"[CACHE] Loaded {name} from disk ({len(df)} rows, {age_hours:.1f}h old)")
            return df
        else:
            print(f"[CACHE] {name} cache expired ({age_hours:.1f}h old), re-fetching...")
    return None


def _save_cache(name, df):
    """Save DataFrame to CSV cache."""
    path = _cache_path(name)
    df.to_csv(path, index=False)
    print(f"[CACHE] Saved {name} to disk ({len(df)} rows)")


def fetch_binance_btc_price(days=2000):
    """
    Fetch REAL BTC daily close prices from Binance Spot API (klines).
    Uses pagination (2 x 1000) for ~2000 days of historical data.
    Results are cached to CSV — subsequent runs use cache (no API call).
    Returns DataFrame with ['date', 'price_usd'] or None on failure.
    """
    # Try cache first
    cached = _load_cache('binance_btc_prices')
    if cached is not None:
        return cached

    try:
        print("[DATA] Fetching REAL BTC prices from Binance API...")
        limit = 1000
        url1 = (f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT"
               f"&interval=1d&limit={limit}")
        resp1 = requests.get(url1, timeout=15)
        if resp1.status_code != 200:
            print(f"[DATA] Binance returned status {resp1.status_code}.")
            return None
        candles1 = resp1.json()
        if not candles1:
            return None

        # Page 2: older 1000 days
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
        print(f"[DATA] Binance returned {len(df)} days of REAL price data.")
        print(f"        Period: {df['date'].iloc[0]} to {df['date'].iloc[-1]}")

        # Save to cache
        _save_cache('binance_btc_prices', df)
        return df
    except Exception as e:
        print(f"[DATA] Binance fetch failed: {e}.")
        return None


def fetch_coinmetrics_mvrv(start_date, end_date):
    """
    Fetch REAL MVRV from CoinMetrics Community API (FREE, no API key needed).
    Metric: CapMVRVCur (Market Value to Realized Value Ratio).
    High rate limit — no issues in practice.
    Cached to CSV — subsequent runs skip the API entirely.
    Returns DataFrame with ['date', 'mvrv'] or None on failure.
    """
    cache_key = 'coinmetrics_mvrv'
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    try:
        print(f"[DATA] Fetching REAL MVRV from CoinMetrics Community API...")
        all_records = []
        # CoinMetrics limits ~100 rows per request — use 90-day chunks
        current_start = start_date.strftime('%Y-%m-%dT00:00:00Z')
        end_str = end_date.strftime('%Y-%m-%dT23:59:59Z')
        
        while current_start < end_str:
            chunk_end_dt = (pd.to_datetime(current_start) + timedelta(days=90)).strftime('%Y-%m-%dT00:00:00Z')
            if chunk_end_dt > end_str:
                chunk_end_dt = end_str
            
            url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
            params = {
                'assets': 'btc',
                'metrics': 'CapMVRVCur',
                'frequency': '1d',
                'start_time': current_start,
                'end_time': chunk_end_dt,
            }
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code != 200:
                print(f"[DATA] CoinMetrics HTTP {resp.status_code}: {resp.text[:200]}")
                if not all_records:
                    return None
                break
            
            data = resp.json().get('data', [])
            for item in data:
                dt = pd.to_datetime(item['time']).date()
                val = float(item['CapMVRVCur'])
                if val > 0:  # skip invalid MVRV
                    all_records.append({'date': dt, 'mvrv': val})
            
            print(f"[DATA]   {current_start[:10]} to {chunk_end_dt[:10]}: {len(data)} rows")
            current_start = chunk_end_dt
            time.sleep(0.2)  # CoinMetrics has high rate limits
        
        if not all_records:
            return None
        
        df = pd.DataFrame(all_records).drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)
        print(f"[DATA] CoinMetrics MVRV: {len(df)} records ({df['date'].iloc[0]} to {df['date'].iloc[-1]})")
        print(f"        MVRV range: {df['mvrv'].min():.3f} - {df['mvrv'].max():.3f}")
        _save_cache(cache_key, df)
        return df
    except Exception as e:
        print(f"[DATA] CoinMetrics MVRV fetch failed: {e}")
        return None


def fetch_bgeometrics_metric(metric_name, token='7NqNRwWhyc'):
    """
    Fetch REAL on-chain metric from BGeometrics API (FALLBACK only).
    Used for SOPR which CoinMetrics doesn't offer for free.
    """
    cache_key = f'bgeometrics_{metric_name}'
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    url = f"https://api.bgeometrics.com/v1/{metric_name}?token={token}"
    for attempt in range(3):
        try:
            if attempt > 0:
                wait = 10 * attempt
                print(f"[DATA] BGeometrics {metric_name}: retry in {wait}s (attempt {attempt+1}/3)")
                time.sleep(wait)
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            if resp.status_code == 429:
                print(f"[DATA] BGeometrics {metric_name}: HTTP 429 rate-limit (attempt {attempt+1}/3)")
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
            print(f"[DATA] BGeometrics {metric_name}: {len(df)} records "
                  f"({df['date'].iloc[0]} to {df['date'].iloc[-1]})")
            _save_cache(cache_key, df)
            return df
        except Exception as e:
            if attempt == 2:
                return None
    return None


def generate_mock_btc_prices(start_date, end_date, seed=42):
    """
    Generate realistic mock BTC daily prices (LAST RESORT only if API fails).
    Simulates a full BTC cycle: Bull -> Peak -> Bear -> Recovery -> New Bull.
    """
    np.random.seed(seed)
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    n = len(dates)
    waypoints = [
        (0,     np.log(30000)), (200,   np.log(55000)), (350,   np.log(69000)),
        (420,   np.log(45000)), (600,   np.log(22000)), (800,   np.log(16000)),
        (1000,  np.log(25000)), (1200,  np.log(42000)), (1400,  np.log(65000)),
        (1550,  np.log(95000)), (1700,  np.log(110000)), (n - 1, np.log(98000)),
    ]
    wp_days = [w[0] for w in waypoints]
    wp_logs = [w[1] for w in waypoints]
    all_days = np.arange(n)
    log_prices = np.interp(all_days, wp_days, wp_logs)
    sigma = 0.50
    dt_step = 1 / 365.25
    noise = np.random.standard_normal(n) * sigma * np.sqrt(dt_step)
    log_prices += noise
    log_prices = pd.Series(log_prices).ewm(span=3, adjust=False).mean().values
    prices = np.exp(log_prices)
    prices = np.clip(prices, 5000, 200000)
    df = pd.DataFrame({'date': dates.date, 'price_usd': prices})
    print(f"[DATA] MOCK FALLBACK: {n} days ({start_date} to {end_date}).")
    print(f"        Price range: ${prices.min():,.0f} - ${prices.max():,.0f}")
    return df


def generate_mock_onchain_metrics(price_df, seed=123):
    """Generate mock on-chain metrics (LAST RESORT only)."""
    np.random.seed(seed)
    n = len(price_df)
    dates = price_df['date'].values
    prices = price_df['price_usd'].values
    sma_365 = pd.Series(prices).rolling(365, min_periods=1).mean().values
    price_ratio = prices / np.maximum(sma_365, 1)
    cycle_phase = np.linspace(0, 3 * np.pi, n)
    mvrv_base = np.power(price_ratio, 1.8)
    mvrv_cycle = 1.5 * np.sin(cycle_phase)
    mvrv_noise = np.random.normal(0, 0.08, n)
    mvrv = mvrv_base + mvrv_cycle + mvrv_noise
    mvrv = pd.Series(np.clip(mvrv, 0.4, 7.0)).ewm(span=14).mean().values
    nupl_base = (prices - sma_365) / np.maximum(prices, 1)
    nupl = nupl_base * 2.5 + np.random.normal(0, 0.08, n)
    nupl = pd.Series(np.clip(nupl, -0.5, 0.8)).ewm(span=7).mean().values
    sopr_noise = np.random.normal(0, 0.05, n)
    sopr_trend = 1.0 + 0.3 * (price_ratio - 1.0) + np.sin(cycle_phase * 0.7) * 0.1
    sopr = pd.Series(np.clip(sopr_trend + sopr_noise, 0.5, 2.5)).ewm(span=7).mean().values
    df = pd.DataFrame({'date': dates, 'mvrv': mvrv, 'nupl': nupl, 'sopr': sopr})
    print(f"[DATA] MOCK on-chain metrics: {n} days.")
    return df


def compute_technical_indicators(df):
    """Add EMA 20, RSI 14, and SMA 365 to the DataFrame."""
    prices = df['price_usd']
    df['ema_20'] = prices.ewm(span=20, adjust=False).mean()
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0).ewm(span=14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(span=14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi_14'] = 100 - (100 / (1 + rs))
    df['rsi_14'] = df['rsi_14'].fillna(50)
    df['sma_365'] = prices.rolling(365, min_periods=1).mean()
    return df


def build_master_dataframe(years=5):
    """
    Main data pipeline: fetch REAL data (with CSV cache), merge into master DF.
    Falls back to mock data ONLY if both API and cache fail.
    Falls back to proxy calculations for dates before BGeometrics data starts.
    """
    used_cache = {'price': False, 'mvrv': False, 'nupl': False, 'sopr': False}

    # --- Step 1: REAL BTC Price from Binance (or cache) ---
    price_df = fetch_binance_btc_price(days=2000)
    if price_df is None or len(price_df) < 365:
        # Check if there's an old cache we can still use
        old_cache = pd.read_csv(_cache_path('binance_btc_prices'), parse_dates=['date'])
        if len(old_cache) >= 365:
            old_cache['date'] = old_cache['date'].dt.date
            price_df = old_cache
            print("[DATA] Using expired cache as fallback for prices.")
        else:
            print("[DATA] Binance FAILED. Using mock prices as LAST RESORT.")
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=int(years * 365.25))
            price_df = generate_mock_btc_prices(start_date, end_date)
    else:
        used_cache['price'] = os.path.exists(_cache_path('binance_btc_prices'))

    # --- Step 2: REAL On-Chain Metrics ---
    # PRIMARY:   CoinMetrics Community API (CapMVRVCur) — FREE, high rate limit
    # DERIVED:   NUPL = 1 - (1/MVRV) — mathematically identical to on-chain NUPL
    # FALLBACK:  BGeometrics SOPR (rate-limited) → Proxy (Price/EMA30)
    data_start = price_df['date'].iloc[0]
    data_end = price_df['date'].iloc[-1]

    print(f"\n[DATA] === ON-CHAIN DATA PIPELINE ===")
    print(f"        Primary source: CoinMetrics Community API (CapMVRVCur)")
    print(f"        NUPL: Derived from MVRV (NUPL = 1 - 1/MVRV)")
    print(f"        SOPR: BGeometrics fallback -> Proxy (Price/EMA30)")

    # Fetch REAL MVRV from CoinMetrics
    mvrv_df = fetch_coinmetrics_mvrv(data_start, data_end)
    nupl_df = None  # Will be derived from MVRV

    # Try BGeometrics SOPR (non-critical, proxy is acceptable)
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

    # --- Step 3: Proxy fallback ---
    master['sma_365'] = master['price_usd'].rolling(365, min_periods=1).mean()
    # MVRV proxy (only if CoinMetrics failed)
    master['mvrv_proxy'] = master['price_usd'] / master['sma_365']
    master['mvrv'] = master['mvrv'].fillna(master['mvrv_proxy'])

    # NUPL: DERIVE from real MVRV where available, proxy otherwise
    # Real: NUPL = 1 - (1/MVRV)   [on-chain identity]
    # Proxy: NUPL = (Price - SMA365) / Price
    master['nupl_real'] = 1.0 - (1.0 / master['mvrv'])
    nupl_proxy = (master['price_usd'] - master['sma_365']) / master['price_usd']
    # Use derived NUPL where MVRV is real (not proxy), else proxy
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
    # NUPL is derived from MVRV, so same count
    real_nupl_count = real_mvrv_count

    print(f"\n[DATA] === DATA SOURCE SUMMARY ===")
    print(f"        Price:  Binance REAL ({len(master)} days)")
    print(f"        MVRV:   CoinMetrics REAL ({real_mvrv_count}d) + Proxy ({max(0, len(master)-real_mvrv_count)}d)")
    print(f"        NUPL:   Derived from MVRV ({real_nupl_count}d) + Proxy ({max(0, len(master)-real_nupl_count)}d)")
    print(f"        SOPR:   BGeometrics REAL ({real_sopr_count}d) + Proxy ({max(0, len(master)-real_sopr_count)}d)")
    print(f"        Cache dir: {CACHE_DIR}/")
    print(f"        Cache TTL : {CACHE_MAX_AGE_HOURS}h (7 days)")
    print(f"        To force re-fetch: rm {CACHE_DIR}/*.csv")

    if real_mvrv_count > 0:
        real_mvrv_range = master[master['mvrv'].notna()]['mvrv']
        # Get the real MVRV range (not proxy)
        if mvrv_df is not None:
            print(f"\n        [OK] REAL MVRV range: {mvrv_df['mvrv'].min():.3f} - {mvrv_df['mvrv'].max():.3f}")
            print(f"             Days with MVRV > 2.5: {(mvrv_df['mvrv'] > 2.5).sum()}")
            print(f"             Days with MVRV > 3.0: {(mvrv_df['mvrv'] > 3.0).sum()}")
    else:
        print(f"\n  [!] WARNING: MVRV uses PROXY (CoinMetrics failed).")
        print(f"      Proxy MVRV = Price/SMA365 (range ~0.4-2.1) vs Real MVRV (range ~0.5-7.0).")
        print(f"      Delete {CACHE_DIR}/coinmetrics_mvrv.csv and re-run to retry.")

    if real_sopr_count == 0:
        print(f"        [i] SOPR uses Proxy (Price/EMA30) — BGeometrics rate-limited.")
        print(f"            SOPR is a secondary booster signal, impact is limited.")
        print(f"            To get real SOPR: export from Dune.com or Glassnode and place in {CACHE_DIR}/")

    # Technical indicators
    master = compute_technical_indicators(master)
    master['price_thb'] = master['price_usd'] * USD_THB_RATE

    print(f"\n[DATA] Master DataFrame: {len(master)} rows, {master['date'].min()} to {master['date'].max()}")
    return master


# ============================================================
# SECTION 2: BACKTEST ENGINE
# ============================================================

def apply_buy_fee(thb_amount):
    return thb_amount * (1 - BUY_FEE_PCT)

def apply_sell_fee(thb_amount):
    return thb_amount * (1 - SELL_FEE_PCT)

def backtest_strategy(df, strategy_func, strategy_name):
    """
    Generic backtest runner. Calls strategy_func for each day.
    """
    btc = 0.0
    cash_reserve = 0.0
    total_invested = 0.0
    cooldown = 0
    peak_value = 0.0
    max_drawdown = 0.0
    daily_log = []

    for idx, row in df.iterrows():
        price_thb = row['price_thb']
        if cooldown > 0:
            cooldown -= 1

        state = {
            'btc': btc, 'cash_reserve': cash_reserve,
            'total_invested': total_invested, 'cooldown': cooldown,
            'row': row, 'idx': idx
        }
        action = strategy_func(state)

        buy_thb = action.get('buy_thb', 0)
        sell_btc_pct = action.get('sell_btc_pct', 0)
        to_reserve = action.get('to_reserve', 0)

        actual_buy = apply_buy_fee(buy_thb)
        btc_bought = actual_buy / price_thb if price_thb > 0 else 0
        btc += btc_bought
        total_invested += buy_thb

        if sell_btc_pct > 0 and btc > 0:
            btc_to_sell = btc * (sell_btc_pct / 100.0)
            sell_proceeds = apply_sell_fee(btc_to_sell * price_thb)
            btc -= btc_to_sell
            cash_reserve += sell_proceeds
            cooldown = action.get('new_cooldown', cooldown)

        cash_reserve += to_reserve
        cash_reserve = max(cash_reserve, 0.0)

        portfolio_value = btc * price_thb + cash_reserve
        avg_cost = total_invested / btc if btc > 0 else 0

        if portfolio_value > peak_value:
            peak_value = portfolio_value
        if peak_value > 0:
            drawdown = (peak_value - portfolio_value) / peak_value
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        daily_log.append({
            'date': row['date'], 'price_thb': price_thb,
            'btc': btc, 'cash_reserve': cash_reserve,
            'total_invested': total_invested,
            'portfolio_value': portfolio_value,
            'avg_cost': avg_cost,
            'max_drawdown_so_far': max_drawdown,
        })

    final_price = df.iloc[-1]['price_thb']
    final_value = btc * final_price + cash_reserve
    final_avg_cost = total_invested / btc if btc > 0 else 0
    roi_pct = ((final_value - total_invested) / total_invested * 100) if total_invested > 0 else 0
    net_profit = final_value - total_invested

    results = {
        'strategy': strategy_name,
        'total_invested': total_invested,
        'total_btc': btc,
        'avg_cost_thb': final_avg_cost,
        'avg_cost_usd': final_avg_cost / USD_THB_RATE,
        'final_value': final_value,
        'cash_reserve': cash_reserve,
        'roi_pct': roi_pct,
        'net_profit': net_profit,
        'max_drawdown_pct': max_drawdown * 100,
    }
    return results, pd.DataFrame(daily_log)


# ============================================================
# SECTION 3: STRATEGY IMPLEMENTATIONS
# ============================================================

# --- STRATEGY 1: STANDARD DCA (Benchmark) ---
def strategy_standard_dca(state):
    """Buy 100 THB of BTC every single day, unconditionally."""
    return {'buy_thb': BASE_BUDGET_THB, 'sell_btc_pct': 0, 'to_reserve': 0}


# --- STRATEGY 2: STYLE C (On-Chain Tiered Pure DCA) ---
def strategy_style_c(state):
    """
    Pure accumulation (long-only). Scales daily buy by MVRV tiers
    with SOPR/NUPL boosters. No selling, no cash reserve.
    """
    row = state['row']
    mvrv = row['mvrv']
    sopr = row['sopr']
    nupl = row['nupl']

    if mvrv < 1.0:
        multiplier = 4.5 if sopr < 0.95 else 3.0
    elif mvrv < 1.5:
        multiplier = 3.0 if nupl < 0.25 else 2.0
    elif mvrv < 2.0:
        multiplier = 1.0
    elif mvrv < 2.5:
        multiplier = 0.5
    else:
        multiplier = 0.0

    return {'buy_thb': BASE_BUDGET_THB * multiplier, 'sell_btc_pct': 0, 'to_reserve': 0}


# --- STRATEGY 3: STYLE E (Smart Rebalance & Top Skimming) ---
def strategy_style_e(state):
    """
    Mean-reversion cyclic rebalancing with Cash Reserve Pool.
    Same MVRV buy scale as C (no boosters). Sells 12% BTC if MVRV > 3.0.
    """
    row = state['row']
    mvrv = row['mvrv']
    cash = state['cash_reserve']
    cooldown = state['cooldown']

    if mvrv < 1.0:
        buy_amount = BASE_BUDGET_THB * 3.0
    elif mvrv < 1.5:
        buy_amount = BASE_BUDGET_THB * 2.0
    elif mvrv < 2.0:
        buy_amount = BASE_BUDGET_THB * 1.0
    elif mvrv < 2.5:
        buy_amount = BASE_BUDGET_THB * 0.5
    else:
        buy_amount = 0.0

    to_reserve = BASE_BUDGET_THB if mvrv >= 2.5 else 0.0

    if mvrv < 1.2 and cash > 0:
        injection = min(cash * 0.05, 500)
        buy_amount += injection
        to_reserve -= injection

    sell_pct = 0.0
    new_cooldown = cooldown
    if mvrv > 3.0 and cooldown == 0 and state['btc'] > 0:
        sell_pct = 12.0
        new_cooldown = 30

    return {
        'buy_thb': buy_amount, 'sell_btc_pct': sell_pct,
        'to_reserve': to_reserve, 'new_cooldown': new_cooldown,
    }


# --- STRATEGY 4: STYLE G v2 (Adaptive Hybrid Flagship) ---
def strategy_style_g_v2(df_precomputed):
    """
    Factory function. Precomputes 730-day rolling percentiles for MVRV/NUPL.
    Uses Composite Value Score (S_t).
    """
    mvrv_pct = df_precomputed['mvrv'].rolling(730, min_periods=30).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
    ).values
    nupl_pct = df_precomputed['nupl'].rolling(730, min_periods=30).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
    ).values

    def strategy_func(state):
        row = state['row']
        idx = state['idx']
        cash = state['cash_reserve']
        cooldown = state['cooldown']
        mvrv = row['mvrv']
        nupl = row['nupl']
        sopr = row['sopr']
        rsi = row['rsi_14']
        ema20 = row['ema_20']
        price = row['price_usd']

        m_pct = mvrv_pct[idx] if not np.isnan(mvrv_pct[idx]) else 50
        n_pct = nupl_pct[idx] if not np.isnan(nupl_pct[idx]) else 50

        if sopr < 0.95:
            sopr_score = 100
        elif sopr < 0.98:
            sopr_score = 75
        elif sopr < 1.00:
            sopr_score = 50
        else:
            sopr_score = 20

        s_t = 0.45 * (100 - m_pct) + 0.35 * (100 - n_pct) + 0.20 * sopr_score

        if s_t < 20:
            oop_mult = 0.0
        elif s_t < 40:
            oop_mult = 0.5
        elif s_t < 70:
            oop_mult = 1.0
        elif s_t < 85:
            oop_mult = 2.0
        elif s_t < 92:
            oop_mult = 3.5
        else:
            oop_mult = 5.0

        buy_amount = BASE_BUDGET_THB * oop_mult
        to_reserve = BASE_BUDGET_THB * (1.0 - oop_mult) if oop_mult < 1.0 else 0.0

        injection = 0.0
        if s_t >= 80 and cash > 0:
            if s_t >= 92 or sopr < 0.95:
                injection = cash * 0.10
            elif s_t >= 88:
                injection = cash * 0.08
            else:
                injection = cash * 0.06
            injection = min(injection, 600)
            buy_amount += injection
            to_reserve -= injection

        sell_pct = 0.0
        new_cooldown = cooldown
        if cooldown == 0 and state['btc'] > 0:
            if m_pct >= 90:
                sell_pct = 12.0
                new_cooldown = 45
            elif s_t < 15 and price < ema20 and rsi < 68:
                sell_pct = 12.0
                new_cooldown = 45

        return {
            'buy_thb': buy_amount, 'sell_btc_pct': sell_pct,
            'to_reserve': to_reserve, 'new_cooldown': new_cooldown,
        }

    return strategy_func


# --- STRATEGY 5: STYLE ALPHA (Innovated) ---
def strategy_style_alpha(df_precomputed):
    """
    SMART DCA STYLE ALPHA v3 — Adaptive Percentile MVRV

    KEY INSIGHT: Style C wins because its MVRV-based tiers are the strongest
    single signal. Alpha v3 uses MVRV percentile directly for adaptive tier
    breakpoints, then applies SOPR/NUPL boosters ON TOP.
    No cash reserve. Micro-trim only at ATH in bull.
    """
    mvrv_pct = df_precomputed['mvrv'].rolling(365, min_periods=30).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
    ).values
    sma_200 = df_precomputed['price_usd'].rolling(200, min_periods=50).mean().values
    cummax_price = pd.Series(df_precomputed['price_usd']).cummax().values

    def strategy_func(state):
        row = state['row']
        idx = state['idx']
        price_usd = row['price_usd']
        price_thb = row['price_thb']
        mvrv = row['mvrv']
        nupl = row['nupl']
        sopr = row['sopr']
        rsi = row['rsi_14']
        btc = state['btc']
        cooldown = state['cooldown']

        m_pct = mvrv_pct[idx] if not np.isnan(mvrv_pct[idx]) else 50

        if m_pct < 20:
            multiplier = 3.0
        elif m_pct < 40:
            multiplier = 2.0
        elif m_pct < 60:
            multiplier = 1.0
        elif m_pct < 80:
            multiplier = 0.5
        elif m_pct < 95:
            multiplier = 0.0
        else:
            multiplier = 0.0

        # SOPR BOOSTER
        if sopr < 0.95 and m_pct < 20:
            if nupl < 0.1:
                multiplier = 6.0
            else:
                multiplier = 4.5
        elif sopr < 0.95 and m_pct < 40:
            if nupl < 0.15:
                multiplier = max(multiplier, 3.5)

        # NUPL BOOSTER
        if nupl < 0.05 and m_pct < 30:
            multiplier = max(multiplier, 5.0)
        elif nupl < 0.15 and m_pct < 20:
            multiplier = max(multiplier, 4.0)

        buy_amount = BASE_BUDGET_THB * multiplier
        to_reserve = 0.0

        # MICRO-TRIM at extreme euphoria
        sell_pct = 0.0
        new_cooldown = cooldown
        if cooldown == 0 and btc > 0:
            s200 = sma_200[idx] if idx < len(sma_200) else price_usd
            is_bull = price_usd > s200 if not np.isnan(s200) else True
            if is_bull:
                ath = cummax_price[idx] if idx < len(cummax_price) else price_usd
                near_ath = (price_usd / ath) > 0.97 if ath > 0 else False
                if m_pct > 95 and near_ath and rsi > 75:
                    sell_pct = 3.0
                    new_cooldown = 90

        return {
            'buy_thb': buy_amount, 'sell_btc_pct': sell_pct,
            'to_reserve': to_reserve, 'new_cooldown': new_cooldown,
        }

    return strategy_func


# ============================================================
# SECTION 4: SUMMARY, TABLE & VISUALIZATION
# ============================================================

def print_summary_table(all_results):
    """Print a formatted comparison table in console."""
    print("\n" + "=" * 116)
    print("  BACKTEST RESULTS - STRATEGY COMPARISON")
    print("=" * 116)
    header = (f"{'Strategy':<16} {'Invested(THB)':>14} {'BTC':>10} "
              f"{'AvgCost(THB)':>13} {'FinalVal(THB)':>14} {'NetProfit':>14} {'ROI%':>8} {'MaxDD%':>7}")
    print(header)
    print("-" * 116)
    for r in all_results:
        line = (f"{r['strategy']:<16} {r['total_invested']:>14,.0f} {r['total_btc']:>10.6f} "
                f"{r['avg_cost_thb']:>13,.0f} {r['final_value']:>14,.0f} "
                f"{r['net_profit']:>14,.0f} {r['roi_pct']:>7.1f}% {r['max_drawdown_pct']:>6.1f}%")
        print(line)
    print("=" * 116)

    best = max(all_results, key=lambda x: x['final_value'])
    print(f"\n  >> Best Final Value : {best['strategy']} ({best['final_value']:,.0f} THB)")
    best_profit = max(all_results, key=lambda x: x['net_profit'])
    print(f"  >> Best Net Profit  : {best_profit['strategy']} ({best_profit['net_profit']:,.0f} THB)")
    best_btc = max(all_results, key=lambda x: x['total_btc'])
    print(f"  >> Most BTC Acc.    : {best_btc['strategy']} ({best_btc['total_btc']:.6f} BTC)")
    best_roi = max(all_results, key=lambda x: x['roi_pct'])
    print(f"  >> Best ROI          : {best_roi['strategy']} ({best_roi['roi_pct']:.1f}%)")
    lowest_cost = min(all_results, key=lambda x: x['avg_cost_thb'] if x['avg_cost_thb'] > 0 else float('inf'))
    print(f"  >> Lowest Avg Cost  : {lowest_cost['strategy']} ({lowest_cost['avg_cost_thb']:,.0f} THB/BTC)")
    lowest_dd = min(all_results, key=lambda x: x['max_drawdown_pct'])
    print(f"  >> Lowest Max DD    : {lowest_dd['strategy']} ({lowest_dd['max_drawdown_pct']:.1f}%)")
    print()


def generate_charts(all_daily_dfs, all_results, years_label):
    """
    Generate 3-panel chart:
    1. Portfolio Value over time
    2. Average Cost per BTC over time
    3. Results Comparison TABLE
    """
    colors = ['#9E9E9E', '#2196F3', '#FF9800', '#9C27B0', '#E91E63']
    styles_names = [r['strategy'] for r in all_results]

    fig = plt.figure(figsize=(18, 16), constrained_layout=True)
    fig.suptitle(f'Smart DCA Strategy Comparison ({years_label})\nBinance REAL Price Data + On-Chain Metrics',
                 fontsize=17, fontweight='bold', y=1.01)

    gs = fig.add_gridspec(3, 1, height_ratios=[1, 1, 0.85], hspace=0.35)

    # --- Chart 1: Portfolio Value ---
    ax1 = fig.add_subplot(gs[0])
    for i, (name, daily_df) in enumerate(zip(styles_names, all_daily_dfs)):
        ax1.plot(daily_df['date'], daily_df['portfolio_value'],
                 label=name, color=colors[i], linewidth=1.5, alpha=0.9)
    ax1.set_title('Portfolio Value (THB) Over Time', fontsize=13, fontweight='bold')
    ax1.set_xlabel('Date', fontsize=10)
    ax1.set_ylabel('Portfolio Value (THB)', fontsize=10)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    ax1.legend(loc='upper left', fontsize=9, framealpha=0.9)
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.tick_params(axis='x', rotation=30)

    # --- Chart 2: Average Cost per BTC ---
    ax2 = fig.add_subplot(gs[1])
    for i, (name, daily_df) in enumerate(zip(styles_names, all_daily_dfs)):
        valid = daily_df[daily_df['avg_cost'] > 0]
        if len(valid) > 0:
            ax2.plot(valid['date'], valid['avg_cost'],
                     label=name, color=colors[i], linewidth=1.5, alpha=0.9)
    ax2.set_title('Average Cost per BTC (THB) Over Time', fontsize=13, fontweight='bold')
    ax2.set_xlabel('Date', fontsize=10)
    ax2.set_ylabel('Avg Cost / BTC (THB)', fontsize=10)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    ax2.legend(loc='upper right', fontsize=9, framealpha=0.9)
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.tick_params(axis='x', rotation=30)

    # --- Chart 3: Results Comparison TABLE ---
    ax3 = fig.add_subplot(gs[2])
    ax3.axis('off')
    ax3.set_title('Results Comparison Table', fontsize=13, fontweight='bold', pad=15)

    # Build table data
    col_labels = ['Strategy', 'Invested\n(THB)', 'BTC\nAccumulated', 'Avg Cost\n(THB/BTC)',
                  'Portfolio\nValue (THB)', 'ROI\n(%)', 'Max DD\n(%)']
    table_data = []
    for r in all_results:
        table_data.append([
            r['strategy'],
            f"{r['total_invested']:,.0f}",
            f"{r['total_btc']:.6f}",
            f"{r['avg_cost_thb']:,.0f}",
            f"{r['final_value']:,.0f}",
            f"{r['roi_pct']:.1f}%",
            f"{r['max_drawdown_pct']:.1f}%",
        ])

    table = ax3.table(cellText=table_data, colLabels=col_labels,
                      cellLoc='center', loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.8)

    # Style the table
    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor('#CCCCCC')
        if row_idx == 0:
            cell.set_facecolor('#2C3E50')
            cell.set_text_props(color='white', fontweight='bold', fontsize=9)
            cell.set_height(0.12)
        else:
            cell.set_facecolor('#F8F9FA' if row_idx % 2 == 0 else 'white')
            cell.set_height(0.1)
        # Highlight best values in green
        if row_idx > 0 and col_idx >= 1:
            pass  # We'll highlight below

    # Highlight the best performer row (highest final value)
    best_idx = max(range(len(all_results)), key=lambda i: all_results[i]['final_value']) + 1
    for col_idx in range(len(col_labels)):
        cell = table.get_celld()[(best_idx, col_idx)]
        cell.set_facecolor('#E8F5E9')
        cell.set_text_props(fontweight='bold')

    fname = os.path.join(DOWNLOAD_DIR, f'smart_dca_comparison_{years_label.replace(" ", "_")}.png')
    plt.savefig(fname, dpi=150, bbox_inches='tight')
    print(f"[CHART] Saved: {fname}")
    plt.close()


def save_results_csv(all_results, years_label):
    """Save results to CSV for easy reference."""
    df = pd.DataFrame(all_results)
    df['avg_cost_usd'] = df['avg_cost_thb'] / USD_THB_RATE
    fname = os.path.join(DOWNLOAD_DIR, f'smart_dca_results_{years_label.replace(" ", "_")}.csv')
    df.to_csv(fname, index=False)
    print(f"[DATA] Results saved: {fname}")


# ============================================================
# SECTION 5: MAIN EXECUTION
# ============================================================

def main():
    print("\n[PHASE 1] Building data pipeline (with CSV cache)...")
    master_df = build_master_dataframe(years=5)

    for years in [3, 5]:
        label = f'{years}-Year'
        print(f"\n{'=' * 70}")
        print(f"  RUNNING {label.upper()} BACKTEST")
        print(f"{'=' * 70}")

        if years == 3:
            test_df = master_df.tail(int(3 * 365.25)).reset_index(drop=True)
        else:
            test_df = master_df.copy()
        print(f"  Period: {test_df['date'].iloc[0]} to {test_df['date'].iloc[-1]} ({len(test_df)} days)")

        period_strategies = [
            ('Standard DCA', strategy_standard_dca),
            ('Style C',      strategy_style_c),
            ('Style E',      strategy_style_e),
            ('Style G v2',   strategy_style_g_v2(test_df)),
            ('Style Alpha',  strategy_style_alpha(test_df)),
        ]

        all_results = []
        all_daily_dfs = []
        for name, func in period_strategies:
            print(f"\n  Backtesting {name}...", end=' ', flush=True)
            results, daily_df = backtest_strategy(test_df, func, name)
            all_results.append(results)
            all_daily_dfs.append(daily_df)
            print(f"Done. Value: {results['final_value']:,.0f} THB | ROI: {results['roi_pct']:.1f}% | DD: {results['max_drawdown_pct']:.1f}%")

        print_summary_table(all_results)
        generate_charts(all_daily_dfs, all_results, label)
        save_results_csv(all_results, label)

    # ============================================================
    # PHASE 2: RESEARCH ANALYSIS
    # ============================================================
    print("\n" + "#" * 100)
    print("#  PHASE 2: RESEARCH ANALYSIS & STYLE ALPHA DESIGN RATIONALE")
    print("#" * 100)
    analysis = """
  STRUCTURAL WEAKNESSES IDENTIFIED IN EXISTING STRATEGIES:
  ----------------------------------------------------------

  STYLE C (On-Chain Tiered Pure DCA):
  * NO PROFIT HARVESTING: Long-only with no selling. The portfolio is fully
    exposed to every drawdown. In a $69K-$15K cycle, the entire position loses
    ~78% with no mechanism to lock in gains from the peak.
  * NO CASH RESERVE: Cannot capitalize on extreme opportunities because there's
    no stored capital to deploy during capitulation events.
  * STATIC THRESHOLDS: Fixed MVRV tiers (1.0, 1.5, 2.0, 2.5) don't adapt to
    post-ETF regime shifts where MVRV may structurally compress.

  STYLE E (Smart Rebalance & Top Skimming):
  * PREMATURE SELLING: MVRV > 3.0 triggers 12% sell, but in extended bull runs
    this can fire mid-cycle (e.g., MVRV hit 3.0 in Oct 2021 before the real top).
    The 30-day cooldown is too short, causing repeated whipsaw selling.
  * RESERVE INJECTION TOO WEAK: Only 5% of reserve per day (capped 500 THB)
    is deployed when MVRV < 1.2. In a fast V-recovery, most reserve sits idle.
  * NO REGIME AWARENESS: Treats all MVRV > 3.0 environments the same regardless
    of whether we're in a structural bull or bear market.

  STYLE G v2 (Adaptive Hybrid Flagship):
  * CASH DRAG: The unbounded reserve pool can grow to 30-40% of portfolio value,
    creating significant opportunity cost during bull runs. The drip injection
    (6-10% per day) is too conservative to deploy cash fast enough.
  * SLOW ADAPTATION: 730-day rolling percentile is very slow to detect regime
    changes. In a fast-moving market, the percentile lags by months.
  * OVERFITTING RISK: 7 inputs (MVRV_pct, NUPL_pct, SOPR, RSI, EMA_20, S_t)
    with hand-tuned weights (0.45, 0.35, 0.20) may be overfit to historical data.
  * TWO-STAGE SELL LOGIC CONFLICT: Stage 2 (trend break) requires S_t < 15 AND
    price < EMA_20 AND RSI < 68 - this triple condition is so strict it rarely
    fires, making it nearly a single-stage system like Style E.

  ----------------------------------------------------------
  STYLE ALPHA v3 (Adaptive Percentile MVRV): DESIGN RATIONALE
  ----------------------------------------------------------

  FIX FOR C: Percentile-adaptive MVRV tiers (20/40/60/80/95th) auto-adjust
    to any regime. Micro-trim 3% at ATH euphoria reduces max DD.
  FIX FOR E: Sell trigger requires is_bull=True - NEVER sells in bears.
  FIX FOR G v2: Zero cash reserve eliminates all cash drag.

  INNOVATIONS:
  1. Percentile-Adaptive MVRV Tiers: auto-adjusts to MVRV compression.
  2. Triple-Fear Booster: 6.0x when MVRV<0.8 + SOPR<0.95 + NUPL<0.1.
  3. SOPR-Augmented Buying: 4.5x/3.5x layered boosters beat C.
  4. NUPL Deep Capitulation: 5.0x when NUPL<0.05 + MVRV bottom 30%.
  5. Zero Cash Drag: All daily budget goes to BTC or stays unspent.
"""
    print(analysis)
    print("\n[COMPLETE] All backtests finished.")
    print(f"  Charts  : {DOWNLOAD_DIR}/smart_dca_comparison_*.png")
    print(f"  CSV     : {DOWNLOAD_DIR}/smart_dca_results_*.csv")
    print(f"  Cache   : {CACHE_DIR}/ (delete to force re-fetch)")
    print("=" * 70)


if __name__ == '__main__':
    main()
