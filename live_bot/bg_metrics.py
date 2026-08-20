"""BGeometrics on-chain metrics fetcher with file-based cache.

Fetches real on-chain data from BGeometrics API:
  - STH-SOPR (Short-Term Holder SOPR)
  - LTH Realized Price
  - Realized Price
  - aSOPR (all UTXO SOPR)
  - STH Realized Price

Cache strategy:
  - Full history cached in bg_cache.json (up to 5 years)
  - Historical data is IMMUTABLE — never re-fetched once cached
  - Only fetches data AFTER the newest cached date (incremental gap-fill)
  - Live mode: fetches only if cache newest date < yesterday
  - Backtest: uses full cache as-is, fetches only missing tail
  - Rate limit: max 10 req/hr on free tier, tracked via timestamps
  - DAILY GUARD: get_all_metrics_today() fetches once per UTC day,
    then reuses in-memory snapshot for subsequent calls (0 API calls)
  - TYPICAL USAGE: 3 API calls/day (1 per metric) on first run,
    0 API calls on subsequent runs the same day

Usage:
    # RECOMMENDED: batch fetch (once per day, minimal API calls)
    from live_bot.bg_metrics import get_all_metrics_today
    m = get_all_metrics_today()  # {sth_sopr, lth_realized_price, realized_price, sopr_source}
    sopr_val = m['sth_sopr']

    # Legacy single lookups (still work but load cache independently)
    from live_bot.bg_metrics import get_sth_sopr, get_lth_realized_price, get_realized_price
    val = get_sth_sopr(date.today())

    # Backtest: pre-load full history
    from live_bot.bg_metrics import ensure_cache, get_cached_series
    ensure_cache()  # fetches only missing data (respects existing cache)
    series = get_cached_series('sth_sopr')  # {date: float, ...}
"""

import json
import os
import time
import math
import tempfile
from datetime import date, datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
import urllib.request


# ── Config ──────────────────────────────────────────────────────────────

_API_BASE = 'https://api.bgeometrics.com/v1'
_TOKEN = os.environ.get('BGEOMETRICS_TOKEN', '')

# Metric name mapping: (endpoint_path, json_key_in_response)
_METRIC_DEFS = {
    'sth_sopr':           ('sth-sopr',           'sthSopr'),
    'lth_sopr':           ('lth-sopr',           'lthSopr'),
    'sopr':               ('sopr',               'sopr'),
    'lth_realized_price': ('lth-realized-price', 'lthRealizedPrice'),
    'sth_realized_price': ('sth-realized-price', 'sthRealizedPrice'),
    'realized_price':     ('realized-price',     'realizedPrice'),
    'mvrv':               ('mvrv',               'mvrv'),
    'mvrv_zscore':        ('mvrv-zscore',        'mvrvZscore'),
}

# Metrics where the API historically returned only a few recent values.
# NOTE: BG now returns full history for most metrics.  Keeping sth_realized_price
# only because it's not used in live mode and rarely needs full history.
_SINGLE_VALUE_METRICS = {'sth_realized_price'}

# For live mode: how far back from today we consider "needs fresh data"
# If cache newest date >= (today - LIVE_FRESHNESS_DAYS), skip fetch
# BG API data is inherently 1-2 days behind, so 3 days avoids unnecessary fetches
# while keeping data within D-2 to D-4 range (acceptable for daily DCA).
_LIVE_FRESHNESS_DAYS = 3  # cache covers up to yesterday = fresh enough

# Rate limit tracking
_MAX_REQUESTS_PER_HOUR = 10
_request_times: List[float] = []  # timestamps of recent requests


def _get_cache_path() -> str:
    """Path to cache file (next to state.json)."""
    # Same dir as this module
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bg_cache.json')


def _load_cache() -> dict:
    """Load cache from disk."""
    path = _get_cache_path()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {'metrics': {}, 'request_log': []}


