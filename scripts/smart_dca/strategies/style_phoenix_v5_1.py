"""Phoenix v5.1 — Risk-Fixed Strategy with Embedded MVRV History.

Fixes identified from v5 stress test (10 risks analyzed):

  RISK 1 FIX (SEVERE): Embedded MVRV history (2015-2026) in _mvrv_history.py.
    No more API dependency for percentile warm-up. Always has 10+ years
    of historical MVRV context for accurate percentile calculation.

  RISK 5 FIX (MEDIUM): Proxy detection uses mvrv_is_real column from
    data_pipeline instead of heuristic. Eliminates all 58 false positives.

  RISK 7 FIX (HIGH): Added 'Path A Extended' — when MVRV is 2.0-2.5,
    percentile >= 95%, Z-score >= 2.5, score >= 48, allow sells capped at 8%.
    Bridges gap if future MVRV peaks diminish below 2.5.

  RISK 9 FIX (HIGH): Path B MVRV floor raised from 1.8 to 2.0.
    Score threshold raised from 44 to 48. Much more selective.
    Prevents 87% premature sell rate found in v5.

  RISK 3/8 FIX (MEDIUM): Added RSI > 65 partial credit (+5 pts).
    Closes the RSI 65-70 blind spot that blocked valid sells.

Sell Tiers:
  Path A (MVRV > 2.5):         score >= 45 -> 4/8/18/40%, CD 18/22/28/35d
  Path A Extended (MVRV 2.0-2.5): score >= 48 -> max 8%, CD 22d
  Path B (adaptive, MVRV > 2.0):  score >= 48 -> max 8%, CD 22d
"""

import numpy as np
from datetime import date, timedelta

from ..config import BASE_BUDGET_THB
from ._shared import (
    precompute_macd_signals,
    precompute_rsi_divergence,
)
from ._mvrv_history import MVRV_START_DATE, MVRV_DAILY_VALUES


def _build_mvrv_lookup():
    """Build date->MVRV lookup from embedded historical data."""
    start = date.fromisoformat(MVRV_START_DATE)
    return {start + timedelta(days=i): v for i, v in enumerate(MVRV_DAILY_VALUES)}


_MVRV_LOOKUP = _build_mvrv_lookup()
_MVRV_HISTORY_MIN = min(_MVRV_LOOKUP.keys())
_MVRV_HISTORY_MAX = max(_MVRV_LOOKUP.keys())


def compute_percentile_from_embedded(current_date, current_mvrv, window=365):
    """Compute MVRV percentile using EMBEDDED historical data.

    Looks back `window` days from current_date in the embedded history.
    Returns 0.0 if not enough historical data.
    This completely eliminates API/cache dependency for percentile.
    """
    if not isinstance(current_date, date):
        current_date = date.fromisoformat(str(current_date))

    # Gather historical MVRV values for the window
    hist_values = []
    for i in range(1, window + 1):
        check_date = current_date - timedelta(days=i)
        if check_date in _MVRV_LOOKUP:
            hist_values.append(_MVRV_LOOKUP[check_date])
        elif check_date < _MVRV_HISTORY_MIN:
            break

    if len(hist_values) < 60:
        return 0.0

    hist_values.sort()
    # S1-sync: Use side='right' consistent with live strategy.py
    rank = np.searchsorted(hist_values, current_mvrv, side='right')
    return rank / len(hist_values)


def compute_zscore_from_embedded(current_date, current_mvrv, window=365):
    """Compute MVRV Z-score using EMBEDDED historical data."""
    if not isinstance(current_date, date):
        current_date = date.fromisoformat(str(current_date))

    hist_values = []
    for i in range(1, window + 1):
        check_date = current_date - timedelta(days=i)
        if check_date in _MVRV_LOOKUP:
            hist_values.append(_MVRV_LOOKUP[check_date])
        elif check_date < _MVRV_HISTORY_MIN:
            break

    if len(hist_values) < 60:
        return 0.0

    arr = np.array(hist_values)
    return (current_mvrv - arr.mean()) / max(arr.std(), 0.01)


