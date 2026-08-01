"""Backtest Engine - Generic strategy runner with fee logic and state tracking.

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
    adjusted_invested = 0.0
    net_capital = 0.0
    total_sell_proceeds = 0.0
    total_reserve_injected = 0.0
    cooldown = 0
    short_cooldown = 0
    peak_value = 0.0
    max_drawdown = 0.0

    # Enhanced tracking
    sell_count = 0
    buy_days = 0
    reserve_buy_days = 0
    total_fees_paid = 0.0
    btc_sold_total = 0.0
    daily_log = []

    # New metrics tracking
    days_in_drawdown = 0
    worst_recovery_start = None
    worst_recovery_days = 0
    current_dd_start = None
    total_sell_value_thb = 0.0  # gross THB from sells (before fees)
    in_drawdown = False

    total_days = len(df)

    for idx, row in df.iterrows():
        price_thb = row['price_thb']
        if cooldown > 0:
            cooldown -= 1
        if short_cooldown > 0:
            short_cooldown -= 1

        # Pass adjusted_avg_cost to strategies that need profit gate
        adj_avg = adjusted_invested / btc if btc > 0 else 0
        state = {
            'btc': btc, 'cash_reserve': cash_reserve,
            'total_invested': total_invested, 'cooldown': cooldown,
            'short_cooldown': short_cooldown,
            'row': row, 'idx': idx,
            'adjusted_avg_cost': adj_avg,
        }

        action = strategy_func(state)

        buy_thb = action.get('buy_thb', 0)
        sell_btc_pct = action.get('sell_btc_pct', 0)
        sell_thb = action.get('sell_thb', 0)
        to_reserve = action.get('to_reserve', 0)
        sell_score = action.get('sell_score', 0)
        reserve_injection = action.get('reserve_injection', 0)

        # === BUY EXECUTION ===
        buy_fee = buy_thb * BUY_FEE_PCT
        actual_buy = apply_buy_fee(buy_thb)
        btc_bought = actual_buy / price_thb if price_thb > 0 else 0
        btc_before_sell = btc + btc_bought
        btc += btc_bought
        total_invested += buy_thb
        adjusted_invested += buy_thb
        net_capital += buy_thb - reserve_injection
        total_reserve_injected += reserve_injection
        total_fees_paid += buy_fee

        if buy_thb > 0:
            buy_days += 1
        if reserve_injection > 0:
            reserve_buy_days += 1

        # === SELL EXECUTION (BTC% based) ===
        if sell_btc_pct > 0 and btc > 0:
            btc_to_sell = btc * (sell_btc_pct / 100.0)
            sell_gross = btc_to_sell * price_thb
            sell_fee = sell_gross * SELL_FEE_PCT
            sell_proceeds = apply_sell_fee(sell_gross)
            btc -= btc_to_sell
            btc_sold_total += btc_to_sell
            cash_reserve += sell_proceeds
            total_sell_proceeds += sell_proceeds
            total_sell_value_thb += sell_gross
            total_fees_paid += sell_fee
            sell_count += 1
            cooldown = action.get('new_cooldown', cooldown)
            sell_frac = btc_to_sell / btc_before_sell if btc_before_sell > 0 else 0
            adjusted_invested *= (1.0 - sell_frac)

        # === SELL EXECUTION (THB-based) ===
        if sell_thb > 0 and btc > 0 and price_thb > 0:
            btc_to_sell = sell_thb / price_thb
            if btc_to_sell > btc:
                btc_to_sell = btc
            sell_gross = btc_to_sell * price_thb
            sell_fee = sell_gross * SELL_FEE_PCT
            sell_proceeds = apply_sell_fee(sell_gross)
            btc -= btc_to_sell
            btc_sold_total += btc_to_sell
            cash_reserve += sell_proceeds
            total_sell_proceeds += sell_proceeds
            total_sell_value_thb += sell_gross
            total_fees_paid += sell_fee
            sell_count += 1
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
            # Recovered from drawdown
            if in_drawdown and current_dd_start is not None:
                recovery_days = idx - current_dd_start
                if recovery_days > worst_recovery_days:
                    worst_recovery_days = recovery_days
                in_drawdown = False
                current_dd_start = None
        if peak_value > 0:
            drawdown = (peak_value - portfolio_value) / peak_value
            if drawdown > 0.001:  # > 0.1% counts as drawdown
                days_in_drawdown += 1
                if not in_drawdown:
                    in_drawdown = True
                    current_dd_start = idx
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        daily_log.append({
            'date': row['date'], 'price_thb': price_thb,
            'price_usd': row['price_usd'],
            'btc': btc, 'cash_reserve': cash_reserve,
            'total_invested': total_invested,
            'portfolio_value': portfolio_value,
            'avg_cost': adjusted_avg_cost,
            'max_drawdown_so_far': max_drawdown,
            'sell_event_thb': total_sell_value_thb,
            'buy_event_thb': buy_thb,
            'reserve_event_thb': reserve_injection,
            'mvrv': row['mvrv'],
        })

    final_price = df.iloc[-1]['price_thb']
    final_value = btc * final_price + cash_reserve
    final_avg_cost = adjusted_invested / btc if btc > 0 else 0
    roi_pct = ((final_value - total_invested) / total_invested * 100) if total_invested > 0 else 0
    net_profit = final_value - total_invested
    true_roi_pct = ((final_value - net_capital) / net_capital * 100) if net_capital > 0 else 0
    true_net_profit = final_value - net_capital

    # Derived metrics
    reserve_utilization_pct = (total_reserve_injected / total_sell_proceeds * 100) if total_sell_proceeds > 0 else 0
    avg_daily_dca = net_capital / total_days if total_days > 0 else 0
    btc_sell_pct = (btc_sold_total / (btc + btc_sold_total) * 100) if (btc + btc_sold_total) > 0 else 0
    days_in_drawdown_pct = (days_in_drawdown / total_days * 100) if total_days > 0 else 0
    avg_sell_price_thb = (total_sell_value_thb / btc_sold_total) if btc_sold_total > 0 else 0
    sell_profit_ratio = (avg_sell_price_thb / final_avg_cost) if (btc_sold_total > 0 and final_avg_cost > 0) else 0
    calmar_ratio = (true_roi_pct / (max_drawdown * 100)) if max_drawdown > 0 else 0

    results = {
        'strategy': strategy_name,
        # Capital flow
        'net_capital': net_capital,
        'total_invested': total_invested,
        'total_sell_proceeds': total_sell_proceeds,
        'total_reserve_injected': total_reserve_injected,
        'reserve_utilization_pct': reserve_utilization_pct,
        'cash_reserve': cash_reserve,
        'total_fees_paid': total_fees_paid,
        # BTC
        'total_btc': btc,
        'btc_sold_total': btc_sold_total,
        'btc_sell_pct': btc_sell_pct,
        'avg_cost_thb': final_avg_cost,
        'avg_cost_usd': final_avg_cost / USD_THB_RATE,
        # Performance
        'final_value': final_value,
        'roi_pct': roi_pct,
        'true_roi_pct': true_roi_pct,
        'net_profit': net_profit,
        'true_net_profit': true_net_profit,
        'max_drawdown_pct': max_drawdown * 100,
        # Activity
        'sell_count': sell_count,
        'buy_days': buy_days,
        'reserve_buy_days': reserve_buy_days,
        'avg_daily_dca': avg_daily_dca,
        'total_days': total_days,
        # New metrics
        'days_in_drawdown_pct': days_in_drawdown_pct,
        'worst_recovery_days': worst_recovery_days,
        'avg_sell_price_thb': avg_sell_price_thb,
        'sell_profit_ratio': sell_profit_ratio,
        'calmar_ratio': calmar_ratio,
    }
    return results, pd.DataFrame(daily_log)