def _save_cache(cache: dict):
    """Save cache to disk atomically."""
    path = _get_cache_path()
    dir_name = os.path.dirname(path) or '.'
    os.makedirs(dir_name, exist_ok=True)
    tmp_path = None                                   # D-09: init before try
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        with os.fdopen(fd, 'w') as f:
            json.dump(cache, f)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path is not None and os.path.exists(tmp_path):  # D-09: guard NameError
            os.unlink(tmp_path)
        raise


def _can_make_request() -> bool:
    """Check if we can make an API request without exceeding rate limit."""
    now = time.time()
    # Clean old entries (older than 1 hour)
    global _request_times
    _request_times = [t for t in _request_times if now - t < 3600]
    return len(_request_times) < _MAX_REQUESTS_PER_HOUR


def _record_request():
    """Record that we made an API request."""
    global _request_times
    _request_times.append(time.time())


def _fetch_endpoint(endpoint: str, token: str, timeout: int = 20) -> Optional[List[dict]]:
    """Fetch data from a BGeometrics endpoint.

    Returns list of raw records, or None on failure.
    """
    if not _can_make_request():
        print(f'[BG] Rate limited ({len(_request_times)}/{_MAX_REQUESTS_PER_HOUR} in last hour). Skipping.')
        return None

    url = f'{_API_BASE}/{endpoint}?token={token}'
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
        })
        _record_request()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())

        if isinstance(data, dict) and 'error' in data:
            print(f'[BG] API error: {data["error"]}')
            return None

        if not isinstance(data, list) or len(data) == 0:
            print(f'[BG] No data from {endpoint}')
            return None

        return data

    except Exception as e:
        print(f'[BG] Fetch error ({endpoint}): {e}')
        return None


def _parse_series(raw: List[dict], json_key: str, metric_name: str = '') -> Dict[str, float]:
    """Parse API response into {date_str: float} dict.

    Smart key detection: if the expected json_key yields 0 results,
    auto-detect the value key by finding the first non-'d' key
    with numeric values.
    """
    result = {}
    for row in raw:
        d_str = row.get('d', '')
        val = row.get(json_key)
        if not d_str or val is None:
            continue
        try:
            fval = float(val)
            if not math.isnan(fval):
                result[d_str] = fval
        except (ValueError, TypeError):
            continue

    # Smart fallback: if expected key yielded nothing, try auto-detect
    if not result and len(raw) > 0:
        sample = raw[0]
        for key, val in sample.items():
            if key == 'd':
                continue
            # Try this key
            candidate = {}
            for row in raw:
                d_str = row.get('d', '')
                v = row.get(key)
                if not d_str or v is None:
                    continue
                try:
                    fval = float(v)
                    if not math.isnan(fval):
                        candidate[d_str] = fval
                except (ValueError, TypeError):
                    continue
            if len(candidate) > len(result):
                result = candidate
                if metric_name:
                    print(f'[BG] {metric_name}: auto-detected key "{key}" ' +
                          f'(expected "{json_key}", got {len(result)} records)')

    return result


# ── Public API: cache-only lookup (ZERO API calls) ─────────────────

def get_cached_value(metric_name: str, target_date=None) -> float:
    """Look up a single metric from DISK CACHE ONLY.  Never calls the API.

    Use this for early/preview reads where you want to avoid triggering
    any network requests.  The actual fetch is deferred to
    get_all_metrics_today() later in the pipeline.

    Args:
        metric_name: e.g. 'mvrv', 'mvrv_zscore', 'sth_sopr'
        target_date: date to look up (default: today)

    Returns:
        float value, or NaN if not in cache.
    """
    if target_date is None:
        target_date = date.today()
    cache = _load_cache()
    series = cache.get('metrics', {}).get(metric_name, {})
    if not series:
        return float('nan')
    return _lookup(series, target_date)


# ── Public API: batch fetch (1 API call per metric, once per day) ─────

