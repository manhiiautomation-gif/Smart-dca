'''Fetch live MVRV from CoinMetrics (primary) or ahasignals.com (fallback).

Provides a web-fetch mechanism when the embedded MVRV history
is stale (i.e. today's date is missing).

Primary:   CoinMetrics Community API (free, no API key)
             metric: CapMVRVCur
             Returns multiple days of data with precise values.

Fallback:  ahasignals.com scraping (BGeometrics source)
             Slower, less precise, but works if CoinMetrics is down.

Usage:
    from live_bot.mvrv_fetcher import fetch_mvrv_from_web
    mvrv, src_date, src = fetch_mvrv_from_web()  # (float, date, str)
'''

import math
import re
import urllib.request
import json
from datetime import date, datetime, timedelta
from typing import Optional, Tuple, List


# ── CoinMetrics Community API (primary) ──────────────────────────────
_CM_API_BASE = 'https://community-api.coinmetrics.io/v4'
_CM_METRIC = 'CapMVRVCur'
_CM_ASSET = 'btc'


def fetch_mvrv_coinmetrics(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    timeout: int = 15,
) -> List[Tuple[date, float]]:
    '''Fetch MVRV time series from CoinMetrics Community API.

    Returns:
        List of (date, mvrv_value) tuples, newest last.
        Empty list on failure.
    '''
    if start_date is None:
        start_date = date.today() - timedelta(days=7)
    if end_date is None:
        end_date = date.today()

    start_str = start_date.isoformat() + 'T00:00:00Z'
    end_str = (end_date + timedelta(days=1)).isoformat() + 'T00:00:00Z'

    url = (
        f'{_CM_API_BASE}/timeseries/asset-metrics'
        f'?assets={_CM_ASSET}'
        f'&metrics={_CM_METRIC}'
        f'&start_time={start_str}'
        f'&end_time={end_str}'
        f'&frequency=1d'
    )

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())

        if 'data' not in data:
            return []

        results = []
        for row in data['data']:
            time_str = row.get('time', '')
            val_str = row.get(_CM_METRIC, '')
            if not time_str or not val_str:
                continue
            # Parse ISO timestamp: '2026-08-04T00:00:00.000000000Z'
            dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            d = dt.date()
            val = float(val_str)
            if val > 0:
                results.append((d, round(val, 4)))

        return results

    except Exception as e:
        print(f'[MVRV] CoinMetrics fetch error: {e}')
        return []


# ── ahasignals.com scraping (fallback) ───────────────────────────────
_AHASIGNALS_URL = 'https://ahasignals.com/current-bitcoin-mvrv-z-score'


