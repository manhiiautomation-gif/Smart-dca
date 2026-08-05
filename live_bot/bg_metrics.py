"""BGeometrics on-chain metrics fetcher with file-based cache.

Fetches real on-chain data from BGeometrics API:
  - STH-SOPR (Short-Term Holder SOPR)
  - LTH Realized Price
  - Realized Price
  - aSOPR (all UTXO SOPR)
  - STH Realized Price

Cache strategy:
  - Full history cached in bg_cache.json (up to 5 years)
  - Live mode: incremental fetch if cache is stale (>12h old)
  - Backtest: load full cache, fetch only if missing
  - Rate limit: max 10 req/hr on free tier, tracked via timestamps

Usage:
    from live_bot.bg_metrics import get_sth_sopr, get_lth_realized_price, get_realized_price
    val = get_sth_sopr(date.today())  # returns float or NaN

    # Backtest: pre-load full history
    from live_bot.bg_metrics import ensure_cache, get_cached_series
    ensure_cache()  # fetches all metrics if cache missing/stale
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
}

# Max age before cache is considered stale (seconds)
_CACHE_FRESHNESS = 12 * 3600  # 12 hours

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
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        with os.fdopen(fd, 'w') as f:
            json.dump(cache, f)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
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


def _parse_series(raw: List[dict], json_key: str) -> Dict[str, float]:
    """Parse API response into {date_str: float} dict."""
    result = {}
    for row in raw:
        d_str = row.get('d', '')
        val = row.get(json_key)
        if not d_str or val is None:
            continue
        try:
            fval = float(val)
            if fval > 0 or not math.isnan(fval):
                result[d_str] = fval
        except (ValueError, TypeError):
            continue
    return result


# ── Public API: single-value lookups ────────────────────────────────────

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


def _get_metric_series(metric_name: str, cache=None, token=None) -> Optional[Dict[str, float]]:
    """Get full series for a metric, fetching if cache is stale."""
    tkn = token or _TOKEN
    if not tkn:
        return None

    if cache is None:
        cache = _load_cache()

    metrics = cache.get('metrics', {})
    metric_data = metrics.get(metric_name, {})

    # Check if cache has recent data
    if metric_data:
        dates_in_cache = sorted(metric_data.keys())
        newest = dates_in_cache[-1] if dates_in_cache else ''
        last_fetch = cache.get('last_fetch', {}).get(metric_name, '')

        # Cache is fresh if newest data is within 2 days and fetched recently
        if (newest and _days_ago(newest) <= 2
                and last_fetch and _seconds_ago(last_fetch) < _CACHE_FRESHNESS):
            return metric_data

    # Need to fetch
    endpoint, json_key = _METRIC_DEFS[metric_name]
    print(f'[BG] Fetching {metric_name} from BGeometrics...')
    raw = _fetch_endpoint(endpoint, tkn)
    if raw is None:
        # Return stale cache if available
        return metric_data if metric_data else None

    # Parse and merge with existing cache
    new_series = _parse_series(raw, json_key)
    if new_series:
        # Merge: new data overwrites old
        merged = {**metric_data, **new_series}

        # Trim to max 5 years (1826 days) from newest
        if merged:
            newest_date = max(merged.keys())
            cutoff = (date.fromisoformat(newest_date) - timedelta(days=1826)).isoformat()
            merged = {d: v for d, v in merged.items() if d >= cutoff}

        metrics[metric_name] = merged
        cache['metrics'] = metrics
        if 'last_fetch' not in cache:
            cache['last_fetch'] = {}
        cache['last_fetch'][metric_name] = datetime.now(timezone.utc).isoformat()
        _save_cache(cache)
        print(f'[BG] {metric_name}: cached {len(merged)} days '
              f'({min(merged.keys())} → {max(merged.keys())})')
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

def ensure_cache(token=None, metrics=None) -> dict:
    """Ensure cache is populated with full history for backtest.

    Fetches specified metrics (or all) if cache is missing/stale.
    Returns the full cache dict.

    Args:
        token: BGeometrics token (default: from env)
        metrics: list of metric names to fetch (default: core 3)
    """
    tkn = token or _TOKEN
    if not tkn:
        print('[BG] No BGEOMETRICS_TOKEN set, cannot fetch')
        return _load_cache()

    if metrics is None:
        metrics = ['sth_sopr', 'lth_realized_price', 'realized_price']

    cache = _load_cache()

    for metric_name in metrics:
        metric_data = cache.get('metrics', {}).get(metric_name, {})
        last_fetch = cache.get('last_fetch', {}).get(metric_name, '')

        # Skip if cache has data and is fresh
        if (metric_data and last_fetch
                and _seconds_ago(last_fetch) < _CACHE_FRESHNESS):
            print(f'[BG] {metric_name}: using cache ({len(metric_data)} days)')
            continue

        # Fetch
        endpoint, json_key = _METRIC_DEFS[metric_name]
        print(f'[BG] Fetching {metric_name} for backtest...')
        raw = _fetch_endpoint(endpoint, tkn)
        if raw is None:
            if metric_data:
                print(f'[BG] {metric_name}: using stale cache ({len(metric_data)} days)')
            else:
                print(f'[BG] {metric_name}: no data available')
            continue

        new_series = _parse_series(raw, json_key)
        if new_series:
            merged = {**metric_data, **new_series}
            # Trim to 5 years
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
