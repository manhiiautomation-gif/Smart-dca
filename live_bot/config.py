'''Live Bot Configuration — all values from environment variables.

Supports multi-currency: THB (Bitkub) and USDT (Binance).
All DCA parameters are configurable via environment variables.

Currency Resolution:
  - EXCHANGE=binance  -> currency=USDT, budgets converted via USD_THB_RATE
  - EXCHANGE=bitkub  -> currency=THB,  budgets used directly
'''

import os

# ═══════════════════════════════════════════════════════════════
#  EXCHANGE & CURRENCY
# ═══════════════════════════════════════════════════════════════
EXCHANGE = os.environ.get('EXCHANGE', 'binance').lower()  # 'binance' or 'bitkub'
USD_THB_RATE = float(os.environ.get('USD_THB_RATE', '33.426'))

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
DAILY_BUDGET_THB = float(os.environ.get('DAILY_BUDGET_THB', '100'))
# Maximum single buy amount (hard cap per trade)
MAX_BUY_THB = float(os.environ.get('MAX_BUY_THB', '1000'))
# Maximum total DCA buys per day (e.g. 3 means up to 3x DCA per day)
MAX_DCA_BUYS_PER_DAY = int(os.environ.get('MAX_DCA_BUYS_PER_DAY', '1'))

# ═══════════════════════════════════════════════════════════════
#  RESERVE DEPLOYMENT PARAMETERS (configurable)
# ═══════════════════════════════════════════════════════════════
# Reserve = profits from BTC sales, held for buy-the-dip deployment
# Minimum reserve floor (in exchange currency) — keep this much cash untouched
RESERVE_FLOOR = float(os.environ.get('RESERVE_FLOOR', '0'))
# Maximum single reserve injection (in exchange currency)
MAX_RESERVE_INJECTION = float(os.environ.get('MAX_RESERVE_INJECTION', '0'))
# Boost multiplier when price < realized_price * threshold
RESERVE_BOOST_MULTIPLIER = float(os.environ.get('RESERVE_BOOST_MULTIPLIER', '1.8'))
# Price threshold for boost: inject more if price < realized_price * this
RESERVE_BOOST_PRICE_RATIO = float(os.environ.get('RESERVE_BOOST_PRICE_RATIO', '1.05'))

# ═══════════════════════════════════════════════════════════════
#  BALANCE ALERT PARAMETERS
# ═══════════════════════════════════════════════════════════════
# Low balance warning threshold (in exchange currency)
LOW_BALANCE_THRESHOLD = float(os.environ.get('LOW_BALANCE_THRESHOLD', '0'))
# Days of DCA budget remaining before warning
LOW_BALANCE_DAYS = int(os.environ.get('LOW_BALANCE_DAYS', '7'))

# ═══════════════════════════════════════════════════════════════
#  HELPER: Convert THB amounts to exchange currency
# ═══════════════════════════════════════════════════════════════
def thb_to_local(thb_amount: float) -> float:
    """Convert THB amount to exchange currency (USDT or THB)."""
    if CURRENCY == 'USDT':
        return thb_amount / USD_THB_RATE
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
DRY_RUN_INITIAL_CASH = float(os.environ.get('DRY_RUN_INITIAL_CASH', '10000'))
MIN_BUY_USDT = 10.0   # Binance minimum order
MIN_BUY_THB = 100.0   # Bitkub minimum order

# ═══════════════════════════════════════════════════════════════
#  FEE ASSUMPTIONS
# ═══════════════════════════════════════════════════════════════
BUY_FEE_PCT = 0.0015   # 0.15%
SELL_FEE_PCT = 0.0015  # 0.15%

# ═══════════════════════════════════════════════════════════════
#  PATHS
# ═══════════════════════════════════════════════════════════════
STATE_FILE = os.environ.get('STATE_FILE', 'live_bot/state.json')
PRICE_CACHE_FILE = os.environ.get('PRICE_CACHE_FILE', 'live_bot/price_cache.csv')
