'Binance Spot API client for Phoenix v5.1 bot.

Supports: get price, get klines, get balance, market buy, market sell.
All trading in USDT (BTCUSDT pair).
Includes retry with exponential backoff and proper klines pagination.
'

import time
import hmac
import hashlib
import requests
from datetime import datetime, timezone, timedelta


def _retry_request(func, max_retries=3, base_delay=1.0):
    """Execute an HTTP request with exponential backoff retry.

    Retries on: timeout, connection error, HTTP 429 (rate limit), HTTP 5xx.
    Does NOT retry on 4xx (client errors like bad signature, insufficient funds).
    """
    for attempt in range(max_retries):
        try:
            resp = func()
            # Retry on rate limit or server errors
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
    # Should not reach here, but just in case
    return func()


class BinanceClient:
    BASE_URL = 'https://api.binance.com'
    SYMBOL = 'BTCUSDT'

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def _sign(self, params: dict) -> dict:
        """Add signature and recvWindow to query params for authenticated requests."""
        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 5000  # 5 second tolerance for clock skew
        qs = '&'.join(f'{k}={v}' for k, v in sorted(params.items()))
        params['signature'] = hmac.new(
            self.api_secret.encode(), qs.encode(), hashlib.sha256
        ).hexdigest()
        return params

    def _headers(self) -> dict:
        return {'X-MBX-APIKEY': self.api_key}

    def get_price(self) -> float:
        """Current BTC price in USDT."""
        resp = _retry_request(lambda: requests.get(
            f'{self.BASE_URL}/api/v3/ticker/price',
            params={'symbol': self.SYMBOL}, timeout=10
        ))
        resp.raise_for_status()
        return float(resp.json()['price'])

    def get_klines(self, days: int = 500) -> list:
        """Get daily klines with proper pagination.

        Uses endTime to page backwards through history correctly.
        Returns list of {'date': date, 'close': float} sorted oldest-first.
        """
        all_candles = []
        # Start from now and work backwards
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        batch_num = 0
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

            # Move endTime to before the earliest candle in this batch
            earliest_time = candles[0][0] - 1
            end_time = earliest_time
            remaining -= len(candles)
            batch_num += 1

            if len(candles) < limit:
                break

        # Sort oldest first
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
        """Market buy BTC using quote_amount USDT.

        Returns {'executed_qty': float, 'cummulative_quote_qty': float}
        """
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
        return {
            'executed_qty': float(data['executedQty']),
            'cummulative_quote_qty': float(data['cummulativeQuoteQty']),
            'status': data['status'],
        }

    def market_sell(self, btc_amount: float) -> dict:
        """Market sell BTC.

        Returns {'executed_qty': float, 'cummulative_quote_qty': float}
        """
        # Binance requires qty with proper precision
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
        return {
            'executed_qty': float(data['executedQty']),
            'cummulative_quote_qty': float(data['cummulativeQuoteQty']),
            'status': data['status'],
        }

    @property
    def currency(self) -> str:
        return 'USDT'
