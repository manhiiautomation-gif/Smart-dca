'''Phoenix v5.1 Bot Engine.

Orchestrates: fetch data, compute indicators, run strategy,
execute trades, update state, send notifications.
'''

import math
import numpy as np
from datetime import date, timedelta

from . import config
from . import indicators as ind
from . import strategy
from . import state as state_mod
from . import notifier


def _fetch_price_history(exchange) -> list:
    '''Fetch daily closes from exchange. Returns list of floats.'''
    klines = exchange.get_klines(days=500)
    return [k['close'] for k in klines]


def _fetch_price_history_with_dates(exchange) -> list:
    '''Fetch daily closes with dates. Returns list of {date, close}.'''
    return exchange.get_klines(days=500)


def _get_cash_balance(exchange) -> float:
    '''Get available cash in exchange currency.'''
    if hasattr(exchange, 'get_usdt_balance'):
        return exchange.get_usdt_balance()
    balances = exchange.get_balance()
    if isinstance(balances, dict):
        return balances.get(exchange.currency, 0.0)
    return 0.0


def _get_btc_balance(exchange) -> float:
    '''Get available BTC balance.'''
    if hasattr(exchange, 'get_balance'):
        bal = exchange.get_balance()
        if isinstance(bal, dict):
            return bal.get('BTC', 0.0)
        return float(bal)
    return 0.0


