'''Phoenix v5.1 Strategy — live version.

Adapted from backtest strategy_style_phoenix_v5_1.py.
Accepts a flat dict of current indicators + state, returns a decision dict.
All monetary amounts in the caller's currency (THB or USDT).
'''

import numpy as np
from datetime import date, timedelta


# ── Embedded MVRV History (self-contained, no pandas dependency) ──
from ._mvrv_history import MVRV_START_DATE, MVRV_DAILY_VALUES


def _build_mvrv_lookup():
    start = date.fromisoformat(MVRV_START_DATE)
    return {start + timedelta(days=i): v for i, v in enumerate(MVRV_DAILY_VALUES)}


_MVRV_LOOKUP = _build_mvrv_lookup()
_MVRV_HISTORY_MIN = min(_MVRV_LOOKUP.keys())
_MVRV_HISTORY_MAX = max(_MVRV_LOOKUP.keys())


def get_mvrv_for_date(d: date) -> float:
    """Get embedded MVRV value for a date. Returns NaN if out of range."""
    if not isinstance(d, date):
        d = date.fromisoformat(str(d))
    return _MVRV_LOOKUP.get(d, float('nan'))


def compute_mvrv_percentile(d: date, current_mvrv: float, window: int = 365) -> float:
    """MVRV percentile from embedded history (same as v5.1 backtest)."""
    if not isinstance(d, date):
        d = date.fromisoformat(str(d))
    hist_values = []
    for i in range(1, window + 1):
        check = d - timedelta(days=i)
        if check in _MVRV_LOOKUP:
            hist_values.append(_MVRV_LOOKUP[check])
        elif check < _MVRV_HISTORY_MIN:
            break
    if len(hist_values) < 60:
        return 0.0
    hist_values.sort()
    rank = np.searchsorted(hist_values, current_mvrv)
    return rank / len(hist_values)


def compute_mvrv_zscore(d: date, current_mvrv: float, window: int = 365) -> float:
    """MVRV Z-score from embedded history (same as v5.1 backtest)."""
    if not isinstance(d, date):
        d = date.fromisoformat(str(d))
    hist_values = []
    for i in range(1, window + 1):
        check = d - timedelta(days=i)
        if check in _MVRV_LOOKUP:
            hist_values.append(_MVRV_LOOKUP[check])
        elif check < _MVRV_HISTORY_MIN:
            break
    if len(hist_values) < 60:
        return 0.0
    arr = np.array(hist_values)
    return (current_mvrv - arr.mean()) / max(arr.std(), 0.01)


