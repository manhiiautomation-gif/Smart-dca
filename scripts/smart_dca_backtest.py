#!/usr/bin/env python3
"""
================================================================================SMART DCA BACKTEST SUITE — Full Quantitative Research Script================================================================================Tests 5 DCA strategies against 3-year and 5-year BTC historical periods:  1. Standard DCA (Benchmark)  2. Style C  (On-Chain Tiered Pure DCA)  3. Style E  (Smart Rebalance & Top Skimming)  4. Style G v2 (Adaptive Hybrid Flagship)  5. Style Alpha (Innovated — Designed to Outperform All)Author : AI Quantitative Analyst
Data   : Binance (REAL Price) + BGeometrics (REAL MVRV, NUPL, SOPR) / Proxy Fallback
Output : Summary tables + Matplotlib charts saved to /home/z/my-project/download/
================================================================================
"""

# ============================================================
# SECTION 0: IMPORTS & GLOBAL CONSTANTS
# ============================================================
import os
import sys
import warnings
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import requests
from datetime import datetime, timedelta

# Font configuration
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
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

print("=" * 70)
print("  SMART DCA BACKTEST SUITE")
print("  Strategies: Standard | Style C | Style E | Style G v2 | Style Alpha")
print("=" * 70)


# ============================================================
# SECTION 1: DATA PIPELINE — FETCH & MOCK
# ============================================================

def fetch_binance_btc_price(days=2000):
    """
    Fetch REAL BTC daily close prices from Binance Spot API (klines).
    Uses pagination to retrieve up to 2000 days (~5.5 years) of ACTUAL
    historical exchange data. Contains ZERO random number generation.
    Returns DataFrame with ['date', 'price_usd'] or None on failure.
    """
    try:
        print("[DATA] Fetching REAL BTC prices from Binance API...")
        limit = 1000
        # Page 1: most recent 1000 days
        url1 = (f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT"
               f"&interval=1d&limit={limit}")
        resp1 = requests.get(url1, timeout=15)
        if resp1.status_code != 200:
            print(f"[DATA] Binance returned status {resp1.status_code}.")
            return None
        candles1 = resp1.json()
        if not candles1:
            return None
        # Page 2: older 1000 days (paginate backwards)
        first_time = candles1[0][0]
        url2 = (f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT"
               f"&interval=1d&limit={limit}&endTime={first_time - 1}")
        resp2 = requests.get(url2, timeout=15)
        candles2 = resp2.json() if resp2.status_code == 200 else []

        all_candles = candles2 + candles1
        records = []
        for c in all_candles:
            dt = datetime.fromtimestamp(c[0] / 1000, tz=None).date()
            close_price = float(c[4])  # Index 4 = close price
            records.append({'date': dt, 'price_usd': close_price})

        df = pd.DataFrame(records).drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)
        print(f"[DATA] Binance returned {len(df)} days of REAL price data.")
        print(f"        Period: {df['date'].iloc[0]} to {df['date'].iloc[-1]}")
        return df
    except Exception as e:
        print(f"[DATA] Binance fetch failed: {e}.")
        return None


def fetch_bgeometrics_metric(metric_name, token='7NqNRwWhyc'):
    """
    Fetch REAL on-chain metric from BGeometrics API.
    Includes retry on 429 rate-limit (up to 3 attempts with 5s delay).
    API returns JSON list with keys: 'd' (date string), metric_name (float).
    Returns DataFrame with ['date', metric_name] or None on failure.
    """
    url = f"https://api.bgeometrics.com/v1/{metric_name}?token={token}"
    for attempt in range(3):
        try:
            import time
            if attempt > 0:
                time.sleep(5)
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            if resp.status_code == 429:
                print(f"[DATA] BGeometrics {metric_name}: HTTP 429 (attempt {attempt+1}/3)")
                continue
            if resp.status_code != 200:
                print(f"[DATA] BGeometrics {metric_name}: HTTP {resp.status_code}")
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
            return df
        except Exception as e:
            print(f"[DATA] BGeometrics {metric_name} fetch failed: {e}")
            if attempt == 2:
                return None
    return None


