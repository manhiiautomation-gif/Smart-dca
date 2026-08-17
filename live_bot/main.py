#!/usr/bin/env python3
'''Phoenix v5.1 Live Bot — entry point.

Usage:
    python live_bot/main.py --exchange binance
    python live_bot/main.py --exchange bitkub --dry-run
    python live_bot/main.py --exchange binance --budget 200
    python live_bot/main.py --demo                           # Demo portfolio
    python live_bot/main.py --demo --validate                 # Demo + validation
    python live_bot/main.py --demo --reset                    # Reset demo
    python live_bot/main.py --demo --scenario aggressive      # Named scenario

Environment variables (or GitHub Secrets):
    BINANCE_API_KEY, BINANCE_API_SECRET
    BITKUB_API_KEY, BITKUB_API_SECRET
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    DAILY_BUDGET_THB, MAX_BUY_THB, USD_THB_RATE
    DRY_RUN=true
    BOT_ENABLED=true   # Kill switch L1
'''

import argparse
import sys
import os
import time

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
    parser.add_argument('--force', '-f', action='store_true',
                        help='Force run even if already ran today (for testing)')
    parser.add_argument('--loop', '-l', type=int, default=0,
                        help='Loop mode: run every N minutes (dry-run only, e.g. --loop 10)')
    # Demo portfolio simulation flags
    parser.add_argument('--demo', action='store_true',
                        help='Run demo portfolio simulation (isolated state, slippage, validation)')
    parser.add_argument('--reset', action='store_true',
                        help='Reset demo portfolio to initial state')
    parser.add_argument('--validate', action='store_true',
                        help='Generate validation report after demo run')
    parser.add_argument('--scenario', '-S', default='default',
                        help='Demo scenario name (default: "default")')
    parser.add_argument('--demo-cash', type=float, default=None,
                        help='Initial cash for new demo portfolio (default: 10000)')
    args = parser.parse_args()

    # Override config
    exchange_name = args.exchange or config.EXCHANGE
    dry_run = args.dry_run or config.DRY_RUN
    if args.budget:
        config.DAILY_BUDGET_THB = args.budget
    state_path = args.state_file or config.STATE_FILE

    # ── DEMO MODE (isolated portfolio simulation) ──
    if args.demo:
        from live_bot import demo_portfolio as dp

        print(f'========================================')
        print(f'  Phoenix v5.1 — DEMO PORTFOLIO')
        print(f'  Exchange: {exchange_name.upper()}')
        print(f'  Budget: {config.DAILY_BUDGET_THB} THB/day')
        print(f'  Scenario: {args.scenario}')
        print(f'========================================')

        # Always use dummy keys for demo (public API only)
        mod_name, cls_name = EXCHANGE_MAP[exchange_name]
        mod = __import__(mod_name, fromlist=[cls_name])
        cls = getattr(mod, cls_name)
        exchange = cls('__demo_key__', '__demo_secret__')

        # Handle --reset
        if args.reset:
            demo_state = dp.init_demo(
                initial_cash=args.demo_cash or 10000.0,
                currency='USDT' if exchange_name == 'binance' else 'THB',
                exchange=exchange_name,
                scenario=args.scenario,
                project_root=PROJECT_ROOT,
            )
            print(f'[DEMO] Portfolio reset complete.')
            sys.exit(0)

        # Handle --validate only (no new run)
        if args.validate and not args.force:
            try:
                demo_state = dp.load_demo_state(PROJECT_ROOT, args.scenario,
                                                  expected_exchange=exchange_name)
            except ValueError as e:
                print(f'[DEMO] {e}')
                print(f'[DEMO] Auto-resetting with exchange={exchange_name}...')
                demo_state = dp.init_demo(
                    initial_cash=args.demo_cash or 10000.0,
                    currency='USDT' if exchange_name == 'binance' else 'THB',
                    exchange=exchange_name,
                    scenario=args.scenario,
                    project_root=PROJECT_ROOT,
                )
            if demo_state.get('run_count', 0) > 0:
                report = dp.generate_validation_report(demo_state, PROJECT_ROOT, args.scenario)
                dp.print_validation_report(report)
                sys.exit(0)

        # Load or init demo state
        # Pass expected_exchange so we detect mismatch with existing state
        try:
            demo_state = dp.load_demo_state(PROJECT_ROOT, args.scenario,
                                              expected_exchange=exchange_name)
        except ValueError as e:
            print(f'[DEMO] {e}')
            print(f'[DEMO] Auto-resetting with exchange={exchange_name}...')
            demo_state = dp.init_demo(
                initial_cash=args.demo_cash or 10000.0,
                currency='USDT' if exchange_name == 'binance' else 'THB',
                exchange=exchange_name,
                scenario=args.scenario,
                project_root=PROJECT_ROOT,
            )

        if args.demo_cash and demo_state.get('run_count', 0) == 0:
            demo_state = dp.init_demo(
                initial_cash=args.demo_cash,
                currency='USDT' if exchange_name == 'binance' else 'THB',
                exchange=exchange_name,
                scenario=args.scenario,
                project_root=PROJECT_ROOT,
            )

        try:
            demo_state = engine.run_demo(
                exchange, demo_state,
                project_root=PROJECT_ROOT,
                scenario=args.scenario,
                force=args.force,
                validate=args.validate,
            )
        except KeyboardInterrupt:
            print('\n[DEMO] Stopped by user.')
        except Exception as e:
            print(f'[DEMO] FATAL ERROR: {e}')
            import traceback
            traceback.print_exc()
            notifier.send_telegram(f'Phoenix v5.1 DEMO ERROR: {e}')
            sys.exit(1)

        dp.save_demo_state(demo_state, PROJECT_ROOT, args.scenario)
        print(f'[DEMO] State saved.')
        print('[DEMO] All done.')
        sys.exit(0)

    # ── STANDARD MODE (dry-run or live) ──
    # Derive paths relative to project root
    trade_log_path = os.path.join(PROJECT_ROOT, 'trade_log.json')
    kill_switch_path = os.path.join(PROJECT_ROOT, 'kill_switch.json')

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

    # In dry-run, create client with dummy keys for public API (price/klines)
    # market_buy/market_sell will NEVER be called (enforced by engine.py)
    if dry_run:
        exchange = cls('__dummy_key__', '__dummy_secret__')
    else:
        exchange = cls(api_key, api_secret)

    # ── Load state ──
    bot_state = state_mod.load_state(state_path)
    print(f'[BOT] State loaded: run #{bot_state["run_count"]} '
          f'cooldown={bot_state["cooldown"]} sells={bot_state["sell_count"]}')

    # ── Run engine ──
    if dry_run:
        print('[BOT] ═══════════════════════════════════════════════════')
        print('[BOT]   DRY RUN MODE — NO REAL TRADES')
        print(f'[BOT]   Virtual cash: {config.DRY_RUN_INITIAL_CASH:,.0f} THB')
        if args.force:
            print('[BOT]   --force enabled (bypass daily limit)')
        print('[BOT] ═══════════════════════════════════════════════════')
    else:
        print('[BOT] ═══════════════════════════════════════════════════')
        print('[BOT]   LIVE MODE — REAL TRADES WILL BE EXECUTED')
        print('[BOT] ═══════════════════════════════════════════════════')

    # ── C2: Concurrency lock — prevent duplicate runs ──
    lock_path = os.path.join(PROJECT_ROOT, 'live_bot', '.bot_lock')
    lock_acquired = False

    def _acquire_lock():
        nonlocal lock_acquired
        if os.path.exists(lock_path):
            lock_age = time.time() - os.path.getmtime(lock_path)
            if lock_age < 1800:  # 30 minutes
                print(f'[BOT] LOCK: Another run in progress (lock age {lock_age:.0f}s). Aborting.')
                sys.exit(0)
            else:
                print(f'[BOT] LOCK: Stale lock ({lock_age:.0f}s old). Removing.')
                os.unlink(lock_path)
        with open(lock_path, 'w') as f:
            f.write(f'pid={os.getpid()}, time={time.time()}')
        lock_acquired = True

    def _release_lock():
        if lock_acquired and os.path.exists(lock_path):
            os.unlink(lock_path)

    try:
        _acquire_lock()

        if args.loop > 0:
            # ── Loop mode: dry-run testing at N-minute intervals ──
            if not dry_run:
                print('ERROR: --loop is only allowed in dry-run mode.')
                sys.exit(1)
            interval_sec = args.loop * 60
            print(f'[BOT] Loop mode: running every {args.loop} minutes (Ctrl+C to stop)')
            run_num = 0
            while True:
                run_num += 1
                print(f'\n{"="*50}')
                print(f'[BOT] Loop iteration #{run_num} — {time.strftime("%Y-%m-%d %H:%M:%S")}')
                print(f'{"="*50}')
                bot_state = engine.run_daily(
                    exchange, bot_state, dry_run=True,
                    trade_log_path=trade_log_path,
                    kill_switch_path=kill_switch_path,
                    force=True,  # Always force in loop mode
                )
                state_mod.save_state(bot_state, state_path)
                print(f'[BOT] Sleeping {args.loop} minutes...')
                time.sleep(interval_sec)
        else:
            # Single run mode
            bot_state = engine.run_daily(
                exchange, bot_state, dry_run=dry_run,
                trade_log_path=trade_log_path,
                kill_switch_path=kill_switch_path,
                force=args.force,
            )

    except KeyboardInterrupt:
        print('\n[BOT] Stopped by user.')
    except Exception as e:
        print(f'[BOT] FATAL ERROR: {e}')
        import traceback
        traceback.print_exc()
        notifier.send_telegram(f'Phoenix v5.1 FATAL ERROR: {e}')
    finally:
        # C2: Always save state — prevents double-buy on crash/interrupt
        try:
            state_mod.save_state(bot_state, state_path)
            print(f'[BOT] State saved to {state_path}')
        except Exception as save_err:
            print(f'[BOT] FAILED to save state: {save_err}')
        _release_lock()


if __name__ == '__main__':
    main()
