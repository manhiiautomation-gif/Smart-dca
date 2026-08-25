"""Binance Spot API client for Phoenix v5.1 bot.

Supports: get price, get klines, get balance, market buy, market sell.
All trading in USDT (BTCUSDT pair).
Includes retry with exponential backoff and proper klines pagination.
Auto-fallback chain when Binance returns 451 (geo-blocked):
  1. Kraken  2. KuCoin  3. CoinCap  4. CoinGecko
"""

import time
import hmac
import hashlib
import requests
from datetime import datetime, timezone, timedelta


# ═══════════════════════════════════════════════════════════════════
# FALLBACK PRICE SOURCES — when Binance geo-blocks (HTTP 451)
# ═══════════════════════════════════════════════════════════════════

def _safe_request(func, label: str) -> requests.Response:
    """Try an HTTP request; return resp or raise with label info."""
    try:
        resp = func()
        resp.raise_for_status()
        return resp
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else '?'
        print(f'[{label}] HTTP {code}')
        raise
    except (requests.Timeout, requests.ConnectionError) as e:
        print(f'[{label}] {type(e).__name__}: {e}')
        raise


def get_price_kraken() -> float:
    """Fetch BTC/USD price from Kraken public API."""
    resp = _safe_request(
        lambda: requests.get(
            'https://api.kraken.com/0/public/Ticker',
            params={'pair': 'XBTUSD'}, timeout=10
        ), 'Kraken-price'
    )
    data = resp.json()
    # Kraken returns XXBTZUSD key for BTC/USD
    for key in data['result']:
        return float(data['result'][key]['c'][0])
    raise ValueError('No price data in Kraken response')


def get_price_kucoin() -> float:
    """Fetch BTC/USDT price from KuCoin public API."""
    resp = _safe_request(
        lambda: requests.get(
            'https://api.kucoin.com/api/v1/market/orderbook/level1',
            params={'symbol': 'BTC-USDT'}, timeout=10
        ), 'KuCoin-price'
    )
    return float(resp.json()['data']['price'])


def get_price_coincap() -> float:
    """Fetch BTC/USD price from CoinCap."""
    resp = _safe_request(
        lambda: requests.get(
            'https://api.coincap.io/v2/assets/bitcoin', timeout=10
        ), 'CoinCap-price'
    )
    return float(resp.json()['data']['priceUsd'])


def get_price_coingecko() -> float:
    """Fetch BTC/USD price from CoinGecko."""
    resp = _safe_request(
        lambda: requests.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={'ids': 'bitcoin', 'vs_currencies': 'usd'}, timeout=15
        ), 'CoinGecko-price'
    )
    return float(resp.json()['bitcoin']['usd'])


def get_price_fallback() -> float:
    """Try multiple free APIs for BTC price until one works.

    Order: Kraken -> KuCoin -> CoinCap -> CoinGecko
    """
    sources = [
        ('Kraken', get_price_kraken),
        ('KuCoin', get_price_kucoin),
        ('CoinCap', get_price_coincap),
        ('CoinGecko', get_price_coingecko),
    ]
    for name, func in sources:
        try:
            price = func()
            print(f'[FALLBACK] Price from {name}: {price:,.2f}')
            return price
        except Exception:
            continue
    raise RuntimeError('All price fallbacks failed (Kraken, KuCoin, CoinCap, CoinGecko)')


# ═══════════════════════════════════════════════════════════════════
# FALLBACK KLINES SOURCES
# ═══════════════════════════════════════════════════════════════════

