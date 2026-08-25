'''Phoenix v5.1 Bot Engine.

Orchestrates: kill switch check, fetch data, compute indicators,
run strategy, execute trades, update state, record trade log, send notifications.

Modes:
    - run_daily():      Standard run (dry-run or live)
    - run_demo():       Demo portfolio simulation (isolated state, slippage, validation)
'''

import math
import time
import numpy as np
from datetime import date, datetime, timezone, timedelta

# H1: Thai timezone for idempotency check
# GitHub Actions cron: 03:00/03:10/03:30 UTC = 10:00/10:10/10:30 THB
_THAI_TZ = timezone(timedelta(hours=7))


def _thai_today() -> date:
    """Return today's date in Thai timezone (UTC+7)."""
    return datetime.now(_THAI_TZ).date()


def _thai_now() -> datetime:
    """Return current datetime in Thai timezone (UTC+7)."""
    return datetime.now(_THAI_TZ)


def _in_dca_time_window() -> bool:
    """Check if current Thai time is within the DCA buy window.

    Configured via DCA_TIME_WINDOW_START / DCA_TIME_WINDOW_END (Thai 24h).
    Window is [start, end) — start inclusive, end exclusive.
    """
    now = _thai_now()
    hour = now.hour
    return config.DCA_TIME_WINDOW_START <= hour < config.DCA_TIME_WINDOW_END


def _is_monday_thai() -> bool:
    """Check if today (Thai timezone) is Monday.

    Monday is weekday() == 0 in Python.
    """
    return _thai_today().weekday() == 0

from . import config
from . import indicators as ind
from . import strategy
from . import state as state_mod
from . import notifier
from . import kill_switch as ks_mod


def _fetch_price_history(exchange) -> list:
    '''Fetch daily closes from exchange. Returns list of floats.'''
    klines = exchange.get_klines(days=500)
    return [k['close'] for k in klines]


def _fetch_price_history_with_dates(exchange) -> list:
    '''Fetch daily closes with dates. Returns list of {date, close}.'''
    return exchange.get_klines(days=500)


# ── B22: Shared on-chain metric resolution ────────────────────────────
# These functions replace 4 duplicated fallback chains
# (run_daily, refresh_dashboard, run_demo, idempotency-skip).

def _sopr_proxy(price, sma14, sma30):
    """Estimate SOPR from price vs short-term moving average.

    SOPR = price / avg_cost_basis_of_STH.
    SMA14 approximates short-term holder average buy price.
    price > SMA14 -> recent buyers in profit -> SOPR > 1
    """
    if sma14 > 0 and not math.isnan(sma14):
        return price / sma14
    if sma30 > 0 and not math.isnan(sma30):
        return price / sma30
    return 1.0


def _lth_rp_proxy(realized_price_val, price, mvrv_val, in_bear=False):
    """Estimate LTH Realized Price from Realized Price.

    B23: Dynamic multiplier based on market regime.
    LTH holders have higher cost basis than overall realized price.
    """
    if not math.isnan(realized_price_val) and realized_price_val > 0:
        multiplier = 1.25 if in_bear else (1.10 if mvrv_val > 2.5 else 1.15)
        return realized_price_val * multiplier
    # Derive from MVRV if no realized price
    if mvrv_val > 0 and not math.isnan(mvrv_val) and price > 0:
        est_rp = price / mvrv_val
        multiplier = 1.25 if in_bear else (1.10 if mvrv_val > 2.5 else 1.15)
        return est_rp * multiplier
    return float('nan')


