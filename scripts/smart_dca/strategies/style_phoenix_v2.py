"""Phoenix v2 - Tuned Adaptive Sell (3/5/7%, short-trend MVRV>2.0 gate)."""

import numpy as np
from ..config import BASE_BUDGET_THB
from ._shared import (
    precompute_macd_signals,
    precompute_rsi_divergence,
    precompute_short_trend_sell,
)


def strategy_style_phoenix_v2(df_precomputed):
    macd_cross_bear, hist_declining_5 = precompute_macd_signals(df_precomputed)
    rsi_divergence = precompute_rsi_divergence(df_precomputed, lookback=40)
    sma_200 = df_precomputed['sma_200'].values
    realized_price = df_precomputed['realized_price'].values
    lth_rp = df_precomputed['lth_realized_price'].values
    short_trend_sell = precompute_short_trend_sell(df_precomputed, sma_200, lookback_60=60)
    cummax_price = np.maximum.accumulate(df_precomputed['price_usd'].values)

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

        # 1. BUY SIDE: Same as Omega
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

        # 2. RESERVE DEPLOYMENT (same as Omega)
        reserve_inj = 0.0
        usable_cash = max(cash - 300.0, 0.0)
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
            rp = realized_price[idx] if idx < len(realized_price) else np.nan
            if not np.isnan(rp) and price_usd < rp * 1.05:
                injection = min(injection * 1.5, 800.0)
            buy_amount += injection
            reserve_inj = injection

        # 3. PRIMARY SELL: TUNED 3/5/7% (v1 was 4/6/8%)
        sell_score = 0
        if mvrv > 2.5: sell_score += 20
        if mvrv > 3.0: sell_score += 15
        if mvrv > 3.5: sell_score += 5
        if rsi > 70:    sell_score += 10
        if rsi > 80:    sell_score += 5
        if macd_cross_bear[idx]: sell_score += 10
        if hist_declining_5[idx]: sell_score += 5
        if rsi_divergence[idx]: sell_score += 15

        lth_val = lth_rp[idx] if idx < len(lth_rp) else np.nan
        if not np.isnan(lth_val) and lth_val > 0:
            p_to_lth = price_usd / lth_val
            if p_to_lth > 3.0: sell_score += 10
            if p_to_lth > 3.5: sell_score += 5

        ath = cummax_price[idx] if idx < len(cummax_price) else price_usd
        if ath > 0 and price_usd > 0.97 * ath:
            sell_score += 5

        s200 = sma_200[idx] if idx < len(sma_200) else price_usd
        if not np.isnan(s200) and price_usd < s200:
            sell_score -= 200
        if mvrv <= 2.5:
            sell_score = 0

        portfolio_val = btc * price_thb + cash
        sell_thb = 0.0
        new_cooldown = cooldown

        if sell_score >= 40 and cooldown == 0 and btc > 0:
            if sell_score >= 75:
                sell_thb = portfolio_val * 0.07
                new_cooldown = 45
            elif sell_score >= 60:
                sell_thb = portfolio_val * 0.05
                new_cooldown = 35
            else:
                sell_thb = portfolio_val * 0.03
                new_cooldown = 20

        # 4. SECONDARY SELL: Short-Trend with MVRV > 2.0 GATE
        sell_thb_secondary = 0.0
        short_cd = state.get('short_cooldown', 0)
        new_short_cd = max(short_cd - 1, 0) if short_cd > 0 else 0

        if (short_trend_sell[idx] and new_short_cd == 0 and btc > 0
                and sell_thb == 0 and mvrv > 2.0):
            sell_thb_secondary = min(portfolio_val * 0.015, 8000.0)
            new_short_cd = 20

        total_sell = sell_thb + sell_thb_secondary

        return {
            'buy_thb': buy_amount, 'sell_btc_pct': 0,
            'sell_thb': total_sell, 'to_reserve': to_reserve,
            'new_cooldown': new_cooldown, 'sell_score': sell_score,
            'reserve_injection': reserve_inj,
            'new_short_cooldown': new_short_cd,
        }

    return strategy_func
