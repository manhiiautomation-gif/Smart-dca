import os
import sys

PATH = '/home/z/my-project/live_bot/engine.py'

with open(PATH, 'r') as f:
    lines = f.readlines()

content = ''.join(lines)

replacements = []

# ── 1. Idempotency-skip: indicator snapshot + state metadata ──
old1 = """                    bot_state['last_indicators'] = {
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
                    bot_state['last_exchange_name'] = exchange.__class__.__name__.replace('Client', '').upper()"""

new1 = """                    rm_for_snap = {**rm, 'price': refresh_price,
                                   'sell_score': bot_state.get('last_indicators', {}).get('sell_score', 0),
                                   'path_taken': bot_state.get('last_indicators', {}).get('path_taken', 'none'),
                                   'in_bear': rm['in_bear'],
                                   'cooldown': bot_state.get('cooldown', 0)}
                    bot_state['last_indicators'] = _build_indicators_snapshot(rm_for_snap)
                    _update_state_metadata(bot_state, exchange, r_btc, r_cash, r_portfolio, refresh_price)"""

replacements.append(('idem-snapshot', old1, new1))

# ── 2. run_daily: indicator snapshot ──
old2 = """    bot_state['last_indicators'] = {
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
    }"""

new2 = """    m_for_snap = {**m, 'price': price,
                   'sell_score': decision.get('sell_score', 0),
                   'path_taken': decision.get('path_taken', 'none'),
                   'in_bear': decision.get('in_bear', False),
                   'cooldown': decision.get('new_cooldown', 0)}
    bot_state['last_indicators'] = _build_indicators_snapshot(m_for_snap)"""

replacements.append(('daily-snapshot', old2, new2))

# ── 3. run_daily: decision metadata ──
old3 = """    # Store decision details for dashboard (multiplier, amounts)
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
    }"""

new3 = """    bot_state['last_decision'] = _build_decision_metadata(decision, monday_boost, in_dca_window)"""

replacements.append(('daily-decision', old3, new3))

# ── 4. run_daily: state metadata ──
old4 = """    bot_state['last_btc_balance'] = round(current_btc, 8)
    bot_state['last_cash_balance'] = round(current_cash, 2)
    bot_state['last_portfolio_value'] = round(portfolio, 2)
    bot_state['last_price'] = round(price, 2)
    bot_state['last_exchange_currency'] = currency
    bot_state['last_exchange_name'] = exchange.__class__.__name__.replace('Client', '').upper()
    bot_state['last_dry_run'] = dry_run

    # ── 11b. B18: Append indicator history"""

new4 = """    _update_state_metadata(bot_state, exchange, current_btc, current_cash, portfolio, price)
    bot_state['last_dry_run'] = dry_run

    # ── 11b. B18: Append indicator history"""

replacements.append(('daily-meta', old4, new4))

# ── 5. run_daily: Monday boost ──
old5 = """    # ── 6a. Monday DCA boost ──
    # Research: Monday has highest next-day BTC returns (+0.38% avg, 6/7 sources).
    # Apply to base_budget BEFORE strategy so max_buy cap inside strategy still works.
    monday_boost = False
    if _is_monday_thai() and config.MONDAY_DCA_MULTIPLIER != 1.0:
        base_budget = base_budget * config.MONDAY_DCA_MULTIPLIER
        monday_boost = True
        print(f'[BOT] MONDAY BOOST: base_budget x{config.MONDAY_DCA_MULTIPLIER} = {base_budget:.2f} {currency}')"""

new5 = """    # ── 6a. Monday DCA boost (CQ: shared helper) ──
    # Research: Monday has highest next-day BTC returns (+0.38% avg, 6/7 sources).
    # Apply to base_budget BEFORE strategy so max_buy cap inside strategy still works.
    base_budget, monday_boost = _apply_monday_boost(base_budget)
    if monday_boost:
        print(f'[BOT] MONDAY BOOST: base_budget x{config.MONDAY_DCA_MULTIPLIER} = {base_budget:.2f} {currency}')"""

replacements.append(('daily-monday', old5, new5))

# ── 6. Remove unused _original_buy_amt/_original_sell_amt ──
old6 = """    _original_buy_amt = decision['buy_amount']
    _original_sell_amt = decision['sell_amount']

    # BUY"""
