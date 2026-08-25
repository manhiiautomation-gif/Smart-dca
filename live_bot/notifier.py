'''Telegram notification sender.'''

import math
import requests
import os


def send_telegram(message: str, token: str = '', chat_id: str = '') -> bool:
    """Send a message to Telegram. Returns True on success."""
    token = token or os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        return False
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    try:
        resp = requests.post(url, json={
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
        }, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def format_report(decision: dict, price: float, mvrv: float,
                  btc_balance: float, cash: float,
                  exchange_currency: str, is_dry_run: bool,
                  monday_boost: float = 1.0,
                  actual_buy: float = 0.0,
                  actual_sell: float = 0.0) -> str:
    """Format a human-readable trading report.

    DI-4: Shows actual exchange fill amounts when available.
    DI-5: Shows 'N/A' instead of 'nan' for unavailable MVRV.
    """
    prefix = '[DRY RUN] ' if is_dry_run else ''
    portfolio = btc_balance * price + cash
    boost_tag = f' (Mon x{monday_boost})' if monday_boost != 1.0 else ''

    # DI-5: Guard MVRV NaN display
    mvrv_display = f'{mvrv:.3f}' if not math.isnan(mvrv) else 'N/A'

    lines = [
        f'{prefix}<b>Phoenix v5.1 Daily Report</b>',
        f'Price: {price:,.2f} {exchange_currency} | MVRV: {mvrv_display}',
        f'Score: {decision["sell_score"]} | Path: {decision["path_taken"]}',
        f'Cooldown: {decision["new_cooldown"]}d | Bear: {decision["in_bear"]}',
        '',
    ]
    if decision['buy_amount'] > 0:
        line = f'BUY: {decision["buy_amount"]:,.2f} {exchange_currency}{boost_tag}'
        # DI-4: Show actual fill if different from intended
        if actual_buy > 0 and abs(actual_buy - decision['buy_amount']) > 0.01:
            line += f' (actual: {actual_buy:,.2f})'
        lines.append(line)
        if decision['reserve_injection'] > 0:
            lines.append(f'  (includes {decision["reserve_injection"]:,.2f} from reserve)')
    else:
        lines.append('BUY: none')

    if decision['sell_amount'] > 0:
        line = f'SELL: {decision["sell_amount"]:,.2f} {exchange_currency}'
        # DI-4: Show actual fill if different from intended
        if actual_sell > 0 and abs(actual_sell - decision['sell_amount']) > 0.01:
            line += f' (actual: {actual_sell:,.2f})'
        lines.append(line)
    else:
        lines.append('SELL: none')

    lines.append(f'')
    lines.append(f'Portfolio: {portfolio:,.2f} {exchange_currency}')
    lines.append(f'BTC: {btc_balance:.8f} | Cash: {cash:,.2f}')
    return '\n'.join(lines)
