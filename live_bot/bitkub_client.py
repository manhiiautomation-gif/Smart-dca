'''Bitkub API client for Phoenix v5.1 bot.

Supports: get price, get OHLCV, get balance, market buy, market sell.
All trading in THB (THB_BTC pair).

Bitkub API v3 docs: https://github.com/bitkub/bitkub-official-api-docs

IMPORTANT: Bitkub often returns HTTP 200 with error in body:
    {"error": 42, "message": "insufficient balance"}
All API methods now check for this via _check_response().
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
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()

    def _sign(self, method: str, path: str, body: str = '') -> tuple:
        '''HMAC-SHA256 signature per Bitkub docs.

        Formula: HMAC-SHA256(timestamp + method + path + body, apiSecret)
        Ref: https://api.bitkub.com/docs/authentication
        '''
        ts = str(int(time.time() * 1000))
        msg = ts + method.upper() + path + (body or '')
        sig = hmac.new(
            self.api_secret.encode(), msg.encode(), hashlib.sha256
        ).hexdigest()
        return ts, sig

    def _auth_headers(self, method: str, path: str, body: str = '') -> dict:
        ts, sig = self._sign(method, path, body=body)
        return {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-BTK-APIKEY': self.api_key,
            'X-BTK-TIMESTAMP': ts,
            'X-BTK-SIGN': sig,
        }

    def _check_response(self, resp, path: str = ''):
        '''Check Bitkub API response for application-level errors.

        Bitkub returns HTTP 200 with error in body:
            {"error": 0, "message": "success", "result": {...}}  ← success
            {"error": 42, "message": "insufficient balance"}      ← actual error
        error=0 means success.  Only raise on non-zero error codes.
        Also validates that 'result' key exists on success.
        Returns the parsed JSON body on success.
        '''
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get('error', 0) != 0:
            err_code = data['error']
            err_msg = data.get('message', 'Unknown error')
            raise RuntimeError(f'Bitkub API error {err_code}: {err_msg} (path: {path})')
        if isinstance(data, dict) and 'result' not in data:
            raise ValueError('Bitkub API response missing "result" key')
        return data

    def get_price(self) -> float:
        """Current BTC price in THB."""
        resp = requests.get(
            f'{self.BASE_URL}/api/v3/market/ticker',
            params={'sym': self.SYMBOL}, timeout=10
        )
        body = self._check_response(resp, 'market/ticker')
        if isinstance(body, list) and body:
            return float(body[0]['last'])
        raise RuntimeError(f"Bitkub API error: unexpected ticker response: {body}")

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
        rate = config.get_usd_thb_rate()
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

    def get_balances(self) -> dict:
        '''Get wallet balances via /api/v3/market/wallet (POST, auth required).

        Bitkub response format:
            {"error": 0, "result": {"THB": 188379.27, "BTC": 8.90397323}}
        Values are flat numbers, NOT nested dicts.
        Returns {'BTC': float, 'THB': float}.
        '''
        path = '/api/v3/market/wallet'
        body = '{}'
        headers = self._auth_headers('POST', path, body=body)
        resp = requests.post(
            f'{self.BASE_URL}{path}', headers=headers, data=body, timeout=10
        )
        data = self._check_response(resp, path)
        result_data = data.get('result', data)
        # Bitkub wallet returns flat numbers: {"BTC": 8.9, "THB": 188379.27}
        btc = result_data.get('BTC', 0)
        thb = result_data.get('THB', 0)
        return {
            'BTC': float(btc) if not isinstance(btc, dict) else float(btc.get('available', 0)),
            'THB': float(thb) if not isinstance(thb, dict) else float(thb.get('available', 0)),
        }

    def market_buy(self, thb_amount: float) -> dict:
        '''Market buy BTC with THB.

        Bitkub uses amount in THB for the 'amt' field on bids.

        Returns standardized dict compatible with engine.py:
            executed_qty:       BTC received
            cummulative_quote_qty: THB spent (total cost)
            fee:               actual fee in THB
        '''
        path = '/api/v3/market/place-bid'
        body = '{{"sym":"{}","amt":{:.2f},"rat":0,"typ":"market"}}'.format(
            self.SYMBOL, thb_amount)
        headers = self._auth_headers('POST', path, body=body)
        resp = requests.post(
            f'{self.BASE_URL}{path}', headers=headers, data=body, timeout=15
        )
        data = self._check_response(resp, path)
        result = data['result']

        # Extract BTC received — Bitkub uses 'recv' field
        btc_received = float(result.get('recv', 0))
        if btc_received <= 0:
            # Fallback: calculate from cost and average rate
            rate = float(result.get('rat', 0))
            cost = float(result.get('cost', 0))
            if rate > 0 and cost > 0:
                btc_received = cost / rate
            else:
                # Last resort: use requested amount / approximate price
                print(f'[BITKUB] WARNING: Cannot determine BTC received from buy response, '
                      f'using cost/last_price fallback')
                btc_received = cost / self.get_price() if cost > 0 else 0

        thb_cost = float(result.get('cost', thb_amount))
        actual_fee = float(result.get('fee', 0))

        return {
            'executed_qty': btc_received,
            'cummulative_quote_qty': thb_cost,
            'fee': actual_fee,
            'id': result.get('id'),
        }

    def market_sell(self, btc_amount: float) -> dict:
        '''Market sell BTC for THB.

        Bitkub uses amount in BTC for the 'amt' field on asks.

        Returns standardized dict compatible with engine.py:
            executed_qty:       BTC sold
            cummulative_quote_qty: THB received (after fee)
            fee:               actual fee in THB
        '''
        path = '/api/v3/market/place-ask'
        body = '{{"sym":"{}","amt":{:.8f},"rat":0,"typ":"market"}}'.format(
            self.SYMBOL, btc_amount)
        headers = self._auth_headers('POST', path, body=body)
        resp = requests.post(
            f'{self.BASE_URL}{path}', headers=headers, data=body, timeout=15
        )
        data = self._check_response(resp, path)
        result = data['result']

        btc_sold = float(result.get('amt', 0))
        # 'recv' for sell = THB received after fee
        thb_received = float(result.get('recv', 0))
        if thb_received <= 0:
            # Fallback: use 'cost' field
            thb_received = float(result.get('cost', 0))
        actual_fee = float(result.get('fee', 0))

        return {
            'executed_qty': btc_sold,
            'cummulative_quote_qty': thb_received,
            'fee': actual_fee,
            'id': result.get('id'),
        }

    def get_klines(self, days: int = 365) -> list:
        '''Alias for get_ohlcv - compatible with engine.py interface.'''
        return self.get_ohlcv(days=days)

    # NOTE: No get_usdt_balance() — engine._get_cash_balance() would
    # call it first and get 0.0, blocking all buys. Removed intentionally.

    @property
    def currency(self) -> str:
        return 'THB'
