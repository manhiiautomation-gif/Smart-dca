'''State persistence — load/save bot state as JSON.

State is committed to the repo after each run so it persists
between GitHub Actions invocations.

H4: File locking via fcntl.flock to prevent concurrent read/write
between simultaneous GitHub Actions runs or local processes.
'''

import fcntl
import json
import os
from datetime import date, datetime, timezone, timedelta

# H1: Thai timezone — must match engine.py
_THAI_TZ = timezone(timedelta(hours=7))


def _thai_today() -> date:
    """Return today's date in Thai timezone (UTC+7)."""
    return datetime.now(_THAI_TZ).date()


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
    # Dry-run virtual balances (only used when dry_run=True)
    # These allow the bot to simulate trades without real money
    'dry_run_cash': None,   # None = not initialized yet, will be set on first dry-run
    'dry_run_btc': None,
    # Price cache for indicator calculation (list of [date_str, price])
    'price_history': [],
}


def _lock_path(path: str) -> str:
    """Derive lock file path from state file path (H4)."""
    return path + '.lock'


def load_state(path: str) -> dict:
    """Load state from JSON file with shared lock, merging with defaults.

    Corruption recovery: if state.json is corrupted, tries to restore
    from state.json.bak (last known good state). Falls back to defaults
    only if both files are unreadable.
    """
    import shutil
    lock = _lock_path(path)
    backup_path = path + '.bak'
    if os.path.exists(path):
        with open(lock, 'w') as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)  # shared lock — allow concurrent reads
            try:
                with open(path, 'r') as f:
                    saved = json.load(f)
            except (json.JSONDecodeError, ValueError) as e:
                print(f'[STATE] WARNING: Corrupted state file: {e}.')
                # Try restoring from backup
                if os.path.exists(backup_path):
                    try:
                        with open(backup_path, 'r') as bf:
                            saved = json.load(bf)
                        print(f'[STATE] Recovered state from backup ({backup_path}).')
                    except (json.JSONDecodeError, ValueError, OSError) as e2:
                        print(f'[STATE] WARNING: Backup also corrupted: {e2}. Using defaults.')
                        saved = {}
                else:
                    print(f'[STATE] No backup found. Using defaults.')
                    saved = {}
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
        merged = {**DEFAULT_STATE, **saved}
        return merged
    return dict(DEFAULT_STATE)


def _sanitize_for_json(obj):
    """Recursively replace NaN/Infinity with None (becomes JSON null)."""
    import math
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def save_state(state: dict, path: str):
    """Save state to JSON file atomically with exclusive lock (H4).

    Uses fcntl.flock(LOCK_EX) to prevent concurrent writes.
    Write is atomic (temp + rename) so readers always see valid JSON.
    NaN/Infinity values are replaced with None to produce valid JSON.
    Also creates a .bak backup of the previous state for corruption recovery.
    """
    import tempfile
    lock = _lock_path(path)
    backup_path = path + '.bak'
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    dir_name = os.path.dirname(path) or '.'
    clean_state = _sanitize_for_json(state)
    with open(lock, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)  # exclusive lock
        tmp_path = None
        try:
            # Backup current state before overwriting
            if os.path.exists(path):
                try:
                    with open(path, 'r') as src:
                        with open(backup_path, 'w') as dst:
                            dst.write(src.read())
                except OSError:
                    pass  # non-critical: backup failure shouldn't block save
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
            with os.fdopen(fd, 'w') as f:
                json.dump(clean_state, f, indent=2, default=str)
            os.replace(tmp_path, path)
        except Exception:
            if tmp_path is not None and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def update_state_after_run(state: dict, decision: dict,
                          buy_price: float, sell_price: float,
                          exchange_currency: str,
                          buy_fee: float = 0.0, sell_fee: float = 0.0,
                          btc_balance: float = 0.0,
                          cash_balance: float = 0.0,
                          sell_proceeds_actual: float = 0.0,
                          actual_buy_cost: float = 0.0) -> dict:
    """Update state after a trading decision has been executed.

    H5: When selling, adjusted_invested is reduced proportionally.
    If you sell X THB worth of BTC from a portfolio worth P THB,
    your cost basis is reduced by the same fraction (X/P).
    This ensures ROI calculations remain accurate after partial sells.
    """
    from datetime import datetime as _dt
    today = _thai_today().isoformat()
    now_str = _dt.now(_THAI_TZ).strftime('%Y-%m-%d %H:%M')
    state['last_run_date'] = today
    state['run_count'] += 1
    state['cooldown'] = decision['new_cooldown']
    state['cumulative_fees'] += buy_fee + sell_fee
    if decision['reserve_injection'] > 0:
        state['total_reserve_injected'] += decision['reserve_injection']

    if decision['buy_amount'] > 0:
        state['buy_count'] += 1
        # B5-fix: Use actual exchange-returned cost when available,
        # falling back to decision amount (accurate for dry-run).
        _cost = actual_buy_cost if actual_buy_cost > 0 else decision['buy_amount']
        state['total_invested'] += _cost
        state['adjusted_invested'] += _cost
        state['last_trade_date'] = now_str

    if decision['sell_amount'] > 0:
        state['sell_count'] += 1
        actual_sell = sell_proceeds_actual if sell_proceeds_actual > 0 else decision['sell_amount']
        state['total_sell_proceeds'] += actual_sell
        state['last_sell_date'] = now_str

        # H5: Reduce adjusted_invested proportionally when selling
        # Sell fraction = sell_amount / portfolio_value_before_sell
        portfolio_before = btc_balance * sell_price + cash_balance
        if portfolio_before > 0 and state['adjusted_invested'] > 0:
            sell_fraction = decision['sell_amount'] / portfolio_before
            state['adjusted_invested'] *= (1 - sell_fraction)
            state['adjusted_invested'] = max(round(state['adjusted_invested'], 2), 0)

    return state


