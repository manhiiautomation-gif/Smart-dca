'''Phoenix v5.1 Bot Engine.

Orchestrates: kill switch check, fetch data, compute indicators,
run strategy, execute trades, update state, record trade log, send notifications.

Modes:
    - run_daily():      Standard run (dry-run or live)
    - run_demo():       Demo portfolio simulation (isolated state, slippage, validation)
'''

import math
import numpy as np
from datetime import date, datetime, timezone, timedelta

# H1: Thai timezone for idempotency check
# GitHub Actions cron: 13:00/13:10/13:30 UTC = 20:00/20:10/20:30 THB
_THAI_TZ = timezone(timedelta(hours=7))


def _thai_today() -> date:
    """Return today's date in Thai timezone (UTC+7)."""
    return datetime.now(_THAI_TZ).date()

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

    # ── 0. Idempotency guard: skip if already ran today (unless --force) ──
    # H1: Uses Thai timezone so daily guard aligns with THB calendar day
    # (cron at 13:00/13:10/13:30 UTC = 20:00/20:10/20:30 THB)
    # Each cron slot also has 3x internal retry with 60s backoff.
    # Backup slots are safety nets — if 1st run succeeds,
    # last_run_date is set and later runs skip via this guard.
    # If 1st run fails (exception/timeout), last_run_date is NOT updated,
    # so the next cron slot proceeds normally.
    if not force and bot_state.get('last_run_date') == today.isoformat():
        print(f'[BOT] Already ran today ({today} THB). Skipping to prevent duplicate trades.')
        print(f'[BOT] Use --force to override (e.g. for testing).')
        return bot_state

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

    # ── 4. Get MVRV + Z-Score — try BG cache first, then embedded, then web ──
    # Priority: BG cache → embedded history → CoinMetrics → ahasignals
    # NUPL is always derived: 1 - 1/mvrv (no separate fetch needed)
    # MVRV Z-Score: BG API (mvrv-zscore) → embedded 365d calculation
    mvrv_val = float('nan')
    mvrv_z = float('nan')
    mvrv_z_source = 'N/A'
    mvrv_source = 'N/A'

    # Try BG cache first (fetched via get_all_metrics_today in section 4b)
    # We do a lightweight cache-only check here to decide MVRV early,
    # then section 4b does the full batch fetch (including MVRV if needed)
    try:
        from . import bg_metrics
        bg_early = bg_metrics.get_all_metrics_today(target_date=today)
        bg_mvrv = bg_early.get('mvrv', float('nan'))
        if not math.isnan(bg_mvrv):
            mvrv_val = bg_mvrv
            mvrv_source = bg_early.get('mvrv_source', 'BG')
            print(f'[BOT] MVRV from BG cache: {mvrv_val:.4f} ({mvrv_source})')
        # MVRV Z-Score from BG
        bg_z = bg_early.get('mvrv_zscore', float('nan'))
        if not math.isnan(bg_z):
            mvrv_z = bg_z
            mvrv_z_source = 'BG'
            print(f'[BOT] MVRV Z-Score from BG: {mvrv_z:.3f}')
    except ImportError:
        pass

    # Fallback: embedded history + web
    if math.isnan(mvrv_val):
        mvrv_val = strategy.get_mvrv_for_date(today)
        if not math.isnan(mvrv_val):
            mvrv_source = 'embedded'
            # Check if embedded data is stale, try web update in background
            from datetime import timedelta as td
            if today - strategy._MVRV_HISTORY_MAX > td(days=1):
                print(f'[BOT] MVRV embedded stale (ends {strategy._MVRV_HISTORY_MAX}), '
                      f'updating in background...')
                try:
                    from . import mvrv_fetcher
                    ok, msg = mvrv_fetcher.try_update_mvrv()
                    print(f'[BOT] MVRV update: {msg}')
                except Exception as e:
                    print(f'[BOT] MVRV background update failed: {e}')
        else:
            # Embedded also missing — try web fetch
            print(f'[BOT] No embedded MVRV for {today}, trying web fallback...')
            from . import mvrv_fetcher
            web_mvrv, web_date, web_source = mvrv_fetcher.fetch_mvrv_from_web()
            if web_mvrv is not None:
                print(f'[BOT] Web MVRV: {web_mvrv:.4f} ({web_date}, {web_source})')
                if web_date and web_date > strategy._MVRV_HISTORY_MAX:
                    mvrv_fetcher.append_mvrv_to_history(web_mvrv, web_date)
                mvrv_val = web_mvrv
                mvrv_source = web_source
            else:
                print(f'[BOT] WARNING: All MVRV sources failed: {web_source}')
                notifier.send_telegram(
                    f'Phoenix v5.1 WARNING: No MVRV data for {today}. '
                    'All sources failed. Skipping trade.'
                )
                return bot_state

    mvrv_pct = strategy.compute_mvrv_percentile(today, mvrv_val)
    if math.isnan(mvrv_z):
        mvrv_z = strategy.compute_mvrv_zscore(today, mvrv_val)
        mvrv_z_source = 'embedded-365d'
    nupl = 1.0 - 1.0 / mvrv_val if mvrv_val > 0 else 0
    realized_price = price / mvrv_val if mvrv_val > 0 else float('nan')

    # ── 4b. Fetch remaining on-chain metrics from BGeometrics (BATCH) ──
    # Uses get_all_metrics_today() which:
    #   - Fetches ALL 5 metrics in one pass (1 cache load/save cycle)
    #   - Daily guard: if already fetched today, returns snapshot (0 API calls)
    #   - Typical: 5 API calls on first run/day, 0 on subsequent runs
    #
    # MVRV already obtained above from BG (section 4), but batch ensures
    # all other metrics (SOPR, RP, LTH-RP) are also fetched.
    #
    # Fallback chain for EACH indicator when API/cache fails:
    #   MVRV:            BG cache → embedded history → CoinMetrics → ahasignals
    #   MVRV Z-Score:    BG API (mvrv-zscore) → embedded 365d calculation
    #   NUPL:            1 - 1/mvrv (always computable if MVRV available)
    #   SOPR:            BG cache → price/SMA14 → price/SMA30
    #   Realized Price:  BG cache → price/mvrv
    #   LTH Realized P:  BG cache → realized_price * 1.15 (LTH holders cost basis)
    #
    # SOPR proxy rationale: SOPR = price / avg_cost_basis_of_STH
    #   SMA14 approximates short-term holder average buy price.
    #   price > SMA14 → recent buyers in profit → SOPR > 1
    #   price < SMA14 → recent buyers in loss  → SOPR < 1
    #   This is far more accurate than mvrv^0.85 which can't produce
    #   SOPR < 1 when MVRV > 1 (common divergence scenario).
    sma14 = ind.sma(closes, 14)
    sma30 = ind.sma(closes, 30)

    def _sopr_proxy(price_val, sma14_val, sma30_val):
        """Estimate SOPR from price vs short-term moving average.

        SOPR measures short-term holder P/L ratio.
        price / SMA(N) approximates this: if price > recent avg,
        recent buyers are in profit (SOPR > 1) and vice versa.
        """
        if sma14_val > 0 and not math.isnan(sma14_val):
            return price_val / sma14_val
        if sma30_val > 0 and not math.isnan(sma30_val):
            return price_val / sma30_val
        return 1.0

    def _lth_rp_proxy(realized_price_val, price, mvrv_val):
        """Estimate LTH Realized Price from Realized Price.

        LTH holders have higher cost basis than overall realized price.
        Historically LTH-RP ≈ Realized Price * 1.10-1.20.
        """
        if not math.isnan(realized_price_val) and realized_price_val > 0:
            return realized_price_val * 1.15
        # Derive from MVRV if no realized price
        if mvrv_val > 0 and not math.isnan(mvrv_val) and price > 0:
            est_rp = price / mvrv_val
            return est_rp * 1.15
        return float('nan')

    # Initialize with NaN
    sopr = float('nan')
    lth_rp = float('nan')
    sopr_source = 'N/A'
    lth_source = 'N/A'
    rp_source = 'N/A'

    try:
        from . import bg_metrics
        # BATCH fetch — one call for all metrics, daily guard active
        bg = bg_metrics.get_all_metrics_today(target_date=today)

        # --- MVRV (if BG has fresher value, override) ---
        if not math.isnan(bg.get('mvrv', float('nan'))):
            bg_mvrv_val = bg['mvrv']
            bg_mvrv_src = bg.get('mvrv_source', 'BG')
            # Only override if section 4 used a lower-priority source
            if mvrv_source != 'BG' and bg_mvrv_src == 'BG':
                mvrv_val = bg_mvrv_val
                mvrv_source = 'BG'
                # Recompute derived values with BG MVRV
                nupl = 1.0 - 1.0 / mvrv_val if mvrv_val > 0 else 0
                realized_price = price / mvrv_val if mvrv_val > 0 else realized_price
                print(f'[BOT] MVRV upgraded from BG: {mvrv_val:.4f}')

        # --- MVRV Z-Score from BG ---
        if not math.isnan(bg.get('mvrv_zscore', float('nan'))):
            mvrv_z = bg['mvrv_zscore']
            mvrv_z_source = 'BG'
            print(f'[BOT] MVRV Z-Score from BG batch: {mvrv_z:.3f}')

        # --- SOPR ---
        if not math.isnan(bg.get('sth_sopr', float('nan'))):
            sopr = bg['sth_sopr']
            sopr_source = 'BG'
        else:
            sopr = _sopr_proxy(price, sma14, sma30)
            sopr_source = 'proxy-sma14'

        # --- Realized Price ---
        if not math.isnan(bg.get('realized_price', float('nan'))):
            realized_price = bg['realized_price']
            rp_source = 'BG'
        # else: keep the MVRV-derived realized_price from section 4 above

        # --- LTH Realized Price ---
        if not math.isnan(bg.get('lth_realized_price', float('nan'))):
            lth_rp = bg['lth_realized_price']
            lth_source = 'BG'
        else:
            lth_rp = _lth_rp_proxy(realized_price, price, mvrv_val)
            lth_source = 'proxy-rp*1.15' if not math.isnan(lth_rp) else 'N/A'

        print(f'[BOT] STH-SOPR={sopr:.4f} ({sopr_source}) '
              f'LTH-RP={lth_rp:,.2f} ({lth_source}) '
              f'RP={realized_price:,.2f} ({rp_source})')
    except ImportError:
        print('[BOT] bg_metrics not found, using all-proxy mode')
        sopr = _sopr_proxy(price, sma14, sma30)
        lth_rp = _lth_rp_proxy(realized_price, price, mvrv_val)
        sopr_source = 'proxy-sma14'
        lth_source = 'proxy-rp*1.15'

    print(f'[BOT] MVRV={mvrv_val:.3f} ({mvrv_source}) Pct={mvrv_pct:.3f} Z={mvrv_z:.2f} ({mvrv_z_source}) NUPL={nupl:.3f}')

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

    # ── 6b. Separate reserve from DCA cash ──
    # In demo: sell_proceeds_reserve is tracked separately
    # In live/dry-run: we track total_sell_proceeds in state as reserve proxy
    # cash_reserve passed to strategy = ONLY profits from BTC sales
    sell_proceeds_reserve = bot_state.get('total_sell_proceeds', 0.0) - bot_state.get('total_invested_from_reserve', 0.0)
    sell_proceeds_reserve = max(sell_proceeds_reserve, 0.0)
    # For dry-run, also consider virtual sell proceeds
    if dry_run and bot_state.get('dry_run_sell_proceeds'):
        sell_proceeds_reserve = bot_state['dry_run_sell_proceeds']
    print(f'[BOT] Sell proceeds reserve: {sell_proceeds_reserve:,.2f} {currency}')

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

    # ── 9. Execute trades ──
    buy_fee = 0.0
    sell_fee = 0.0
    buy_btc_got = 0.0
    sell_btc_sold = 0.0
    buy_cost_actual = 0.0
    sell_proceeds_actual = 0.0

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
            print(f'[BOT] Bought {buy_btc_got:.8f} BTC for {buy_cost_actual:.2f} {currency} (fee: {buy_fee:.2f})')
            print(f'[BOT] BUY STATUS: SUCCESS')
        except Exception as e:
            print(f'[BOT] BUY ERROR: {e}')
            print(f'[BOT] BUY STATUS: FAILED')
            decision['buy_amount'] = 0
    elif decision['buy_amount'] > 0 and dry_run:
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
        btc_to_sell = decision['sell_amount'] / price
        if btc_to_sell >= btc_balance * 0.99:
            btc_to_sell = btc_balance * 0.99  # Never sell 100%
        min_sell = 10.0 if currency == 'USDT' else 100.0
        if btc_to_sell * price < min_sell:
            print(f'[BOT] Sell amount {btc_to_sell * price:.2f} below minimum {min_sell}. Skipping.')
            decision['sell_amount'] = 0
        else:
            print(f'[BOT] LIVE SELL: {btc_to_sell:.8f} BTC (~{decision["sell_amount"]:.2f} {currency})...')
            try:
                result = exchange.market_sell(btc_to_sell)
                sell_btc_sold = float(result.get('executed_qty', result.get('amount', 0)))
                sell_proceeds_actual = float(result.get('cummulative_quote_qty', result.get('cost', decision['sell_amount'])))
                sell_fee = float(result.get('fee', sell_proceeds_actual * config.SELL_FEE_PCT))
                bot_state['total_btc_sold'] += sell_btc_sold
                # Update cash reserve after sell
                cash_balance += sell_proceeds_actual - sell_fee
                print(f'[BOT] Sold {sell_btc_sold:.8f} BTC for {sell_proceeds_actual:.2f} {currency} (fee: {sell_fee:.2f})')
            except Exception as e:
                print(f'[BOT] SELL ERROR: {e}')
                decision['sell_amount'] = 0
    elif decision['sell_amount'] > 0 and dry_run:
        sell_btc_sold = decision['sell_amount'] / price
        sell_proceeds_actual = decision['sell_amount']
        sell_fee = sell_proceeds_actual * config.SELL_FEE_PCT
        bot_state['total_btc_sold'] += sell_btc_sold
        print(f'[BOT] DRY RUN SELL: {sell_btc_sold:.8f} BTC → {sell_proceeds_actual:.2f} {currency} (fee: {sell_fee:.2f})')

    # ── 10. Update state ──
    bot_state = state_mod.update_state_after_run(
        bot_state, decision, price, price, currency,
        buy_fee=buy_fee, sell_fee=sell_fee,
        btc_balance=btc_balance, cash_balance=cash_balance,
    )

    # Record trades in trade log
    if decision['buy_amount'] > 0 and buy_btc_got > 0:
        state_mod.append_trade_log(
            trade_log_path, 'buy', buy_cost_actual, buy_btc_got,
            price, buy_fee,
            extra={'reserve': round(decision.get('reserve_injection', 0), 2)}
        )

    if decision['sell_amount'] > 0 and sell_btc_sold > 0:
        state_mod.append_trade_log(
            trade_log_path, 'sell', sell_proceeds_actual, sell_btc_sold,
            price, sell_fee,
            extra={'path': decision.get('path_taken', ''),
                   'score': decision.get('sell_score', 0)}
        )

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
        # Track sell proceeds for reserve
        if sell_proceeds_actual > 0:
            bot_state['sell_proceeds_reserve'] = bot_state.get('sell_proceeds_reserve', 0.0) + sell_proceeds_actual - sell_fee
    portfolio = current_btc * price + current_cash

    if portfolio > bot_state['peak_value']:
        bot_state['peak_value'] = portfolio
    if bot_state['peak_value'] > 0:
        dd = (bot_state['peak_value'] - portfolio) / bot_state['peak_value']
        if dd > bot_state['max_drawdown']:
            bot_state['max_drawdown'] = dd

    # ── 11. Snapshot indicators for dashboard ──
    bot_state['last_indicators'] = {
        'price': round(price, 2),
        'mvrv': round(mvrv_val, 3),
        'mvrv_source': mvrv_source,
        'mvrv_pct': round(mvrv_pct, 3),
        'mvrv_z': round(mvrv_z, 2),
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
    base_budget_val = base_budget
    if base_budget_val > 0 and buy_amt > 0:
        calc_multiplier = round(buy_amt / base_budget_val, 1)
    else:
        calc_multiplier = 0.0
    bot_state['last_decision'] = {
        'buy_amount': round(buy_amt, 2),
        'sell_amount': round(decision.get('sell_amount', 0), 2),
        'multiplier': calc_multiplier,
        'base_budget': round(base_budget_val, 2),
        'reserve_injection': round(decision.get('reserve_injection', 0), 2),
    }
    bot_state['last_btc_balance'] = round(current_btc, 8)
    bot_state['last_cash_balance'] = round(current_cash, 2)
    bot_state['last_portfolio_value'] = round(portfolio, 2)
    bot_state['last_price'] = round(price, 2)
    bot_state['last_exchange_currency'] = currency
    bot_state['last_exchange_name'] = exchange.__class__.__name__.replace('Client', '').upper()
    bot_state['last_dry_run'] = dry_run

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
    msg = notifier.format_report(
        decision, price, mvrv_val, current_btc, current_cash,
        currency, is_dry_run=dry_run
    )
    if notifier.send_telegram(msg):
        print('[BOT] Telegram notification sent')
    else:
        print('[BOT] Telegram not configured or failed')

    print(f'[BOT] Done. Portfolio: {portfolio:,.2f} {currency}')
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
        mvrv_pct = strategy.compute_mvrv_percentile(today, mvrv_val) if not math.isnan(mvrv_val) else 0
        mvrv_z = strategy.compute_mvrv_zscore(today, mvrv_val) if not math.isnan(mvrv_val) else 0
        mvrv_z_source = 'embedded-365d'
        nupl = 1.0 - 1.0 / mvrv_val if mvrv_val > 0 and not math.isnan(mvrv_val) else 0

        bot_state['last_indicators'] = {
            'price': round(price, 2),
            'mvrv': round(mvrv_val, 3) if not math.isnan(mvrv_val) else None,
            'mvrv_pct': round(mvrv_pct, 3),
            'mvrv_z': round(mvrv_z, 2),
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
        bot_state['last_dry_run'] = dry_run
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

    # ── 3. Compute technical indicators (same as live) ──
    print('[DEMO] Computing indicators...')
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

    print(f'[DEMO] SMA200={sma_200:,.2f} RSI={rsi_val:.1f} MACD_H={macd_h:.4f}')

    # ── 4. Get MVRV — try BG cache first, then embedded, then web ──
    mvrv_val = float('nan')
    mvrv_source = 'N/A'

    try:
        from . import bg_metrics
        bg_early = bg_metrics.get_all_metrics_today(target_date=today)
        bg_mvrv = bg_early.get('mvrv', float('nan'))
        if not math.isnan(bg_mvrv):
            mvrv_val = bg_mvrv
            mvrv_source = bg_early.get('mvrv_source', 'BG')
            print(f'[DEMO] MVRV from BG: {mvrv_val:.4f} ({mvrv_source})')
    except ImportError:
        pass

    if math.isnan(mvrv_val):
        mvrv_val = strategy.get_mvrv_for_date(today)
        if not math.isnan(mvrv_val):
            mvrv_source = 'embedded'
        else:
            print(f'[DEMO] No embedded MVRV for {today}, trying web fallback...')
            from . import mvrv_fetcher
            web_mvrv, web_date, web_source = mvrv_fetcher.fetch_mvrv_from_web()
            if web_mvrv is not None:
                mvrv_val = web_mvrv
                mvrv_source = web_source
                print(f'[DEMO] Web MVRV: {web_mvrv:.4f}')
            else:
                print(f'[DEMO] WARNING: No MVRV data. Skipping.')
                return demo_state

    mvrv_pct = strategy.compute_mvrv_percentile(today, mvrv_val)
    mvrv_z = strategy.compute_mvrv_zscore(today, mvrv_val)
    mvrv_z_source = 'embedded-365d'
    nupl = 1.0 - 1.0 / mvrv_val if mvrv_val > 0 else 0
    realized_price = price / mvrv_val if mvrv_val > 0 else float('nan')

    # ── 4b. BGeometrics metrics (BATCH + fallbacks) ──
    sma14 = ind.sma(closes, 14)
    sma30 = ind.sma(closes, 30)
    def _sopr_proxy_demo(price_val, sma14_val, sma30_val):
        if sma14_val > 0 and not math.isnan(sma14_val):
            return price_val / sma14_val
        if sma30_val > 0 and not math.isnan(sma30_val):
            return price_val / sma30_val
        return 1.0

    def _lth_rp_proxy_demo(realized_price_val, price, mvrv_val):
        if not math.isnan(realized_price_val) and realized_price_val > 0:
            return realized_price_val * 1.15
        if mvrv_val > 0 and not math.isnan(mvrv_val) and price > 0:
            return (price / mvrv_val) * 1.15
        return float('nan')

    sopr = float('nan')
    lth_rp = float('nan')
    sopr_source = 'N/A'
    lth_source = 'N/A'
    rp_source = 'N/A'

    try:
        from . import bg_metrics
        bg = bg_metrics.get_all_metrics_today(target_date=today)

        # MVRV Z-Score from BG (override embedded if available)
        if not math.isnan(bg.get('mvrv_zscore', float('nan'))):
            mvrv_z = bg['mvrv_zscore']
            mvrv_z_source = bg.get('mvrv_z_source', 'BG')
            print(f'[DEMO] MVRV Z-Score from BG: {mvrv_z:.3f}')

        # MVRV upgrade from BG if applicable
        if not math.isnan(bg.get('mvrv', float('nan'))):
            bg_mvrv_val = bg['mvrv']
            bg_mvrv_src = bg.get('mvrv_source', 'BG')
            if mvrv_source != 'BG' and bg_mvrv_src == 'BG':
                mvrv_val = bg_mvrv_val
                mvrv_source = 'BG'
                nupl = 1.0 - 1.0 / mvrv_val if mvrv_val > 0 else 0
                realized_price = price / mvrv_val if mvrv_val > 0 else realized_price

        if not math.isnan(bg.get('sth_sopr', float('nan'))):
            sopr = bg['sth_sopr']
            sopr_source = 'BG'
        else:
            sopr = _sopr_proxy_demo(price, sma14, sma30)
            sopr_source = 'proxy-sma14'

        if not math.isnan(bg.get('realized_price', float('nan'))):
            realized_price = bg['realized_price']
            rp_source = 'BG'

        if not math.isnan(bg.get('lth_realized_price', float('nan'))):
            lth_rp = bg['lth_realized_price']
            lth_source = 'BG'
        else:
            lth_rp = _lth_rp_proxy_demo(realized_price, price, mvrv_val)
            lth_source = 'proxy-rp*1.15' if not math.isnan(lth_rp) else 'N/A'
    except ImportError:
        sopr = _sopr_proxy_demo(price, sma14, sma30)
        lth_rp = _lth_rp_proxy_demo(realized_price, price, mvrv_val)
        sopr_source = 'proxy-sma14'
        lth_source = 'proxy-rp*1.15'

    print(f'[DEMO] STH-SOPR={sopr:.4f} ({sopr_source}) '
          f'LTH-RP={lth_rp:,.2f} ({lth_source}) '
          f'RP={realized_price:,.2f} ({rp_source})')
    print(f'[DEMO] MVRV={mvrv_val:.3f} ({mvrv_source}) Pct={mvrv_pct:.3f} Z={mvrv_z:.2f} NUPL={nupl:.3f}')

    # ── 5. Convert budget ──
    base_budget = config.get_daily_budget()
    max_buy = config.get_max_buy()
    print(f'[DEMO] Budget: {base_budget:.2f} {currency}/run (max buy: {max_buy:.2f})')

    # ── 5b. Reserve = sell proceeds only ──
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
        cash_reserve=demo_reserve,  # Only BTC sale profits, not DCA cash
        cooldown=demo_state['cooldown'],
        base_budget=base_budget, max_buy=max_buy,
        # Reserve deployment config (all in exchange currency)
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
    )

    # ── 8. Snapshot indicators ──
    indicators_snapshot = {
        'price': round(price, 2),
        'mvrv': round(mvrv_val, 3),
        'mvrv_pct': round(mvrv_pct, 3),
        'mvrv_z': round(mvrv_z, 2),
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
    buy_amt = decision.get('buy_amount', 0)
    if base_budget > 0 and buy_amt > 0:
        calc_mult = round(buy_amt / base_budget, 1)
    else:
        calc_mult = 0.0
    demo_state['last_decision'] = {
        'buy_amount': round(buy_amt, 2),
        'sell_amount': round(decision.get('sell_amount', 0), 2),
        'multiplier': calc_mult,
        'base_budget': round(base_budget, 2),
        'reserve_injection': round(decision.get('reserve_injection', 0), 2),
    }
    dp.snapshot_indicators(demo_state, indicators_snapshot)

    # ── 9. Send notification ──
    msg = notifier.format_report(
        decision, price, mvrv_val,
        demo_state['btc'], demo_state['cash'],
        currency, is_dry_run=True,
    )
    msg = msg.replace('DRY RUN', 'DEMO')
    if notifier.send_telegram(msg):
        print('[DEMO] Telegram notification sent')

    # ── 10. Validation report (optional) ──
    if validate:
        report = dp.generate_validation_report(demo_state, project_root, scenario)
        dp.print_validation_report(report)

    return demo_state