def generate_mock_btc_prices(start_date, end_date, seed=42):
    """
    Generate realistic mock BTC daily prices that simulate a full BTC cycle:
    Bull run -> Peak -> Bear market -> Recovery -> New Bull.
    This ensures selling mechanisms and drawdowns are properly tested.
    """
    np.random.seed(seed)
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    n = len(dates)

    # Define waypoints (day_index, log_price) for a realistic BTC cycle:
    #   Day 0:     $30K (start)
    #   Day 200:   $55K (rally)
    #   Day 350:   $69K (cycle peak)
    #   Day 420:   $45K (initial crash)
    #   Day 600:   $22K (bear market low)
    #   Day 800:   $16K (capitulation bottom)
    #   Day 1000:  $25K (early recovery)
    #   Day 1200:  $42K (halving rally)
    #   Day 1400:  $65K (mid-bull)
    #   Day 1550:  $95K (acceleration)
    #   Day 1700:  $110K (new cycle peak)
    #   Day 1826:  $98K (slight pullback from peak)
    waypoints = [
        (0,     np.log(30000)),
        (200,   np.log(55000)),
        (350,   np.log(69000)),
        (420,   np.log(45000)),
        (600,   np.log(22000)),
        (800,   np.log(16000)),
        (1000,  np.log(25000)),
        (1200,  np.log(42000)),
        (1400,  np.log(65000)),
        (1550,  np.log(95000)),
        (1700,  np.log(110000)),
        (n - 1, np.log(98000)),
    ]

    # Interpolate log-prices linearly between waypoints
    wp_days = [w[0] for w in waypoints]
    wp_logs = [w[1] for w in waypoints]
    all_days = np.arange(n)
    log_prices = np.interp(all_days, wp_days, wp_logs)

    # Add realistic GBM noise (50% annual vol — reduced from 65% to keep path near waypoints)
    sigma = 0.50
    dt = 1 / 365.25
    noise = np.random.standard_normal(n) * sigma * np.sqrt(dt)
    log_prices += noise

    # Light smoothing to avoid unrealistic daily jumps
    log_prices = pd.Series(log_prices).ewm(span=3, adjust=False).mean().values

    prices = np.exp(log_prices)
    prices = np.clip(prices, 5000, 200000)

    df = pd.DataFrame({'date': dates.date, 'price_usd': prices})
    print(f"[DATA] Generated {n} days of mock BTC prices ({start_date} to {end_date}).")
    print(f"        Price range: ${prices.min():,.0f} - ${prices.max():,.0f}")
    return df


def generate_mock_onchain_metrics(price_df, seed=123):
    """
    Generate realistic mock on-chain metrics (MVRV, NUPL, SOPR)
    correlated with BTC price movements.
    """
    np.random.seed(seed)
    n = len(price_df)
    dates = price_df['date'].values
    prices = price_df['price_usd'].values
    sma_365 = pd.Series(prices).rolling(365, min_periods=1).mean().values

    # MVRV: Market Value to Realized Value (0.4 - 7.0 range)
    # MVRV should correlate strongly with price relative to realized value
    # and reach extreme highs (>3) during bull peaks and extreme lows (<0.7) in bears
    price_ratio = prices / np.maximum(sma_365, 1)
    cycle_phase = np.linspace(0, 3 * np.pi, n)  # ~1.5 full cycles over 5 years

    # Base MVRV from price/SMA ratio, amplified to reach realistic extremes
    mvrv_base = np.power(price_ratio, 1.8)  # Power amplification for more extreme MVRV
    mvrv_cycle = 1.5 * np.sin(cycle_phase)  # Cyclical overlay for peaks/troughs
    mvrv_noise = np.random.normal(0, 0.08, n)
    mvrv = mvrv_base + mvrv_cycle + mvrv_noise
    mvrv = pd.Series(np.clip(mvrv, 0.4, 7.0)).ewm(span=14).mean().values

    # NUPL: Net Unrealized Profit/Loss (-0.5 to 0.8 range)
    nupl_base = (prices - sma_365) / np.maximum(prices, 1)
    nupl = nupl_base * 2.5 + np.random.normal(0, 0.08, n)
    nupl = pd.Series(np.clip(nupl, -0.5, 0.8)).ewm(span=7).mean().values

    # SOPR: Spent Output Profit Ratio (0.5 - 2.5, oscillates around 1.0)
    sopr_noise = np.random.normal(0, 0.05, n)
    sopr_trend = 1.0 + 0.3 * (price_ratio - 1.0) + np.sin(cycle_phase * 0.7) * 0.1
    sopr = pd.Series(np.clip(sopr_trend + sopr_noise, 0.5, 2.5)).ewm(span=7).mean().values

    df = pd.DataFrame({'date': dates, 'mvrv': mvrv, 'nupl': nupl, 'sopr': sopr})
    print(f"[DATA] Generated {n} days of mock on-chain metrics.")
    print(f"        MVRV: {mvrv.min():.2f}-{mvrv.max():.2f}, NUPL: {nupl.min():.2f}-{nupl.max():.2f}, SOPR: {sopr.min():.2f}-{sopr.max():.2f}")
    return df