# In-memory daily snapshot: once populated, reused for the rest of the day
_daily_snapshot: Optional[Dict[str, float]] = None
_daily_snapshot_date: Optional[str] = None


def get_all_metrics_today(
    target_date=None,
    token=None,
    force_refetch: bool = False,
) -> Dict[str, float]:
    """Fetch ALL on-chain metrics for today in ONE batch.

    Daily guard: if we already fetched today (same UTC date), returns
    cached snapshot immediately — ZERO API calls.

    Args:
        target_date: date to look up (default: today)
        token: BGeometrics token (default: from env)
        force_refetch: ignore daily guard, re-fetch from API

    Returns:
        Dict with keys: sth_sopr, lth_realized_price, realized_price, sopr_source
        Values are float (NaN if unavailable).
    """
    global _daily_snapshot, _daily_snapshot_date

    if target_date is None:
        target_date = date.today()
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    # Daily guard: reuse today's snapshot
    if (not force_refetch
            and _daily_snapshot is not None
            and _daily_snapshot_date == today_utc):
        print(f'[BG] Using today\'s snapshot (fetched at {_daily_snapshot_date})')
        result = {}
        for metric_name in ['sth_sopr', 'lth_realized_price', 'realized_price', 'mvrv', 'mvrv_zscore']:
            val = _lookup_from_snapshot(metric_name, target_date)
            result[metric_name] = val
        # Update source tags based on whether we actually found values
        result['sopr_source'] = 'cache' if not math.isnan(result.get('sth_sopr', float('nan'))) else _daily_snapshot.get('sopr_source', 'N/A')
        result['mvrv_source'] = 'cache' if not math.isnan(result.get('mvrv', float('nan'))) else _daily_snapshot.get('mvrv_source', 'N/A')
        return result

    tkn = token or _TOKEN
    metrics_to_fetch = ['sth_sopr', 'lth_realized_price', 'realized_price', 'mvrv', 'mvrv_zscore']

    if not tkn:
        print('[BG] No BGEOMETRICS_TOKEN — reading from cache only')
        cache = _load_cache()
        snapshot = {}
        for metric_name in ['sth_sopr', 'lth_realized_price', 'realized_price', 'mvrv', 'mvrv_zscore']:
            series = cache.get('metrics', {}).get(metric_name, {})
            snapshot[metric_name] = _lookup(series, target_date) if series else float('nan')
        snapshot['sopr_source'] = 'cache' if not math.isnan(snapshot.get('sth_sopr', float('nan'))) else 'no-token'
        snapshot['mvrv_source'] = 'cache' if not math.isnan(snapshot.get('mvrv', float('nan'))) else 'no-token'
        _daily_snapshot = snapshot
        _daily_snapshot_date = today_utc
        return dict(snapshot)

    # Load cache ONCE for all metrics
    cache = _load_cache()
    api_calls_made = 0
    series_cache = {}  # metric_name -> {date_str: float}

    for metric_name in metrics_to_fetch:
        metric_data = cache.get('metrics', {}).get(metric_name, {})

        if not _needs_incremental_fetch(metric_data, metric_name=metric_name):
            newest = max(metric_data.keys()) if metric_data else 'N/A'
            print(f'[BG] {metric_name}: cache fresh ({len(metric_data)}d, newest={newest})')
            series_cache[metric_name] = metric_data
            continue

        # Fetch from API
        endpoint, json_key = _METRIC_DEFS[metric_name]
        newest_cached = max(metric_data.keys()) if metric_data else 'empty'
        print(f'[BG] {metric_name}: cache ends {newest_cached}, fetching...')
        raw = _fetch_endpoint(endpoint, tkn)
        if raw is None:
            print(f'[BG] {metric_name}: fetch failed, using stale cache')
            series_cache[metric_name] = metric_data
            continue

        api_calls_made += 1
        new_series = _parse_series(raw, json_key, metric_name=metric_name)
        if new_series:
            merged = _merge_and_trim(metric_data, new_series, metric_name, cache)
            series_cache[metric_name] = merged
            cache = _load_cache()  # re-read after save
            print(f'[BG] {metric_name}: cached successfully ({len(new_series)} new records)')
        else:
            print(f'[BG] {metric_name}: API returned no usable data (key={json_key})')
            series_cache[metric_name] = metric_data

    # Build snapshot with values for target_date
    snapshot = {}
    for metric_name in metrics_to_fetch:
        series = series_cache.get(metric_name, {})
        snapshot[metric_name] = _lookup(series, target_date) if series else float('nan')
    snapshot['sopr_source'] = 'BG' if not math.isnan(snapshot.get('sth_sopr', float('nan'))) else 'cache-stale'
    snapshot['mvrv_source'] = 'BG' if not math.isnan(snapshot.get('mvrv', float('nan'))) else 'cache-stale'
    snapshot['mvrv_z_source'] = 'BG' if not math.isnan(snapshot.get('mvrv_zscore', float('nan'))) else 'embedded-365d'

    # Store in memory for the rest of the day
    _daily_snapshot = snapshot
    _daily_snapshot_date = today_utc

    print(f'[BG] Batch complete: {api_calls_made} API calls, '
          f'snapshot cached for {today_utc}')
    return dict(snapshot)