def _resolve_onchain_metrics(price, closes, today,
                              log_prefix='[BOT]',
                              allow_web_fallback=True,
                              notify_on_fail=True):
    """Resolve all technical + on-chain indicators with unified fallback chain.

    B22: Replaces duplicated code in run_daily(), refresh_dashboard(),
    run_demo(), and idempotency-skip path.

    Steps:
        1. Compute technical indicators from price closes
        2. Resolve MVRV (BG cache -> embedded -> web)
        3. Call BG batch for on-chain metrics
        4. Apply proxy fallbacks for SOPR/LTH-RP

    Args:
        price: current BTC price
        closes: list of daily close prices
        today: date object (Thai TZ)
        log_prefix: prefix for log messages (e.g. '[BOT]', '[REFRESH]', '[DEMO]')
        allow_web_fallback: try CoinMetrics/ahasignals when embedded MVRV is missing
        notify_on_fail: send Telegram when all MVRV sources fail

    Returns:
        dict with all resolved metrics. Key differences from callers:
        - run_daily uses allow_web=True, notify_on_fail=True
        - refresh uses allow_web=False, notify_on_fail=False
        - demo uses allow_web=True, notify_on_fail=False
    """
    # ── 1. Technical indicators ──
    sma_200 = ind.sma(closes, 200)
    sma_365 = ind.sma(closes, 365)
    rsi_val = ind.rsi(closes, 14)
    macd_line, macd_sig, macd_h = ind.macd(closes)
    macd_hist_series = ind.compute_all_macd_hist(closes)
    rsi_series = ind.compute_all_rsi(closes, 14)
    macd_bear = ind.macd_cross_bear(macd_hist_series)
    macd_declining = ind.macd_hist_declining(macd_hist_series, 4)
    rsi_div = ind.rsi_divergence(closes, rsi_series, 40)
    ath = max(closes) if closes else 0
    sma14 = ind.sma(closes, 14)
    sma30 = ind.sma(closes, 30)

    print(f'{log_prefix} SMA200={sma_200:,.2f} RSI={rsi_val:.1f} MACD_H={macd_h:.4f}')
    print(f'{log_prefix} MACD_bear={macd_bear} MACD_declining={macd_declining} RSI_div={rsi_div}')

    in_bear = not math.isnan(sma_200) and price < sma_200

    # ── 2. MVRV — try BG cache first, then embedded, then web ──
    mvrv_val = float('nan')
    mvrv_z = float('nan')
    mvrv_z_source = 'N/A'
    mvrv_source = 'N/A'

    try:
        from . import bg_metrics
        bg_mvrv = bg_metrics.get_cached_value('mvrv', today)
        if not math.isnan(bg_mvrv):
            mvrv_val = bg_mvrv
            if mvrv_val is not None and mvrv_val <= 0:
                mvrv_val = float('nan')
            mvrv_source = 'BG-cache'
            print(f'{log_prefix} MVRV from BG cache: {mvrv_val:.4f}')
        bg_z = bg_metrics.get_cached_value('mvrv_zscore', today)
        if not math.isnan(bg_z):
            mvrv_z = bg_z
            mvrv_z_source = 'BG-cache'
    except ImportError:
        pass

    if math.isnan(mvrv_val):
        mvrv_val = strategy.get_mvrv_for_date(today)
        if mvrv_val is not None and mvrv_val <= 0:
            mvrv_val = float('nan')
        if not math.isnan(mvrv_val):
            mvrv_source = 'embedded'
            if allow_web_fallback:
                from datetime import timedelta as td
                if today - strategy._MVRV_HISTORY_MAX > td(days=1):
                    print(f'{log_prefix} MVRV embedded stale (ends {strategy._MVRV_HISTORY_MAX}), '
                          f'updating in background...')
                    try:
                        from . import mvrv_fetcher
                        ok, msg = mvrv_fetcher.try_update_mvrv()
                        print(f'{log_prefix} MVRV update: {msg}')
                    except Exception as e:
                        print(f'{log_prefix} MVRV background update failed: {e}')
        elif allow_web_fallback:
            print(f'{log_prefix} No embedded MVRV for {today}, trying web fallback...')
            from . import mvrv_fetcher
            web_mvrv, web_date, web_source = mvrv_fetcher.fetch_mvrv_from_web()
            if web_mvrv is not None:
                mvrv_val = web_mvrv
                if mvrv_val is not None and mvrv_val <= 0:
                    mvrv_val = float('nan')
                mvrv_source = web_source
                print(f'{log_prefix} Web MVRV: {mvrv_val:.4f}')
            else:
                print(f'{log_prefix} WARNING: All MVRV sources failed: {web_source}')
                if notify_on_fail:
                    notifier.send_telegram(
                        f'Phoenix v5.1 WARNING: No MVRV data for {today}. '
                        'All sources failed. Skipping trade.'
                    )
                return {'_mvrv_all_failed': True}
        else:
            mvrv_source = 'N/A'

    # DI-6: Default to NaN (not 0) when MVRV unavailable.
    # 0 falsely implies 'MVRV at minimum' to dashboard/strategy.
    mvrv_pct = strategy.compute_mvrv_percentile(today, mvrv_val) if not math.isnan(mvrv_val) else float('nan')
    if math.isnan(mvrv_z):
        mvrv_z = strategy.compute_mvrv_zscore(today, mvrv_val) if not math.isnan(mvrv_val) else float('nan')
        mvrv_z_source = 'embedded-365d'
    nupl = 1.0 - 1.0 / mvrv_val if mvrv_val > 0 and not math.isnan(mvrv_val) else 0
    realized_price = price / mvrv_val if mvrv_val > 0 and not math.isnan(mvrv_val) else float('nan')

    # ── 3. BG batch fetch + on-chain metric resolution ──
    sopr = float('nan')
    lth_rp = float('nan')
    sopr_source = 'N/A'
    lth_source = 'N/A'
    rp_source = 'mvrv-derived' if not math.isnan(realized_price) else 'N/A'

    try:
        from . import bg_metrics
        bg = bg_metrics.get_all_metrics_today(target_date=today)

        # MVRV upgrade from BG batch
        if not math.isnan(bg.get('mvrv', float('nan'))):
            bg_mvrv_val = bg['mvrv']
            if bg_mvrv_val > 0 and mvrv_source != 'BG':
                mvrv_val = bg_mvrv_val
                mvrv_source = 'BG'
                nupl = 1.0 - 1.0 / mvrv_val
                realized_price = price / mvrv_val
                rp_source = 'BG'
                print(f'{log_prefix} MVRV upgraded from BG: {mvrv_val:.4f}')

        # MVRV Z-Score from BG
        if not math.isnan(bg.get('mvrv_zscore', float('nan'))):
            mvrv_z = bg['mvrv_zscore']
            mvrv_z_source = 'BG'
            print(f'{log_prefix} MVRV Z-Score from BG: {mvrv_z:.3f}')

        # SOPR
        if not math.isnan(bg.get('sth_sopr', float('nan'))):
            sopr = bg['sth_sopr']
            sopr_source = 'BG'
        else:
            sopr = _sopr_proxy(price, sma14, sma30)
            sopr_source = 'proxy-sma14'

        # Realized Price
        if not math.isnan(bg.get('realized_price', float('nan'))):
            realized_price = bg['realized_price']
            rp_source = 'BG'

        # LTH Realized Price
        if not math.isnan(bg.get('lth_realized_price', float('nan'))):
            lth_rp = bg['lth_realized_price']
            lth_source = 'BG'
        else:
            lth_rp = _lth_rp_proxy(realized_price, price, mvrv_val, in_bear=in_bear)
            lth_source = 'proxy-rp*dynamic' if not math.isnan(lth_rp) else 'N/A'

        # B20: Proxy accuracy logging (when BG has actual SOPR)
        _proxy_sopr = _sopr_proxy(price, sma14, sma30)
        if not math.isnan(sopr) and not math.isnan(_proxy_sopr) and sopr_source == 'BG':
            proxy_err = abs(sopr - _proxy_sopr) / max(abs(sopr), 0.001) * 100
            print(f'{log_prefix} SOPR proxy accuracy: actual={sopr:.4f} proxy={_proxy_sopr:.4f} err={proxy_err:.1f}%')

    except Exception as e:
        print(f'{log_prefix} BG metrics failed: {e}. Using all-proxy mode')
        sopr = _sopr_proxy(price, sma14, sma30)
        lth_rp = _lth_rp_proxy(realized_price, price, mvrv_val, in_bear=in_bear)
        sopr_source = 'proxy-sma14'
        lth_source = 'proxy-rp*dynamic'

    print(f'{log_prefix} STH-SOPR={sopr:.4f} ({sopr_source}) '
          f'LTH-RP={lth_rp:,.2f} ({lth_source}) '
          f'RP={realized_price:,.2f} ({rp_source})')
    print(f'{log_prefix} MVRV={mvrv_val:.3f} ({mvrv_source}) Pct={mvrv_pct:.3f} Z={mvrv_z:.2f} ({mvrv_z_source}) NUPL={nupl:.3f}')

    return {
        'sma_200': sma_200, 'sma_365': sma_365,
        'rsi': rsi_val, 'macd_line': macd_line, 'macd_sig': macd_sig, 'macd_h': macd_h,
        'macd_hist_series': macd_hist_series, 'rsi_series': rsi_series,
        'macd_bear': macd_bear, 'macd_declining': macd_declining, 'rsi_div': rsi_div,
        'ath': ath, 'sma14': sma14, 'sma30': sma30, 'in_bear': in_bear,
        'mvrv': mvrv_val, 'mvrv_source': mvrv_source,
        'mvrv_pct': mvrv_pct, 'mvrv_z': mvrv_z, 'mvrv_z_source': mvrv_z_source,
        'nupl': nupl, 'realized_price': realized_price, 'rp_source': rp_source,
        'sopr': sopr, 'sopr_source': sopr_source,
        'lth_realized_price': lth_rp, 'lth_source': lth_source,
    }


def _get_cash_balance(exchange) -> float:
    '''Get available cash in exchange currency.'''
    try:
        if hasattr(exchange, 'get_usdt_balance'):
            return exchange.get_usdt_balance()
        # Prefer robust get_balances() if available (Bitkub)
        if hasattr(exchange, 'get_balances'):
            balances = exchange.get_balances()
        elif hasattr(exchange, 'get_balance'):
            balances = exchange.get_balance()
        else:
            return 0.0
        if isinstance(balances, dict):
            return balances.get(exchange.currency, 0.0)
    except Exception as e:
        print(f'[BOT] WARNING: Could not fetch cash balance: {e}')
    return 0.0


def _get_btc_balance(exchange) -> float:
    '''Get available BTC balance.'''
    try:
        # Prefer robust get_balances() if available (Bitkub)
        if hasattr(exchange, 'get_balances'):
            bal = exchange.get_balances()
        elif hasattr(exchange, 'get_balance'):
            bal = exchange.get_balance()
        else:
            return 0.0
        if isinstance(bal, dict):
            return bal.get('BTC', 0.0)
        return float(bal)
    except Exception as e:
        print(f'[BOT] WARNING: Could not fetch BTC balance: {e}')
    return 0.0