def run_daily(exchange, bot_state: dict, dry_run: bool = False) -> dict:
    '''Main daily run. Returns updated state.'''
    currency = exchange.currency
    today = date.today()

    # ── 0. Idempotency guard: skip if already ran today ──
    if bot_state.get('last_run_date') == today.isoformat():
        print(f'[BOT] Already ran today ({today}). Skipping to prevent duplicate trades.')
        return bot_state

    # ── 1. Fetch current price ──
    print(f'[BOT] Fetching price from {exchange.__class__.__name__}...')
    price = exchange.get_price()
    print(f'[BOT] Current price: {price:,.2f} {currency}')

    # ── 2. Fetch price history for indicators ──
    print('[BOT] Fetching price history (500d)...')
    klines = _fetch_price_history_with_dates(exchange)
    closes = [k['close'] for k in klines]
    print(f'[BOT] Got {len(closes)} daily closes')

    if len(closes) < 50:
        print('[BOT] ERROR: Not enough price history for indicators')
        notifier.send_telegram(
            f'Phoenix v5.1 ERROR: Only {len(closes)} days of price data. Skipping.'
        )
        return bot_state

    # ── 3. Compute technical indicators ──
    print('[BOT] Computing indicators...')
    sma_200 = ind.sma(closes, 200)
    sma_365 = ind.sma(closes, 365)
    rsi_val = ind.rsi(closes, 14)
    macd_line, macd_sig, macd_h = ind.macd(closes)

    # Series-based indicators
    macd_hist_series = ind.compute_all_macd_hist(closes)
    rsi_series = ind.compute_all_rsi(closes, 14)

    macd_bear = ind.macd_cross_bear(macd_hist_series)
    macd_declining = ind.macd_hist_declining(macd_hist_series, 4)
    rsi_div = ind.rsi_divergence(closes, rsi_series, 40)

    ath = max(closes) if closes else 0

    print(f'[BOT] SMA200={sma_200:,.2f} RSI={rsi_val:.1f} MACD_H={macd_h:.4f}')
    print(f'[BOT] MACD_bear={macd_bear} MACD_declining={macd_declining} RSI_div={rsi_div}')

    # ── 4. Get MVRV from embedded history ──
    mvrv_val = strategy.get_mvrv_for_date(today)
    if math.isnan(mvrv_val):
        print(f'[BOT] WARNING: No embedded MVRV for {today}. Skipping.')
        notifier.send_telegram(
            f'Phoenix v5.1 WARNING: No MVRV data for {today}. '  
            'Embedded data may need updating. Skipping trade.'
        )
        return bot_state

    mvrv_pct = strategy.compute_mvrv_percentile(today, mvrv_val)
    mvrv_z = strategy.compute_mvrv_zscore(today, mvrv_val)
    nupl = 1.0 - 1.0 / mvrv_val if mvrv_val > 0 else 0
    realized_price = price / mvrv_val if mvrv_val > 0 else float('nan')

    # SOPR proxy (Price / EMA30) — same as backtest fallback
    ema30 = ind.ema(closes, 30)
    sopr = price / ema30 if ema30 > 0 else 1.0

    # LTH Realized Price — not available via free API; set NaN (non-critical)
    lth_rp = float('nan')

    print(f'[BOT] MVRV={mvrv_val:.3f} Pct={mvrv_pct:.3f} Z={mvrv_z:.2f} NUPL={nupl:.3f}')

    # ── 5. Get exchange balances ──
    btc_balance = _get_btc_balance(exchange)
    cash_balance = _get_cash_balance(exchange)
    print(f'[BOT] Balances: BTC={btc_balance:.8f} Cash={cash_balance:,.2f} {currency}')

    # ── 6. Convert budget to exchange currency ──
    if currency == 'USDT':
        base_budget = config.DAILY_BUDGET_THB / config.USD_THB_RATE
        max_buy = config.MAX_BUY_THB / config.USD_THB_RATE
    else:
        base_budget = config.DAILY_BUDGET_THB
        max_buy = config.MAX_BUY_THB

    # ── 7. Decrement cooldown ──
    if bot_state['cooldown'] > 0:
        bot_state['cooldown'] -= 1
        print(f'[BOT] Cooldown: {bot_state["cooldown"] + 1} -> {bot_state["cooldown"]}')

    # ── 8. Run strategy ──
    print('[BOT] Running Phoenix v5.1 strategy...')
    decision = strategy.phoenix_v5_1_decision(
        mvrv=mvrv_val, rsi=rsi_val, sopr=sopr, nupl=nupl,
        price=price, sma_200=sma_200, sma_365=sma_365,
        realized_price=realized_price, lth_realized_price=lth_rp,
        mvrv_pct=mvrv_pct, mvrv_z=mvrv_z,
        macd_cross_bear=macd_bear, macd_hist_declining=macd_declining,
        rsi_divergence_flag=rsi_div, ath=ath,
        btc_balance=btc_balance, cash_reserve=cash_balance,
        cooldown=bot_state['cooldown'],
        base_budget=base_budget, max_buy=max_buy,
    )

    print(f'[BOT] Decision: buy={decision["buy_amount"]:.2f} '  
          f'sell={decision["sell_amount"]:.2f} '  
          f'score={decision["sell_score"]} path={decision["path_taken"]}')

    # ── 9. Execute trades ──
    buy_fee = 0.0
    sell_fee = 0.0

    # BUY
    if decision['buy_amount'] > 0:
        # Check minimum order size
        min_buy = config.MIN_BUY_USDT if currency == 'USDT' else config.MIN_BUY_THB
        if decision['buy_amount'] < min_buy:
            print(f'[BOT] Buy amount {decision["buy_amount"]:.2f} below minimum {min_buy}. Skipping.')
            decision['buy_amount'] = 0
        elif cash_balance < decision['buy_amount']:
            print(f'[BOT] Insufficient cash: have {cash_balance:,.2f}, need {decision["buy_amount"]:.2f}')
            # Buy with what we have
            if cash_balance >= min_buy:
                decision['buy_amount'] = cash_balance
            else:
                decision['buy_amount'] = 0

    if decision['buy_amount'] > 0 and not dry_run:
        print(f'[BOT] BUYING {decision["buy_amount"]:.2f} {currency} of BTC...')
        try:
            result = exchange.market_buy(decision['buy_amount'])
            btc_got = result.get('executed_qty', result.get('amount', 0))
            cost = result.get('cummulative_quote_qty', result.get('cost', decision['buy_amount']))
            fee = result.get('fee', cost * config.BUY_FEE_PCT)
            buy_fee = float(fee)
            bot_state['total_btc_bought'] += float(btc_got)
            print(f'[BOT] Bought {btc_got:.8f} BTC for {cost:.2f} {currency} (fee: {buy_fee:.2f})')
        except Exception as e:
            print(f'[BOT] BUY ERROR: {e}')
            decision['buy_amount'] = 0
    elif decision['buy_amount'] > 0 and dry_run:
        print(f'[BOT] [DRY RUN] Would buy {decision["buy_amount"]:.2f} {currency}')

    # SELL
    if decision['sell_amount'] > 0 and not dry_run:
        btc_to_sell = decision['sell_amount'] / price
        if btc_to_sell >= btc_balance * 0.99:
            btc_to_sell = btc_balance * 0.99  # Never sell 100%
        min_sell = 10.0 if currency == 'USDT' else 100.0
        if btc_to_sell * price < min_sell:
            print(f'[BOT] Sell amount {btc_to_sell * price:.2f} below minimum {min_sell}. Skipping.')
            decision['sell_amount'] = 0
        else:
            print(f'[BOT] SELLING {btc_to_sell:.8f} BTC (~{decision["sell_amount"]:.2f} {currency})...')
            try:
                result = exchange.market_sell(btc_to_sell)
                btc_sold = result.get('executed_qty', result.get('amount', 0))
                proceeds = result.get('cummulative_quote_qty', result.get('cost', decision['sell_amount']))
                fee = result.get('fee', proceeds * config.SELL_FEE_PCT)
                sell_fee = float(fee)
                bot_state['total_btc_sold'] += float(btc_sold)
                # Update cash reserve after sell
                cash_balance += float(proceeds) - sell_fee
                print(f'[BOT] Sold {btc_sold:.8f} BTC for {proceeds:.2f} {currency} (fee: {sell_fee:.2f})')
            except Exception as e:
                print(f'[BOT] SELL ERROR: {e}')
                decision['sell_amount'] = 0
    elif decision['sell_amount'] > 0 and dry_run:
        print(f'[BOT] [DRY RUN] Would sell {decision["sell_amount"]:.2f} {currency} of BTC')

    # ── 10. Update state ──
    bot_state = state_mod.update_state_after_run(
        bot_state, decision, price, price, currency,
        buy_fee=buy_fee, sell_fee=sell_fee
    )

    # Track portfolio value
    current_btc = _get_btc_balance(exchange) if not dry_run else btc_balance
    current_cash = _get_cash_balance(exchange) if not dry_run else cash_balance
    portfolio = current_btc * price + current_cash

    if portfolio > bot_state['peak_value']:
        bot_state['peak_value'] = portfolio
    if bot_state['peak_value'] > 0:
        dd = (bot_state['peak_value'] - portfolio) / bot_state['peak_value']
        if dd > bot_state['max_drawdown']:
            bot_state['max_drawdown'] = dd

    # ── 11. Send notification ──
    msg = notifier.format_report(
        decision, price, mvrv_val, current_btc, current_cash,
        currency, dry_run
    )
    if notifier.send_telegram(msg):
        print('[BOT] Telegram notification sent')
    else:
        print('[BOT] Telegram not configured or failed')

    print(f'[BOT] Done. Portfolio: {portfolio:,.2f} {currency}')
    return bot_state