def _lookup_from_snapshot(metric_name: str, target_date) -> float:
    """Look up a metric value from the full cache for a specific date.

    Used by get_all_metrics_today() when reusing a daily snapshot
    to get the value for a possibly different target_date.
    """
    cache = _load_cache()
    series = cache.get('metrics', {}).get(metric_name, {})
    if series:
        return _lookup(series, target_date)
    return float('nan')


def invalidate_daily_snapshot():
    """Force next call to get_all_metrics_today() to re-fetch from API."""
    global _daily_snapshot, _daily_snapshot_date
    _daily_snapshot = None
    _daily_snapshot_date = None


# ── Public API: single-value lookups (legacy, still work) ──────────────

def get_sth_sopr(target_date, cache=None, token=None) -> float:
    """Get STH-SOPR for a specific date. Returns NaN if unavailable."""
    series = _get_metric_series('sth_sopr', cache, token)
    if series is None:
        return float('nan')
    return _lookup(series, target_date)


def get_lth_realized_price(target_date, cache=None, token=None) -> float:
    """Get LTH Realized Price for a specific date. Returns NaN if unavailable."""
    series = _get_metric_series('lth_realized_price', cache, token)
    if series is None:
        return float('nan')
    return _lookup(series, target_date)


def get_realized_price(target_date, cache=None, token=None) -> float:
    """Get Realized Price for a specific date. Returns NaN if unavailable."""
    series = _get_metric_series('realized_price', cache, token)
    if series is None:
        return float('nan')
    return _lookup(series, target_date)


def get_sopr(target_date, cache=None, token=None) -> float:
    """Get aSOPR for a specific date. Returns NaN if unavailable."""
    series = _get_metric_series('sopr', cache, token)
    if series is None:
        return float('nan')
    return _lookup(series, target_date)


def _merge_and_trim(metric_data: Dict[str, float], new_series: Dict[str, float], metric_name: str, cache: dict) -> Dict[str, float]:
    """Merge new data into existing cache, trim to 5 years, save to disk."""
    merged = {**metric_data, **new_series}

    # Trim to max 5 years (1826 days) from newest
    if merged:
        newest_date = max(merged.keys())
        cutoff = (date.fromisoformat(newest_date) - timedelta(days=1826)).isoformat()
        merged = {d: v for d, v in merged.items() if d >= cutoff}

    if 'metrics' not in cache:
        cache['metrics'] = {}
    cache['metrics'][metric_name] = merged
    if 'last_fetch' not in cache:
        cache['last_fetch'] = {}
    cache['last_fetch'][metric_name] = datetime.now(timezone.utc).isoformat()
    _save_cache(cache)
    print(f'[BG] {metric_name}: cached {len(merged)} days '
          f'({min(merged.keys())} → {max(merged.keys())})')
    return merged


