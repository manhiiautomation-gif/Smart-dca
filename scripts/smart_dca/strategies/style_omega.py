"""Strategy: Style Omega — Capital Cyclone (LTH-Aware Reserve Recycler).

DESIGN PHILOSOPHY: \"Style C's proven buying + Aggressive Reserve Recycling\"

KEY IMPROVEMENTS OVER BETA v3:
1. % based reserve drain (deploys 8-20% of cash/day vs 100 THB fixed)
2. Escalating deploy rate by MVRV depth (deeper fear = faster deploy)
3. Realized Price distance as buy enhancer for reserve deployment
4. LTH RP (SMA180 Realized Price) as CONFIRMATION signal on sell side
5. Shorter cooldowns (15-45 vs 30-60) -> more sell windows captured
6. Reserve floor 300 THB (always keep small buffer)

BUY SIDE: Same MVRV tiers as C + hard cap 300 THB/day base
SELL SIDE: Multi-Confirm Score (MVRV+RSI+MACD+LTH_RP+ATH) with SMA200 bear block
RESERVE:  Self-funding from sells, % based drain with MVRV-escalated rates
"""

import numpy as np
import pandas as pd

from ..config import BASE_BUDGET_THB
from ._shared import precompute_macd_signals


def strategy_style_omega(df_precomputed):
    """Factory: returns strategy_func(state)."""
    macd_cross_bear, hist_declining_5 = precompute_macd_signals(df_precomputed)
    cummax_price = pd.Series(df_precomputed['price_usd']).cummax().values
    sma_200 = df_precomputed['sma_200'].values
    realized_price = df_precomputed['realized_price'].values
    lth_rp = df_precomputed['lth_realized_price'].values

    def strategy_func(state):
        row = state['row']
        idx = state['idx']
        mvrv = row['mvrv']
        sopr = row['sopr']
        nupl = row['nupl']
        rsi = row['rsi_14']
        price_usd = row['price_usd']
        cash = state['cash_reserve']
        cooldown = state['cooldown']

        # BUY SIDE: C's proven MVRV tiers (identical)
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

        # RESERVE DEPLOYMENT (% based drain)
        reserve_inj = 0.0
        usable_cash = max(cash - 300.0, 0.0)  # Keep 300 THB floor
        if usable_cash > 0 and mvrv < 1.3:
            s200 = sma_200[idx] if idx < len(sma_200) else price_usd
            in_bear = not np.isnan(s200) and price_usd < s200

            if mvrv < 0.9 and in_bear:
                deploy_rate = 0.20
            elif mvrv < 1.0:
                deploy_rate = 0.12
            elif mvrv < 1.1:
                deploy_rate = 0.08
            else:
                deploy_rate = 0.05

            injection = min(usable_cash * deploy_rate, 600.0)

            # Realized Price floor boost
            rp = realized_price[idx] if idx < len(realized_price) else np.nan
            if not np.isnan(rp) and price_usd < rp * 1.05:
                injection = min(injection * 1.5, 800.0)

            buy_amount += injection
            reserve_inj = injection

        # MULTI-CONFIRM SELL SCORE (MVRV + RSI + MACD + LTH_RP + ATH)
        sell_score = 0

        if mvrv > 2.5: sell_score += 20
        if mvrv > 3.0: sell_score += 15
        if mvrv > 3.5: sell_score += 5
        if rsi > 70:    sell_score += 10
        if rsi > 80:    sell_score += 5
        if macd_cross_bear[idx]: sell_score += 10
        if hist_declining_5[idx]: sell_score += 5

        # LTH Realized Price (CONFIRMATION signal)
        lth_val = lth_rp[idx] if idx < len(lth_rp) else np.nan
        if not np.isnan(lth_val) and lth_val > 0:
            p_to_lth = price_usd / lth_val
            if p_to_lth > 3.0: sell_score += 10
            if p_to_lth > 3.5: sell_score += 5

        ath = cummax_price[idx] if idx < len(cummax_price) else price_usd
        if ath > 0 and price_usd > 0.97 * ath:
            sell_score += 5

        # Bear block + MVRV gate
        s200 = sma_200[idx] if idx < len(sma_200) else price_usd
        if not np.isnan(s200) and price_usd < s200:
            sell_score -= 200
        if mvrv <= 2.5:
            sell_score = 0

        # Sell tiers (THB-based, shorter cooldowns than Beta)
        sell_thb = 0.0
        new_cooldown = cooldown
        if sell_score >= 40 and cooldown == 0 and state['btc'] > 0:
            if sell_score >= 75:
                sell_thb = 18000.0
                new_cooldown = 45
            elif sell_score >= 60:
                sell_thb = 12000.0
                new_cooldown = 30
            else:
                sell_thb = 7000.0
                new_cooldown = 15

        return {
            'buy_thb': buy_amount, 'sell_btc_pct': 0,
            'sell_thb': sell_thb, 'to_reserve': to_reserve,
            'new_cooldown': new_cooldown, 'sell_score': sell_score,
            'reserve_injection': reserve_inj,
        }

    return strategy_func
