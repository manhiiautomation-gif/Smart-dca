'''Telegram notification sender.'''

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
                  monday_boost: float = 1.0) -> str:
    """Format a human-readable trading report."""
    prefix = '[DRY RUN] ' if is_dry_run else ''
    portfolio = btc_balance * price + cash
    boost_tag = f' (Mon x{monday_boost})' if monday_boost != 1.0 else ''
    lines = [
        f'{prefix}<b>Phoenix v5.1 Daily Report</b>',
        f'Price: {price:,.2f} {exchange_currency} | MVRV: {mvrv:.3f}',
        f'Score: {decision["sell_score"]} | Path: {decision["path_taken"]}',
        f'Cooldown: {decision["new_cooldown"]}d | Bear: {decision["in_bear"]}',
        '',
    ]
    if decision['buy_amount'] > 0:
        lines.append(f'BUY: {decision["buy_amount"]:,.2f} {exchange_currency}{boost_tag}')
        if decision['reserve_injection'] > 0:
            lines.append(f'  (includes {decision["reserve_injection"]:,.2f} from reserve)')
    else:
        lines.append('BUY: none')

    if decision['sell_amount'] > 0:
        lines.append(f'SELL: {decision["sell_amount"]:,.2f} {exchange_currency}')
    else:
        lines.append('SELL: none')

    lines.append(f'')
    lines.append(f'Portfolio: {portfolio:,.2f} {exchange_currency}')
    lines.append(f'BTC: {btc_balance:.8f} | Cash: {cash:,.2f}')
    return '\n'.join(lines)