new6 = """    # BUY"""
replacements.append(('dead-originals', old6, new6))

# ── 7. run_daily: unused variable unpacking ──
old7 = """    macd_line = m['macd_line']
    macd_sig = m['macd_sig']
    macd_h = m['macd_h']
    macd_hist_series = m['macd_hist_series']
    rsi_series = m['rsi_series']
    macd_bear = m['macd_bear']"""
new7 = """    macd_h = m['macd_h']
    macd_bear = m['macd_bear']"""
replacements.append(('daily-unpack', old7, new7))

# ── 8. min closes checks ──
old8a = """    if len(closes) < 50:
        print('[BOT] ERROR: Not enough price history for indicators')"""
new8a = """    if len(closes) < MIN_CLOSES_FOR_INDICATORS:
        print('[BOT] ERROR: Not enough price history for indicators')"""
replacements.append(('daily-min-closes', old8a, new8a))

old8b = """    if len(closes) < 50:
        print('[REFRESH] ERROR: Not enough price history')"""
new8b = """    if len(closes) < MIN_CLOSES_FOR_INDICATORS:
        print('[REFRESH] ERROR: Not enough price history')"""
replacements.append(('refresh-min-closes', old8b, new8b))

old8c = """    if len(closes) < 50:
        print('[DEMO] ERROR: Not enough price history')"""
new8c = """    if len(closes) < MIN_CLOSES_FOR_INDICATORS:
        print('[DEMO] ERROR: Not enough price history')"""
replacements.append(('demo-min-closes', old8c, new8c))

old8d = """        if len(closes) < 50:"""
new8d = """        if len(closes) < MIN_CLOSES_FOR_INDICATORS:"""
replacements.append(('snapshot-min-closes', old8d, new8d))

# ── 9. time.sleep(5) → BALANCE_VERIFY_DELAY_S ──
old9 = """                time.sleep(5)"""
new9 = """                time.sleep(BALANCE_VERIFY_DELAY_S)"""
replacements.append(('sleep-5', old9, new9))

# ── 10. btc_diff > 1e-8 → BTC_BALANCE_EPSILON ──
old10 = """                    if btc_diff > 1e-8:  # BTC balance increased"""
new10 = """                    if btc_diff > BTC_BALANCE_EPSILON:  # BTC balance increased"""
replacements.append(('btc-epsilon', old10, new10))

# ── 11. 0.99 sell cap → MAX_SELL_PCT_OF_BALANCE ──
old11 = """            if btc_to_sell >= btc_balance * 0.99:
                btc_to_sell = btc_balance * 0.99  # Never sell 100%"""
new11 = """            if btc_to_sell >= btc_balance * MAX_SELL_PCT_OF_BALANCE:
                btc_to_sell = btc_balance * MAX_SELL_PCT_OF_BALANCE  # Never sell 100%"""
replacements.append(('sell-cap', old11, new11))

# ── 12. dead branch min_sell ──
old12 = """            min_sell = 10.0 if currency == 'USDT' else 10.0"""
new12 = """            min_sell = MIN_SELL_AMOUNT"""
replacements.append(('dead-min-sell', old12, new12))

# ── 13. Remove inline import os ──
old13 = """    try:
        import os
        ih_path = os.path.join(os.path.dirname(trade_log_path), 'indicator_history.json')"""
new13 = """    try:
        ih_path = os.path.join(os.path.dirname(trade_log_path), 'indicator_history.json')"""
replacements.append(('inline-import-os', old13, new13))

# ── 14. refresh_dashboard: indicator snapshot + metadata ──
old14 = """    # ── 6. Snapshot indicators to state (same format as run_daily) ──
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
    bot_state['last_exchange_name'] = exchange.__class__.__name__.replace('Client', '').upper()"""

new14 = """    # ── 6. Snapshot indicators to state (CQ: shared helpers) ──
    rm_for_snap = {**rm, 'price': price,
                   'sell_score': bot_state.get('last_indicators', {}).get('sell_score', 0),
                   'path_taken': bot_state.get('last_indicators', {}).get('path_taken', 'none'),
                   'in_bear': in_bear,
                   'cooldown': bot_state.get('cooldown', 0)}
    bot_state['last_indicators'] = _build_indicators_snapshot(rm_for_snap, {'refreshed': True})
    _update_state_metadata(bot_state, exchange, btc_balance, cash_balance, portfolio, price)"""

