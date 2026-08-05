"""Phoenix v5 — Risk-Mitigated Adaptive Seller.

Addresses ALL 8 identified risks from v4 analysis:

  RISK 1 (Cold-Start):    Solved in data_pipeline.py — pre-warmed MVRV
                            percentile from 2015+ extended historical data.

  RISK 2 (False Trigger):  Path B sells CAPPED at 8% portfolio max.
                            Conservative sizing prevents mid-cycle damage.

  RISK 3 (50% Too Big):    Graduated 4-tier sells: 4/8/18/40% (was 4/15/50%)
                            Top tier reduced from 50% to 40%.

  RISK 4 (Path B Score):   SEPARATE score thresholds:
                            Path A (MVRV > 2.5): score >= 45 (proven)
                            Path B (adaptive):     score >= 44 (high bar)

  RISK 5 (Short-Trend):    REMOVED — caused loss-making sells at MVRV 2.0-2.5.
                            v4 proved short-trend sell is net-negative.

  RISK 6 (MVRV Proxy):    Proxy detection: if detected, lower Path A MVRV
                            gate to 1.8 since proxy underestimates.

  RISK 7 (Cooldown):       Moderate cooldowns: 18/22/28/35d
                            Balance between capturing tops and over-trading.

  RISK 8 (Low Vol):        Path B at score >= 44 with MVRV > 1.8 catches
                            low-vol cycle peaks with strong multi-confirm.

Sell Tiers (Path A — MVRV > 2.5 absolute):
  score >= 75  -> Sell 40% portfolio, cooldown 35d
  score >= 60  -> Sell 18% portfolio, cooldown 28d
  score >= 50  -> Sell  8% portfolio, cooldown 22d
  score >= 45  -> Sell  4% portfolio, cooldown 18d

Sell Tiers (Path B — adaptive, capped at 8% max):
  score >= 56  -> Sell  8% portfolio, cooldown 28d
  score >= 44  -> Sell  4% portfolio, cooldown 22d
"""

import numpy as np

from ..config import BASE_BUDGET_THB
from ._shared import (
    precompute_macd_signals,
    precompute_rsi_divergence,
)