def _needs_incremental_fetch(metric_data: Dict[str, float], metric_name: str = '', min_days: int = 30) -> bool:
    """Check if there's a gap between cached data and today.

    Historical data is immutable, so we ONLY fetch if the cache doesn't
    reach recent dates. Returns True if we need to fetch.

    Args:
        metric_data: existing cached {date_str: float} dict
        metric_name: metric name (used to detect single-value metrics)
        min_days: minimum days of data to consider cache "complete enough"
                   to skip re-fetch. If cache has fewer days, it's likely
                   a failed partial fetch (e.g. only 1 day due to key mismatch).
    """
    # Single-value metrics (mvrv_zscore, etc.) only need 1 cached day
    effective_min = 1 if metric_name in _SINGLE_VALUE_METRICS else min_days

    if not metric_data or len(metric_data) < effective_min:
        return True  # No data or too little — must fetch

    newest = max(metric_data.keys())
    gap_days = _days_ago(newest)

    if gap_days <= _LIVE_FRESHNESS_DAYS:
        return False

    return True


def _get_metric_series(metric_name: str, cache=None, token=None) -> Optional[Dict[str, float]]:
    """Get full series for a metric, fetching only if gap detected.

    Key behavior: HISTORICAL DATA IS NEVER RE-FETCHED.
    Only the gap between newest cached date and today is filled.
    """
    tkn = token or _TOKEN
    if not tkn:
        return None

    if cache is None:
        cache = _load_cache()

    metrics = cache.get('metrics', {})
    metric_data = metrics.get(metric_name, {})

    # Check if we need to fetch (only for missing recent data)
    if not _needs_incremental_fetch(metric_data, metric_name=metric_name):
        return metric_data

    # Need to fetch — but API returns ALL history, we just merge
    endpoint, json_key = _METRIC_DEFS[metric_name]
    newest_cached = max(metric_data.keys()) if metric_data else ''
    print(f'[BG] {metric_name}: cache ends {newest_cached}, fetching incremental...')
    raw = _fetch_endpoint(endpoint, tkn)
    if raw is None:
        # Return existing cache even if stale
        return metric_data if metric_data else None

    # Parse and merge
    new_series = _parse_series(raw, json_key, metric_name=metric_name)
    if new_series:
        merged = _merge_and_trim(metric_data, new_series, metric_name, cache)
        return merged

    return metric_data if metric_data else None


def _lookup(series: Dict[str, float], target_date) -> float:
    """Look up a value for a date, with 1-day fallback."""
    if isinstance(target_date, date):
        d_str = target_date.isoformat()
    else:
        d_str = str(target_date)[:10]

    if d_str in series:
        return series[d_str]

    # 1-day fallback (API data might be 1 day behind)
    try:
        d = date.fromisoformat(d_str) - timedelta(days=1)
        fb = d.isoformat()
        if fb in series:
            return series[fb]
    except (ValueError, TypeError):
        pass

    return float('nan')


def _days_ago(date_str: str) -> int:
    """Days since a date string."""
    try:
        return (date.today() - date.fromisoformat(date_str)).days
    except (ValueError, TypeError):
        return 999


def _seconds_ago(iso_str: str) -> float:
    """Seconds since an ISO timestamp."""
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except (ValueError, TypeError):
        return 999999


# ── Public API: backtest support ────────────────────────────────────────

