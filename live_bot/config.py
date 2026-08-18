'''Live Bot Configuration — all values from environment variables.

Supports multi-currency: THB (Bitkub) and USDT (Binance).
All DCA parameters are configurable via environment variables.

Currency Resolution:
  - EXCHANGE=binance  -> currency=USDT, budgets converted via USD_THB_RATE
  - EXCHANGE=bitkub  -> currency=THB,  budgets used directly
'''

import os
import json
import requests


_RATE_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'usd_thb_rate.json'
)


def _env_float(key: str, default: str) -> float:
    """Get float from env var, treating empty string as default."""
    val = os.environ.get(key, default)
    return float(val) if val and val.strip() else float(default)


def _env_int(key: str, default: str) -> int:
    """Get int from env var, treating empty string as default."""
    val = os.environ.get(key, default)
    return int(val) if val and val.strip() else int(default)


# ═══════════════════════════════════════════════════════════════
#  EXCHANGE & CURRENCY
# ═══════════════════════════════════════════════════════════════
EXCHANGE = os.environ.get('EXCHANGE', 'binance').lower()  # 'binance' or 'bitkub'

# ═══════════════════════════════════════════════════════════════
#  LIVE USD/THB RATE from Bitkub USDT_THB ticker
# ═══════════════════════════════════════════════════════════════
_FALLBACK_RATE = 33.426
_usd_thb_cache = {'rate': None, 'date': None}


