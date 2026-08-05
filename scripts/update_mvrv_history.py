#!/usr/bin/env python3
'''Update MVRV history from CoinMetrics (primary) or ahasignals (fallback).

Fetches MVRV data from web and appends new values to
live_bot/_mvrv_history.py if the web data is newer.

Usage:
    python scripts/update_mvrv_history.py          # auto fetch & append
    python scripts/update_mvrv_history.py --dry-run   # preview only
    python scripts/update_mvrv_history.py --force     # force fetch
    python scripts/update_mvrv_history.py --value 1.85 --date 2026-08-06  # manual
    python scripts/update_mvrv_history.py --series    # show CoinMetrics series
'''

import os
import sys
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from live_bot.mvrv_fetcher import (
    fetch_mvrv_from_web,
    fetch_mvrv_coinmetrics,
    fetch_mvrv_series,
    append_mvrv_to_history,
    append_mvrv_series_to_history,
    try_update_mvrv,
)
from live_bot._mvrv_history import MVRV_START_DATE, MVRV_DAILY_VALUES
from datetime import date, timedelta


def main():
    parser = argparse.ArgumentParser(
        description='Update MVRV history from CoinMetrics / ahasignals'
    )
    parser.add_argument('--force', action='store_true',
                        help='Force fetch even if history appears current')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would happen without modifying files')
    parser.add_argument('--value', type=float, default=None,
                        help='Manually specify MVRV value to append')
    parser.add_argument('--date', type=str, default=None,
                        help='Date for the value (YYYY-MM-DD). Default: today')
    parser.add_argument('--series', action='store_true',
                        help='Show CoinMetrics series without modifying files')
    args = parser.parse_args()

    start = date.fromisoformat(MVRV_START_DATE)
    current_end = start + timedelta(days=len(MVRV_DAILY_VALUES) - 1)
    today = date.today()

    print(f'=== MVRV History Update ===')
    print(f'History range: {MVRV_START_DATE} → {current_end}')
    print(f'  Total days: {len(MVRV_DAILY_VALUES)}')
    print(f'  Last 5 values: {MVRV_DAILY_VALUES[-5:]}')
    print(f'Today: {today}')
    print(f'Gap: {max(0, (today - current_end).days)} days')
    print()

    # --series: just show CoinMetrics data
    if args.series:
        print('--- CoinMetrics recent series ---')
        cm = fetch_mvrv_coinmetrics(
            start_date=current_end - timedelta(days=3),
            end_date=today,
        )
        if cm:
            for d, v in cm:
                in_local = '✓' if d <= current_end else 'NEW'
                print(f'  {d}: {v:.4f}  {in_local}')
        else:
            print('  No data from CoinMetrics')
        return

    # --value: manual mode
    if args.value is not None:
        target_date = date.fromisoformat(args.date) if args.date else today
        print(f'Manual mode: MVRV={args.value:.4f} for {target_date}')
        if args.dry_run:
            print(f'[DRY RUN] Would append MVRV={args.value:.4f} for {target_date}')
        else:
            appended = append_mvrv_to_history(args.value, target_date)
            if appended > 0:
                print(f'Success: appended {appended} days')
            else:
                print('No changes needed')
        return

    # Auto / force / dry-run: use CoinMetrics series
    if args.dry_run or args.force:
        cm = fetch_mvrv_coinmetrics(
            start_date=current_end,
            end_date=today,
        )
        if not cm:
            print('CoinMetrics returned no data')
            if not args.force:
                return

        # Filter to only newer dates
        new_points = [(d, v) for d, v in cm if d > current_end]
        if not new_points:
            print(f'CoinMetrics latest ({cm[-1][0]}) not newer than local ({current_end})')
            return

        print(f'CoinMetrics has {len(new_points)} new point(s):')
        for d, v in new_points:
            print(f'  {d}: {v:.4f}')

        if args.dry_run:
            print(f'[DRY RUN] Would append {len(new_points)} days')
        else:
            appended = append_mvrv_series_to_history(new_points)
            print(f'Result: appended {appended} days')
        return

    # Normal mode: full auto
    ok, msg = try_update_mvrv()
    print(f'Result: {ok} — {msg}')


if __name__ == '__main__':
    main()