def load_trade_log(path: str = 'trade_log.json') -> list:
    """Load trade log from JSON file with shared lock (H4)."""
    lock = path + '.lock'
    if os.path.exists(path):
        with open(lock, 'w') as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    return []


def append_trade_log(log_path: str, trade_type: str, amount: float,
                     btc_amount: float, price: float, fee: float = 0.0,
                     extra: dict = None):
    """Append a trade record to the trade log. Atomic write.

    Uses a SINGLE exclusive lock for the entire read-modify-write cycle
    to prevent TOCTOU race conditions (H3).
    """
    from datetime import datetime as _dt
    import tempfile
    dir_name = os.path.dirname(log_path) or '.'
    os.makedirs(dir_name, exist_ok=True)
    lock = log_path + '.lock'

    record = {
        'date': _dt.now(_THAI_TZ).strftime('%Y-%m-%d %H:%M'),
        'type': trade_type,
        'amount': round(amount, 2),
        'btc': round(btc_amount, 8),
        'price': round(price, 2),
        'fee': round(fee, 2),
    }
    if extra:
        record.update(extra)

    tmp_path = None
    with open(lock, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)  # exclusive lock for ENTIRE read-modify-write
        try:
            # Read existing log (under exclusive lock)
            if os.path.exists(log_path):
                with open(log_path, 'r') as f:
                    log = json.load(f)
            else:
                log = []

            log.append(record)
            if len(log) > 5000:
                log = log[-5000:]

            # Atomic write (still under exclusive lock)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
            with os.fdopen(fd, 'w') as f:
                json.dump(log, f, indent=2, default=str)
            os.replace(tmp_path, log_path)
        except Exception:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
    return record


def clear_trade_log(log_path: str):
    """Clear all entries from the trade log. Atomic write with exclusive lock (H4).

    Used during D3 (dry-run → live transition) to remove contaminated dry-run
    entries so the dashboard only shows live trades.
    """
    import tempfile
    dir_name = os.path.dirname(log_path) or '.'
    os.makedirs(dir_name, exist_ok=True)
    lock = log_path + '.lock'
    tmp_path = None
    with open(lock, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
            with os.fdopen(fd, 'w') as f:
                json.dump([], f, indent=2)
            os.replace(tmp_path, log_path)
            print('[STATE] Trade log cleared (D3: dry-run → live transition).')
        except Exception:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