def _load_rate_cache() -> dict:
    """Load cached rate from disk. Returns {rate, date, source} or empty dict."""
    try:
        if os.path.exists(_RATE_CACHE_FILE):
            with open(_RATE_CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_rate_cache(rate: float, source: str):
    """Persist rate to disk so it survives across process restarts."""
    from datetime import date as _date
    try:
        data = {'rate': rate, 'date': _date.today().isoformat(), 'source': source}
        with open(_RATE_CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f'[CONFIG] WARNING: Could not save rate cache: {e}')


def _fetch_usdt_thb_from_bitkub() -> float:
    """Fetch live USDT/THB rate from Bitkub public ticker.

    Returns the 'last' price of the USDT_THB pair.
    Falls back to _FALLBACK_RATE on any error.
    """
    try:
        resp = requests.get(
            'https://api.bitkub.com/api/v3/market/ticker',
            params={'sym': 'USDT_THB'},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            rate = float(data[0].get('last', 0))
            if rate > 0:
                return rate
    except Exception as e:
        print(f'[CONFIG] WARNING: Failed to fetch USDT/THB from Bitkub: {e}')
    return _FALLBACK_RATE


def get_usd_thb_rate() -> float:
    """Get USD/THB rate.

    Priority:
    1. Bitkub USDT_THB live ticker (always first, refreshed daily)
    2. Disk cache from previous successful fetch
    3. Fallback constant 33.426

    Rate is persisted to usd_thb_rate.json after each successful fetch.
    """
    global _usd_thb_cache
    from datetime import date as _date
    today_str = _date.today().isoformat()

    # Return in-memory cache if fetched today
    if (_usd_thb_cache['rate'] is not None
            and _usd_thb_cache['date'] == today_str):
        return _usd_thb_cache['rate']

    # Always try Bitkub live first
    rate = _fetch_usdt_thb_from_bitkub()
    source = 'bitkub' if rate != _FALLBACK_RATE else 'fallback'

    # If Bitkub failed, try disk cache from previous day
    if rate == _FALLBACK_RATE:
        disk = _load_rate_cache()
        if disk.get('rate') and disk.get('rate') > 0:
            rate = disk['rate']
            source = 'disk_cache'
            print(f'[CONFIG] USD/THB using disk cache: {rate} ({disk.get("date")})')

    # Persist to disk and in-memory cache
    _usd_thb_cache['rate'] = rate
    _usd_thb_cache['date'] = today_str
    if source == 'bitkub':
        _save_rate_cache(rate, source)
    print(f'[CONFIG] USD/THB rate: {rate} (source: {source})')
    return rate


# Module-level initial value (lazy — use get_usd_thb_rate() at runtime)
USD_THB_RATE = _env_float('USD_THB_RATE', str(_FALLBACK_RATE))

# Currency derived from exchange — do NOT override manually
EXCHANGE_CURRENCY_MAP = {
    'binance': 'USDT',
    'bitkub': 'THB',
}
CURRENCY = EXCHANGE_CURRENCY_MAP.get(EXCHANGE, 'USDT')

# ═══════════════════════════════════════════════════════════════
#  DCA BUY PARAMETERS (configurable)
# ═══════════════════════════════════════════════════════════════
# Daily DCA budget — always specified in THB, auto-converted for USDT
DAILY_BUDGET_THB = _env_float('DAILY_BUDGET_THB', '100')
# Maximum single buy amount (hard cap per trade)
MAX_BUY_THB = _env_float('MAX_BUY_THB', '1000')
# Maximum total DCA buys per day (e.g. 3 means up to 3x DCA per day)
MAX_DCA_BUYS_PER_DAY = _env_int('MAX_DCA_BUYS_PER_DAY', '1')

# ═══════════════════════════════════════════════════════════════
#  RESERVE DEPLOYMENT PARAMETERS (configurable)
# ═══════════════════════════════════════════════════════════════
# Reserve = profits from BTC sales, held for buy-the-dip deployment
# Minimum reserve floor (in exchange currency) — keep this much cash untouched
RESERVE_FLOOR = _env_float('RESERVE_FLOOR', '0')
# Maximum single reserve injection (in exchange currency)
MAX_RESERVE_INJECTION = _env_float('MAX_RESERVE_INJECTION', '0')
# Boost multiplier when price < realized_price * threshold
RESERVE_BOOST_MULTIPLIER = _env_float('RESERVE_BOOST_MULTIPLIER', '1.8')
# Price threshold for boost: inject more if price < realized_price * this
RESERVE_BOOST_PRICE_RATIO = _env_float('RESERVE_BOOST_PRICE_RATIO', '1.05')

# ═══════════════════════════════════════════════════════════════
#  BALANCE ALERT PARAMETERS
# ═══════════════════════════════════════════════════════════════
# Days of DCA budget remaining before warning
LOW_BALANCE_DAYS = _env_int('LOW_BALANCE_DAYS', '7')

# ═══════════════════════════════════════════════════════════════
#  HELPER: Convert THB amounts to exchange currency
# ═══════════════════════════════════════════════════════════════
def thb_to_local(thb_amount: float) -> float:
    """Convert THB amount to exchange currency (USDT or THB).

    Uses live USD/THB rate from Bitkub when in USDT mode.
    """
    if CURRENCY == 'USDT':
        return thb_amount / get_usd_thb_rate()
    return thb_amount


def get_daily_budget() -> float:
    """Get daily DCA budget in exchange currency."""
    return thb_to_local(DAILY_BUDGET_THB)


def get_max_buy() -> float:
    """Get max single buy in exchange currency."""
    return thb_to_local(MAX_BUY_THB)


def get_reserve_floor() -> float:
    """Get reserve floor in exchange currency.

    If not explicitly set, defaults:
      - USDT: ~6 USDT (≈200 THB)
      - THB: 200 THB
    """
    if RESERVE_FLOOR > 0:
        return RESERVE_FLOOR
    # Default: 200 THB equivalent
    return thb_to_local(200.0)


def get_max_reserve_injection() -> float:
    """Get max reserve injection in exchange currency.

    If not explicitly set, defaults:
      - USDT: ~27 USDT (≈900 THB)
      - THB: 900 THB
    """
    if MAX_RESERVE_INJECTION > 0:
        return MAX_RESERVE_INJECTION
    return thb_to_local(900.0)


def get_max_reserve_boosted() -> float:
    """Get max boosted reserve injection in exchange currency.

    If not explicitly set, defaults:
      - USDT: ~36 USDT (≈1200 THB)
      - THB: 1200 THB
    """
    # Use MAX_RESERVE_INJECTION as base if set, otherwise 900 THB equivalent
    if MAX_RESERVE_INJECTION > 0:
        base = MAX_RESERVE_INJECTION
    else:
        base = thb_to_local(900.0)
    return base * RESERVE_BOOST_MULTIPLIER


# ═══════════════════════════════════════════════════════════════
#  API KEYS (from GitHub Secrets)
# ═══════════════════════════════════════════════════════════════
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.environ.get('BINANCE_API_SECRET', '')
BITKUB_API_KEY = os.environ.get('BITKUB_API_KEY', '')
BITKUB_API_SECRET = os.environ.get('BITKUB_API_SECRET', '')

# ═══════════════════════════════════════════════════════════════
#  TELEGRAM NOTIFICATIONS (optional)
# ═══════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# ═══════════════════════════════════════════════════════════════
#  DRY RUN TESTING
# ═══════════════════════════════════════════════════════════════
DRY_RUN = os.environ.get('DRY_RUN', 'false').lower() == 'true'
DRY_RUN_INITIAL_CASH = _env_float('DRY_RUN_INITIAL_CASH', '10000')
MIN_BUY_USDT = 10.0   # Binance minimum order
MIN_BUY_THB = 100.0   # Bitkub minimum order

# ═══════════════════════════════════════════════════════════════
#  FEE ASSUMPTIONS
# ═══════════════════════════════════════════════════════════════
# Bitkub basic tier = 0.25% (actual fee from API response is preferred)
# These are fallback values only when API response doesn't include fee
BUY_FEE_PCT = 0.0025   # 0.25% — Bitkub basic tier
SELL_FEE_PCT = 0.0025  # 0.25% — Bitkub basic tier

# ═══════════════════════════════════════════════════════════════
#  PATHS
# ═══════════════════════════════════════════════════════════════
STATE_FILE = os.environ.get('STATE_FILE', 'live_bot/state.json')
PRICE_CACHE_FILE = os.environ.get('PRICE_CACHE_FILE', 'live_bot/price_cache.csv')
