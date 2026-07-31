"""Phoenix v4 — Adaptive Cycle-Aware Seller.

PROBLEM SOLVED: MVRV peaks diminish each cycle (7→5→4→2.8).
A fixed MVRV > 2.5 gate will FAIL in future cycles.

SOLUTION: Dual-Trigger System
  Path A (Absolute): MVRV > 2.5 + score >= 45 (proven from v3)
  Path B (Adaptive):  MVRV percentile >= 92% of 365d range + multi-confirm

Path B activates when MVRV absolute value is lower than historical peaks
but is STILL at the extreme of the CURRENT cycle's range.
This means even if cycle 5 peaks at MVRV 2.2, percentile 92% catches it.

Sell tiers: 4/15/50% (same as v3, max 50% portfolio).
Reserve deploy: Same boosted rates as v3.
No short-trend sell.
"""

import numpy as np

from ..config import BASE_BUDGET_THB
from ._shared import (
    precompute_macd_signals,
    precompute_rsi_divergence,
    precompute_mvrv_percentile,
)


def strategy_style_phoenix_v4(df_precomputed):
    macd_cross_bear, hist_declining_5 = precompute_macd_signals(df_precomputed)
    rsi_divergence = precompute_rsi_divergence(df_precomputed, lookback=40)
    mvrv_pct = precompute_mvrv_percentile(df_precomputed, window=365)
    sma_200 = df_precomputed['sma_200'].values
    realized_price = df_precomputed['realized_price'].values
    lth_rp = df_precomputed['lth_realized_price'].values
    cummax_price = np.maximum.accumulate(df_precomputed['price_usd'].values)
    nupl_arr = df_precomputed['nupl'].values

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

        # 1. BUY SIDE: Same proven Omega tiers
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

        # 2. RESERVE DEPLOYMENT — boosted (same as v3)
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

        # 3. SELL SCORING — same multi-confirm as v3
        sell_score = 0

        # MVRV absolute scoring
        if mvrv > 2.5: sell_score += 15
        if mvrv > 3.0: sell_score += 15
        if mvrv > 3.5: sell_score += 10
        if mvrv > 4.0: sell_score += 10

        # MVRV percentile adaptive scoring (Path B booster)
        pct_val = mvrv_pct[idx] if idx < len(mvrv_pct) else 0
        if pct_val >= 0.92:
            sell_score += 12   # near cycle extreme
        if pct_val >= 0.97:
            sell_score += 8    # at cycle extreme

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

        # DUAL-TRIGGER GATE
        # Path A: MVRV > 2.5 (absolute) — same as v3/Omega
        # Path B: MVRV percentile >= 92% + mvrv > 1.8 (adaptive for low-peak cycles)
        path_a = mvrv > 2.5
        path_b = (pct_val >= 0.92) and (mvrv > 1.8)
        if not (path_a or path_b):
            sell_score = 0

        # SELL EXECUTION — 4/15/50% tiers, longer cooldowns
        portfolio_val = btc * price_thb + cash
        sell_thb = 0.0
        new_cooldown = cooldown

        if sell_score >= 45 and cooldown == 0 and btc > 0:
            if sell_score >= 80:
                sell_thb = portfolio_val * 0.50
                new_cooldown = 60
            elif sell_score >= 60:
                sell_thb = portfolio_val * 0.15
                new_cooldown = 45
            else:
                sell_thb = portfolio_val * 0.04
                new_cooldown = 30

        # NO short-trend sell

        return {
            'buy_thb': buy_amount, 'sell_btc_pct': 0,
            'sell_thb': sell_thb, 'to_reserve': to_reserve,
            'new_cooldown': new_cooldown, 'sell_score': sell_score,
            'reserve_injection': reserve_inj,
            'new_short_cooldown': 0,
        }

    return strategy_func
