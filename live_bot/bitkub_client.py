'''Bitkub API client for Phoenix v5.1 bot.

Supports: get price, get OHLCV, get balance, market buy, market sell.
All trading in THB (THB_BTC pair).

Bitkub API v3 docs: https://github.com/bitkub/bitkub-official-api-docs
'''

import time
import hmac
import hashlib
import requests
from datetime import datetime


class BitkubClient:
    BASE_URL = 'https://api.bitkub.com'
    SYMBOL = 'THB_BTC'

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def _sign(self, path: str, params: dict = None, body: str = '') -> str:
        '''HMAC-SHA256 signature: api_key + timestamp + path + body.'''
        ts = str(int(time.time() * 1000))
        msg = self.api_key + ts + path + (body or '')
        sig = hmac.new(
            self.api_secret.encode(), msg.encode(), hashlib.sha256
        ).hexdigest()
        return ts, sig

    def _auth_headers(self, path: str, body: str = '') -> dict:
        ts, sig = self._sign(path, body=body)
        return {
            'X-BTK-APIKEY': self.api_key,
            'X-BTK-TIMESTAMP': ts,
            'X-BTK-SIGNATURE': sig,
            'Content-Type': 'application/json',
        }

        def get_price(self) -> float:
        '''Current BTC price in THB.'''
        resp = requests.get(
            f'{self.BASE_URL}/api/v3/market/ticker',
            params={'sym': self.SYMBOL}, timeout=10
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get('result'):
            raise RuntimeError(f"Bitkub API returned no result: {body}")
        data = body['result'][self.SYMBOL]
        return float(data['last'])

    def get_ohlcv(self, days: int = 365) -> list:
        '''Get daily OHLCV. Returns list of {''date'': date, ''close'': float}.'''
        from_ts = int((datetime.utcnow().timestamp() - days * 86400) * 1000)
        resp = requests.get(
            f'{self.BASE_URL}/api/v3/market/tradingview',
            params={'sym': self.SYMBOL, 'int': 'day', 'from': str(from_ts),
                    'to': str(int(time.time() * 1000))},
            timeout=15
        )
        resp.raise_for_status()
        result = []
        for item in resp.json()['result']:
            if not item:  # skip empty
                continue
            dt = datetime.fromtimestamp(item[0] / 1000).date()
            result.append({'date': dt, 'close': float(item[4])})
        return result

    def get_balance(self) -> dict:
        '''Get wallet balances. Returns {''BTC'': float, ''THB'': float}.'''
        path = '/api/v3/market/wallet'
        headers = self._auth_headers(path)
        resp = requests.get(
            f'{self.BASE_URL}{path}', headers=headers, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()['result']
        return {
            'BTC': float(data.get('btc', {}).get('available', 0)),
            'THB': float(data.get('thb', {}).get('available', 0)),
        }

    def market_buy(self, thb_amount: float) -> dict:
        '''Market buy BTC with THB.

        Bitkub uses amount in THB for the ''amt'' field on bids.
        '''
        path = '/api/v3/market/place-bid'
        body = f'{{"sym":"{self.SYMBOL}","amt":{thb_amount:.2f},"rat":0,"typ":"market"}}'
        headers = self._auth_headers(path, body=body)
        resp = requests.post(
            f'{self.BASE_URL}{path}', headers=headers, data=body, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()['result']
        return {
            'id': data.get('id'),
            'amount': float(data.get('amt', 0)),
            'cost': float(data.get('cost', 0)),
            'fee': float(data.get('fee', 0)),
        }

    def market_sell(self, btc_amount: float) -> dict:
        '''Market sell BTC for THB.

        Bitkub uses amount in BTC for the ''amt'' field on asks.
        '''
        path = '/api/v3/market/place-ask'
        body = f'{{"sym":"{self.SYMBOL}","amt":{btc_amount:.8f},"rat":0,"typ":"market"}}'
        headers = self._auth_headers(path, body=body)
        resp = requests.post(
            f'{self.BASE_URL}{path}', headers=headers, data=body, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()['result']
        return {
            'id': data.get('id'),
            'amount': float(data.get('amt', 0)),
            'cost': float(data.get('cost', 0)),
            'fee': float(data.get('fee', 0)),
        }

    def get_klines(self, days: int = 365) -> list:
        '''Alias for get_ohlcv — compatible with engine.py interface.'''
        return self.get_ohlcv(days=days)

    def get_usdt_balance(self) -> float:
        '''Not applicable for Bitkub (THB only).'''
        return 0.0

    @property
    def currency(self) -> str:
        return 'THB'
