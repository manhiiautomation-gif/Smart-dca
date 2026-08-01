'''Binance Spot API client for Phoenix v5.1 bot.

Supports: get price, get klines, get balance, market buy, market sell.
All trading in USDT (BTCUSDT pair).
'''

import time
import hmac
import hashlib
import requests
from datetime import datetime


class BinanceClient:
    BASE_URL = 'https://api.binance.com'
    SYMBOL = 'BTCUSDT'

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def _sign(self, params: dict) -> dict:
        """Add signature to query params for authenticated requests."""
        params['timestamp'] = int(time.time() * 1000)
        qs = '&'.join(f'{k}={v}' for k, v in sorted(params.items()))
        params['signature'] = hmac.new(
            self.api_secret.encode(), qs.encode(), hashlib.sha256
        ).hexdigest()
        return params

    def _headers(self) -> dict:
        return {'X-MBX-APIKEY': self.api_key}

    def get_price(self) -> float:
        """Current BTC price in USDT."""
        resp = requests.get(
            f'{self.BASE_URL}/api/v3/ticker/price',
            params={'symbol': self.SYMBOL}, timeout=10
        )
        resp.raise_for_status()
        return float(resp.json()['price'])

    def get_klines(self, days: int = 500) -> list:
        """Get daily klines. Returns list of {'date': date, 'close': float}."""
        all_candles = []
        # Binance returns max 1000 per request
        for batch in range(0, days, 1000):
            limit = min(1000, days - batch)
            resp = requests.get(
                f'{self.BASE_URL}/api/v3/klines',
                params={'symbol': self.SYMBOL, 'interval': '1d', 'limit': limit},
                timeout=15
            )
            resp.raise_for_status()
            candles = resp.json()
            if not candles:
                break
            for c in candles:
                dt = datetime.fromtimestamp(c[0] / 1000).date()
                all_candles.append({'date': dt, 'close': float(c[4])})
            if len(candles) < limit:
                break
        return all_candles

    def get_balance(self, asset: str = 'BTC') -> float:
        """Free balance of an asset."""
        params = self._sign({})
        resp = requests.get(
            f'{self.BASE_URL}/api/v3/account',
            params=params, headers=self._headers(), timeout=10
        )
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
        resp = requests.post(
            f'{self.BASE_URL}/api/v3/order',
            params=params, headers=self._headers(), timeout=15
        )
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
        resp = requests.post(
            f'{self.BASE_URL}/api/v3/order',
            params=params, headers=self._headers(), timeout=15
        )
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