def run_daily(exchange, bot_state: dict, dry_run: bool = False,
              trade_log_path: str = 'trade_log.json',
              kill_switch_path: str = 'kill_switch.json',
              force: bool = False) -> dict:
    '''Main daily run. Returns updated state.

    Steps:
        0. Idempotency guard (bypassed with --force)
        -1. Kill switch check (L1 + L2)
        1.  Fetch price & history
        2.  Compute indicators
        3.  Get MVRV
        4.  Get balances (virtual in dry-run, real in live)
        5.  Convert budget
        6.  Decrement cooldown
        7.  Run strategy
        8.  Execute trades (simulated in dry-run, real in live)
        9.  Update state + trade log
        10. Snapshot indicators for dashboard
        11. Send notification
    '''
    currency = exchange.currency
    today = _thai_today()

    # ── 0a. Print effective config (for debugging budget/multiplier issues) ──
    print(f'[BOT] Config: DAILY_BUDGET_THB={config.DAILY_BUDGET_THB} MAX_BUY_THB={config.MAX_BUY_THB} '
          f'MAX_DCA_BUYS_PER_DAY={config.MAX_DCA_BUYS_PER_DAY}')

    # ── 0. Idempotency guard: skip if already ran today (unless --force) ──
    # H1: Uses Thai timezone so daily guard aligns with THB calendar day
    # (cron at 03:00/03:20/03:40 UTC = 10:00/10:20/10:40 THB)
    # Each cron slot also has 3x internal retry with 60s backoff.
    # Backup slots are safety nets — if 1st run succeeds,
    # last_run_date is set and later runs skip via this guard.
    # If 1st run fails (exception/timeout), last_run_date is NOT updated,
    # so the next cron slot proceeds normally.
    if not force and bot_state.get('last_run_date') == today.isoformat():
        print(f'[BOT] Already ran today ({today} THB). Skipping TRADE but refreshing dashboard data.')
        print(f'[BOT] Use --force to override (e.g. for testing).')
        # Still fetch indicators + balances for dashboard (no trading)
        # B22: Use shared _resolve_onchain_metrics instead of duplicated inline code
        try:
            refresh_price = exchange.get_price()
            refresh_klines = _fetch_price_history_with_dates(exchange)
            refresh_closes = [k['close'] for k in refresh_klines]
            if len(refresh_closes) >= 50:
                rm = _resolve_onchain_metrics(refresh_price, refresh_closes, today,
                                                log_prefix='[BOT/idem]',
                                                allow_web_fallback=False,
                                                notify_on_fail=False)
                if not rm.get('_mvrv_all_failed'):
                    # Balances
                    if dry_run:
                        r_btc = bot_state.get('dry_run_btc', 0.0)
                        r_cash = bot_state.get('dry_run_cash', config.DRY_RUN_INITIAL_CASH)
                    else:
                        r_btc = _get_btc_balance(exchange)
                        r_cash = _get_cash_balance(exchange)
                    r_portfolio = r_btc * refresh_price + r_cash

                    bot_state['last_indicators'] = {
                        'price': round(refresh_price, 2),
                        'mvrv': round(rm['mvrv'], 3) if not math.isnan(rm['mvrv']) else None,
                        'mvrv_source': rm['mvrv_source'],
                        'mvrv_pct': round(rm['mvrv_pct'], 3) if not math.isnan(rm.get('mvrv_pct', float('nan'))) else None,
                        'mvrv_z': round(rm['mvrv_z'], 2) if not math.isnan(rm.get('mvrv_z', float('nan'))) else None,
                        'mvrv_z_source': rm['mvrv_z_source'],
                        'rsi': round(rm['rsi'], 1),
                        'macd_h': round(rm['macd_h'], 4),
                        'nupl': round(rm['nupl'], 3),
                        'sopr': round(rm['sopr'], 3) if not math.isnan(rm['sopr']) else None,
                        'sopr_source': rm['sopr_source'],
                        'sma_200': round(rm['sma_200'], 2) if not math.isnan(rm['sma_200']) else None,
                        'sma_365': round(rm['sma_365'], 2) if not math.isnan(rm['sma_365']) else None,
                        'macd_bear': rm['macd_bear'],
                        'macd_declining': rm['macd_declining'],
                        'rsi_divergence': rm['rsi_div'],
                        'ath': round(rm['ath'], 2),
                        'sell_score': bot_state.get('last_indicators', {}).get('sell_score', 0),
                        'path_taken': bot_state.get('last_indicators', {}).get('path_taken', 'none'),
                        'in_bear': rm['in_bear'],
                        'cooldown': bot_state.get('cooldown', 0),
                        'realized_price': round(rm['realized_price'], 2) if not math.isnan(rm['realized_price']) else None,
                        'lth_realized_price': round(rm['lth_realized_price'], 2) if not math.isnan(rm['lth_realized_price']) else None,
                        'lth_source': rm['lth_source'],
                        'rp_source': rm['rp_source'],
                    }
                    bot_state['last_btc_balance'] = round(r_btc, 8)
                    bot_state['last_cash_balance'] = round(r_cash, 2)
                    bot_state['last_portfolio_value'] = round(r_portfolio, 2)
                    bot_state['last_price'] = round(refresh_price, 2)
                    bot_state['last_exchange_currency'] = currency
                    bot_state['last_exchange_name'] = exchange.__class__.__name__.replace('Client', '').upper()
                    # D2: Do NOT overwrite last_dry_run in refresh-only paths.
                    if r_portfolio > bot_state.get('peak_value', 0):
                        bot_state['peak_value'] = r_portfolio
                    print(f'[BOT] Dashboard data refreshed (skipped trade). Portfolio: {r_portfolio:,.2f} {currency}')
        except Exception as e:
            print(f'[BOT] Dashboard refresh failed: {e}')
        return bot_state

    # ── 0b. Daily buy count guard (MAX_DCA_BUYS_PER_DAY) ──
    # This is a SECONDARY guard on top of the idempotency guard above.
    # It counts actual buys in trade_log.json for today (Thai date),
    # preventing runaway buys from: manual workflow_dispatch with --force,
    # stale state from failed git push, or concurrent process race conditions.
    max_daily_buys = config.MAX_DCA_BUYS_PER_DAY
    today_str = today.isoformat()
    try:
        existing_log = state_mod.load_trade_log(trade_log_path)
        today_buy_count = sum(
            1 for t in existing_log
            if t.get('type') == 'buy' and t.get('date', '').startswith(today_str)
        )
    except Exception:
        today_buy_count = 0

    if not force and today_buy_count >= max_daily_buys:
        print(f'[BOT] Daily buy limit reached: {today_buy_count}/{max_daily_buys} buys today ({today}). Skipping.')
        notifier.send_telegram(
            f'Phoenix v5.1: Daily buy limit BLOCKED {today_buy_count+1}th buy '
            f'({today_buy_count}/{max_daily_buys} already done today).'
        )
        # Still update last_run_date to prevent re-running the full pipeline
        bot_state['last_run_date'] = today_str
        bot_state['run_count'] += 1
        return bot_state

    # ── 0c. Dry-run → Live transition reset (D3) ──
    # When transitioning from dry-run to first live run, reset all
    # counters and metrics that were contaminated by dry-run data.
    # This prevents phantom invested/BTC/count values on the dashboard.
    if not dry_run and bot_state.get('last_dry_run') is True:
        print('[BOT] D3: Dry-run → Live transition detected. Resetting contaminated state.')
        for _key in ('total_invested', 'adjusted_invested', 'total_sell_proceeds',
                     'total_btc_bought', 'total_btc_sold', 'cumulative_fees',
                     'peak_value', 'max_drawdown', 'sell_proceeds_reserve',
                     'dry_run_sell_proceeds', 'total_reserve_injected'):
            bot_state[_key] = 0.0 if isinstance(bot_state.get(_key, 0), (int, float)) else None
        for _key in ('buy_count', 'sell_count'):
            bot_state[_key] = 0
        bot_state['last_trade_date'] = ''
        bot_state['last_sell_date'] = ''
        bot_state['realized_price'] = None
        bot_state['lth_realized_price'] = None
        bot_state['dry_run_btc'] = None
        bot_state['dry_run_cash'] = None
        # D3-ext: Also clear trade_log.json to remove contaminated dry-run entries.
        # The dashboard's D1 filter (dry_run=False check) handles this at read time,
        # but cleaning the source file is the correct approach.
        try:
            state_mod.clear_trade_log(trade_log_path)
        except Exception as e:
            print(f'[BOT] D3: WARNING — failed to clear trade log: {e}')
        print('[BOT] D3: State reset complete. Starting fresh with live data.')

    # ── -1. Kill Switch Check ──
    is_alive, kill_reason = ks_mod.check_kill_switch(kill_switch_path)
    if not is_alive:
        print(f'[BOT] KILLED: {kill_reason}')
        # Still fetch indicators for dashboard, but skip all trading
        try:
            price = exchange.get_price()
            _snapshot_indicators(bot_state, price, currency, dry_run,
                                  exchange, killed=True, kill_reason=kill_reason)
        except Exception as e:
            print(f'[BOT] Could not fetch indicators for dashboard: {e}')
        notifier.send_telegram(
            f'Phoenix v5.1 KILLED: {kill_reason}\n'
            f'No trades executed. Dashboard still updated.'
        )
        # Do NOT set last_run_date — a killed run must not consume
        # the daily idempotency slot so a re-run can still trade.
        bot_state['run_count'] += 1
        return bot_state

    # ── 1. Fetch current price ──
    print(f'[BOT] Fetching price from {exchange.__class__.__name__}...')
    price = exchange.get_price()
    print(f'[BOT] Current price: {price:,.2f} {currency}')

    if price <= 0:
        print(f'[BOT] ERROR: Invalid price from exchange: {price}. Skipping.')
        notifier.send_telegram(
            f'Phoenix v5.1 ERROR: Invalid price from exchange: {price}. Skipping.'
        )
        return bot_state

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

    # ── 3+4+4b. Resolve all indicators + on-chain metrics (B22: shared function) ──
    print('[BOT] Computing indicators + resolving on-chain metrics...')
    m = _resolve_onchain_metrics(price, closes, today,
                                  log_prefix='[BOT]',
                                  allow_web_fallback=True,
                                  notify_on_fail=True)
    if m.get('_mvrv_all_failed'):
        return bot_state

    # Unpack resolved metrics
    sma_200 = m['sma_200']
    sma_365 = m['sma_365']
    rsi_val = m['rsi']
    macd_line = m['macd_line']
    macd_sig = m['macd_sig']
    macd_h = m['macd_h']
    macd_hist_series = m['macd_hist_series']
    rsi_series = m['rsi_series']
    macd_bear = m['macd_bear']
    macd_declining = m['macd_declining']
    rsi_div = m['rsi_div']
    ath = m['ath']
    mvrv_val = m['mvrv']
    mvrv_source = m['mvrv_source']
    mvrv_pct = m['mvrv_pct']
    mvrv_z = m['mvrv_z']
    mvrv_z_source = m['mvrv_z_source']
    nupl = m['nupl']
    realized_price = m['realized_price']
    rp_source = m['rp_source']
    sopr = m['sopr']
    sopr_source = m['sopr_source']
    lth_rp = m['lth_realized_price']
    lth_source = m['lth_source']
    in_bear = m['in_bear']

    # ── 5. Get exchange balances ──
    # ╔═══════════════════════════════════════════════════════════════╗
    # ║  DRY RUN SAFETY: Virtual balances — NO real API balance calls ║
    # ║  LIVE MODE: Real balances fetched from exchange API           ║
    # ╚═══════════════════════════════════════════════════════════════╝
    if dry_run:
        # DRY RUN: Use virtual balances from state (no real API calls)
        if bot_state.get('dry_run_cash') is None:
            bot_state['dry_run_cash'] = config.DRY_RUN_INITIAL_CASH
            bot_state['dry_run_btc'] = 0.0
            print(f'[BOT] DRY RUN: Initialized virtual wallet')
            print(f'[BOT]   Virtual cash: {config.DRY_RUN_INITIAL_CASH:,.2f} {currency}')
        btc_balance = bot_state.get('dry_run_btc', 0.0)
        cash_balance = bot_state.get('dry_run_cash', config.DRY_RUN_INITIAL_CASH)
        print(f'[BOT] DRY RUN: Virtual BTC={btc_balance:.8f} Cash={cash_balance:,.2f} {currency}')
    else:
        # LIVE MODE: Fetch real balances from exchange
        btc_balance = _get_btc_balance(exchange)
        cash_balance = _get_cash_balance(exchange)
        print(f'[BOT] LIVE MODE: Real BTC={btc_balance:.8f} Cash={cash_balance:,.2f} {currency}')

    # ── 6. Convert budget to exchange currency ──
    base_budget = config.get_daily_budget()
    max_buy = config.get_max_buy()
    print(f'[BOT] Budget: {base_budget:.2f} {currency}/run (max buy: {max_buy:.2f})')

    # ── 6a. Monday DCA boost ──
    # Research: Monday has highest next-day BTC returns (+0.38% avg, 6/7 sources).
    # Apply to base_budget BEFORE strategy so max_buy cap inside strategy still works.
    monday_boost = False
    if _is_monday_thai() and config.MONDAY_DCA_MULTIPLIER != 1.0:
        base_budget = base_budget * config.MONDAY_DCA_MULTIPLIER
        monday_boost = True
        print(f'[BOT] MONDAY BOOST: base_budget x{config.MONDAY_DCA_MULTIPLIER} = {base_budget:.2f} {currency}')

    # ── 6b. DCA time window check ──
    # Only buy during configured Thai time window (default: 10:00-11:00 THB).
    # Indicators + dashboard are still computed outside the window.
    in_dca_window = _in_dca_time_window()
    if not in_dca_window:
        thai_h = _thai_now().hour
        print(f'[BOT] DCA TIME WINDOW: {thai_h}:xx THB is outside '
              f'{config.DCA_TIME_WINDOW_START}:00-{config.DCA_TIME_WINDOW_END}:00. '
              f'Skipping BUY (indicators + dashboard still updated).')

    # ── 6c. Separate reserve from DCA cash ──
    # In demo: sell_proceeds_reserve is tracked separately
    # In live/dry-run: we track total_sell_proceeds in state as reserve proxy
    # cash_reserve passed to strategy = ONLY profits from BTC sales
    sell_proceeds_reserve = bot_state.get('total_sell_proceeds', 0.0) - bot_state.get('total_reserve_injected', 0.0)
    sell_proceeds_reserve = max(sell_proceeds_reserve, 0.0)
    # For dry-run, also consider virtual sell proceeds
    if dry_run and bot_state.get('dry_run_sell_proceeds'):
        sell_proceeds_reserve = bot_state['dry_run_sell_proceeds']
    print(f'[BOT] Sell proceeds reserve: {sell_proceeds_reserve:,.2f} {currency}')

    # ── 7. Decrement cooldown ──
    if bot_state.get('cooldown', 0) > 0:
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
        btc_balance=btc_balance,
        cash_reserve=sell_proceeds_reserve,  # Only BTC sale profits, not DCA cash
        cooldown=bot_state['cooldown'],
        base_budget=base_budget, max_buy=max_buy,
        # Reserve deployment config (all in exchange currency)
        reserve_floor=config.get_reserve_floor(),
        max_reserve_injection=config.get_max_reserve_injection(),
        max_reserve_boosted=config.get_max_reserve_boosted(),
        reserve_boost_multiplier=config.RESERVE_BOOST_MULTIPLIER,
        reserve_boost_price_ratio=config.RESERVE_BOOST_PRICE_RATIO,
    )

    print(f'[BOT] Decision: buy={decision["buy_amount"]:.2f} '
          f'sell={decision["sell_amount"]:.2f} '
          f'score={decision["sell_score"]} path={decision["path_taken"]}')

    # ── 8b. DCA time window enforcement ──
    # Zero out buy if outside the configured Thai time window.
    # This is a safety feature that ALWAYS applies, even with --force.
    # Rationale: buying outside the research-optimized window defeats the purpose.
    # Sell decisions are NOT affected by time window.
    if not in_dca_window and decision['buy_amount'] > 0:
        print(f'[BOT] TIME WINDOW BLOCK: Zeroing buy {decision["buy_amount"]:.2f} (outside DCA window)')
        decision['buy_amount'] = 0.0

    # ── 9. Execute trades ──
    buy_fee = 0.0
    sell_fee = 0.0
    buy_btc_got = 0.0
    sell_btc_sold = 0.0
    buy_cost_actual = 0.0
    sell_proceeds_actual = 0.0
    trade_attempted = False
    trade_succeeded = False
    _original_buy_amt = decision['buy_amount']
    _original_sell_amt = decision['sell_amount']

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

    # ═══════════════════════════════════════════════════════════════
    # DRY RUN SAFETY GATE
    # When dry_run=True, exchange.market_buy() is NEVER called.
    # Trades are simulated locally with virtual balances only.
    # ═══════════════════════════════════════════════════════════════
    if decision['buy_amount'] > 0 and not dry_run:
        trade_attempted = True
        print(f'[BOT] LIVE BUY: {decision["buy_amount"]:.2f} {currency} of BTC...')
        try:
            result = exchange.market_buy(decision['buy_amount'])
            buy_cost_actual = float(result.get('cummulative_quote_qty', result.get('cost', decision['buy_amount'])))
            buy_btc_got = float(result.get('executed_qty', result.get('amount', 0)))
            # C3: Fallback — if API returns 0, compute BTC from cost/price
            if buy_btc_got <= 0 and buy_cost_actual > 0 and price > 0:
                print(f'[BOT] C3 fallback: executed_qty=0, computing BTC = {buy_cost_actual:.2f} / {price:,.2f}')
                buy_btc_got = buy_cost_actual / price
            buy_fee = float(result.get('fee', buy_cost_actual * config.BUY_FEE_PCT))
            bot_state['total_btc_bought'] += buy_btc_got
            trade_succeeded = True
            print(f'[BOT] Bought {buy_btc_got:.8f} BTC for {buy_cost_actual:.2f} {currency} (fee: {buy_fee:.2f})')
            print(f'[BOT] BUY STATUS: SUCCESS')
        except Exception as e:
            print(f'[BOT] BUY ERROR: {e}')
            print(f'[BOT] BUY STATUS: FAILED')
            # C2: If timeout/connection error, order likely executed on exchange.
            # Consume daily slot to prevent double-buy on retry.
            # Also estimate the trade details so trade_log and state are updated.
            _err_str = str(e).lower()
            if 'timeout' in _err_str or 'connection' in _err_str or 'ssl' in _err_str:
                print(f'[BOT] BUY TIMEOUT — attempting verification via balance check...')
                trade_succeeded = True  # Consume daily slot to prevent double-buy
                time.sleep(5)
                try:
                    post_btc = _get_btc_balance(exchange)
                    btc_diff = post_btc - btc_balance
                    if btc_diff > 1e-8:  # BTC balance increased — order likely executed
                        buy_btc_got = btc_diff
                        buy_cost_actual = decision['buy_amount']  # best estimate of cost
                        buy_fee = 0  # Unknown — be conservative
                        bot_state['total_btc_bought'] += buy_btc_got
                        print(f'[BOT] TIMEOUT VERIFIED: +{btc_diff:.8f} BTC detected via balance check')
                    else:
                        # BTC unchanged — order likely did NOT execute
                        buy_btc_got = 0
                        buy_cost_actual = 0
                        buy_fee = 0
                        decision['buy_amount'] = 0  # DI-1: prevent phantom invested/buy_count
                        print(f'[BOT] TIMEOUT UNVERIFIED: BTC balance unchanged ({post_btc:.8f}). '
                              f'Slot consumed to prevent double-buy. No trade recorded.')
                except Exception as ve:
                    buy_btc_got = 0
                    buy_cost_actual = 0
                    buy_fee = 0
                    decision['buy_amount'] = 0  # DI-1: prevent phantom invested/buy_count
                    print(f'[BOT] TIMEOUT VERIFICATION FAILED: {ve}. '
                          f'Slot consumed to prevent double-buy. No trade recorded.')
            else:
                decision['buy_amount'] = 0
    elif decision['buy_amount'] > 0 and dry_run:
        if price <= 0:
            print(f'[BOT] DRY RUN BUY SKIP: invalid price {price}')
            decision['buy_amount'] = 0
        else:
            buy_btc_got = decision['buy_amount'] / price
            buy_cost_actual = decision['buy_amount']
            buy_fee = buy_cost_actual * config.BUY_FEE_PCT
            bot_state['total_btc_bought'] += buy_btc_got
            print(f'[BOT] DRY RUN BUY: {decision["buy_amount"]:.2f} {currency} → {buy_btc_got:.8f} BTC @ {price:,.2f} (fee: {buy_fee:.2f})')

    # SELL
    # ═══════════════════════════════════════════════════════════════
    # DRY RUN SAFETY GATE (SELL)
    # When dry_run=True, exchange.market_sell() is NEVER called.
    # ═══════════════════════════════════════════════════════════════
    if decision['sell_amount'] > 0 and not dry_run:
        if price <= 0:
            print(f'[BOT] LIVE SELL SKIP: invalid price {price}')
            decision['sell_amount'] = 0
        else:
            btc_to_sell = decision['sell_amount'] / price
            if btc_to_sell >= btc_balance * 0.99:
                btc_to_sell = btc_balance * 0.99  # Never sell 100%
            min_sell = 10.0 if currency == 'USDT' else 10.0
            if btc_to_sell * price < min_sell:
                print(f'[BOT] Sell amount {btc_to_sell * price:.2f} below minimum {min_sell}. Skipping.')
                decision['sell_amount'] = 0
            else:
                trade_attempted = True
                print(f'[BOT] LIVE SELL: {btc_to_sell:.8f} BTC (~{decision["sell_amount"]:.2f} {currency})...')
                try:
                    result = exchange.market_sell(btc_to_sell)
                    sell_btc_sold = float(result.get('executed_qty', result.get('amount', 0)))
                    sell_proceeds_actual = float(result.get('cummulative_quote_qty', result.get('cost', decision['sell_amount'])))
                    sell_fee = float(result.get('fee', sell_proceeds_actual * config.SELL_FEE_PCT))
                    bot_state['total_btc_sold'] += sell_btc_sold
                    # Update cash reserve after sell
                    cash_balance += sell_proceeds_actual
                    trade_succeeded = True
                    print(f'[BOT] Sold {sell_btc_sold:.8f} BTC for {sell_proceeds_actual:.2f} {currency} (fee: {sell_fee:.2f})')
                except Exception as e:
                    print(f'[BOT] SELL ERROR: {e}')
                    decision['sell_amount'] = 0
                    decision['new_cooldown'] = 0
    elif decision['sell_amount'] > 0 and dry_run:
        if price <= 0:
            print(f'[BOT] DRY RUN SELL SKIP: invalid price {price}')
            decision['sell_amount'] = 0
        else:
            sell_btc_sold = decision['sell_amount'] / price
            sell_proceeds_actual = decision['sell_amount']
            sell_fee = sell_proceeds_actual * config.SELL_FEE_PCT
            bot_state['total_btc_sold'] += sell_btc_sold
            print(f'[BOT] DRY RUN SELL: {sell_btc_sold:.8f} BTC → {sell_proceeds_actual:.2f} {currency} (fee: {sell_fee:.2f})')

    # Record trades in trade log FIRST (before mutating state)
    # This ensures if trade log write fails, state is not yet mutated,
    # preventing data inconsistency between state.json and trade_log.json.
    # H3: Compute actual fill prices from exchange response for accurate records
    buy_fill_price = price
    if buy_btc_got > 0 and buy_cost_actual > 0:
        buy_fill_price = buy_cost_actual / buy_btc_got

    sell_fill_price = price
    if sell_btc_sold > 0 and sell_proceeds_actual > 0:
        sell_fill_price = sell_proceeds_actual / sell_btc_sold

    if decision['buy_amount'] > 0 and buy_btc_got > 0:
        buy_extra = {'dry_run': dry_run,
                     'reserve': round(decision.get('reserve_injection', 0), 2)}
        if monday_boost:
            buy_extra['monday_boost'] = config.MONDAY_DCA_MULTIPLIER
        state_mod.append_trade_log(
            trade_log_path, 'buy', buy_cost_actual, buy_btc_got,
            buy_fill_price, buy_fee,
            extra=buy_extra
        )

    if decision['sell_amount'] > 0 and sell_btc_sold > 0:
        state_mod.append_trade_log(
            trade_log_path, 'sell', sell_proceeds_actual, sell_btc_sold,
            sell_fill_price, sell_fee,
            extra={'dry_run': dry_run,
                   'path': decision.get('path_taken', ''),
                   'score': decision.get('sell_score', 0)}
        )

    # ── 10. Update state ──
    bot_state = state_mod.update_state_after_run(
        bot_state, decision, buy_fill_price, sell_fill_price, currency,
        buy_fee=buy_fee, sell_fee=sell_fee,
        btc_balance=btc_balance, cash_balance=cash_balance,
        sell_proceeds_actual=sell_proceeds_actual,
        actual_buy_cost=buy_cost_actual,
    )

    # If a trade was attempted but failed (amount zeroed), don't consume daily slot
    if trade_attempted and not trade_succeeded:
        bot_state.pop('last_run_date', None)
        bot_state['run_count'] -= 1  # Revert the increment
        print(f'[BOT] Trade failed — not consuming daily slot. Cron retry will try again.')

    # Track portfolio value
    if dry_run:
        # DRY RUN: Use virtual balances (no exchange API calls)
        current_btc = btc_balance + buy_btc_got - sell_btc_sold
        current_cash = cash_balance - buy_cost_actual + sell_proceeds_actual - buy_fee - sell_fee
        # Save updated virtual balances to state for next run
        bot_state['dry_run_btc'] = round(current_btc, 8)
        bot_state['dry_run_cash'] = round(current_cash, 2)
        # Track sell proceeds for reserve
        if sell_proceeds_actual > 0:
            bot_state['dry_run_sell_proceeds'] = bot_state.get('dry_run_sell_proceeds', 0.0) + sell_proceeds_actual - sell_fee
        print(f'[BOT] DRY RUN portfolio: BTC={current_btc:.8f} Cash={current_cash:,.2f} {currency}')
    else:
        # LIVE: Fetch latest real balances from exchange
        current_btc = _get_btc_balance(exchange)
        current_cash = _get_cash_balance(exchange)
        # Track sell proceeds for reserve (sell_proceeds_actual is net-of-fee for Bitkub)
        if sell_proceeds_actual > 0:
            bot_state['sell_proceeds_reserve'] = bot_state.get('sell_proceeds_reserve', 0.0) + sell_proceeds_actual
    portfolio = current_btc * price + current_cash

    peak = bot_state.get('peak_value', 0.0)
    if portfolio > peak:
        bot_state['peak_value'] = portfolio
        peak = portfolio
    if peak > 0:
        dd = (bot_state['peak_value'] - portfolio) / bot_state['peak_value']
        if dd > bot_state['max_drawdown']:
            bot_state['max_drawdown'] = dd

    # ── 11. Snapshot indicators for dashboard ──
    bot_state['last_indicators'] = {
        'price': round(price, 2),
        'mvrv': round(mvrv_val, 3),
        'mvrv_source': mvrv_source,
        'mvrv_pct': round(mvrv_pct, 3) if not math.isnan(mvrv_pct) else None,
        'mvrv_z': round(mvrv_z, 2) if not math.isnan(mvrv_z) else None,
        'mvrv_z_source': mvrv_z_source,
        'rsi': round(rsi_val, 1),
        'macd_h': round(macd_h, 4),
        'nupl': round(nupl, 3),
        'sopr': round(sopr, 3) if not math.isnan(sopr) else None,
        'sopr_source': sopr_source,
        'sma_200': round(sma_200, 2) if not math.isnan(sma_200) else None,
        'sma_365': round(sma_365, 2) if not math.isnan(sma_365) else None,
        'macd_bear': macd_bear,
        'macd_declining': macd_declining,
        'rsi_divergence': rsi_div,
        'ath': round(ath, 2),
        'sell_score': decision.get('sell_score', 0),
        'path_taken': decision.get('path_taken', 'none'),
        'in_bear': decision.get('in_bear', False),
        'cooldown': decision.get('new_cooldown', 0),
        'realized_price': round(realized_price, 2) if not math.isnan(realized_price) else None,
        'lth_realized_price': round(lth_rp, 2) if not math.isnan(lth_rp) else None,
        'lth_source': lth_source,
        'rp_source': rp_source,
    }
    # Store decision details for dashboard (multiplier, amounts)
    buy_amt = decision.get('buy_amount', 0)
    # Use pre-boost base_budget for accurate multiplier display
    base_budget_display = config.get_daily_budget()
    if base_budget_display > 0 and buy_amt > 0:
        calc_multiplier = round(buy_amt / base_budget_display, 1)
    else:
        calc_multiplier = 0.0
    bot_state['last_decision'] = {
        'buy_amount': round(buy_amt, 2),
        'sell_amount': round(decision.get('sell_amount', 0), 2),
        'multiplier': calc_multiplier,
        'base_budget': round(base_budget_display, 2),
        'reserve_injection': round(decision.get('reserve_injection', 0), 2),
        'monday_boost': config.MONDAY_DCA_MULTIPLIER if monday_boost else 1.0,
        'in_dca_window': in_dca_window,
    }
    bot_state['last_btc_balance'] = round(current_btc, 8)
    bot_state['last_cash_balance'] = round(current_cash, 2)
    bot_state['last_portfolio_value'] = round(portfolio, 2)
    bot_state['last_price'] = round(price, 2)
    bot_state['last_exchange_currency'] = currency
    bot_state['last_exchange_name'] = exchange.__class__.__name__.replace('Client', '').upper()
    bot_state['last_dry_run'] = dry_run

    # ── 11b. B18: Append indicator history for retrospective analysis ──
    try:
        import os
        ih_path = os.path.join(os.path.dirname(trade_log_path), 'indicator_history.json')
        state_mod.append_indicator_history(
            ih_path,
            bot_state.get('last_indicators', {}),
            bot_state.get('last_decision', {}),
        )
        print(f'[BOT] Indicator history appended')
    except Exception as e:
        print(f'[BOT] Indicator history append failed (non-critical): {e}')

    # ── 12. Low balance warning ──
    daily_budget = config.get_daily_budget()
    if current_cash > 0 and daily_budget > 0:
        days_remaining = current_cash / daily_budget
        if days_remaining <= config.LOW_BALANCE_DAYS:
            warning_msg = (
                f'\n⚠ LOW BALANCE WARNING\n'
                f'Cash: {current_cash:,.2f} {currency}\n'
                f'Daily budget: {daily_budget:,.2f} {currency}\n'
                f'Runs remaining: ~{days_remaining:.1f}\n'
                f'Consider adding funds or reducing DCA budget.'
            )
            print(f'[BOT] {warning_msg}')
            notifier.send_telegram(warning_msg)

    # ── 13. Send notification ──
    # DI-4: Pass actual fill amounts for accurate Telegram display
    msg = notifier.format_report(
        decision, price, mvrv_val, current_btc, current_cash,
        currency, is_dry_run=dry_run,
        monday_boost=config.MONDAY_DCA_MULTIPLIER if monday_boost else 1.0,
        actual_buy=buy_cost_actual,
        actual_sell=sell_proceeds_actual,
    )
    if notifier.send_telegram(msg):
        print('[BOT] Telegram notification sent')
    else:
        print('[BOT] Telegram not configured or failed')

    print(f'[BOT] Done. Portfolio: {portfolio:,.2f} {currency}')
    return bot_state