def get_klines_kraken(days: int = 500) -> list:
    """Fetch daily BTC/USD OHLC from Kraken.

    Kraken returns max 720 candles per request.
    Returns list of {'date': date, 'close': float} sorted oldest-first.
    """
    all_candles = []
    # Kraken uses Unix timestamp in seconds for 'since' param
    # Work backwards from now
    end_ts = int(datetime.now(timezone.utc).timestamp())
    remaining = days

    while remaining > 0:
        batch_size = min(720, remaining)
        # Calculate start time
        start_ts = end_ts - (batch_size + 1) * 86400

        resp = _safe_request(
            lambda s=start_ts, e=end_ts: requests.get(
                'https://api.kraken.com/0/public/OHLC',
                params={'pair': 'XBTUSD', 'interval': '1440', 'since': s},
                timeout=30
            ), 'Kraken-klines'
        )
        data = resp.json()
        # Kraken returns {'result': {'XXBTZUSD': [...], 'last': 12345}}
        pair_key = [k for k in data['result'].keys() if k != 'last'][0]
        ohlc_list = data['result'][pair_key]

        for candle in ohlc_list:
            # [time, open, high, low, close, vwap, volume, count]
            dt = datetime.fromtimestamp(int(float(candle[0])), tz=timezone.utc).date()
            close = float(candle[4])
            all_candles.append({'date': dt, 'close': close})

        if len(ohlc_list) == 0:
            break

        # Move end_ts to before the earliest candle
        earliest = min(int(float(c[0])) for c in ohlc_list)
        end_ts = earliest - 1
        remaining -= len(ohlc_list)

        if len(ohlc_list) < batch_size:
            break

    # Deduplicate and sort
    seen = {}
    for c in all_candles:
        seen[c['date']] = c
    result = sorted(seen.values(), key=lambda x: x['date'])
    return result[-days:]


def get_klines_kucoin(days: int = 500) -> list:
    """Fetch daily BTC/USDT candles from KuCoin.

    KuCoin returns max 300 candles per request, newest first.
    All values are strings, time is in seconds.
    Returns list of {'date': date, 'close': float} sorted oldest-first.
    """
    all_candles = []
    remaining = days
    last_end_ts = None

    while remaining > 0:
        params = {'type': '1day', 'symbol': 'BTC-USDT'}
        if last_end_ts is not None:
            params['endAt'] = str(last_end_ts)

        resp = _safe_request(
            lambda p=params: requests.get(
                'https://api.kucoin.com/api/v1/market/candles',
                params=p, timeout=30
            ), 'KuCoin-klines'
        )
        data = resp.json().get('data', [])
        if not data:
            break

        for candle in data:
            # [time_s_as_str, open, close, high, low, volume, turnover]
            dt = datetime.fromtimestamp(int(float(candle[0])), tz=timezone.utc).date()
            close = float(candle[2])
            all_candles.append({'date': dt, 'close': close})

        # KuCoin returns newest-first; earliest is the last element
        earliest_ts = int(float(data[-1][0]))
        if last_end_ts is not None and earliest_ts >= last_end_ts:
            break
        last_end_ts = earliest_ts
        remaining -= len(data)

        if len(data) < 200:
            break

    # Deduplicate and sort oldest-first
    seen = {}
    for c in all_candles:
        seen[c['date']] = c
    result = sorted(seen.values(), key=lambda x: x['date'])
    return result[-days:]


def get_klines_coincap(days: int = 500) -> list:
    """Fetch daily BTC/USD history from CoinCap.

    Returns list of {'date': date, 'close': float} sorted oldest-first.
    """
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = now_ms - (days + 1) * 86400000
    resp = _safe_request(
        lambda: requests.get(
            'https://api.coincap.io/v2/assets/bitcoin/history',
            params={'interval': 'd1', 'start': start_ms, 'end': now_ms},
            timeout=30
        ), 'CoinCap-klines'
    )
    data = resp.json()['data']
    candles = []
    for item in data:
        dt = datetime.fromtimestamp(item['time'] / 1000, tz=timezone.utc).date()
        candles.append({'date': dt, 'close': float(item['priceUsd'])})
    seen = {}
    for c in candles:
        seen[c['date']] = c
    result = sorted(seen.values(), key=lambda x: x['date'])
    return result[-days:]