def phoenix_v5_1_decision(
    # Current indicators
    mvrv: float,
    rsi: float,
    sopr: float,
    nupl: float,
    price: float,          # in exchange currency
    sma_200: float,
    sma_365: float,
    realized_price: float,  # derived: price / mvrv
    lth_realized_price: float,
    mvrv_pct: float,
    mvrv_z: float,
    macd_cross_bear: bool,
    macd_hist_declining: bool,
    rsi_divergence_flag: bool,
    ath: float,            # all-time high in exchange currency
    # State
    btc_balance: float,
    cash_reserve: float,
    cooldown: int,
    # Config
    base_budget: float,
    max_buy: float,
) -> dict:
    """Run Phoenix v5.1 strategy for one decision point.

    Returns dict with keys:
        buy_amount, sell_amount, new_cooldown, sell_score,
        reserve_injection, path_taken
    """
    # ── Proxy detection ──
    # In live, if MVRV is NaN we skip trading entirely
    if np.isnan(mvrv):
        return _no_trade('MVRV unavailable')

    # ── BEAR BLOCK CHECK ──
    in_bear = not np.isnan(sma_200) and price < sma_200

    # ═══ 1. BUY SIDE ═══
    buy_amount = 0.0
    reserve_injection = 0.0

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

    buy_amount = min(base_budget * multiplier, max_buy)

    # ═══ 2. RESERVE DEPLOYMENT ═══
    usable_cash = max(cash_reserve - 200.0, 0.0)
    if usable_cash > 0 and mvrv < 1.5 and not np.isnan(realized_price):
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
        if price < realized_price * 1.05:
            injection = min(injection * 1.8, 1200.0)
        buy_amount += injection
        reserve_injection = injection

    # ═══ 3. SELL SCORING ═══
    sell_score = 0

    if mvrv > 2.5: sell_score += 20
    if mvrv > 3.0: sell_score += 15
    if mvrv > 3.5: sell_score += 10
    if mvrv > 4.0: sell_score += 10

    # RSI partial credit (v5.1 fix)
    if rsi > 65:  sell_score += 5
    if rsi > 70:  sell_score += 5
    if rsi > 80:  sell_score += 7

    if mvrv_pct >= 0.92: sell_score += 12
    if mvrv_pct >= 0.97: sell_score += 8

    if mvrv_z > 3.0: sell_score += 8
    if mvrv_z > 4.0: sell_score += 7

    if macd_cross_bear: sell_score += 10
    if macd_hist_declining: sell_score += 5
    if rsi_divergence_flag: sell_score += 15

    # LTH Realized Price
    if not np.isnan(lth_realized_price) and lth_realized_price > 0:
        p_to_lth = price / lth_realized_price
        if p_to_lth > 3.0: sell_score += 8
        if p_to_lth > 3.5: sell_score += 5
        if p_to_lth > 4.0: sell_score += 5

    # ATH proximity
    if ath > 0 and price > 0.97 * ath:
        sell_score += 7

    # NUPL
    if nupl > 0.70: sell_score += 5
    if nupl > 0.80: sell_score += 5

    # Bear block
    if in_bear:
        sell_score -= 200

    # ═══ TRIPLE-TRIGGER GATE ═══
    path_a = mvrv > 2.5
    path_a_ext = (2.0 <= mvrv <= 2.5 and mvrv_pct >= 0.95 and mvrv_z >= 2.5
                   and not path_a)
    path_b = (mvrv_pct >= 0.92 and mvrv > 2.0
              and not path_a and not path_a_ext)

    if not (path_a or path_a_ext or path_b):
        sell_score = 0

    # ═══ SELL EXECUTION ═══
    sell_amount = 0.0
    new_cooldown = cooldown
    path_taken = 'none'

    portfolio_val = btc_balance * price + cash_reserve

    if cooldown == 0 and btc_balance > 0:
        if path_a and sell_score >= 45:
            path_taken = 'A'
            if sell_score >= 75:
                sell_amount = portfolio_val * 0.40
                new_cooldown = 35
            elif sell_score >= 60:
                sell_amount = portfolio_val * 0.18
                new_cooldown = 28
            elif sell_score >= 50:
                sell_amount = portfolio_val * 0.08
                new_cooldown = 22
            else:
                sell_amount = portfolio_val * 0.04
                new_cooldown = 18

        elif path_a_ext and sell_score >= 48:
            path_taken = 'A-Ext'
            sell_amount = portfolio_val * 0.08
            new_cooldown = 22

        elif path_b and sell_score >= 48:
            path_taken = 'B'
            if sell_score >= 56:
                sell_amount = portfolio_val * 0.08
                new_cooldown = 28
            else:
                sell_amount = portfolio_val * 0.04
                new_cooldown = 22

    # If buy_amount is effectively zero, set to 0
    if buy_amount < 0.01:
        buy_amount = 0.0

    return {
        'buy_amount': round(buy_amount, 2),
        'sell_amount': round(sell_amount, 2),
        'new_cooldown': new_cooldown,
        'sell_score': sell_score,
        'reserve_injection': round(reserve_injection, 2),
        'path_taken': path_taken,
        'in_bear': in_bear,
    }


def _no_trade(reason: str) -> dict:
    return {
        'buy_amount': 0.0, 'sell_amount': 0.0,
        'new_cooldown': 0, 'sell_score': 0,
        'reserve_injection': 0.0, 'path_taken': f'no-trade:{reason}',
        'in_bear': False,
    }