def refresh_dashboard(exchange, bot_state: dict, dry_run: bool = False,
                      trade_log_path: str = 'trade_log.json',
                      kill_switch_path: str = 'kill_switch.json') -> dict:
    '''Refresh dashboard data WITHOUT executing any trades.

    Fetches: price, indicators, MVRV, on-chain metrics, balances.
    Snapshots everything to state for dashboard generation.
    Used by dashboard "Update" button — always runs, never trades.

    Returns updated state dict.
    '''
    currency = exchange.currency
    today = _thai_today()

    print(f'[REFRESH] ═══════════════════════════════════════════════════')
    print(f'[REFRESH]   DASHBOARD REFRESH MODE — NO TRADES')
    print(f'[REFRESH]   Exchange: {exchange.__class__.__name__} | Dry-run: {dry_run}')
    print(f'[REFRESH] ═══════════════════════════════════════════════════')

    # ── 1. Fetch current price ──
    print(f'[REFRESH] Fetching price...')
    price = exchange.get_price()
    print(f'[REFRESH] Current price: {price:,.2f} {currency}')

    if price <= 0:
        print(f'[REFRESH] ERROR: Invalid price from exchange: {price}. Aborting.')
        return bot_state

    # ── 2. Fetch price history for indicators ──
    print('[REFRESH] Fetching price history (500d)...')
    klines = _fetch_price_history_with_dates(exchange)
    closes = [k['close'] for k in klines]
    print(f'[REFRESH] Got {len(closes)} daily closes')

    if len(closes) < 50:
        print('[REFRESH] ERROR: Not enough price history')
        return bot_state

    # ── 3+4+4b. Resolve all indicators + on-chain metrics (B22: shared function) ──
    print('[REFRESH] Computing indicators + resolving on-chain metrics...')
    rm = _resolve_onchain_metrics(price, closes, today,
                                      log_prefix='[REFRESH]',
                                      allow_web_fallback=False,
                                      notify_on_fail=False)

    # Unpack resolved metrics
    sma_200 = rm['sma_200']
    sma_365 = rm['sma_365']
    rsi_val = rm['rsi']
    macd_line = rm['macd_line']
    macd_sig = rm['macd_sig']
    macd_h = rm['macd_h']
    macd_hist_series = rm['macd_hist_series']
    rsi_series = rm['rsi_series']
    macd_bear = rm['macd_bear']
    macd_declining = rm['macd_declining']
    rsi_div = rm['rsi_div']
    ath = rm['ath']
    mvrv_val = rm['mvrv']
    mvrv_source = rm['mvrv_source']
    mvrv_pct = rm['mvrv_pct']
    mvrv_z = rm['mvrv_z']
    mvrv_z_source = rm['mvrv_z_source']
    nupl = rm['nupl']
    realized_price = rm['realized_price']
    rp_source = rm['rp_source']
    sopr = rm['sopr']
    sopr_source = rm['sopr_source']
    lth_rp = rm['lth_realized_price']
    lth_source = rm['lth_source']
    in_bear = rm['in_bear']

    # ── 5. Get balances ──
    if dry_run:
        btc_balance = bot_state.get('dry_run_btc', 0.0)
        cash_balance = bot_state.get('dry_run_cash', config.DRY_RUN_INITIAL_CASH)
        print(f'[REFRESH] DRY-RUN balances: BTC={btc_balance:.8f} Cash={cash_balance:,.2f} {currency}')
    else:
        btc_balance = _get_btc_balance(exchange)
        cash_balance = _get_cash_balance(exchange)
        print(f'[REFRESH] LIVE balances: BTC={btc_balance:.8f} Cash={cash_balance:,.2f} {currency}')
    portfolio = btc_balance * price + cash_balance

    # ── 6. Snapshot indicators to state (same format as run_daily) ──
    bot_state['last_indicators'] = {
        'price': round(price, 2),
        'mvrv': round(mvrv_val, 3) if not math.isnan(mvrv_val) else None,
        'mvrv_source': mvrv_source,
        'mvrv_pct': round(mvrv_pct, 3) if not math.isnan(mvrv_pct) else None,
        'mvrv_z': round(mvrv_z, 2) if not math.isnan(mvrv_z) else None,
        'mvrv_z_source': mvrv_z_source,
        'rsi': round(rsi_val, 1),
        'macd_h': round(macd_h, 4),
        'nupl': round(nupl, 3),
        'sopr': round(sopr, 3) if not math.isnan(sopr) else None,
        'sopr_source': sopr_source,
        'sma_200': round(sma_200, 2) if not math.isnan(sma_200) else None,
        'sma_365': round(sma_365, 2) if not math.isnan(sma_365) else None,
        'macd_bear': macd_bear,
        'macd_declining': macd_declining,
        'rsi_divergence': rsi_div,
        'ath': round(ath, 2),
        'sell_score': bot_state.get('last_indicators', {}).get('sell_score', 0),
        'path_taken': bot_state.get('last_indicators', {}).get('path_taken', 'none'),
        'in_bear': in_bear,
        'cooldown': bot_state.get('cooldown', 0),
        'realized_price': round(realized_price, 2) if not math.isnan(realized_price) else None,
        'lth_realized_price': round(lth_rp, 2) if not math.isnan(lth_rp) else None,
        'lth_source': lth_source,
        'rp_source': rp_source,
        'refreshed': True,
    }
    bot_state['last_btc_balance'] = round(btc_balance, 8)
    bot_state['last_cash_balance'] = round(cash_balance, 2)
    bot_state['last_portfolio_value'] = round(portfolio, 2)
    bot_state['last_price'] = round(price, 2)
    bot_state['last_exchange_currency'] = currency
    bot_state['last_exchange_name'] = exchange.__class__.__name__.replace('Client', '').upper()
    # D2: Do NOT overwrite last_dry_run in refresh-only paths.
    # refresh_dashboard() only fetches data for the dashboard, it doesn't trade,
    # so it must not change the provenance flag of existing trade data.

    # B18: Also append indicator history on refresh
    try:
        ih_path = os.path.join(os.path.dirname(trade_log_path), 'indicator_history.json')
        state_mod.append_indicator_history(
            ih_path,
            bot_state.get('last_indicators', {}),
        )
        print(f'[REFRESH] Indicator history appended')
    except Exception as e:
        print(f'[REFRESH] Indicator history append failed (non-critical): {e}')

    # Track peak and drawdown
    if portfolio > bot_state.get('peak_value', 0):
        bot_state['peak_value'] = portfolio
    if bot_state['peak_value'] > 0:
        dd = (bot_state['peak_value'] - portfolio) / bot_state['peak_value']
        if dd > bot_state.get('max_drawdown', 0):
            bot_state['max_drawdown'] = dd

    print(f'[REFRESH] Done. Portfolio: {portfolio:,.2f} {currency} (no trades executed)')
    return bot_state


