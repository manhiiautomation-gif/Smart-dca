# ============================================================
# GLOBAL CONSTANTS
# ============================================================

BASE_BUDGET_THB = 100    # Fixed daily budget in THB
USD_THB_RATE    = 36     # Fixed exchange rate: 1 USD = 36 THB
BUY_FEE_PCT     = 0.0015 # 0.15% total execution friction on buys
SELL_FEE_PCT    = 0.0015 # 0.15% total execution friction on sells

import os
DOWNLOAD_DIR = '/home/z/my-project/download'
CACHE_DIR    = '/home/z/my-project/cache'

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_MAX_AGE_HOURS = 168  # 7 days — historical data doesn't change