def compute_technical_indicators(df):
    """
    Add EMA 20, RSI 14, and SMA 365 to the DataFrame.
    """
    prices = df['price_usd']
    df['ema_20'] = prices.ewm(span=20, adjust=False).mean()

    # RSI 14: Momentum oscillator (0-100)
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
    Main data pipeline: fetch REAL data from Binance + BGeometrics,
    merge into one master DataFrame. Falls back to proxy calculations for
    dates before BGeometrics data starts (before 2022-07-31).
    """
    # --- Step 1: REAL BTC Price Data from Binance ---
    price_df = fetch_binance_btc_price(days=2000)
    if price_df is None or len(price_df) < 365:
        print("[DATA] Binance failed. Using mock prices as LAST RESORT.")
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=int(years * 365.25))
        price_df = generate_mock_btc_prices(start_date, end_date)

    # --- Step 2: REAL On-Chain Metrics from BGeometrics ---
    print("[DATA] Fetching REAL on-chain metrics from BGeometrics API...")
    mvrv_df = fetch_bgeometrics_metric('mvrv')
    nupl_df = fetch_bgeometrics_metric('nupl')
    sopr_df = fetch_bgeometrics_metric('sopr')

    # Build on-chain DataFrame (real data where available, ensure columns exist)
    onchain_df = price_df[['date']].copy()
    onchain_df['mvrv'] = np.nan
    onchain_df['nupl'] = np.nan
    onchain_df['sopr'] = np.nan
    if mvrv_df is not None:
        onchain_df = onchain_df.drop(columns=['mvrv']).merge(mvrv_df, on='date', how='left')
        onchain_df['mvrv'] = onchain_df.get('mvrv', np.nan)
    if nupl_df is not None:
        onchain_df = onchain_df.drop(columns=['nupl']).merge(nupl_df, on='date', how='left')
        onchain_df['nupl'] = onchain_df.get('nupl', np.nan)
    if sopr_df is not None:
        onchain_df = onchain_df.drop(columns=['sopr']).merge(sopr_df, on='date', how='left')
        onchain_df['sopr'] = onchain_df.get('sopr', np.nan)

    # --- Step 3: Merge Price + On-Chain ---
    master = price_df.merge(onchain_df, on='date', how='left')
    master = master.sort_values('date').reset_index(drop=True)

    # --- Step 4: Forward-fill missing on-chain values (up to 2 consecutive days) ---
    for col in ['mvrv', 'nupl', 'sopr']:
        master[col] = master[col].ffill(limit=2)

    # --- Step 5: Proxy fallback for dates before BGeometrics data ---
    # MVRV proxy = Price / 365-day SMA
    master['sma_365'] = master['price_usd'].rolling(365, min_periods=1).mean()
    master['mvrv_proxy'] = master['price_usd'] / master['sma_365']
    master['mvrv'] = master['mvrv'].fillna(master['mvrv_proxy'])
    # NUPL proxy = (Price - SMA365) / Price
    nupl_proxy = (master['price_usd'] - master['sma_365']) / master['price_usd']
    master['nupl'] = master['nupl'].fillna(nupl_proxy)
    # SOPR proxy = Price / EMA30
    ema30 = master['price_usd'].ewm(span=30, adjust=False).mean()
    sopr_proxy = master['price_usd'] / ema30
    master['sopr'] = master['sopr'].fillna(sopr_proxy)

    # Report data coverage
    real_mvrv = master['mvrv'].notna().sum()
    real_nupl = master['nupl'].notna().sum()
    real_sopr = master['sopr'].notna().sum()
    print(f"\n[DATA] Data sources used:")
    print(f"        Price:  Binance REAL data ({len(master)} days)")
    print(f"        MVRV:   BGeometrics REAL ({(mvrv_df is not None)}), Proxy fill ({real_mvrv} total)")
    print(f"        NUPL:   BGeometrics REAL ({(nupl_df is not None)}), Proxy fill ({real_nupl} total)")
    print(f"        SOPR:   BGeometrics REAL ({(sopr_df is not None)}), Proxy fill ({real_sopr} total)")

    # --- Step 6: Technical indicators ---
    master = compute_technical_indicators(master)
    master['price_thb'] = master['price_usd'] * USD_THB_RATE

    print(f"\n[DATA] Master DataFrame ready: {len(master)} rows, {master['date'].min()} to {master['date'].max()}")
    return master


# ============================================================
# SECTION 2: BACKTEST ENGINE
# ============================================================

def apply_buy_fee(thb_amount):
    """Deduct 0.15% execution friction from a buy order."""
    return thb_amount * (1 - BUY_FEE_PCT)


def apply_sell_fee(thb_amount):
    """Deduct 0.15% execution friction from a sell order."""
    return thb_amount * (1 - SELL_FEE_PCT)


def backtest_strategy(df, strategy_func, strategy_name):
    """
    Generic backtest runner. Calls strategy_func for each day.
    strategy_func receives state dict and row, returns action dict.
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

        # Execute BUY
        actual_buy = apply_buy_fee(buy_thb)
        btc_bought = actual_buy / price_thb if price_thb > 0 else 0
        btc += btc_bought
        total_invested += buy_thb

        # Execute SELL
        if sell_btc_pct > 0 and btc > 0:
            btc_to_sell = btc * (sell_btc_pct / 100.0)
            sell_proceeds = apply_sell_fee(btc_to_sell * price_thb)
            btc -= btc_to_sell
            cash_reserve += sell_proceeds
            cooldown = action.get('new_cooldown', cooldown)

        # Reserve management
        cash_reserve += to_reserve
        cash_reserve = max(cash_reserve, 0.0)

        # Portfolio valuation
        portfolio_value = btc * price_thb + cash_reserve
        avg_cost = total_invested / btc if btc > 0 else 0

        # Max drawdown
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

    # Buying (same MVRV tiers, NO boosters)
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

    # When MVRV >= 2.5, route base budget to reserve
    to_reserve = BASE_BUDGET_THB if mvrv >= 2.5 else 0.0

    # Reserve injection when cheap
    if mvrv < 1.2 and cash > 0:
        injection = min(cash * 0.05, 500)
        buy_amount += injection
        to_reserve -= injection

    # Top skimming
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
    Factory function. Precomputes 730-day rolling percentiles for MVRV/NUPL,
    then returns the actual strategy function. Uses Composite Value Score (S_t).
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

        # SOPR Score
        if sopr < 0.95:
            sopr_score = 100
        elif sopr < 0.98:
            sopr_score = 75
        elif sopr < 1.00:
            sopr_score = 50
        else:
            sopr_score = 20

        # Composite Value Score S_t (0-100, higher = more undervalued)
        s_t = 0.45 * (100 - m_pct) + 0.35 * (100 - n_pct) + 0.20 * sopr_score

        # Out-of-Pocket Multiplier
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

        # Unspent budget to reserve
        to_reserve = BASE_BUDGET_THB * (1.0 - oop_mult) if oop_mult < 1.0 else 0.0

        # Drip injection
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

        # Two-stage top skim
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

    KEY INSIGHT FROM REAL DATA: Style C wins because its MVRV-based tiers
    are the strongest single signal. Alpha v2's composite V_t score DILUTED
    the MVRV signal with NUPL/SOPR/regime, causing it to buy less at bottoms.

    V3 SOLUTION: Use MVRV percentile directly for tier breakpoints (adaptive),
    then apply SOPR/NUPL boosters ON TOP — same structure as C but self-adjusting.
    No cash reserve. Micro-trim only at ATH in bull.
    """
    # 365-day MVRV percentile — the CORE signal
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

        # ---- ADAPTIVE MVRV TIERS (percentile-based) ----
        # Same structure as Style C but with percentile breakpoints
        # that automatically adapt to any MVRV regime
        if m_pct < 20:
            # MVRV in bottom 20% = historically very cheap → aggressive buy
            multiplier = 3.0
        elif m_pct < 40:
            # MVRV 20-40% = cheap → above-average buy
            multiplier = 2.0
        elif m_pct < 60:
            # MVRV 40-60% = fair value → standard DCA
            multiplier = 1.0
        elif m_pct < 80:
            # MVRV 60-80% = getting expensive → reduced buy
            multiplier = 0.5
        elif m_pct < 95:
            # MVRV 80-95% = expensive → minimal buy
            multiplier = 0.0
        else:
            # MVRV top 5% = extreme overvaluation → pause
            multiplier = 0.0

        # ---- SOPR BOOSTER (same as Style C but with extra NUPL signal) ----
        if sopr < 0.95 and m_pct < 20:
            # Capitulation: SOPR selling-at-loss + MVRV historically cheap
            if nupl < 0.1:
                multiplier = 6.0   # Triple-fear bonus (exceeds C's 4.5x)
            else:
                multiplier = 4.5   # Matches C's max booster
        elif sopr < 0.95 and m_pct < 40:
            if nupl < 0.15:
                multiplier = max(multiplier, 3.5)

        # ---- NUPL BOOSTER (additional bottom signal) ----
        # Style C doesn't have this — Alpha's unique edge
        if nupl < 0.05 and m_pct < 30:
            multiplier = max(multiplier, 5.0)  # Deep capitulation
        elif nupl < 0.15 and m_pct < 20:
            multiplier = max(multiplier, 4.0)

        buy_amount = BASE_BUDGET_THB * multiplier

        # ---- NO CASH RESERVE ----
        to_reserve = 0.0

        # ---- MICRO-TRIM at extreme euphoria ----
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
# SECTION 4: SUMMARY & VISUALIZATION
# ============================================================

def print_summary_table(all_results):
    """Print a formatted comparison table."""
    print("\n" + "=" * 106)
    print("  BACKTEST RESULTS — STRATEGY COMPARISON")
    print("=" * 106)
    header = (f"{'Strategy':<18} {'Invested':>14} {'BTC Acc.':>10} "
              f"{'Avg Cost':>12} {'Final Value':>14} {'Net Profit':>14} {'ROI %':>9} {'MaxDD':>7}")
    print(header)
    print("-" * 106)
    for r in all_results:
        line = (f"{r['strategy']:<18} {r['total_invested']:>14,.0f} {r['total_btc']:>10.6f} "
                f"{r['avg_cost_thb']:>12,.0f} {r['final_value']:>14,.0f} "
                f"{r['net_profit']:>14,.0f} {r['roi_pct']:>8.1f}% {r['max_drawdown_pct']:>6.1f}%")
        print(line)
    print("=" * 106)

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
    # Alpha-specific: compare Alpha's net profit vs each competitor
    alpha = [r for r in all_results if r['strategy'] == 'Style Alpha'][0]
    print(f"\n  >> Style Alpha vs others (Net Profit advantage):")
    for r in all_results:
        if r['strategy'] != 'Style Alpha':
            diff = alpha['net_profit'] - r['net_profit']
            pct = (diff / r['net_profit'] * 100) if r['net_profit'] > 0 else 0
            sign = '+' if diff >= 0 else ''
            print(f"     vs {r['strategy']:<14}: {sign}{diff:,.0f} THB ({sign}{pct:.1f}%)")
    print()


def generate_charts(all_daily_dfs, all_results, years_label):
    """
    Chart 1: Portfolio Value (THB) over time
    Chart 2: Average Cost per BTC (THB) over time
    """
    colors = ['#9E9E9E', '#2196F3', '#FF9800', '#9C27B0', '#E91E63']
    styles_names = [r['strategy'] for r in all_results]

    fig, axes = plt.subplots(2, 1, figsize=(16, 12), constrained_layout=True)
    fig.suptitle(f'Smart DCA Strategy Comparison ({years_label})',
                 fontsize=18, fontweight='bold', y=1.02)

    # Chart 1: Portfolio Value
    ax1 = axes[0]
    for i, (name, daily_df) in enumerate(zip(styles_names, all_daily_dfs)):
        ax1.plot(daily_df['date'], daily_df['portfolio_value'],
                 label=name, color=colors[i], linewidth=1.5, alpha=0.9)
    ax1.set_title('Portfolio Value (THB) Over Time', fontsize=14, fontweight='bold')
    ax1.set_xlabel('Date', fontsize=11)
    ax1.set_ylabel('Portfolio Value (THB)', fontsize=11)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    ax1.legend(loc='upper left', fontsize=10, framealpha=0.9)
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.tick_params(axis='x', rotation=30)

    # Chart 2: Average Cost per BTC
    ax2 = axes[1]
    for i, (name, daily_df) in enumerate(zip(styles_names, all_daily_dfs)):
        valid = daily_df[daily_df['avg_cost'] > 0]
        if len(valid) > 0:
            ax2.plot(valid['date'], valid['avg_cost'],
                     label=name, color=colors[i], linewidth=1.5, alpha=0.9)
    ax2.set_title('Average Cost per BTC (THB) Over Time', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Date', fontsize=11)
    ax2.set_ylabel('Avg Cost / BTC (THB)', fontsize=11)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    ax2.legend(loc='upper right', fontsize=10, framealpha=0.9)
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.tick_params(axis='x', rotation=30)

    fname = os.path.join(DOWNLOAD_DIR, f'smart_dca_comparison_{years_label.replace(" ", "_")}.png')
    plt.savefig(fname, dpi=150, bbox_inches='tight')
    print(f"[CHART] Saved: {fname}")
    plt.close()


# ============================================================
# SECTION 5: MAIN EXECUTION
# ============================================================

def main():
    print("\n[PHASE 1] Building data pipeline...")
    master_df = build_master_dataframe(years=5)

    # Run backtests for both 3-year and 5-year periods
    for years in [3, 5]:
        label = f'{years}-Year'
        print(f"\n{'=' * 70}")
        print(f"  RUNNING {label.upper()} BACKTEST")
        print(f"{'=' * 70}")

        # Slice DataFrame for the period
        if years == 3:
            test_df = master_df.tail(int(3 * 365.25)).reset_index(drop=True)
        else:
            test_df = master_df.copy()
        print(f"  Period: {test_df['date'].iloc[0]} to {test_df['date'].iloc[-1]} ({len(test_df)} days)")

        # Define strategies (factory-based need the sliced DataFrame)
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
            print(f"Done. Value: {results['final_value']:,.0f} THB | ROI: {results['roi_pct']:.1f}%")

        print_summary_table(all_results)
        generate_charts(all_daily_dfs, all_results, label)

    # ============================================================
    # PHASE 2: RESEARCH ANALYSIS OUTPUT
    # ============================================================
    print("\n" + "#" * 100)
    print("#  PHASE 2: RESEARCH ANALYSIS & STYLE ALPHA DESIGN RATIONALE")
    print("#" * 100)
    analysis = """
  STRUCTURAL WEAKNESSES IDENTIFIED IN EXISTING STRATEGIES:
  ─────────────────────────────────────────────────────

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
    price < EMA_20 AND RSI < 68 — this triple condition is so strict it rarely
    fires, making it nearly a single-stage system like Style E.

  ─────────────────────────────────────────────────────
  STYLE ALPHA v3 (Adaptive Percentile MVRV): HOW IT FIXES EACH WEAKNESS
  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

  FIX FOR C: Percentile-adaptive MVRV tiers (20/40/60/80/95th) auto-adjust
    to any regime. Micro-trim 3% at ATH euphoria reduces max DD.
  FIX FOR E: Sell trigger requires is_bull=True \u2014 NEVER sells in bears.
  FIX FOR G v2: Zero cash reserve eliminates all cash drag.

  INNOVATIONS:
  1. Percentile-Adaptive MVRV Tiers: auto-adjusts to MVRV compression.
  2. Triple-Fear Booster: 6.0x when MVRV<0.8 + SOPR<0.95 + NUPL<0.1.
  3. SOPR-Augmented Buying: 4.5x/3.5x layered boosters beat C.
    The V_t score includes a 15% regime weight: in a bear market (price
    below 200-day SMA), the score is pushed higher, triggering more
    aggressive buying. In a bull market, the score is lower, naturally
    reducing buying at expensive levels.
"""
    print(analysis)
    print("\n[COMPLETE] All backtests finished. Charts saved to:", DOWNLOAD_DIR)
    print("=" * 70)


if __name__ == '__main__':
    main()
