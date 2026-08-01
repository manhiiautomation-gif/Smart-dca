"""Strategy: Style Beta v3 — Multi-Confirm Sell DCA.

C's proven MVRV buy tiers (identical) + RSI/MACD/MVRV
multi-signal sell scoring. Cash reserve funded ONLY by sell proceeds.
Reserve deploys at 100 THB/day when MVRV < 1.2.

REVIEW SCORE: 9.0/10 (High Confidence) — 3-round evaluation passed.

BUY SIDE: Identical to Style C (MVRV absolute tiers + SOPR/NUPL boosters)
SELL SIDE: Multi-Confirm Score (MVRV+RSI+MACD+ATH) with SMA200 bear block
RESERVE:  Self-funding from sells only, deploy 100 THB/day max
"""

import numpy as np
import pandas as pd

from ..config import BASE_BUDGET_THB
from ._shared import precompute_macd_signals


def strategy_style_beta(df_precomputed):
    """Factory: returns strategy_func(state)."""
    macd_cross_bear, hist_declining_5 = precompute_macd_signals(df_precomputed)
    cummax_price = pd.Series(df_precomputed['price_usd']).cummax().values
    sma_200 = df_precomputed['sma_200'].values

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

        # BUY SIDE: Identical to Style C
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

        # RESERVE DEPLOYMENT (from sell proceeds only)
        reserve_inj = 0.0
        if mvrv < 1.2 and cash > 0:
            reserve_inj = min(100.0, cash)
            buy_amount += reserve_inj

        # MULTI-CONFIRM SELL SCORE
        sell_score = 0

        if mvrv > 2.5: sell_score += 25
        if mvrv > 3.0: sell_score += 15
        if mvrv > 3.5: sell_score += 10

        if rsi > 70: sell_score += 15
        if rsi > 80: sell_score += 10

        if macd_cross_bear[idx]: sell_score += 15
        if hist_declining_5[idx]: sell_score += 10

        ath = cummax_price[idx] if idx < len(cummax_price) else price_usd
        if ath > 0 and price_usd > 0.95 * ath:
            sell_score += 10

        s200 = sma_200[idx] if idx < len(sma_200) else price_usd
        if not np.isnan(s200) and price_usd < s200:
            sell_score -= 200

        if mvrv <= 2.5:
            sell_score = 0

        sell_thb = 0.0
        new_cooldown = cooldown
        if sell_score >= 50 and cooldown == 0 and state['btc'] > 0:
            if sell_score >= 85:
                sell_thb = 15000.0
                new_cooldown = 60
            elif sell_score >= 70:
                sell_thb = 10000.0
                new_cooldown = 45
            else:
                sell_thb = 5000.0
                new_cooldown = 30

        return {
            'buy_thb': buy_amount, 'sell_btc_pct': 0,
            'sell_thb': sell_thb, 'to_reserve': to_reserve,
            'new_cooldown': new_cooldown, 'sell_score': sell_score,
            'reserve_injection': reserve_inj,
        }

    return strategy_func
