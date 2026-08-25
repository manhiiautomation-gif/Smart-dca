PATH = '/home/z/my-project/live_bot/binance_client.py'

import re

with open(PATH, 'r') as f:
    content = f.read()

# 1. Insert helpers before BINANCE RETRY HELPER
helper_code = '\n# -- CQ: Shared helpers (eliminate duplication) --\n\n\ndef _check_binance_app_error(data):\n    """Check Binance application-level error (HTTP 200 with error code)."""  \n    if isinstance(data, dict) and 'code' in data:\n        raise RuntimeError(f"Binance API error {data['code']}: {data.get('msg', '')}")\n\n\ndef _extract_usdt_fee(data):\n    """Extract USDT fee from Binance fills array."""  \n    total_fee = 0.0\n    for fill in data.get('fills', []):\n        if fill.get('commissionAsset') == 'USDT':\n            total_fee += float(fill.get('commission', 0))\n    return total_fee\n\n\ndef _dedup_sort_trim(candles, days):\n    """Deduplicate candles by date, sort oldest-first, trim to last N."""  \n    seen = {}\n    for c in candles:\n        seen[c['date']] = c\n    return sorted(seen.values(), key=lambda x: x['date'])[-days:]\n'

pattern = r'(\n# ={60,}+\n# BINANCE RETRY HELPER\n# ={60,}+)'
match = re.search(pattern, content)
if match:
    content = content[:match.start()] + helper_code + content[match.start():]
    print('OK: inserted helpers')
else:
    print('SKIP: helpers pattern not found')

# 2-3. Replace fee extraction in market_buy and market_sell
old_fee = '        # Check Binance application-level error (HTTP 200 with error code)\\n'
old_fee += '        if isinstance(data, dict) and \'code\' in data:\n'
old_fee += '            raise RuntimeError(f"Binance API error {data[\'code\']}: {data.get(\'msg\', \'\')}")\\n'
old_fee += '        # Extract actual fee from fills array (quote currency only)\\n'
old_fee += '        total_fee = 0.0\\n'
old_fee += '        for fill in data.get(\'fills\', []):\\n'
old_fee += '            if fill.get(\'commissionAsset\') == \'USDT\':\\n'
old_fee += '                total_fee += float(fill.get(\'commission\', 0))\\n'
old_fee += '        '

# Hmm this is getting complicated, let me use a different approach
print('Reverting to simple approach...')

# Just check that the helpers are now present
print('Checking _check_binance_app_error defined:', 'def _check_binance_app_error' in content)
print('Checking _extract_usdt_fee defined:', 'def _extract_usdt_fee' in content)
print('Checking _dedup_sort_trim defined:', 'def _dedup_sort_trim' in content)

# File was restored, so all dedup patterns still exist
# Let me just write the whole final version
print('Will use full file write approach instead')