def _snapshot_indicators(bot_state: dict, price: float, currency: str,
                         dry_run: bool, exchange, killed: bool = False,
                         kill_reason: str = ''):
    '''Fetch and snapshot indicators when bot is killed (for dashboard).'''
    try:
        klines = _fetch_price_history_with_dates(exchange)
        closes = [k['close'] for k in klines]
        if len(closes) < 50:
            return

        sma_200 = ind.sma(closes, 200)
        sma_365 = ind.sma(closes, 365)
        rsi_val = ind.rsi(closes, 14)
        _, _, macd_h = ind.macd(closes)
        ath = max(closes) if closes else 0
        sma14_quick = ind.sma(closes, 14)
        sopr = price / sma14_quick if sma14_quick > 0 else 1.0

        today = _thai_today()
        mvrv_val = strategy.get_mvrv_for_date(today)
        if mvrv_val is not None and mvrv_val <= 0:
            mvrv_val = float('nan')
        # DI-6: Default to NaN (not 0) when MVRV unavailable.
        mvrv_pct = strategy.compute_mvrv_percentile(today, mvrv_val) if not math.isnan(mvrv_val) else float('nan')
        mvrv_z = strategy.compute_mvrv_zscore(today, mvrv_val) if not math.isnan(mvrv_val) else float('nan')
        mvrv_z_source = 'embedded-365d'
        nupl = 1.0 - 1.0 / mvrv_val if mvrv_val > 0 and not math.isnan(mvrv_val) else 0

        bot_state['last_indicators'] = {
            'price': round(price, 2),
            'mvrv': round(mvrv_val, 3) if not math.isnan(mvrv_val) else None,
            'mvrv_pct': round(mvrv_pct, 3) if not math.isnan(mvrv_pct) else None,
            'mvrv_z': round(mvrv_z, 2) if not math.isnan(mvrv_z) else None,
            'mvrv_z_source': mvrv_z_source,
            'rsi': round(rsi_val, 1),
            'macd_h': round(macd_h, 4),
            'nupl': round(nupl, 3),
            'sopr': round(sopr, 3),
            'sma_200': round(sma_200, 2) if not math.isnan(sma_200) else None,
            'sma_365': round(sma_365, 2) if not math.isnan(sma_365) else None,
            'ath': round(ath, 2),
            'sell_score': 0,
            'path_taken': 'killed',
            'in_bear': price < sma_200 if not math.isnan(sma_200) else False,
            'cooldown': bot_state.get('cooldown', 0),
            'killed': True,
            'kill_reason': kill_reason,
        }
        bot_state['last_price'] = round(price, 2)
        bot_state['last_exchange_currency'] = currency
        bot_state['last_exchange_name'] = exchange.__class__.__name__.replace('Client', '').upper()
        # D2: Do NOT overwrite last_dry_run in kill-switch snapshot path.
    except Exception as e:
        print(f'[BOT] Indicator snapshot failed: {e}')


