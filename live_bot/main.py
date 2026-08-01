#!/usr/bin/env python3
'''Phoenix v5.1 Live Bot — entry point.

Usage:
    python live_bot/main.py --exchange binance
    python live_bot/main.py --exchange bitkub --dry-run
    python live_bot/main.py --exchange binance --budget 200

Environment variables (or GitHub Secrets):
    BINANCE_API_KEY, BINANCE_API_SECRET
    BITKUB_API_KEY, BITKUB_API_SECRET
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    DAILY_BUDGET_THB, MAX_BUY_THB, USD_THB_RATE
    DRY_RUN=true
'''

import argparse
import sys
import os

# Add project root to path for MVRV history import
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from live_bot import config
from live_bot import state as state_mod
from live_bot import engine
from live_bot import notifier


EXCHANGE_MAP = {
    'binance': ('live_bot.binance_client', 'BinanceClient'),
    'bitkub': ('live_bot.bitkub_client', 'BitkubClient'),
}


def main():
    parser = argparse.ArgumentParser(description='Phoenix v5.1 DCA Bot')
    parser.add_argument('--exchange', '-e', default=None,
                        choices=['binance', 'bitkub'],
                        help='Exchange to use (default: from env)')
    parser.add_argument('--dry-run', '-d', action='store_true',
                        help='Simulate without real trades')
    parser.add_argument('--budget', '-b', type=float, default=None,
                        help='Daily budget in THB')
    parser.add_argument('--state-file', '-s', default=None,
                        help='Path to state JSON file')
    args = parser.parse_args()

    # Override config
    exchange_name = args.exchange or config.EXCHANGE
    dry_run = args.dry_run or config.DRY_RUN
    if args.budget:
        config.DAILY_BUDGET_THB = args.budget
    state_path = args.state_file or config.STATE_FILE

    print(f'========================================')
    print(f'  Phoenix v5.1 Live Bot')
    print(f'  Exchange: {exchange_name.upper()}')
    print(f'  Budget: {config.DAILY_BUDGET_THB} THB/day')
    print(f'  USD/THB: {config.USD_THB_RATE}')
    print(f'  Dry Run: {dry_run}')
    print(f'========================================')

    # ── Load exchange client ──
    mod_name, cls_name = EXCHANGE_MAP[exchange_name]
    mod = __import__(mod_name, fromlist=[cls_name])
    cls = getattr(mod, cls_name)

    if exchange_name == 'binance':
        api_key = config.BINANCE_API_KEY
        api_secret = config.BINANCE_API_SECRET
    else:
        api_key = config.BITKUB_API_KEY
        api_secret = config.BITKUB_API_SECRET

    if not api_key or not api_secret:
        if not dry_run:
            print(f'ERROR: {exchange_name.upper()} API keys not set. ')
            print(f'  Set {exchange_name.upper()}_API_KEY and {exchange_name.upper()}_API_SECRET env vars.')
            sys.exit(1)
        else:
            print(f'WARNING: No API keys. Running in dry-run mode.')
            dry_run = True

    exchange = cls(api_key, api_secret) if not dry_run else None

    # ── Load state ──
    bot_state = state_mod.load_state(state_path)
    print(f'[BOT] State loaded: run #{bot_state["run_count"]} '
          f'cooldown={bot_state["cooldown"]} sells={bot_state["sell_count"]}')

    # ── Run engine (or dry-run stub) ──
    if dry_run:
        print('[BOT] DRY RUN MODE — no real trades')
        # For dry run without API keys, we need a minimal client
        # Create a mock that can still fetch public data
        if exchange is None:
            exchange = cls('__dummy_key__', '__dummy_secret__')

    try:
        bot_state = engine.run_daily(exchange, bot_state, dry_run=dry_run)
    except Exception as e:
        print(f'[BOT] FATAL ERROR: {e}')
        import traceback
        traceback.print_exc()
        notifier.send_telegram(f'Phoenix v5.1 FATAL ERROR: {e}')
        sys.exit(1)

    # ── Save state ──
    state_mod.save_state(bot_state, state_path)
    print(f'[BOT] State saved to {state_path}')

    print('[BOT] All done.')


if __name__ == '__main__':
    main()