replacements.append(('refresh-snapshot', old14, new14))

# ── 15. refresh_dashboard: unused variable unpacking ──
old15 = """    macd_line = rm['macd_line']
    macd_sig = rm['macd_sig']
    macd_h = rm['macd_h']
    macd_hist_series = rm['macd_hist_series']
    rsi_series = rm['rsi_series']
    macd_bear = rm['macd_bear']"""
new15 = """    macd_h = rm['macd_h']
    macd_bear = rm['macd_bear']"""
replacements.append(('refresh-unpack', old15, new15))

# ── 16. run_demo: Monday boost ──
old16 = """    # ── 5a. Monday DCA boost (same as run_daily) ──
    monday_boost = False
    if _is_monday_thai() and config.MONDAY_DCA_MULTIPLIER != 1.0:
        base_budget = base_budget * config.MONDAY_DCA_MULTIPLIER
        monday_boost = True
        print(f'[DEMO] MONDAY BOOST: base_budget x{config.MONDAY_DCA_MULTIPLIER} = {base_budget:.2f} {currency}')"""

new16 = """    # ── 5a. Monday DCA boost (CQ: shared helper) ──
    base_budget, monday_boost = _apply_monday_boost(base_budget)
    if monday_boost:
        print(f'[DEMO] MONDAY BOOST: base_budget x{config.MONDAY_DCA_MULTIPLIER} = {base_budget:.2f} {currency}')"""

replacements.append(('demo-monday', old16, new16))

# ── 17. run_demo: indicator snapshot ──
old17 = """    # ── 8. Snapshot indicators ──
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
    }"""

new17 = """    # ── 8. Snapshot indicators (CQ: shared helper) ──
    dm_for_snap = {**dm, 'price': price,
                   'sell_score': decision.get('sell_score', 0),
                   'path_taken': decision.get('path_taken', 'none'),
                   'in_bear': decision.get('in_bear', False),
                   'cooldown': decision.get('new_cooldown', 0)}
    indicators_snapshot = _build_indicators_snapshot(dm_for_snap)"""

replacements.append(('demo-snapshot', old17, new17))

# ── 18. run_demo: decision metadata ──
old18 = """    # Store decision details for dashboard
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
    }"""

new18 = """    demo_state['last_decision'] = _build_decision_metadata(decision, monday_boost, in_dca_window)"""

replacements.append(('demo-decision', old18, new18))

# ── 19. run_demo: unused variable unpacking ──
old19 = """    macd_line = dm['macd_line']
    macd_sig = dm['macd_sig']
    macd_h = dm['macd_h']
    macd_hist_series = dm['macd_hist_series']
    rsi_series = dm['rsi_series']
    macd_bear = dm['macd_bear']"""
new19 = """    macd_h = dm['macd_h']
    macd_bear = dm['macd_bear']"""
replacements.append(('demo-unpack', old19, new19))

# ── 20. _snapshot_indicators: state metadata ──
old20 = """        bot_state['last_price'] = round(price, 2)
        bot_state['last_exchange_currency'] = currency
        bot_state['last_exchange_name'] = exchange.__class__.__name__.replace('Client', '').upper()
        # D2: Do NOT overwrite last_dry_run in kill-switch snapshot path."""

new20 = """        _update_state_metadata(bot_state, exchange, 0.0, 0.0, 0.0, price)
        # D2: Do NOT overwrite last_dry_run in kill-switch snapshot path."""

replacements.append(('snapshot-meta', old20, new20))

# ═══ EXECUTE ALL REPLACEMENTS ═══
ok_count = 0
skip_count = 0

for name, old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        print(f'OK: {name}')
        ok_count += 1
    else:
        print(f'SKIP: {name} (not found — already refactored?)')
        skip_count += 1

with open(PATH, 'w') as f:
    f.write(content)

print(f'\nDone. {ok_count} replacements applied, {skip_count} skipped.')
print(f'File: {PATH} ({len(content)} chars)')
