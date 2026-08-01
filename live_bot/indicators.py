"""Technical indicator calculations for live bot.

Pure numpy — no pandas dependency. All functions accept lists/arrays
and return scalars for the current (last) bar.
"""

import numpy as np


def sma(closes: list, period: int) -> float:
    """Simple Moving Average of the last `period` closes."""
    if len(closes) < period:
        return float('nan')
    return float(np.mean(closes[-period:]))


def ema(closes: list, period: int) -> float:
    """Exponential Moving Average (full EMA from start)."""
    if len(closes) < 2:
        return float(closes[-1]) if closes else float('nan')
    k = 2.0 / (period + 1)
    val = float(closes[0])
    for c in closes[1:]:
        val = c * k + val * (1 - k)
    return val


def rsi(closes: list, period: int = 14) -> float:
    """RSI using Wilder smoothing (matches backtest: ewm span=14)."""
    if len(closes) < period + 1:
        return float('nan')
    # Use last value from compute_all_rsi for consistency
    all_rsi = compute_all_rsi(closes, period)
    return all_rsi[-1] if all_rsi else float('nan')


def macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, histogram for the latest bar.

    Returns: (macd_line, signal_line, histogram)
    """
    if len(closes) < slow + signal:
        nan = float('nan')
        return nan, nan, nan
    ema_fast = _ema_array(closes, fast)
    ema_slow = _ema_array(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    sig = _ema_array(macd_line, signal)
    hist = [m - s for m, s in zip(macd_line, sig)]
    return float(macd_line[-1]), float(sig[-1]), float(hist[-1])


def _ema_array(data: list, period: int) -> list:
    """Compute full EMA series."""
    k = 2.0 / (period + 1)
    result = [float(data[0])]
    for v in data[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def macd_cross_bear(macd_hist: list) -> bool:
    """True if MACD line crossed below signal line on the latest bar."""
    if len(macd_hist) < 2:
        return False
    return macd_hist[-2] >= 0 and macd_hist[-1] < 0


def macd_hist_declining(macd_hist: list, periods: int = 4) -> bool:
    """True if MACD histogram has been declining for `periods` consecutive bars.
    
    Backtest checks 4 consecutive declines (hist[i] < hist[i-1] for i in range(4)).
    """
    if len(macd_hist) < periods + 1:
        return False
    for i in range(1, periods + 1):
        if macd_hist[-i] >= macd_hist[-i - 1]:
            return False
    return True


def rsi_divergence(closes: list, rsi_vals: list, lookback: int = 40) -> bool:
    """Bearish RSI divergence: price near lookback high but RSI 8+ pts below lookback RSI high.

    Excludes current bar from lookback window (matches backtest: price_arr[i-lookback:i]).
    """
    if len(closes) < lookback + 1 or len(rsi_vals) < lookback + 1:
        return False
    w_price = closes[-(lookback + 1):-1]  # exclude current bar
    w_rsi = rsi_vals[-(lookback + 1):-1]      # exclude current bar
    # Filter out NaN from RSI warm-up period
    valid_pairs = [(p, r) for p, r in zip(w_price, w_rsi) if not _is_nan(r)]
    if len(valid_pairs) < 10:
        return False
    w_price_v = [p for p, r in valid_pairs]
    w_rsi_v = [r for p, r in valid_pairs]
    price_max = max(w_price_v)
    rsi_max = max(w_rsi_v)
    if price_max <= 0 or rsi_max <= 0:
        return False
    price_near_high = closes[-1] >= price_max * 0.97
    rsi_below_high = rsi_vals[-1] <= rsi_max - 8.0
    rsi_still_elevated = rsi_vals[-1] >= 58
    return price_near_high and rsi_below_high and rsi_still_elevated

def _is_nan(v) -> bool:
    return v != v  # NaN is never equal to itself


def compute_all_macd_hist(closes: list, fast=12, slow=26, signal=9) -> list:
    """Compute full MACD histogram series."""
    if len(closes) < slow + signal:
        return []
    ema_f = _ema_array(closes, fast)
    ema_s = _ema_array(closes, slow)
    ml = [f - s for f, s in zip(ema_f, ema_s)]
    sig = _ema_array(ml, signal)
    return [m - s for m, s in zip(ml, sig)]


def compute_all_rsi(closes: list, period: int = 14) -> list:
    """Compute RSI for every bar using Wilder EMA (matches backtest ewm).
    
    Uses exponential moving average with alpha = 1/period,
    equivalent to pandas ewm(span=period, adjust=False).
    """
    if len(closes) < period + 1:
        return []
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    
    # Initial averages (simple mean of first `period` values)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    
    alpha = 1.0 / period
    result = [float('nan')] * period
    
    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100.0 - 100.0 / (1.0 + rs))
    
    # Wilder smoothing for remaining bars
    for i in range(period, len(gains)):
        avg_gain = (1 - alpha) * avg_gain + alpha * gains[i]
        avg_loss = (1 - alpha) * avg_loss + alpha * losses[i]
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100.0 - 100.0 / (1.0 + rs))
    
    return result