def strategy_style_phoenix_v5(df_precomputed):
    macd_cross_bear, hist_declining_5 = precompute_macd_signals(df_precomputed)
    rsi_divergence = precompute_rsi_divergence(df_precomputed, lookback=40)

    # FIX (Risk 1): Use PRE-WARMED percentile from data pipeline
    # (computed on 2015+ MVRV data, not just backtest window)
    if 'mvrv_pct' in df_precomputed.columns:
        mvrv_pct = df_precomputed['mvrv_pct'].values
    else:
        # Fallback: compute locally (no warm-up, first 365d = 0)
        from ._shared import precompute_mvrv_percentile
        mvrv_pct = precompute_mvrv_percentile(df_precomputed, window=365)

    # MVRV Z-Score (from data pipeline, pre-warmed)
    mvrv_zscore = df_precomputed['mvrv_zscore'].values if 'mvrv_zscore' in df_precomputed.columns else np.zeros(len(df_precomputed))
    sma_200 = df_precomputed['sma_200'].values
    realized_price = df_precomputed['realized_price'].values
    lth_rp = df_precomputed['lth_realized_price'].values
    cummax_price = np.maximum.accumulate(df_precomputed['price_usd'].values)
    nupl_arr = df_precomputed['nupl'].values

    # RISK 6: Proxy detection — compute proxy inline for comparison
    sma_365 = df_precomputed.get('sma_365', df_precomputed['price_usd'].rolling(365, min_periods=1).mean()).values
    price_arr = df_precomputed['price_usd'].values

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

        # ─── RISK 6: Proxy Detection ───
        # If real MVRV is unavailable, proxy (Price/SMA365) is used.
        # Proxy systematically underestimates MVRV (correlation ~0.64).
        # Detect: if mvrv ≈ price/sma_365, it's likely proxy.
        proxy_val = price_usd / sma_365[idx] if idx < len(sma_365) and sma_365[idx] > 0 else 999
        is_proxy = abs(mvrv - proxy_val) < 0.15 if not np.isnan(proxy_val) else False

        # When using proxy, lower Path A threshold to 1.8
        # (proxy MVRV rarely exceeds 1.5, so this mostly helps Path B)
        path_a_threshold = 1.8 if is_proxy else 2.5

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

        # ═══ 2. RESERVE DEPLOYMENT — boosted (same as v3/v4) ═══
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

        # ═══ 3. SELL SCORING — same multi-confirm as v4 ═══
        sell_score = 0

        # MVRV absolute scoring
        if mvrv > 2.5: sell_score += 20
        if mvrv > 3.0: sell_score += 15
        if mvrv > 3.5: sell_score += 10
        if mvrv > 4.0: sell_score += 10

        # MVRV percentile adaptive scoring (Path B booster)
        pct_val = mvrv_pct[idx] if idx < len(mvrv_pct) else 0
        if pct_val >= 0.92:
            sell_score += 12
        if pct_val >= 0.97:
            sell_score += 8

        # NEW: MVRV Z-Score bonus (normalizes across cycles)
        # Z > 3 = statistically extreme, Z > 4 = historically rare top zone
        z_val = mvrv_zscore[idx] if idx < len(mvrv_zscore) else 0
        if z_val > 3.0:
            sell_score += 8
        if z_val > 4.0:
            sell_score += 7

        # Momentum
        if rsi > 70:    sell_score += 10
        if rsi > 80:    sell_score += 7
        if macd_cross_bear[idx]: sell_score += 10
        if hist_declining_5[idx]: sell_score += 5
        if rsi_divergence[idx]: sell_score += 15

        # LTH RP confirmation
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

        # NUPL euphoria
        nupl_val = nupl_arr[idx] if idx < len(nupl_arr) else 0
        if nupl_val > 0.70:
            sell_score += 5
        if nupl_val > 0.80:
            sell_score += 5

        # Bear block
        s200 = sma_200[idx] if idx < len(sma_200) else price_usd
        if not np.isnan(s200) and price_usd < s200:
            sell_score -= 200

        # ═══ DUAL-TRIGGER GATE (RISK 4 FIX: separate thresholds) ═══
        # Path A (Absolute): MVRV > threshold (2.5 normally, 1.8 if proxy)
        # Path B (Adaptive):  MVRV percentile >= 92% + MVRV > 1.8
        path_a = mvrv > path_a_threshold
        path_b = (pct_val >= 0.92) and (mvrv > 1.8)

        if not (path_a or path_b):
            sell_score = 0

        # ═══ SELL EXECUTION (RISK 3+7 FIX: graduated tiers, shorter CDs) ═══
        portfolio_val = btc * price_thb + cash
        sell_thb = 0.0
        new_cooldown = cooldown

        if path_a and sell_score >= 45 and cooldown == 0 and btc > 0:
            # Path A: Full sell tiers (proven absolute trigger)
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

        elif path_b and not path_a and sell_score >= 44 and cooldown == 0 and btc > 0:
            # Path B: Conservative capped tiers (RISK 2 FIX: max 8%)
            if sell_score >= 56:
                sell_thb = portfolio_val * 0.08
                new_cooldown = 28
            else:  # 44-55
                sell_thb = portfolio_val * 0.04
                new_cooldown = 22

        # ═══ NO SHORT-TREND SELL (RISK 5: removed — caused loss-making sells) ═══
        total_sell = sell_thb

        return {
            'buy_thb': buy_amount, 'sell_btc_pct': 0,
            'sell_thb': total_sell, 'to_reserve': to_reserve,
            'new_cooldown': new_cooldown, 'sell_score': sell_score,
            'reserve_injection': reserve_inj,
            'new_short_cooldown': 0,
        }

    return strategy_func
