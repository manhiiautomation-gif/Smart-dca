'''State persistence — load/save bot state as JSON.

State is committed to the repo after each run so it persists
between GitHub Actions invocations.
'''

import json
import os
from datetime import date


DEFAULT_STATE = {
    'cooldown': 0,
    'total_invested': 0.0,
    'adjusted_invested': 0.0,
    'total_sell_proceeds': 0.0,
    'total_reserve_injected': 0.0,
    'peak_value': 0.0,
    'max_drawdown': 0.0,
    'sell_count': 0,
    'buy_count': 0,
    'total_btc_bought': 0.0,
    'total_btc_sold': 0.0,
    'last_run_date': '',
    'last_trade_date': '',
    'last_sell_date': '',
    'run_count': 0,
    'cumulative_fees': 0.0,
    # Last known indicators (for dashboard when bot is killed)
    'last_indicators': {},
    # Last known balances
    'last_btc_balance': 0.0,
    'last_cash_balance': 0.0,
    'last_portfolio_value': 0.0,
    'last_price': 0.0,
    'last_exchange_currency': 'USDT',
    'last_dry_run': False,
    # Price cache for indicator calculation (list of [date_str, price])
    'price_history': [],
}


def load_state(path: str) -> dict:
    """Load state from JSON file, merging with defaults for new keys."""
    if os.path.exists(path):
        with open(path, 'r') as f:
            saved = json.load(f)
        merged = {**DEFAULT_STATE, **saved}
        return merged
    return dict(DEFAULT_STATE)


def save_state(state: dict, path: str):
    """Save state to JSON file atomically (write to temp then rename)."""
    import tempfile
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    dir_name = os.path.dirname(path) or '.'
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def update_state_after_run(state: dict, decision: dict,
                          buy_price: float, sell_price: float,
                          exchange_currency: str,
                          buy_fee: float = 0.0, sell_fee: float = 0.0) -> dict:
    """Update state after a trading decision has been executed."""
    today = date.today().isoformat()
    state['last_run_date'] = today
    state['run_count'] += 1
    state['cooldown'] = decision['new_cooldown']
    state['cumulative_fees'] += buy_fee + sell_fee
    if decision['reserve_injection'] > 0:
        state['total_reserve_injected'] += decision['reserve_injection']

    if decision['buy_amount'] > 0:
        state['buy_count'] += 1
        state['total_invested'] += decision['buy_amount']
        state['adjusted_invested'] += decision['buy_amount']
        state['last_trade_date'] = today

    if decision['sell_amount'] > 0:
        state['sell_count'] += 1
        state['total_sell_proceeds'] += decision['sell_amount']
        state['last_sell_date'] = today

    return state


def load_trade_log(path: str = 'trade_log.json') -> list:
    """Load trade log from JSON file."""
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return []


def append_trade_log(log_path: str, trade_type: str, amount: float,
                     btc_amount: float, price: float, fee: float = 0.0,
                     extra: dict = None):
    """Append a trade record to the trade log. Atomic write."""
    log = load_trade_log(log_path)
    record = {
        'date': date.today().isoformat(),
        'type': trade_type,  # 'buy' or 'sell'
        'amount': round(amount, 2),
        'btc': round(btc_amount, 8),
        'price': round(price, 2),
        'fee': round(fee, 2),
    }
    if extra:
        record.update(extra)
    log.append(record)
    # Keep last 500 trades max to prevent file bloat
    if len(log) > 500:
        log = log[-500:]
    # Atomic save
    import tempfile
    dir_name = os.path.dirname(log_path) or '.'
    os.makedirs(dir_name, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        with os.fdopen(fd, 'w') as f:
            json.dump(log, f, indent=2, default=str)
        os.replace(tmp_path, log_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return record
