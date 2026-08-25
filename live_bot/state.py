'''State persistence — load/save bot state as JSON.

State is committed to the repo after each run so it persists
between GitHub Actions invocations.

H4: File locking via fcntl.flock to prevent concurrent read/write
between simultaneous GitHub Actions runs or local processes.
'''

import fcntl
import json
import os
import shutil
import time
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



# ── CQ: Shared atomic JSON write helper ──
# Eliminates duplication across save_state, append_trade_log,
# clear_trade_log, append_indicator_history.

_MAX_TRADE_LOG_ENTRIES = 5000  # ~13.7 years at 1 trade/day


def _atomic_json_write(path: str, data, max_entries: int = 0,
                        make_backup: bool = False) -> None:
    """Write JSON data atomically with exclusive lock.

    Args:
        path: file to write
        data: data to serialize (list or dict)
        max_entries: if > 0 and data is a list, trim to last N entries
        make_backup: if True, copy current file to .bak before overwriting

    Uses tempfile + os.replace for atomicity and fcntl.flock for exclusivity.
    """
    import tempfile
    dir_name = os.path.dirname(path) or '.'
    os.makedirs(dir_name, exist_ok=True)
    lock = _lock_path(path)

    if max_entries > 0 and isinstance(data, list):
        data = data[-max_entries:]

    tmp_path = None
    with open(lock, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            # Backup current content before overwriting
            if make_backup and os.path.exists(path):
                try:
                    with open(path, 'r') as src:
                        with open(path + '.bak', 'w') as dst:
                            dst.write(src.read())
                except OSError:
                    pass
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp_path, path)
        except Exception:
            if tmp_path is not None and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def save_state(state: dict, path: str):
    """Save state to JSON file atomically with exclusive lock (H4).

    Uses fcntl.flock(LOCK_EX) to prevent concurrent writes.
    Write is atomic (temp + rename) so readers always see valid JSON.
    NaN/Infinity values are replaced with None to produce valid JSON.
    Also creates a .bak backup of the previous state for corruption recovery.
    """
    clean_state = _sanitize_for_json(state)
    _atomic_json_write(path, clean_state, make_backup=True)


def _load_json_locked(path: str, default=None):
    """Load JSON from file with shared lock. Returns default on any error.

    Used by load_state, load_trade_log, load_indicator_history.
    """
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    lock = _lock_path(path)
    with open(lock, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_SH)
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print(f'[STATE] WARNING: corrupted file at {path}, returning default')
            return default
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
        # DI-2: Use actual proceeds (not strategy's intended amount) for sell fraction.
        # This accounts for 99% sell cap and market slippage.
        portfolio_before = btc_balance * sell_price + cash_balance
        if portfolio_before > 0 and state['adjusted_invested'] > 0:
            sell_fraction = actual_sell / portfolio_before
            state['adjusted_invested'] *= (1 - sell_fraction)
            state['adjusted_invested'] = max(round(state['adjusted_invested'], 2), 0)

    return state


def load_trade_log(path: str = 'trade_log.json') -> list:
    """Load trade log from JSON file with shared lock (H4).

    Handles corrupted JSON gracefully (same as load_state).
    """
    lock = path + '.lock'
    if os.path.exists(path):
        with open(lock, 'w') as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f'[STATE] WARNING: corrupted trade log at {path}, returning empty list')
                # Backup corrupted file
                bak = path + '.corrupted.' + str(int(time.time()))
                try:
                    shutil.copy2(path, bak)
                    print(f'[STATE] Corrupted trade log backed up to {bak}')
                except Exception:
                    pass
                return []
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
    lock = _lock_path(log_path)

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

    # CQ: Use _MAX_TRADE_LOG_ENTRIES constant instead of magic 5000
    tmp_path = None
    with open(lock, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)  # exclusive lock for ENTIRE read-modify-write
        try:
            if os.path.exists(log_path):
                with open(log_path, 'r') as f:
                    log = json.load(f)
            else:
                log = []

            log.append(record)
            if len(log) > _MAX_TRADE_LOG_ENTRIES:
                log = log[-_MAX_TRADE_LOG_ENTRIES:]

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
    _atomic_json_write(log_path, [])
    print('[STATE] Trade log cleared (D3: dry-run → live transition).')


# ── B18: Indicator History ─────────────────────────────────────────────
# Stores daily indicator snapshots as a time-series for retrospective analysis.
# Unlike last_indicators (overwritten each run), this APPENDS every run.
# Stored in a separate file (indicator_history.json) to keep state.json small.

_MAX_INDICATOR_HISTORY = 730  # ~2 years of daily data


def append_indicator_history(history_path: str, indicators: dict,
                               decision: dict = None):
    """Append an indicator snapshot to the indicator history log.

    B18: Stores daily indicator values as a time-series for
    retrospective analysis and dashboard charting.

    Each entry is a dict with 'date' (Thai TZ ISO) and all indicator
    values. Retention: last 730 entries (~2 years).
    """
    import tempfile
    dir_name = os.path.dirname(history_path) or '.'
    os.makedirs(dir_name, exist_ok=True)
    lock = _lock_path(history_path)

    now_str = datetime.now(_THAI_TZ).strftime('%Y-%m-%d %H:%M')
    entry = {'date': now_str}
    entry.update(indicators)
    if decision:
        entry['decision'] = decision

    # CQ: Use _MAX_INDICATOR_HISTORY constant
    tmp_path = None
    with open(lock, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            if os.path.exists(history_path):
                with open(history_path, 'r') as f:
                    history = json.load(f)
            else:
                history = []

            history.append(_sanitize_for_json(entry))
            if len(history) > _MAX_INDICATOR_HISTORY:
                history = history[-_MAX_INDICATOR_HISTORY:]

            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
            with os.fdopen(fd, 'w') as f:
                json.dump(history, f, indent=2)
            os.replace(tmp_path, history_path)
        except Exception:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def load_indicator_history(history_path: str) -> list:
    """Load indicator history. Returns list of snapshot dicts.

    Returns empty list if file doesn't exist or is corrupted.
    """
    if os.path.exists(history_path):
        lock = history_path + '.lock'
        with open(lock, 'w') as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)
            try:
                with open(history_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                print(f'[STATE] WARNING: corrupted indicator history at {history_path}')
                return []
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    return []
