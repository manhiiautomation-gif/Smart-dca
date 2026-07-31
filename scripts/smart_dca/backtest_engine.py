"""Backtest Engine — Generic strategy runner with fee logic and state tracking.

Every strategy receives a `state` dict and returns an `action` dict.
The engine handles: buy execution, sell execution (BTC% and THB-based),
fee deduction, adjusted_invested tracking, drawdown tracking.
"""

import numpy as np
import pandas as pd

from .config import BUY_FEE_PCT, SELL_FEE_PCT, USD_THB_RATE


def apply_buy_fee(thb_amount):
    return thb_amount * (1 - BUY_FEE_PCT)


def apply_sell_fee(thb_amount):
    return thb_amount * (1 - SELL_FEE_PCT)


def backtest_strategy(df, strategy_func, strategy_name):
    """
    Generic backtest runner. Calls strategy_func(state) for each day.

    State dict keys provided to strategy:
        btc, cash_reserve, total_invested, cooldown, short_cooldown, row, idx

    Action dict keys the engine reads:
        buy_thb, sell_btc_pct, sell_thb, to_reserve, sell_score,
        new_cooldown, new_short_cooldown, reserve_injection

    Returns:
        results (dict), daily_log (DataFrame)
    """
    btc = 0.0
    cash_reserve = 0.0
    total_invested = 0.0
    adjusted_invested = 0.0  # Reduces proportionally on sells (smooth avg cost)
    net_capital = 0.0       # Only new user capital (excludes reserve recycling)
    total_sell_proceeds = 0.0
    total_reserve_injected = 0.0
    cooldown = 0
    short_cooldown = 0
    peak_value = 0.0
    max_drawdown = 0.0
    daily_log = []

    for idx, row in df.iterrows():
        price_thb = row['price_thb']
        if cooldown > 0:
            cooldown -= 1
        if short_cooldown > 0:
            short_cooldown -= 1

        state = {
            'btc': btc, 'cash_reserve': cash_reserve,
            'total_invested': total_invested, 'cooldown': cooldown,
            'short_cooldown': short_cooldown,
            'row': row, 'idx': idx
        }

        action = strategy_func(state)

        buy_thb = action.get('buy_thb', 0)
        sell_btc_pct = action.get('sell_btc_pct', 0)
        sell_thb = action.get('sell_thb', 0)
        to_reserve = action.get('to_reserve', 0)
        sell_score = action.get('sell_score', 0)
        reserve_injection = action.get('reserve_injection', 0)

        actual_buy = apply_buy_fee(buy_thb)
        btc_bought = actual_buy / price_thb if price_thb > 0 else 0
        btc_before_sell = btc + btc_bought
        btc += btc_bought
        total_invested += buy_thb
        adjusted_invested += buy_thb
        net_capital += buy_thb - reserve_injection
        total_reserve_injected += reserve_injection

        if sell_btc_pct > 0 and btc > 0:
            btc_to_sell = btc * (sell_btc_pct / 100.0)
            sell_proceeds = apply_sell_fee(btc_to_sell * price_thb)
            btc -= btc_to_sell
            cash_reserve += sell_proceeds
            cooldown = action.get('new_cooldown', cooldown)
            sell_frac = btc_to_sell / btc_before_sell if btc_before_sell > 0 else 0
            adjusted_invested *= (1.0 - sell_frac)

        # THB-based selling
        if sell_thb > 0 and btc > 0 and price_thb > 0:
            btc_to_sell = sell_thb / price_thb
            if btc_to_sell > btc:
                btc_to_sell = btc
            sell_proceeds = apply_sell_fee(btc_to_sell * price_thb)
            btc -= btc_to_sell
            cash_reserve += sell_proceeds
            total_sell_proceeds += sell_proceeds
            cooldown = action.get('new_cooldown', cooldown)
            sell_frac = btc_to_sell / btc_before_sell if btc_before_sell > 0 else 0
            adjusted_invested *= (1.0 - sell_frac)

        cash_reserve += to_reserve
        cash_reserve = max(cash_reserve, 0.0)

        portfolio_value = btc * price_thb + cash_reserve
        avg_cost = total_invested / btc if btc > 0 else 0
        adjusted_avg_cost = adjusted_invested / btc if btc > 0 else 0

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
            'avg_cost': adjusted_avg_cost,
            'max_drawdown_so_far': max_drawdown,
        })

    final_price = df.iloc[-1]['price_thb']
    final_value = btc * final_price + cash_reserve
    final_avg_cost = adjusted_invested / btc if btc > 0 else 0
    roi_pct = ((final_value - total_invested) / total_invested * 100) if total_invested > 0 else 0
    net_profit = final_value - total_invested
    true_roi_pct = ((final_value - net_capital) / net_capital * 100) if net_capital > 0 else 0
    true_net_profit = final_value - net_capital

    results = {
        'strategy': strategy_name,
        'total_invested': total_invested,
        'net_capital': net_capital,
        'total_btc': btc,
        'avg_cost_thb': final_avg_cost,
        'avg_cost_usd': final_avg_cost / USD_THB_RATE,
        'final_value': final_value,
        'cash_reserve': cash_reserve,
        'roi_pct': roi_pct,
        'true_roi_pct': true_roi_pct,
        'net_profit': net_profit,
        'true_net_profit': true_net_profit,
        'total_sell_proceeds': total_sell_proceeds,
        'total_reserve_injected': total_reserve_injected,
        'max_drawdown_pct': max_drawdown * 100,
    }
    return results, pd.DataFrame(daily_log)