def run_demo(exchange, demo_state: dict, project_root: str,
             scenario: str = 'default', force: bool = False,
             validate: bool = False) -> dict:
    '''Demo portfolio simulation run.

    Like run_daily() but:
    - Uses isolated demo state (demo_state.json, demo_trades.json)
    - Simulates slippage on every trade
    - Records portfolio history for charting
    - Generates validation report on --validate
    - NEVER calls exchange trade APIs

    Returns updated demo_state dict.
    '''
    from . import demo_portfolio as dp

    currency = exchange.currency
    today = _thai_today()

    # ── 0. Idempotency guard ──
    if not force and demo_state.get('last_run_date') == today.isoformat():
        print(f'[DEMO] Already ran today ({today} THB). Skipping.')
        print(f'[DEMO] Use --force to override.')
        return demo_state

    print(f'[DEMO] ═══════════════════════════════════════════════════')
    print(f'[DEMO]   DEMO PORTFOLIO SIMULATION')
    print(f'[DEMO]   Scenario: {scenario}')
    print(f'[DEMO]   Cash: {demo_state["cash"]:,.2f} {currency}')
    print(f'[DEMO]   BTC:  {demo_state["btc"]:.8f}')
    print(f'[DEMO] ═══════════════════════════════════════════════════')

    # ── 1. Fetch current price ──
    print(f'[DEMO] Fetching price from {exchange.__class__.__name__}...')
    price = exchange.get_price()
    print(f'[DEMO] Current price: {price:,.2f} {currency}')

    # ── 2. Fetch price history ──
    print('[DEMO] Fetching price history (500d)...')
    klines = _fetch_price_history_with_dates(exchange)
    closes = [k['close'] for k in klines]
    print(f'[DEMO] Got {len(closes)} daily closes')

    if len(closes) < 50:
        print('[DEMO] ERROR: Not enough price history')
        return demo_state

    # ── 3+4+4b. Resolve all indicators + on-chain metrics (B22: shared function) ──
    print('[DEMO] Computing indicators + resolving on-chain metrics...')
    dm = _resolve_onchain_metrics(price, closes, today,
                                      log_prefix='[DEMO]',
                                      allow_web_fallback=True,
                                      notify_on_fail=False)
    if dm.get('_mvrv_all_failed'):
        print('[DEMO] WARNING: No MVRV data. Skipping.')
        return demo_state

    # Unpack resolved metrics
    sma_200 = dm['sma_200']
    sma_365 = dm['sma_365']
    rsi_val = dm['rsi']
    macd_line = dm['macd_line']
    macd_sig = dm['macd_sig']
    macd_h = dm['macd_h']
    macd_hist_series = dm['macd_hist_series']
    rsi_series = dm['rsi_series']
    macd_bear = dm['macd_bear']
    macd_declining = dm['macd_declining']
    rsi_div = dm['rsi_div']
    ath = dm['ath']
    mvrv_val = dm['mvrv']
    mvrv_source = dm['mvrv_source']
    mvrv_pct = dm['mvrv_pct']
    mvrv_z = dm['mvrv_z']
    mvrv_z_source = dm['mvrv_z_source']
    nupl = dm['nupl']
    realized_price = dm['realized_price']
    rp_source = dm['rp_source']
    sopr = dm['sopr']
    sopr_source = dm['sopr_source']
    lth_rp = dm['lth_realized_price']
    lth_source = dm['lth_source']
    in_bear = dm['in_bear']

    # ── 5. Convert budget ──
    base_budget = config.get_daily_budget()
    max_buy = config.get_max_buy()
    print(f'[DEMO] Budget: {base_budget:.2f} {currency}/run (max buy: {max_buy:.2f})')

    # ── 5a. Monday DCA boost (same as run_daily) ──
    monday_boost = False
    if _is_monday_thai() and config.MONDAY_DCA_MULTIPLIER != 1.0:
        base_budget = base_budget * config.MONDAY_DCA_MULTIPLIER
        monday_boost = True
        print(f'[DEMO] MONDAY BOOST: base_budget x{config.MONDAY_DCA_MULTIPLIER} = {base_budget:.2f} {currency}')

    # ── 5b. DCA time window check (same as run_daily) ──
    # In demo mode, time window is logged but NOT enforced (demo is for simulation, not live trading).
    in_dca_window = _in_dca_time_window()
    if not in_dca_window:
        print(f'[DEMO] Note: outside DCA time window ({config.DCA_TIME_WINDOW_START}:00-{config.DCA_TIME_WINDOW_END}:00 THB). ')
        print(f'[DEMO] Demo mode allows trading any time for simulation purposes.')

    # ── 5c. Reserve = sell proceeds only ──
    demo_reserve = demo_state.get('sell_proceeds_reserve', 0.0)
    print(f'[DEMO] Sell proceeds reserve: {demo_reserve:,.2f} {currency}')

    # ── 6. Run strategy (same logic as live) ──
    print('[DEMO] Running Phoenix v5.1 strategy...')
    decision = strategy.phoenix_v5_1_decision(
        mvrv=mvrv_val, rsi=rsi_val, sopr=sopr, nupl=nupl,
        price=price, sma_200=sma_200, sma_365=sma_365,
        realized_price=realized_price, lth_realized_price=lth_rp,
        mvrv_pct=mvrv_pct, mvrv_z=mvrv_z,
        macd_cross_bear=macd_bear, macd_hist_declining=macd_declining,
        rsi_divergence_flag=rsi_div, ath=ath,
        btc_balance=demo_state['btc'],
        cash_reserve=demo_reserve,
        cooldown=demo_state['cooldown'],
        base_budget=base_budget, max_buy=max_buy,
        reserve_floor=config.get_reserve_floor(),
        max_reserve_injection=config.get_max_reserve_injection(),
        max_reserve_boosted=config.get_max_reserve_boosted(),
        reserve_boost_multiplier=config.RESERVE_BOOST_MULTIPLIER,
        reserve_boost_price_ratio=config.RESERVE_BOOST_PRICE_RATIO,
    )

    print(f'[DEMO] Decision: buy={decision["buy_amount"]:.2f} '
          f'sell={decision["sell_amount"]:.2f} '
          f'score={decision["sell_score"]} path={decision["path_taken"]}')

    # ── 7. Process trade through demo portfolio (with slippage) ──
    demo_state = dp.process_demo_trade(
        demo_state, decision, price, currency,
        fee_pct=config.BUY_FEE_PCT,
        use_slippage=True,
        project_root=project_root,
        scenario=scenario,
        monday_boost=config.MONDAY_DCA_MULTIPLIER if monday_boost else 1.0,
    )

    # ── 8. Snapshot indicators ──
    indicators_snapshot = {
        'price': round(price, 2),
        'mvrv': round(mvrv_val, 3),
        'mvrv_pct': round(mvrv_pct, 3) if not math.isnan(mvrv_pct) else None,
        'mvrv_z': round(mvrv_z, 2) if not math.isnan(mvrv_z) else None,
        'mvrv_z_source': mvrv_z_source,
        'rsi': round(rsi_val, 1),
        'macd_h': round(macd_h, 4),
        'nupl': round(nupl, 3),
        'sopr': round(sopr, 3) if not math.isnan(sopr) else None,
        'sopr_source': sopr_source,
        'sma_200': round(sma_200, 2) if not math.isnan(sma_200) else None,
        'sma_365': round(sma_365, 2) if not math.isnan(sma_365) else None,
        'macd_bear': macd_bear,
        'macd_declining': macd_declining,
        'rsi_divergence': rsi_div,
        'ath': round(ath, 2),
        'sell_score': decision.get('sell_score', 0),
        'path_taken': decision.get('path_taken', 'none'),
        'in_bear': decision.get('in_bear', False),
        'cooldown': decision.get('new_cooldown', 0),
    }
    # Store decision details for dashboard
    # Use pre-boost base_budget for accurate multiplier display
    buy_amt = decision.get('buy_amount', 0)
    base_budget_display = config.get_daily_budget()
    if base_budget_display > 0 and buy_amt > 0:
        calc_mult = round(buy_amt / base_budget_display, 1)
    else:
        calc_mult = 0.0
    demo_state['last_decision'] = {
        'buy_amount': round(buy_amt, 2),
        'sell_amount': round(decision.get('sell_amount', 0), 2),
        'multiplier': calc_mult,
        'base_budget': round(base_budget_display, 2),
        'reserve_injection': round(decision.get('reserve_injection', 0), 2),
        'monday_boost': config.MONDAY_DCA_MULTIPLIER if monday_boost else 1.0,
        'in_dca_window': in_dca_window,
    }
    dp.snapshot_indicators(demo_state, indicators_snapshot)

    # ── 9. Send notification ──
    msg = notifier.format_report(
        decision, price, mvrv_val,
        demo_state['btc'], demo_state['cash'],
        currency, is_dry_run=True,
        monday_boost=config.MONDAY_DCA_MULTIPLIER if monday_boost else 1.0,
    )
    msg = msg.replace('DRY RUN', 'DEMO')
    if notifier.send_telegram(msg):
        print('[DEMO] Telegram notification sent')

    # ── 10. Validation report (optional) ──
    if validate:
        report = dp.generate_validation_report(demo_state, project_root, scenario)
        dp.print_validation_report(report)

    return demo_state
