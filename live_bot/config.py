'''Live Bot Configuration — all values from environment variables.'''

import os

# ── Trading Parameters ──
DAILY_BUDGET_THB = float(os.environ.get('DAILY_BUDGET_THB', '100'))
MAX_BUY_THB = float(os.environ.get('MAX_BUY_THB', '1000'))
USD_THB_RATE = float(os.environ.get('USD_THB_RATE', '36'))

# ── Exchange ──
EXCHANGE = os.environ.get('EXCHANGE', 'binance').lower()  # 'binance' or 'bitkub'

# ── API Keys (from GitHub Secrets) ──
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.environ.get('BINANCE_API_SECRET', '')
BITKUB_API_KEY = os.environ.get('BITKUB_API_KEY', '')
BITKUB_API_SECRET = os.environ.get('BITKUB_API_SECRET', '')

# ── Telegram Notifications (optional) ──
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# ── Safety ──
DRY_RUN = os.environ.get('DRY_RUN', 'false').lower() == 'true'
MIN_BUY_USDT = 10.0   # Binance minimum order
MIN_BUY_THB = 100.0   # Bitkub minimum order

# ── Fee Assumptions ──
BUY_FEE_PCT = 0.0015   # 0.15%
SELL_FEE_PCT = 0.0015  # 0.15%

# ── Paths ──
STATE_FILE = os.environ.get('STATE_FILE', 'live_bot/state.json')
PRICE_CACHE_FILE = os.environ.get('PRICE_CACHE_FILE', 'live_bot/price_cache.csv')