def get_klines_coingecko(days: int = 500) -> list:
    """Fetch daily BTC/USD klines from CoinGecko market_chart."""
    resp = _safe_request(
        lambda: requests.get(
            'https://api.coingecko.com/api/v3/coins/bitcoin/market_chart',
            params={'vs_currency': 'usd', 'days': days, 'interval': 'daily'},
            timeout=30
        ), 'CoinGecko-klines'
    )
    data = resp.json()
    candles = []
    for ts_ms, price in data.get('prices', []):
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
        candles.append({'date': dt, 'close': float(price)})
    seen = {}
    for c in candles:
        seen[c['date']] = c
    result = sorted(seen.values(), key=lambda x: x['date'])
    return result[-days:]


def get_klines_fallback(days: int = 500) -> list:
    """Try multiple free APIs for daily BTC klines until one works.

    Order: Kraken -> KuCoin -> CoinCap -> CoinGecko
    """
    sources = [
        ('Kraken', get_klines_kraken),
        ('KuCoin', get_klines_kucoin),
        ('CoinCap', get_klines_coincap),
        ('CoinGecko', get_klines_coingecko),
    ]
    for name, func in sources:
        try:
            klines = func(days)
            min_required = min(days, 50)
            if len(klines) < min_required:
                print(f'[{name}] Only {len(klines)} candles, need {min_required}+')
                continue
            print(f'[FALLBACK] Klines from {name}: {len(klines)} candles')
            return klines
        except Exception as e:
            print(f'[{name}] Failed: {type(e).__name__}')
            continue
    raise RuntimeError('All klines fallbacks failed')


# ═══════════════════════════════════════════════════════════════════
# BINANCE RETRY HELPER
# ═══════════════════════════════════════════════════════════════════

def _retry_request(func, max_retries=3, base_delay=1.0):
    """Execute an HTTP request with exponential backoff retry.

    Retries on: timeout, connection error, HTTP 429 (rate limit), HTTP 5xx.
    Does NOT retry on 4xx (client errors like bad signature, insufficient funds).
    """
    for attempt in range(max_retries):
        try:
            resp = func()
            if resp.status_code == 429:
                retry_after = int(resp.headers.get('Retry-After', base_delay * (2 ** attempt)))
                print(f'[BINANCE] Rate limited (429). Retrying in {retry_after}s... (attempt {attempt+1}/{max_retries})')
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                delay = base_delay * (2 ** attempt)
                print(f'[BINANCE] Server error ({resp.status_code}). Retrying in {delay}s... (attempt {attempt+1}/{max_retries})')
                time.sleep(delay)
                continue
            return resp
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f'[BINANCE] {type(e).__name__}: {e}. Retrying in {delay}s... (attempt {attempt+1}/{max_retries})')
            time.sleep(delay)
    return func()


# ═══════════════════════════════════════════════════════════════════
# BINANCE CLIENT
# ═══════════════════════════════════════════════════════════════════