def _fetch_mvrv_ahasignals(timeout: int = 20) -> Tuple[Optional[float], Optional[date], str]:
    '''Scrape ahasignals.com for the latest MVRV ratio.

    Returns:
        (mvrv_value, source_date, source_name)
        On failure: (None, None, error_message)
    '''
    try:
        req = urllib.request.Request(_AHASIGNALS_URL, headers={
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode('utf-8', errors='replace')

        m = re.search(
            r'raw Bitcoin MVRV ratio is (\d+\.\d{2,3})',
            html, re.IGNORECASE
        )
        if m:
            mvrv_val = float(m.group(1))
            date_m = re.search(
                r'(August|Jul|Jun|May|Apr|Mar|Feb|Jan|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(202\d)',
                html
            )
            if date_m:
                month_map = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
                    'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
                    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                }
                month_str = date_m.group(0)[:3].lower()
                day = int(date_m.group(2))
                year = int(date_m.group(3))
                source_date = date(year, month_map.get(month_str, 8), day)
            else:
                source_date = date.today()
            return (mvrv_val, source_date, 'ahasignals/BGeometrics')

        m = re.search(r'MVRV RATIO\s+(\d+\.\d{2,3})', html, re.IGNORECASE)
        if m:
            return (float(m.group(1)), date.today(), 'ahasignals/BGeometrics')

        return (None, None, 'No MVRV pattern found in ahasignals page')

    except Exception as e:
        return (None, None, f'ahasignals error: {e}')


# ── Unified fetch: try CoinMetrics first, then ahasignals ─────────────

def fetch_mvrv_from_web(
    timeout: int = 15,
) -> Tuple[Optional[float], Optional[date], str]:
    '''Fetch latest MVRV. Tries CoinMetrics first, then ahasignals.

    Returns:
        (mvrv_value, source_date, source_name)
        On failure: (None, None, error_message)
    '''
    # 1) CoinMetrics Community API (fast, precise, structured)
    cm_data = fetch_mvrv_coinmetrics(timeout=timeout)
    if cm_data:
        newest_date, newest_val = cm_data[-1]
        print(f'[MVRV] CoinMetrics: {len(cm_data)} points, '
              f'latest={newest_val:.4f} ({newest_date})')
        return (newest_val, newest_date, 'CoinMetrics')

    # 2) ahasignals fallback (scraping)
    print('[MVRV] CoinMetrics failed, trying ahasignals...')
    mvrv_val, src_date, src = _fetch_mvrv_ahasignals(timeout=timeout + 10)
    if mvrv_val is not None:
        return (mvrv_val, src_date, src)

    return (None, None, f'All sources failed. CoinMetrics: no data; ahasignals: {src}')


def fetch_mvrv_series(
    days_back: int = 7,
    timeout: int = 15,
) -> List[Tuple[date, float]]:
    '''Fetch a short MVRV series (for gap-filling multiple days).

    Returns:
        List of (date, mvrv_value) tuples, newest last.
    '''
    start = date.today() - timedelta(days=days_back)
    return fetch_mvrv_coinmetrics(start_date=start, timeout=timeout)


# ── History append logic ──────────────────────────────────────────────

def append_mvrv_to_history(
    mvrv_value: float,
    target_date: date,
    history_path: Optional[str] = None,
) -> int:
    '''Append a new MVRV value to the embedded _mvrv_history.py file.

    Args:
        mvrv_value: The MVRV ratio to append.
        target_date: The date this value is for.
        history_path: Path to _mvrv_history.py. If None, uses default.

    Returns:
        Number of days appended (0 if already up-to-date).
    '''
    import os

    if history_path is None:
        history_path = os.path.join(
            os.path.dirname(__file__), '_mvrv_history.py'
        )

    from ._mvrv_history import MVRV_START_DATE, MVRV_DAILY_VALUES

    start = date.fromisoformat(MVRV_START_DATE)
    current_end = start + timedelta(days=len(MVRV_DAILY_VALUES) - 1)

    # Already have this date or newer
    if target_date <= current_end:
        print(f'[MVRV] History already covers {target_date} (ends {current_end})')
        return 0

    # Fill gaps between current_end and target_date
    days_to_add = (target_date - current_end).days
    if days_to_add <= 0:
        return 0

    new_values = []
    for i in range(1, days_to_add):
        new_values.append(MVRV_DAILY_VALUES[-1])
    new_values.append(round(mvrv_value, 4))

    # Read the file
    with open(history_path, 'r', encoding='utf-8') as f:
        content = f.read()

    bracket_pos = content.rfind(']')
    if bracket_pos == -1:
        print('[MVRV] ERROR: Could not find array end in _mvrv_history.py')
        return 0

    before_bracket = content[:bracket_pos].rstrip()
    after_bracket = content[bracket_pos:]

    new_entries = ', '.join(f'{v:.4f}' for v in new_values)

    new_content = before_bracket + ', ' + new_entries + after_bracket

    with open(history_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f'[MVRV] Appended {days_to_add} days to history '
          f'({current_end} → {target_date}, MVRV={mvrv_value:.4f})')

    # Invalidate the lookup cache
    import live_bot.strategy as strat
    if hasattr(strat, '_MVRV_LOOKUP'):
        strat._MVRV_LOOKUP = strat._build_mvrv_lookup()
        strat._MVRV_HISTORY_MAX = max(strat._MVRV_LOOKUP.keys())
        print(f'[MVRV] Lookup cache refreshed, new max: {strat._MVRV_HISTORY_MAX}')

    return days_to_add


def append_mvrv_series_to_history(
    series: List[Tuple[date, float]],
    history_path: Optional[str] = None,
) -> int:
    '''Append multiple MVRV values from a series to the history.

    Args:
        series: List of (date, mvrv_value) tuples, sorted ascending.
        history_path: Path to _mvrv_history.py.

    Returns:
        Total number of days appended.
    '''
    import os

    if history_path is None:
        history_path = os.path.join(
            os.path.dirname(__file__), '_mvrv_history.py'
        )

    if not series:
        return 0

    from ._mvrv_history import MVRV_START_DATE, MVRV_DAILY_VALUES

    start = date.fromisoformat(MVRV_START_DATE)
    current_end = start + timedelta(days=len(MVRV_DAILY_VALUES) - 1)

    # Filter to only dates newer than current_end
    new_entries = [(d, v) for d, v in series if d > current_end]
    if not new_entries:
        print(f'[MVRV] No entries newer than {current_end}')
        return 0

    # Build complete value list: fill gaps + new values
    new_values = []
    cursor = current_end
    for target_date, mvrv_value in new_entries:
        gap = (target_date - cursor).days
        # Fill gaps with last known value
        for _ in range(1, gap):
            new_values.append(MVRV_DAILY_VALUES[-1] if not new_values else new_values[-1])
        new_values.append(round(mvrv_value, 4))
        cursor = target_date

    if not new_values:
        return 0

    # Read and modify the file
    with open(history_path, 'r', encoding='utf-8') as f:
        content = f.read()

    bracket_pos = content.rfind(']')
    if bracket_pos == -1:
        print('[MVRV] ERROR: Could not find array end')
        return 0

    before_bracket = content[:bracket_pos].rstrip()
    after_bracket = content[bracket_pos:]

    entries_str = ', '.join(f'{v:.4f}' for v in new_values)
    new_content = before_bracket + ', ' + entries_str + after_bracket

    with open(history_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f'[MVRV] Appended {len(new_values)} days ({current_end} → {new_entries[-1][0]})')

    # Refresh cache
    import live_bot.strategy as strat
    if hasattr(strat, '_MVRV_LOOKUP'):
        strat._MVRV_LOOKUP = strat._build_mvrv_lookup()
        strat._MVRV_HISTORY_MAX = max(strat._MVRV_LOOKUP.keys())

    return len(new_values)


def try_update_mvrv(history_path: Optional[str] = None) -> Tuple[bool, str]:
    '''Try to fetch MVRV from web and append to history.

    Tries CoinMetrics first for a series of recent values, then
    falls back to ahasignals for a single value.

    Returns:
        (success: bool, message: str)
    '''
    from ._mvrv_history import MVRV_START_DATE, MVRV_DAILY_VALUES

    start = date.fromisoformat(MVRV_START_DATE)
    current_end = start + timedelta(days=len(MVRV_DAILY_VALUES) - 1)

    if current_end >= date.today():
        return (False, f'History already current (ends {current_end})')

    print(f'[MVRV] History ends {current_end}, attempting web fetch...')

    # Try CoinMetrics series first (can fill multiple days)
    cm_series = fetch_mvrv_coinmetrics(
        start_date=current_end,
        end_date=date.today(),
    )
    if cm_series:
        appended = append_mvrv_series_to_history(cm_series, history_path)
        if appended > 0:
            newest = cm_series[-1]
            return (True, f'CoinMetrics: appended {appended} days '
                          f'(MVRV={newest[1]:.4f} on {newest[0]})')
        return (False, 'CoinMetrics data not newer than local')

    # Fallback: ahasignals (single value)
    mvrv_val, source_date, source = _fetch_mvrv_ahasignals()
    if mvrv_val is None:
        return (False, f'Failed to fetch MVRV: {source}')

    print(f'[MVRV] ahasignals: MVRV={mvrv_val:.4f} for {source_date}')
    target = source_date or date.today()

    if target <= current_end:
        return (False, f'ahasignals data ({target}) not newer than local ({current_end})')

    appended = append_mvrv_to_history(mvrv_val, target, history_path)
    if appended > 0:
        return (True, f'ahasignals: appended {appended} days (MVRV={mvrv_val:.4f})')
    return (False, 'No new days to append')


if __name__ == '__main__':
    import os
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print('=== MVRV Web Fetcher ===')
    print()
    print('--- CoinMetrics (primary) ---')
    series = fetch_mvrv_coinmetrics()
    if series:
        print(f'Got {len(series)} data points:')
        for d, v in series:
            print(f'  {d}: {v:.4f}')
    else:
        print('No data from CoinMetrics')

    print()
    print('--- Unified fetch ---')
    mvrv, src_date, src = fetch_mvrv_from_web()
    if mvrv:
        print(f'MVRV: {mvrv:.4f} (date: {src_date}, source: {src})')
    else:
        print(f'Failed: {src}')
