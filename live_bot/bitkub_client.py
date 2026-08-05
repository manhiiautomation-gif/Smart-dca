'''Bitkub API client for Phoenix v5.1 bot.

Supports: get price, get OHLCV, get balance, market buy, market sell.
All trading in THB (THB_BTC pair).

Bitkub API v3 docs: https://github.com/bitkub/bitkub-official-api-docs
'''

import time
import hmac
import hashlib
import io
import zipfile
import requests
from datetime import datetime, timedelta, date


class BitkubClient:
    BASE_URL = 'https://api.bitkub.com'
    SYMBOL = 'BTC_THB'

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
        """Current BTC price in THB."""
        resp = requests.get(
            f'{self.BASE_URL}/api/v3/market/ticker',
            params={'sym': self.SYMBOL}, timeout=10
        )
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, list) and body:
            return float(body[0]['last'])
        raise RuntimeError(f"Bitkub API error: {body}")

    def get_ohlcv(self, days: int = 365) -> list:
        """Get daily OHLCV for indicators.

        Priority:
        1. Binance Vision (500+ days, public, no auth, no geo-block)
        2. CoinGecko fallback (~90 days daily, >90 days becomes weekly)
        Returns list of {'date': date, 'close': float} in THB.
        """
        try:
            result = self._ohlcv_binance_vision(days)
            if len(result) >= 200:
                print(f'[BITKUB] Got {len(result)} daily closes from Binance Vision')
                return result
            print(f'[BITKUB] Binance Vision returned only {len(result)} rows, trying CoinGecko...')
        except Exception as e:
            print(f'[BITKUB] Binance Vision failed: {e}. Falling back to CoinGecko...')
        return self._ohlcv_coingecko(min(days, 365))

    def _ohlcv_binance_vision(self, days: int) -> list:
        """Download BTCUSDT daily klines from Binance Vision.

        data.binance.vision serves static ZIP/CSV files - NOT geo-blocked
        unlike api.binance.com.  Prices are converted USDT -> THB.
        Binance Vision changed timestamp format in 2025:
          - <=2024: 13-digit millisecond timestamps
          - >=2025: 16-digit microsecond timestamps
        Auto-detected by digit count.
        """
        from live_bot import config

        end = date.today()
        start = end - timedelta(days=days + 60)

        # Build YYYY-MM list
        months = []
        cur = start.replace(day=1)
        while cur <= end:
            months.append(cur.strftime('%Y-%m'))
            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)

        base_url = 'https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d'
        rate = config.USD_THB_RATE
        seen = {}

        for m in months:
            url = f'{base_url}/BTCUSDT-1d-{m}.zip'
            try:
                resp = requests.get(url, timeout=30)
                if resp.status_code == 404:
                    continue  # current month may not exist yet
                resp.raise_for_status()
            except requests.HTTPError:
                continue

            # Unzip CSV in memory
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            csv_text = zf.read(zf.namelist()[0]).decode('utf-8')
            for line in csv_text.strip().split('\n'):
                parts = line.split(',')
                if len(parts) < 5:
                    continue
                try:
                    ts_raw = int(parts[0])
                    # Auto-detect: >=16 digits = microseconds, else milliseconds
                    if len(parts[0]) >= 16:
                        dt = datetime.fromtimestamp(ts_raw / 1_000_000).date()
                    else:
                        dt = datetime.fromtimestamp(ts_raw / 1_000).date()
                    seen[dt] = float(parts[4]) * rate
                except (ValueError, OSError):
                    continue

        # Sort, deduplicate, trim
        result = [{'date': d, 'close': p} for d, p in sorted(seen.items())]
        return result[-days:]

    def _ohlcv_coingecko(self, days: int) -> list:
        """Fallback: CoinGecko public API (~90 days daily candles on free tier)."""
        resp = requests.get(
            'https://api.coingecko.com/api/v3/coins/bitcoin/ohlc',
            params={'vs_currency': 'thb', 'days': min(days, 365)},
            timeout=30
        )
        resp.raise_for_status()
        result = []
        for c in resp.json():
            dt = datetime.fromtimestamp(c[0] / 1000).date()
            result.append({'date': dt, 'close': float(c[4])})
        return result

    def get_balance(self) -> dict:
        '''Get wallet balances. Returns {'BTC': float, 'THB': float}.'''
        path = '/api/v3/market/wallet'
        body = '{}'
        headers = self._auth_headers(path, body=body)
        resp = requests.post(
            f'{self.BASE_URL}{path}', headers=headers, data=body, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()['result']
        return {
            'BTC': float(data.get('btc', {}).get('available', 0)),
            'THB': float(data.get('thb', {}).get('available', 0)),
        }

    def get_balances(self) -> dict:
        '''Get wallet balances with multi-endpoint fallback.

        Tries multiple endpoint variants for compatibility.
        Returns {'BTC': float, 'THB': float}.
        '''
        for path in ['/api/v3/market/wallet', '/api/v3/wallet']:
            body = '{}'
            headers = self._auth_headers(path, body=body)
            try:
                resp = requests.post(
                    f'{self.BASE_URL}{path}', headers=headers, data=body, timeout=10
                )
                resp.raise_for_status()
                data = resp.json().get('result', resp.json())
                if isinstance(data, dict):
                    return {
                        'BTC': float(data.get('btc', {}).get('available', 0)),
                        'THB': float(data.get('thb', {}).get('available', 0)),
                    }
            except Exception:
                continue
        # All variants failed - return zeros (bot will use 0 balance)
        print('[BITKUB] WARNING: Could not fetch wallet balance. Using 0.')
        return {'BTC': 0.0, 'THB': 0.0}

    def market_buy(self, thb_amount: float) -> dict:
        '''Market buy BTC with THB.

        Bitkub uses amount in THB for the 'amt' field on bids.
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

        Bitkub uses amount in BTC for the 'amt' field on asks.
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
        '''Alias for get_ohlcv - compatible with engine.py interface.'''
        return self.get_ohlcv(days=days)

    def get_usdt_balance(self) -> float:
        '''Not applicable for Bitkub (THB only).'''
        return 0.0

    @property
    def currency(self) -> str:
        return 'THB'