class BinanceClient:
    BASE_URL = 'https://api.binance.com'
    SYMBOL = 'BTCUSDT'

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def _sign(self, params: dict) -> dict:
        """Add signature and recvWindow to query params for authenticated requests."""
        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 5000
        qs = '&'.join(f'{k}={v}' for k, v in sorted(params.items()))
        params['signature'] = hmac.new(
            self.api_secret.encode(), qs.encode(), hashlib.sha256
        ).hexdigest()
        return params

    def _headers(self) -> dict:
        return {'X-MBX-APIKEY': self.api_key}

    def get_price(self) -> float:
        """Current BTC price in USDT. Falls back on 451 (geo-blocked)."""
        try:
            resp = _retry_request(lambda: requests.get(
                f'{self.BASE_URL}/api/v3/ticker/price',
                params={'symbol': self.SYMBOL}, timeout=10
            ))
            resp.raise_for_status()
            return float(resp.json()['price'])
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 451:
                print('[BINANCE] Geo-blocked (451). Switching to fallback APIs...')
                return get_price_fallback()
            raise

    def get_klines(self, days: int = 500) -> list:
        """Get daily klines with pagination. Falls back on 451 (geo-blocked).

        Returns list of {'date': date, 'close': float} sorted oldest-first.
        """
        try:
            return self._get_klines_binance(days)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 451:
                print('[BINANCE] Geo-blocked (451). Switching to fallback APIs...')
                return get_klines_fallback(days)
            raise

    def _get_klines_binance(self, days: int = 500) -> list:
        """Internal: fetch klines from Binance only."""
        all_candles = []
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        remaining = days

        while remaining > 0:
            limit = min(1000, remaining)
            resp = _retry_request(lambda et=end_time, lim=limit: requests.get(
                f'{self.BASE_URL}/api/v3/klines',
                params={
                    'symbol': self.SYMBOL,
                    'interval': '1d',
                    'limit': lim,
                    'endTime': et,
                },
                timeout=15
            ))
            resp.raise_for_status()
            candles = resp.json()
            if not candles:
                break

            for c in candles:
                dt = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).date()
                all_candles.append({'date': dt, 'close': float(c[4])})

            earliest_time = candles[0][0] - 1
            end_time = earliest_time
            remaining -= len(candles)

            if len(candles) < limit:
                break

        all_candles.sort(key=lambda x: x['date'])
        return all_candles

    def get_balance(self, asset: str = 'BTC') -> float:
        """Free balance of an asset."""
        params = self._sign({})
        resp = _retry_request(lambda: requests.get(
            f'{self.BASE_URL}/api/v3/account',
            params=params, headers=self._headers(), timeout=10
        ))
        resp.raise_for_status()
        for b in resp.json()['balances']:
            if b['asset'] == asset:
                return float(b['free'])
        return 0.0

    def get_usdt_balance(self) -> float:
        """Free USDT balance."""
        return self.get_balance('USDT')

    def market_buy(self, quote_amount: float) -> dict:
        """Market buy BTC using quote_amount USDT."""
        params = self._sign({
            'symbol': self.SYMBOL,
            'side': 'BUY',
            'type': 'MARKET',
            'quoteOrderQty': f'{quote_amount:.2f}',
        })
        resp = _retry_request(lambda: requests.post(
            f'{self.BASE_URL}/api/v3/order',
            params=params, headers=self._headers(), timeout=15
        ))
        resp.raise_for_status()
        data = resp.json()
        # Check Binance application-level error (HTTP 200 with error code)
        if isinstance(data, dict) and 'code' in data:
            raise RuntimeError(f"Binance API error {data['code']}: {data.get('msg', '')}")
        # Extract actual fee from fills array (quote currency only)
        total_fee = 0.0
        for fill in data.get('fills', []):
            if fill.get('commissionAsset') == 'USDT':
                total_fee += float(fill.get('commission', 0))
        return {
            'executed_qty': float(data['executedQty']),
            'cummulative_quote_qty': float(data['cummulativeQuoteQty']),
            'fee': total_fee,
            'status': data['status'],
        }

    def market_sell(self, btc_amount: float) -> dict:
        """Market sell BTC."""
        qty_str = f'{btc_amount:.6f}'
        params = self._sign({
            'symbol': self.SYMBOL,
            'side': 'SELL',
            'type': 'MARKET',
            'quantity': qty_str,
        })
        resp = _retry_request(lambda: requests.post(
            f'{self.BASE_URL}/api/v3/order',
            params=params, headers=self._headers(), timeout=15
        ))
        resp.raise_for_status()
        data = resp.json()
        # Check Binance application-level error (HTTP 200 with error code)
        if isinstance(data, dict) and 'code' in data:
            raise RuntimeError(f"Binance API error {data['code']}: {data.get('msg', '')}")
        # Extract actual fee from fills array (quote currency only)
        total_fee = 0.0
        for fill in data.get('fills', []):
            if fill.get('commissionAsset') == 'USDT':
                total_fee += float(fill.get('commission', 0))
        return {
            'executed_qty': float(data['executedQty']),
            'cummulative_quote_qty': float(data['cummulativeQuoteQty']),
            'fee': total_fee,
            'status': data['status'],
        }

    @property
    def currency(self) -> str:
        return 'USDT'