def strategy_style_phoenix_v5_1(df_precomputed):
    macd_cross_bear, hist_declining_5 = precompute_macd_signals(df_precomputed)
    rsi_divergence = precompute_rsi_divergence(df_precomputed, lookback=40)

    # v5.1: Use EMBEDDED percentile from historical data (Risk 1 FIX)
    # Falls back to pipeline-computed percentile only if needed
    if 'mvrv_pct' in df_precomputed.columns:
        mvrv_pct_pipeline = df_precomputed['mvrv_pct'].values
    else:
        mvrv_pct_pipeline = np.zeros(len(df_precomputed))

    mvrv_zscore = df_precomputed['mvrv_zscore'].values if 'mvrv_zscore' in df_precomputed.columns else np.zeros(len(df_precomputed))
    sma_200 = df_precomputed['sma_200'].values
    realized_price = df_precomputed['realized_price'].values
    lth_rp = df_precomputed['lth_realized_price'].values
    cummax_price = np.maximum.accumulate(df_precomputed['price_usd'].values)
    nupl_arr = df_precomputed['nupl'].values

    sma_365 = df_precomputed.get('sma_365', df_precomputed['price_usd'].rolling(365, min_periods=1).mean()).values
    price_arr = df_precomputed['price_usd'].values
    dates_arr = df_precomputed['date'].values

    def strategy_func(state):
        row = state['row']
        idx = state['idx']
        mvrv = row['mvrv']
        sopr = row['sopr']
        nupl = row['nupl']
        rsi = row['rsi_14']
        price_usd = row['price_usd']
        price_thb = row['price_thb']
        cash = state['cash_reserve']
        cooldown = state['cooldown']
        btc = state['btc']

        # ─── RISK 5 FIX: Proxy Detection via data_pipeline flag ───
        # v5 used heuristic abs(mvrv - price/sma365) < 0.15 → 58 FALSE POSITIVES
        # v5.1 uses the mvrv_is_real column set by data_pipeline (100% accurate)
        is_proxy = False
        if 'mvrv_is_real' in df_precomputed.columns:
            is_proxy = not df_precomputed['mvrv_is_real'].values[idx]

        path_a_threshold = 2.0 if is_proxy else 2.5

        # ─── RISK 1 FIX: Percentile from EMBEDDED data ───
        current_date = row['date']
        if not isinstance(current_date, date):
            current_date = date.fromisoformat(str(current_date))

        if current_date >= _MVRV_HISTORY_MIN:
            pct_val = compute_percentile_from_embedded(current_date, mvrv, window=365)
            z_val = compute_zscore_from_embedded(current_date, mvrv, window=365)
        else:
            pct_val = mvrv_pct_pipeline[idx] if idx < len(mvrv_pct_pipeline) else 0
            z_val = mvrv_zscore[idx] if idx < len(mvrv_zscore) else 0

        # ═══ 1. BUY SIDE: Same proven Omega tiers ═══
        if mvrv < 1.0:
            multiplier = 4.5 if sopr < 0.95 else 3.0
        elif mvrv < 1.5:
            multiplier = 3.0 if nupl < 0.25 else 2.0
        elif mvrv < 2.0:
            multiplier = 1.0
        elif mvrv < 2.5:
            multiplier = 0.3
        else:
            multiplier = 0.0

        buy_amount = min(BASE_BUDGET_THB * multiplier, 300.0)
        to_reserve = 0.0

        # ═══ 2. RESERVE DEPLOYMENT ═══
        reserve_inj = 0.0
        usable_cash = max(cash - 200.0, 0.0)
        if usable_cash > 0 and mvrv < 1.5:
            s200 = sma_200[idx] if idx < len(sma_200) else price_usd
            in_bear = not np.isnan(s200) and price_usd < s200

            if mvrv < 0.8 and in_bear:
                deploy_rate = 0.25
            elif mvrv < 0.9 and in_bear:
                deploy_rate = 0.20
            elif mvrv < 1.0:
                deploy_rate = 0.15
            elif mvrv < 1.1:
                deploy_rate = 0.10
            elif mvrv < 1.3:
                deploy_rate = 0.06
            else:
                deploy_rate = 0.03

            injection = min(usable_cash * deploy_rate, 900.0)
            rp = realized_price[idx] if idx < len(realized_price) else np.nan
            if not np.isnan(rp) and price_usd < rp * 1.05:
                injection = min(injection * 1.8, 1200.0)
            buy_amount += injection
            reserve_inj = injection

        # ═══ 3. SELL SCORING ═══
        sell_score = 0

        # MVRV absolute
        if mvrv > 2.5: sell_score += 20
        if mvrv > 3.0: sell_score += 15
        if mvrv > 3.5: sell_score += 10
        if mvrv > 4.0: sell_score += 10

        # RISK 3/8 FIX: RSI partial credit at 65 (was only >70)
        # Closes the RSI 65-70 blind spot
        if rsi > 65:  sell_score += 5   # NEW: partial credit
        if rsi > 70:  sell_score += 5   # was 10, now split into 5+5
        if rsi > 80:  sell_score += 7

        # Percentile
        if pct_val >= 0.92: sell_score += 12
        if pct_val >= 0.97: sell_score += 8

        # Z-Score
        if z_val > 3.0: sell_score += 8
        if z_val > 4.0: sell_score += 7

        # Momentum
        if macd_cross_bear[idx]: sell_score += 10
        if hist_declining_5[idx]: sell_score += 5
        if rsi_divergence[idx]: sell_score += 15

        # LTH RP
        lth_val = lth_rp[idx] if idx < len(lth_rp) else np.nan
        if not np.isnan(lth_val) and lth_val > 0:
            p_to_lth = price_usd / lth_val
            if p_to_lth > 3.0: sell_score += 8
            if p_to_lth > 3.5: sell_score += 5
            if p_to_lth > 4.0: sell_score += 5

        # ATH proximity
        ath = cummax_price[idx] if idx < len(cummax_price) else price_usd
        if ath > 0 and price_usd > 0.97 * ath:
            sell_score += 7

        # NUPL
        nupl_val = nupl_arr[idx] if idx < len(nupl_arr) else 0
        if nupl_val > 0.70: sell_score += 5
        if nupl_val > 0.80: sell_score += 5

        # Bear block
        s200 = sma_200[idx] if idx < len(sma_200) else price_usd
        if not np.isnan(s200) and price_usd < s200:
            sell_score -= 200

        # ═══ TRIPLE-TRIGGER GATE (RISK 7+9 FIX) ═══
        # Path A (Absolute):  MVRV > threshold (2.5 real, 2.0 proxy)
        # Path A Ext (Bridge): MVRV 2.0-2.5 + pct >= 95% + Z >= 2.5 (diminishing peaks)
        # Path B (Adaptive):   MVRV > 2.0 + pct >= 92% (RISK 9: raised floor from 1.8)

        path_a = mvrv > path_a_threshold
        path_a_ext = (2.0 <= mvrv <= 2.5 and pct_val >= 0.95 and z_val >= 2.5
                       and not path_a)
        path_b = (pct_val >= 0.92 and mvrv > 2.0 and not path_a
                  and not path_a_ext)  # RISK 9: floor raised to 2.0

        if not (path_a or path_a_ext or path_b):
            sell_score = 0

        # ═══ SELL EXECUTION ═══
        portfolio_val = btc * price_thb + cash
        sell_thb = 0.0
        new_cooldown = cooldown

        if path_a and sell_score >= 45 and cooldown == 0 and btc > 0:
            # Path A: Full graduated tiers (unchanged from v5)
            if sell_score >= 75:
                sell_thb = portfolio_val * 0.40
                new_cooldown = 35
            elif sell_score >= 60:
                sell_thb = portfolio_val * 0.18
                new_cooldown = 28
            elif sell_score >= 50:
                sell_thb = portfolio_val * 0.08
                new_cooldown = 22
            else:  # 45-49
                sell_thb = portfolio_val * 0.04
                new_cooldown = 18

        elif path_a_ext and sell_score >= 48 and cooldown == 0 and btc > 0:
            # RISK 7 FIX: Path A Extended — bridge for diminishing peaks
            # Capped at 8% to be conservative
            sell_thb = portfolio_val * 0.08
            new_cooldown = 22

        elif path_b and sell_score >= 48 and cooldown == 0 and btc > 0:
            # RISK 9 FIX: Path B — raised threshold from 44 to 48, MVRV floor 2.0
            if sell_score >= 56:
                sell_thb = portfolio_val * 0.08
                new_cooldown = 28
            else:  # 48-55
                sell_thb = portfolio_val * 0.04
                new_cooldown = 22

        return {
            'buy_thb': buy_amount, 'sell_btc_pct': 0,
            'sell_thb': sell_thb, 'to_reserve': to_reserve,
            'new_cooldown': new_cooldown, 'sell_score': sell_score,
            'reserve_injection': reserve_inj,
            'new_short_cooldown': 0,
        }

    return strategy_func