def ensure_cache(token=None, metrics=None, force_refetch=False) -> dict:
    """Ensure cache is populated for backtest.

    SMART FETCH: Only fetches if there's a gap between cached data and today.
    Historical data (already in cache) is NEVER re-fetched.
    Use force_refetch=True only if you suspect data corruption.

    Args:
        token: BGeometrics token (default: from env)
        metrics: list of metric names to fetch (default: core 3)
        force_refetch: if True, ignore cache and re-fetch everything

    Returns:
        The full cache dict.
    """
    tkn = token or _TOKEN
    if not tkn:
        print('[BG] No BGEOMETRICS_TOKEN set, cannot fetch')
        return _load_cache()

    if metrics is None:
        metrics = ['sth_sopr', 'lth_realized_price', 'realized_price', 'mvrv', 'mvrv_zscore']

    cache = _load_cache()

    for metric_name in metrics:
        metric_data = cache.get('metrics', {}).get(metric_name, {})

        if force_refetch:
            # Wipe and re-fetch
            print(f'[BG] {metric_name}: force re-fetching...')
            metric_data = {}
        elif not _needs_incremental_fetch(metric_data, metric_name=metric_name):
            # Cache has recent data — no fetch needed
            newest = max(metric_data.keys()) if metric_data else 'N/A'
            print(f'[BG] {metric_name}: using cache ({len(metric_data)} days, newest={newest})')
            continue

        # Need to fetch (first time or gap detected)
        endpoint, json_key = _METRIC_DEFS[metric_name]
        newest_cached = max(metric_data.keys()) if metric_data else 'empty'
        print(f'[BG] {metric_name}: cache ends {newest_cached}, fetching...')
        raw = _fetch_endpoint(endpoint, tkn)
        if raw is None:
            if metric_data:
                print(f'[BG] {metric_name}: fetch failed, using existing cache ({len(metric_data)} days)')
            else:
                print(f'[BG] {metric_name}: no data available')
            continue

        new_series = _parse_series(raw, json_key, metric_name=metric_name)
        if new_series:
            _merge_and_trim(metric_data, new_series, metric_name, cache)
            cache = _load_cache()  # re-read after save
        else:
            print(f'[BG] {metric_name}: API returned no usable data')

    return cache


def get_cached_series(metric_name: str, cache=None) -> Dict[str, float]:
    """Get full cached series for a metric.

    Returns {date_str: float} dict. Empty dict if not cached.
    """
    if cache is None:
        cache = _load_cache()
    return dict(cache.get('metrics', {}).get(metric_name, {}))


def get_cached_series_as_dates(metric_name: str, cache=None) -> Dict[date, float]:
    """Get full cached series with date objects as keys."""
    raw = get_cached_series(metric_name, cache)
    return {date.fromisoformat(d): v for d, v in raw.items()}


def cache_info() -> dict:
    """Return info about current cache state."""
    cache = _load_cache()
    info = {'metrics': {}}
    for name, data in cache.get('metrics', {}).items():
        if data:
            dates = sorted(data.keys())
            info['metrics'][name] = {
                'days': len(data),
                'range': f'{dates[0]} → {dates[-1]}' if dates else 'empty',
                'last_fetch': cache.get('last_fetch', {}).get(name, 'never'),
            }
    return info


if __name__ == '__main__':
    import sys
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print('=== BGeometrics Cache Manager ===')
    print()

    if not _TOKEN:
        print('WARNING: BGEOMETRICS_TOKEN not set')
        print('Set it via: export BGEOMETRICS_TOKEN=your_token')
        sys.exit(1)

    # Fetch core metrics
    print('Fetching core metrics (STH-SOPR, LTH-RP, RP)...')
    cache = ensure_cache()

    print()
    info = cache_info()
    for name, minfo in info['metrics'].items():
        print(f'  {name}: {minfo["days"]}d {minfo["range"]}')

    # Demo lookups
    print()
    today = date.today()
    print(f'STH-SOPR ({today}): {get_sth_sopr(today)}')
    print(f'LTH-RP ({today}):   {get_lth_realized_price(today)}')
    print(f'RP ({today}):       {get_realized_price(today)}')
