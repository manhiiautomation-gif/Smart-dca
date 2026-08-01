"""Shared signal precomputation utilities for strategies.

Used by Beta, Omega, and Phoenix to avoid duplicating MACD signal code.
"""

import numpy as np
import pandas as pd


def precompute_macd_signals(df):
    """Return (macd_cross_bear, hist_declining_5) boolean arrays."""
    macd_line = df['macd_line'].values
    macd_signal = df['macd_signal'].values
    macd_hist = df['macd_hist'].values
    n = len(df)

    macd_cross_bear = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if (not np.isnan(macd_line[i-1]) and not np.isnan(macd_signal[i-1])
                and not np.isnan(macd_line[i]) and not np.isnan(macd_signal[i])):
            if macd_line[i-1] >= macd_signal[i-1] and macd_line[i] < macd_signal[i]:
                macd_cross_bear[i] = True

    hist_declining_5 = np.zeros(n, dtype=bool)
    for i in range(5, n):
        if all(not np.isnan(macd_hist[i-j]) for j in range(5)):
            if all(macd_hist[i-j] < macd_hist[i-j-1] for j in range(4)):
                hist_declining_5[i] = True

    return macd_cross_bear, hist_declining_5


def precompute_rsi_divergence(df, lookback=40):
    """RSI bearish divergence: price near 40d high but RSI >8pts below 40d RSI high."""
    price_arr = df['price_usd'].values
    rsi_arr = df['rsi_14'].values
    n = len(df)
    rsi_divergence = np.zeros(n, dtype=bool)

    for i in range(lookback, n):
        window_price = price_arr[i-lookback:i]
        window_rsi = rsi_arr[i-lookback:i]
        if np.isnan(window_price).any() or np.isnan(window_rsi).any():
            continue
        price_max = np.nanmax(window_price)
        rsi_max = np.nanmax(window_rsi)
        if price_max > 0 and rsi_max > 0:
            price_near_high = price_arr[i] >= price_max * 0.97
            rsi_below_high = rsi_arr[i] <= rsi_max - 8.0
            rsi_still_elevated = rsi_arr[i] >= 58
            if price_near_high and rsi_below_high and rsi_still_elevated:
                rsi_divergence[i] = True

    return rsi_divergence


def precompute_mvrv_percentile(df, window=365):
    """Rolling percentile rank of MVRV over window days.

    Returns array where 0.0 = lowest MVRV in window, 1.0 = highest.
    This adapts to diminishing MVRV peaks across cycles.
    """
    mvrv = df['mvrv'].values
    n = len(mvrv)
    pct = np.zeros(n)
    for i in range(window, n):
        w = mvrv[i - window:i]
        valid = w[~np.isnan(w)]
        if len(valid) > 10:
            pct[i] = np.searchsorted(np.sort(valid), mvrv[i]) / len(valid)
    return pct


def precompute_short_trend_sell(df, sma_200, lookback_60=60):
    """Short-term downtrend: price dropped >15% from 60d high, still above SMA200."""
    price_arr = df['price_usd'].values
    n = len(df)
    short_trend_sell = np.zeros(n, dtype=bool)

    for i in range(lookback_60, n):
        window = price_arr[i-lookback_60:i]
        if np.isnan(window).any():
            continue
        high_60d = np.nanmax(window)
        if high_60d > 0:
            drop_pct = (high_60d - price_arr[i]) / high_60d
            s200 = sma_200[i]
            if not np.isnan(s200) and drop_pct >= 0.15 and price_arr[i] > s200:
                short_trend_sell[i] = True

    return short_trend_sell
