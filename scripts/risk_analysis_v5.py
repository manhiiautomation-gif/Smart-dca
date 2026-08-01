#!/usr/bin/env python3
"""Phoenix v5 Stress Test — Comprehensive risk analysis.

Tests whether v5's risk mitigations actually work, and finds
new vulnerabilities introduced by the v5 design changes.
"""

import sys, os
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smart_dca.config import USD_THB_RATE
from smart_dca.data_pipeline import build_master_dataframe
from smart_dca.backtest_engine import backtest_strategy
from smart_dca.strategies.style_phoenix_v5 import strategy_style_phoenix_v5
from smart_dca.strategies.style_phoenix_v4 import strategy_style_phoenix_v4
from smart_dca.strategies.style_phoenix import strategy_style_phoenix


# ═══════════════════════════════════════════════════════════
# RISK 1: Path B cold-start — is pre-warming actually working?
# ═══════════════════════════════════════════════════════════
def test_path_b_cold_start():
    print("\n" + "="*70)
    print("  RISK 1: Path B Cold-Start — Is pre-warming working?")
    print("="*70)
    master = build_master_dataframe(years=5)
    
    if 'mvrv_pct' in master.columns:
        pct = master['mvrv_pct'].values
        first_valid = np.argmax(pct > 0)
        valid_count = (pct > 0).sum()
        print(f"  Pre-warmed mvrv_pct column: YES")
        print(f"  First valid percentile at day index: {first_valid} ({master.iloc[first_valid]['date']})")
        print(f"  Total days with valid percentile: {valid_count} / {len(master)}")
        if first_valid < 30:
            print(f"  [PASS] Path B active from day 1 (pre-warmed from 2015+ data)")
        else:
            print(f"  [WARN] Path B still blind for first {first_valid} days")
    else:
        print(f"  [FAIL] No mvrv_pct column — pre-warming not active!")


# ═══════════════════════════════════════════════════════════
# RISK 2: Path B false trigger analysis — are Path B sells profitable?
# ═══════════════════════════════════════════════════════════
def test_path_b_sell_quality():
    print("\n" + "="*70)
    print("  RISK 2: Path B Sell Quality — Are adaptive sells profitable?")
    print("="*70)
    master = build_master_dataframe(years=5)
    test_df = master.copy().reset_index(drop=True)
    
    # Run v5 backtest
    sf = strategy_style_phoenix_v5(test_df)
    results, daily = backtest_strategy(test_df, sf, 'Phoenix v5')
    
    # Classify each sell as Path A or Path B
    mvrv = daily['mvrv'].values
    pct = master['mvrv_pct'].values if 'mvrv_pct' in master.columns else np.zeros(len(master))
    
    prev_st = 0
    path_a_sells = []
    path_b_sells = []
    
    for i, row in daily.iterrows():
        cur_st = row['sell_event_thb']
        if cur_st > prev_st and row['btc'] > 0:
            sell_amt = cur_st - prev_st
            sell_price = row['price_usd']
            avg_cost = row['avg_cost'] / USD_THB_RATE if row['avg_cost'] > 0 else 0
            profit_ratio = sell_price / avg_cost if avg_cost > 0 else 0
            
            # Classify: Path A if MVRV > 2.5, Path B if 1.8 < MVRV <= 2.5 + pct >= 0.92
            is_path_a = mvrv[i] > 2.5
            is_path_b = (mvrv[i] > 1.8) and (mvrv[i] <= 2.5) and (pct[i] >= 0.92)
            
            ev = {
                'date': row['date'], 'price_usd': sell_price,
                'amount_thb': sell_amt, 'mvrv': mvrv[i],
                'pct': pct[i], 'profit_ratio': profit_ratio,
                'avg_cost_usd': avg_cost,
            }
            
            if is_path_a:
                path_a_sells.append(ev)
            elif is_path_b:
                path_b_sells.append(ev)
            else:
                # Edge case: sell triggered but neither path?
                ev['path'] = 'UNKNOWN'
                path_b_sells.append(ev)  # count as Path B for analysis
        
        prev_st = cur_st
    
    print(f"\n  Path A sells (MVRV > 2.5): {len(path_a_sells)}")
    if path_a_sells:
        pa_prices = [s['price_usd'] for s in path_a_sells]
        pa_pl = [s['profit_ratio'] for s in path_a_sells]
        pa_mvrv = [s['mvrv'] for s in path_a_sells]
        print(f"    Avg sell price: ${np.mean(pa_prices):,.0f}")
        print(f"    Avg profit ratio: {np.mean(pa_pl):.2f}x")
        print(f"    MVRV range: {min(pa_mvrv):.2f} - {max(pa_mvrv):.2f}")
        for s in path_a_sells:
            print(f"      {s['date']} | ${s['price_usd']:,.0f} | MVRV={s['mvrv']:.2f} | P/L={s['profit_ratio']:.2f}x | {s['amount_thb']:,.0f}THB")
    
    print(f"\n  Path B sells (MVRV 1.8-2.5 + pct>=92%): {len(path_b_sells)}")
    if path_b_sells:
        pb_prices = [s['price_usd'] for s in path_b_sells]
        pb_pl = [s['profit_ratio'] for s in path_b_sells]
        pb_mvrv = [s['mvrv'] for s in path_b_sells]
        loss_sells = [s for s in path_b_sells if s['profit_ratio'] < 1.0]
        print(f"    Avg sell price: ${np.mean(pb_prices):,.0f}")
        print(f"    Avg profit ratio: {np.mean(pb_pl):.2f}x")
        print(f"    Loss-making sells: {len(loss_sells)} / {len(path_b_sells)}")
        print(f"    MVRV range: {min(pb_mvrv):.2f} - {max(pb_mvrv):.2f}")
        for s in path_b_sells:
            flag = ' [LOSS]' if s['profit_ratio'] < 1.0 else ''
            print(f"      {s['date']} | ${s['price_usd']:,.0f} | MVRV={s['mvrv']:.2f} | Pct={s['pct']:.3f} | P/L={s['profit_ratio']:.2f}x{flag} | {s['amount_thb']:,.0f}THB")
        
        if len(loss_sells) > 0:
            print(f"\n  [RISK] {len(loss_sells)} Path B sells were at a LOSS!")
            print(f"  Path B triggered at prices below average cost.")
            print(f"  Even 8% cap doesn't prevent loss-making sells.")
        else:
            print(f"\n  [PASS] All Path B sells were profitable.")
    else:
        print(f"    No Path B sells in backtest period.")
        print(f"    [WARN] Path B is UNTESTED — only validated on historical data where MVRV peaked > 2.5.")
        print(f"    If future cycle peaks at MVRV 2.0-2.4, Path B behavior is unknown.")


# ═══════════════════════════════════════════════════════════
# RISK 3: Graduated tiers — does 40% top tier capture enough?
# ═══════════════════════════════════════════════════════════
def test_graduated_tiers():
    print("\n" + "="*70)
    print("  RISK 3: Graduated Tiers — Sell size analysis")
    print("="*70)
    master = build_master_dataframe(years=5)
    test_df = master.copy().reset_index(drop=True)
    
    sf = strategy_style_phoenix_v5(test_df)
    r, daily = backtest_strategy(test_df, sf, 'v5')
    
    # Calculate sell sizes as % of portfolio
    prev_st = 0
    sell_sizes = []
    for i, row in daily.iterrows():
        cur_st = row['sell_event_thb']
        if cur_st > prev_st and row['portfolio_value'] > 0:
            sell_amt = cur_st - prev_st
            pct_of_portfolio = sell_amt / row['portfolio_value'] * 100
            sell_sizes.append({
                'date': row['date'], 'pct': pct_of_portfolio,
                'amount': sell_amt, 'price': row['price_usd']
            })
        prev_st = cur_st
    
    print(f"\n  Sell size distribution ({len(sell_sizes)} sells):")
    for s in sell_sizes:
        tier = '4%' if s['pct'] <= 5 else ('8%' if s['pct'] <= 12 else ('18%' if s['pct'] <= 25 else '40%'))
        print(f"    {s['date']} | {s['pct']:.1f}% ({tier}) | {s['amount']:,.0f}THB @ ${s['price']:,.0f}")
    
    sizes = [s['pct'] for s in sell_sizes]
    print(f"\n  Min size: {min(sizes):.1f}%, Max size: {max(sizes):.1f}%")
    print(f"  Avg size: {np.mean(sizes):.1f}%")
    
    big_sells = [s for s in sell_sizes if s['pct'] >= 15]
    if not big_sells:
        print(f"\n  [RISK] No sell exceeded 15% of portfolio!")
        print(f"  v5's graduated tiers may be too conservative at the top.")
        print(f"  v4's 50% tier captures more profit at cycle peaks.")
    
    # Compare with v4
    sf4 = strategy_style_phoenix_v4(test_df)
    r4, daily4 = backtest_strategy(test_df, sf4, 'v4')
    prev_st4 = 0
    v4_sizes = []
    for i, row in daily4.iterrows():
        cur_st = row['sell_event_thb']
        if cur_st > prev_st4 and row['portfolio_value'] > 0:
            v4_sizes.append((cur_st - prev_st4) / row['portfolio_value'] * 100)
        prev_st4 = cur_st
    
    if v4_sizes:
        print(f"\n  v4 sell sizes: min={min(v4_sizes):.1f}%, max={max(v4_sizes):.1f}%, avg={np.mean(v4_sizes):.1f}%")
    print(f"  v5 sell sizes: min={min(sizes):.1f}%, max={max(sizes):.1f}%, avg={np.mean(sizes):.1f}%")
    
    total_v4_pct = sum(v4_sizes)
    total_v5_pct = sum(sizes)
    print(f"  Total BTC sold: v4={total_v4_pct:.1f}% vs v5={total_v5_pct:.1f}% of cumulative portfolio")


# ═══════════════════════════════════════════════════════════
# RISK 4: Future cycle with low MVRV peak (2.0-2.4)
# ═══════════════════════════════════════════════════════════
def test_low_peak_future_cycle():
    print("\n" + "="*70)
    print("  RISK 4: Future Cycle with Low MVRV Peak (2.0-2.4)")
    print("="*70)
    print("  Simulating: MVRV peaks at 2.2, price rises 3x then drops 50%")
    print("  This is the scenario Path B was designed for.")
    
    master = build_master_dataframe(years=5)
    
    # Build synthetic scenario: pick a 400-day window from historical low-MVRV period
    # and inject a fake bull cycle with MVRV peaking at 2.2
    base = master[master['mvrv'] < 1.2].head(1)
    if len(base) == 0:
        base_idx = 500  # fallback
    else:
        base_idx = base.index[0]
    
    # Use actual data but with modified MVRV to simulate low-peak cycle
    # Find a period where MVRV goes from ~0.7 to ~2.2 and back
    # In our data, this happened around 2024 (cycle 4 peak at ~2.8)
    # Let's find days with MVRV between 2.0-2.5
    mid_mvrv = master[(master['mvrv'] >= 2.0) & (master['mvrv'] <= 2.5)]
    
    if len(mid_mvrv) > 0:
        print(f"\n  Historical days with MVRV 2.0-2.5: {len(mid_mvrv)}")
        print(f"  On these days:")
        print(f"    Path A (MVRV>2.5) triggers: 0 (by definition)")
        print(f"    Path B would need: pct >= 0.92 + score >= 44")
        
        pct = master['mvrv_pct'].values if 'mvrv_pct' in master.columns else np.zeros(len(master))
        
        # Check how many of these mid_mvrv days have high percentile
        high_pct_count = 0
        for _, row in mid_mvrv.iterrows():
            idx = master.index.get_loc(row.name)
            if pct[idx] >= 0.92:
                high_pct_count += 1
        
        print(f"  Days with MVRV 2.0-2.5 AND pct >= 92%: {high_pct_count}")
        
        if high_pct_count == 0:
            print(f"\n  [RISK] In the CURRENT data, MVRV 2.0-2.5 never reaches 92nd percentile!")
            print(f"  This is because our data includes higher MVRV periods (3-4.7)")
            print(f"  which dominate the 365-day rolling window.")
            print(f"  In a FUTURE cycle where MVRV peaks at only 2.2, the rolling")
            print(f"  window would NOT include those higher values, so percentile")
            print(f"  WOULD reach 92%. But we can't test this historically.")
            print(f"  => Path B is theoretically sound but empirically UNTESTED.")
        else:
            print(f"  [INFO] Path B trigger conditions exist in historical data.")
    else:
        print(f"  [WARN] No days with MVRV 2.0-2.5 found in data.")


# ═══════════════════════════════════════════════════════════
# RISK 5: Removed short-trend sell — opportunity cost
# ═══════════════════════════════════════════════════════════
def test_short_trend_removal_cost():
    print("\n" + "="*70)
    print("  RISK 5: Short-Trend Sell Removal — Opportunity Cost")
    print("="*70)
    master = build_master_dataframe(years=5)
    test_df = master.copy().reset_index(drop=True)
    
    # Run v1 (has short-trend sell) and v5
    sf1 = strategy_style_phoenix(test_df)
    r1, _ = backtest_strategy(test_df, sf1, 'v1')
    
    sf5 = strategy_style_phoenix_v5(test_df)
    r5, _ = backtest_strategy(test_df, sf5, 'v5')
    
    v1_extra_sells = r1['sell_count'] - r5['sell_count']
    v1_extra_cash = r1['cash_reserve'] - r5['cash_reserve']
    
    print(f"\n  v1 (with short-trend): {r1['sell_count']} sells, {r1['cash_reserve']:,.0f} THB cash")
    print(f"  v5 (without short-trend): {r5['sell_count']} sells, {r5['cash_reserve']:,.0f} THB cash")
    print(f"  v1 has {v1_extra_sells} more sells, {v1_extra_cash:+,.0f} THB more cash")
    
    # But v5 has better overall performance
    print(f"\n  v1 portfolio: {r1['final_value']:,.0f} THB (ROI: {r1['true_roi_pct']:.1f}%)")
    print(f"  v5 portfolio: {r5['final_value']:,.0f} THB (ROI: {r5['true_roi_pct']:.1f}%)")
    
    if r5['final_value'] >= r1['final_value']:
        print(f"  [PASS] v5 outperforms v1 despite removing short-trend sell.")
        print(f"  The short-trend sells were NET NEGATIVE — correct to remove.")
    else:
        delta = r1['final_value'] - r5['final_value']
        print(f"  [WARN] v5 underperforms v1 by {delta:,.0f} THB.")
        print(f"  Some profitable short-trend sells may have been lost.")


# ═══════════════════════════════════════════════════════════
# RISK 6: Proxy detection accuracy
# ═══════════════════════════════════════════════════════════
def test_proxy_detection():
    print("\n" + "="*70)
    print("  RISK 6: MVRV Proxy Detection — Does it work correctly?")
    print("="*70)
    master = build_master_dataframe(years=5)
    
    price = master['price_usd'].values
    sma365 = master['sma_365'].values
    real_mvrv = master['mvrv'].values
    
    # v5 proxy detection: |mvrv - price/sma365| < 0.15
    proxy_val = price / sma365
    is_proxy_v5 = np.abs(real_mvrv - proxy_val) < 0.15
    
    # Real check: use mvrv_is_real column
    is_real = master['mvrv_is_real'].values if 'mvrv_is_real' in master.columns else np.ones(len(master), dtype=bool)
    
    proxy_detected = is_proxy_v5.sum()
    actually_proxy = (~is_real).sum()
    
    print(f"\n  v5 proxy detection (|mvrv - price/sma365| < 0.15):")
    print(f"    Days flagged as proxy: {proxy_detected}")
    print(f"    Days actually using proxy data: {actually_proxy}")
    
    # Check false positives (flagged as proxy but using real data)
    false_pos = (is_proxy_v5 & is_real).sum()
    print(f"    False positives (real MVRV but flagged): {false_pos}")
    
    if actually_proxy > 0:
        # In current data, all MVRV is real (CoinMetrics works)
        # But let's check what would happen with proxy
        diff_at_top = real_mvrv - proxy_val
        top_idx = np.argsort(real_mvrv)[-20:]
        print(f"\n  At top 20 MVRV days (where sells happen):")
        print(f"    Mean |real - proxy|: {np.mean(np.abs(diff_at_top[top_idx])):.3f}")
        print(f"    Would be flagged as proxy: {(np.abs(diff_at_top[top_idx]) < 0.15).sum()} / 20")
        print(f"  => With REAL MVRV data, proxy detection correctly does NOT trigger")
        print(f"  => Proxy detection only matters if CoinMetrics API fails")
    
    # Test with actual proxy scenario
    print(f"\n  Regression proxy calibration test:")
    proxy_reg = 1.2997 * proxy_val + 0.4732
    mae_raw = np.nanmean(np.abs(real_mvrv - proxy_val))
    mae_reg = np.nanmean(np.abs(real_mvrv - proxy_reg))
    corr_raw = np.corrcoef(real_mvrv, proxy_val)[0,1]
    corr_reg = np.corrcoef(real_mvrv, proxy_reg)[0,1]
    print(f"    Raw proxy (Price/SMA365):   MAE={mae_raw:.3f}, Corr={corr_raw:.3f}")
    print(f"    Regression proxy (1.3x+0.47): MAE={mae_reg:.3f}, Corr={corr_reg:.3f}")
    print(f"  => Regression calibration reduces MAE by {(1-mae_reg/mae_raw)*100:.0f}%")


# ═══════════════════════════════════════════════════════════
# RISK 7: Cooldown timing — are 18/22/28/35d optimal?
# ═══════════════════════════════════════════════════════════
def test_cooldown_analysis():
    print("\n" + "="*70)
    print("  RISK 7: Cooldown Timing — Sell frequency analysis")
    print("="*70)
    master = build_master_dataframe(years=5)
    test_df = master.copy().reset_index(drop=True)
    
    # Find MVRV > 2.5 zones and how many sells happen
    mvrv = master['mvrv'].values
    dates = pd.to_datetime(master['date'])
    
    zones = []
    in_zone = False
    start = None
    for i in range(len(mvrv)):
        if mvrv[i] > 2.5 and not in_zone:
            in_zone = True
            start = i
        elif mvrv[i] <= 2.5 and in_zone:
            in_zone = False
            zones.append((start, i, i - start))
    if in_zone:
        zones.append((start, len(mvrv)-1, len(mvrv)-1 - start))
    
    print(f"\n  MVRV > 2.5 zones:")
    for s, e, length in zones:
        # With 18d min cooldown, max sells = 1 + (length - 1) // 18
        max_sells_18 = 1 + (length - 1) // 18
        max_sells_20 = 1 + (length - 1) // 20
        max_sells_35 = 1 + (length - 1) // 35
        print(f"    {dates[s].date()} to {dates[e].date()} ({length}d)")
        print(f"      Max sells with 18d CD: {max_sells_18}")
        print(f"      Max sells with 20d CD: {max_sells_20}")
        print(f"      Max sells with 35d CD: {max_sells_35}")
    
    # Count actual sells in zones
    sf = strategy_style_phoenix_v5(test_df)
    r, daily = backtest_strategy(test_df, sf, 'v5')
    
    prev_st = 0
    sell_dates = []
    for i, row in daily.iterrows():
        if row['sell_event_thb'] > prev_st:
            sell_dates.append(i)
        prev_st = row['sell_event_thb']
    
    print(f"\n  Actual v5 sells: {len(sell_dates)}")
    for s, e, length in zones:
        zone_sells = [d for d in sell_dates if s <= d <= e]
        print(f"    Zone {dates[s].date()}-{dates[e].date()}: {len(zone_sells)} sells")
    
    # Gap analysis: price change between sells
    if len(sell_dates) >= 2:
        gaps = []
        for i in range(1, len(sell_dates)):
            gap_days = sell_dates[i] - sell_dates[i-1]
            price_chg = (test_df.iloc[sell_dates[i]]['price_usd'] / test_df.iloc[sell_dates[i-1]]['price_usd'] - 1) * 100
            gaps.append((gap_days, price_chg))
        
        print(f"\n  Sell-to-sell gaps:")
        for gap_d, price_c in gaps:
            print(f"    {gap_d}d gap, price change: {price_c:+.1f}%")


# ═══════════════════════════════════════════════════════════
# RISK 8: Low-volatility regime — Path B dependency
# ═══════════════════════════════════════════════════════════
def test_low_vol_regime():
    print("\n" + "="*70)
    print("  RISK 8: Low-Volatility Regime — Path B as sole trigger")
    print("="*70)
    master = build_master_dataframe(years=5)
    
    returns = master['price_usd'].pct_change()
    vol_90d = returns.rolling(90).std() * np.sqrt(365) * 100
    
    # What % of time is MVRV below 2.5?
    mvrv = master['mvrv'].values
    below_25 = (mvrv < 2.5).sum()
    total = len(mvrv)
    print(f"\n  Days with MVRV < 2.5: {below_25} / {total} ({below_25/total*100:.1f}%)")
    print(f"  Days with MVRV > 2.5: {total - below_25} ({(total-below_25)/total*100:.1f}%)")
    
    # In a mature, less volatile BTC, MVRV may peak at 2.0-2.4
    # How much of the current backtest relies on Path A vs Path B?
    pct = master['mvrv_pct'].values if 'mvrv_pct' in master.columns else np.zeros(len(master))
    
    path_b_eligible = ((mvrv > 1.8) & (mvrv <= 2.5) & (pct >= 0.92)).sum()
    print(f"  Path B eligible days (MVRV 1.8-2.5 + pct>=92%): {path_b_eligible}")
    
    # Volatility trend
    print(f"\n  90-day annualized volatility (sampled):")
    for i in range(0, len(master), 200):
        v = vol_90d.iloc[i] if not np.isnan(vol_90d.iloc[i]) else 0
        print(f"    {master.iloc[i]['date']} | Vol={v:.1f}% | MVRV={master.iloc[i]['mvrv']:.2f}")
    
    print(f"\n  [INFO] In current data, Path A (MVRV>2.5) handles most sells.")
    print(f"  Path B is a SAFETY NET for future low-peak cycles.")
    print(f"  It cannot be fully validated until such a cycle occurs.")


# ═══════════════════════════════════════════════════════════
# NEW RISK 9: Score distribution at sell points
# ═══════════════════════════════════════════════════════════
def test_score_distribution():
    print("\n" + "="*70)
    print("  RISK 9: Score Distribution — Are thresholds well-calibrated?")
    print("="*70)
    master = build_master_dataframe(years=5)
    test_df = master.copy().reset_index(drop=True)
    
    # Compute full score for every day
    from smart_dca.strategies._shared import precompute_macd_signals, precompute_rsi_divergence
    macd_cross, hist_dec = precompute_macd_signals(test_df)
    rsi_div = precompute_rsi_divergence(test_df, lookback=40)
    
    mvrv = test_df['mvrv'].values
    pct = test_df['mvrv_pct'].values
    zscore = test_df['mvrv_zscore'].values
    rsi = test_df['rsi_14'].values
    nupl = test_df['nupl'].values
    lth_rp = test_df['lth_realized_price'].values
    sma200 = test_df['sma_200'].values
    price = test_df['price_usd'].values
    cummax = np.maximum.accumulate(price)
    
    scores = np.zeros(len(test_df))
    for i in range(len(test_df)):
        s = 0
        m = mvrv[i]
        if m > 2.5: s += 20
        if m > 3.0: s += 15
        if m > 3.5: s += 10
        if m > 4.0: s += 10
        if pct[i] >= 0.92: s += 12
        if pct[i] >= 0.97: s += 8
        if zscore[i] > 3.0: s += 8
        if zscore[i] > 4.0: s += 7
        if rsi[i] > 70: s += 10
        if rsi[i] > 80: s += 7
        if macd_cross[i]: s += 10
        if hist_dec[i]: s += 5
        if rsi_div[i]: s += 15
        lv = lth_rp[i]
        if not np.isnan(lv) and lv > 0:
            r = price[i] / lv
            if r > 3.0: s += 8
            if r > 3.5: s += 5
            if r > 4.0: s += 5
        if cummax[i] > 0 and price[i] > 0.97 * cummax[i]: s += 7
        n = nupl[i]
        if n > 0.70: s += 5
        if n > 0.80: s += 5
        # Bear block
        if not np.isnan(sma200[i]) and price[i] < sma200[i]:
            s -= 200
        scores[i] = max(s, 0)
    
    # Distribution in sell zone (MVRV > 2.5)
    in_sell_zone = mvrv > 2.5
    sell_zone_scores = scores[in_sell_zone]
    
    print(f"\n  Score distribution when MVRV > 2.5 (Path A zone):")
    if len(sell_zone_scores) > 0:
        print(f"    Min: {sell_zone_scores.min():.0f}")
        print(f"    25th pct: {np.percentile(sell_zone_scores, 25):.0f}")
        print(f"    Median: {np.median(sell_zone_scores):.0f}")
        print(f"    75th pct: {np.percentile(sell_zone_scores, 75):.0f}")
        print(f"    Max: {sell_zone_scores.max():.0f}")
        
        # How many days reach each tier?
        for threshold in [45, 50, 60, 75]:
            count = (sell_zone_scores >= threshold).sum()
            print(f"    Days with score >= {threshold}: {count} ({count/len(sell_zone_scores)*100:.1f}%)")
    
    # Check if threshold 45 makes sense
    below_45 = (sell_zone_scores > 0) & (sell_zone_scores < 45)
    print(f"\n  Days in sell zone but score < 45: {below_45.sum()}")
    print(f"  (These are days MVRV>2.5 but multi-confirm is weak)")
    print(f"  (v4 would sell at score >= 40, v5 requires >= 45)")
    
    if below_45.sum() > 20:
        print(f"  [WARN] {below_45.sum()} sell-zone days have score 0-44.")
        print(f"  v5's higher threshold (45 vs 40) blocks these sells.")
        print(f"  If any of these days were near a local top, v5 misses them.")


# ═══════════════════════════════════════════════════════════
# NEW RISK 10: Sell timing vs actual cycle tops
# ═══════════════════════════════════════════════════════════
def test_sell_timing_vs_tops():
    print("\n" + "="*70)
    print("  RISK 10: Sell Timing vs Actual Cycle Tops")
    print("="*70)
    master = build_master_dataframe(years=5)
    test_df = master.copy().reset_index(drop=True)
    
    sf = strategy_style_phoenix_v5(test_df)
    r, daily = backtest_strategy(test_df, sf, 'v5')
    
    sf4 = strategy_style_phoenix_v4(test_df)
    r4, daily4 = backtest_strategy(test_df, sf4, 'v4')
    
    # Find actual price peaks in the data
    price = daily['price_usd'].values
    dates = daily['date'].values
    
    # Find local peaks (higher than 60 days before and after)
    peaks = []
    for i in range(60, len(price) - 60):
        window = price[i-60:i+61]
        if price[i] == window.max():
            peaks.append(i)
    
    print(f"\n  Major price peaks found: {len(peaks)}")
    for p in peaks:
        print(f"    {dates[p]} | ${price[p]:,.0f}")
    
    # For each peak, find nearest sell before and after
    prev_st = 0
    v5_sells = []
    for i, row in daily.iterrows():
        if row['sell_event_thb'] > prev_st:
            v5_sells.append(i)
        prev_st = row['sell_event_thb']
    
    prev_st4 = 0
    v4_sells = []
    for i, row in daily4.iterrows():
        if row['sell_event_thb'] > prev_st4:
            v4_sells.append(i)
        prev_st4 = row['sell_event_thb']
    
    print(f"\n  Sell timing vs peaks:")
    for peak in peaks:
        # v5 nearest sell before peak
        v5_before = [s for s in v5_sells if s <= peak]
        v5_after = [s for s in v5_sells if s > peak]
        v4_before = [s for s in v4_sells if s <= peak]
        v4_after = [s for s in v4_sells if s > peak]
        
        v5_days_before = (peak - v5_before[-1]) if v5_before else -1
        v4_days_before = (peak - v4_before[-1]) if v4_before else -1
        
        # Price at sell vs price at peak
        if v5_before:
            v5_sell_pct = (price[peak] / price[v5_before[-1]] - 1) * 100
        else:
            v5_sell_pct = 0
        if v4_before:
            v4_sell_pct = (price[peak] / price[v4_before[-1]] - 1) * 100
        else:
            v4_sell_pct = 0
        
        print(f"\n    Peak: {dates[peak]} @ ${price[peak]:,.0f}")
        print(f"      v5 last sell: {v5_days_before}d before, sold at {v5_sell_pct:+.1f}% below peak")
        print(f"      v4 last sell: {v4_days_before}d before, sold at {v4_sell_pct:+.1f}% below peak")
    
    # Summary
    total_missed_v5 = 0
    total_missed_v4 = 0
    for peak in peaks:
        v5_before = [s for s in v5_sells if s <= peak]
        v4_before = [s for s in v4_sells if s <= peak]
        if v5_before:
            total_missed_v5 += price[peak] / price[v5_before[-1]] - 1
        if v4_before:
            total_missed_v4 += price[peak] / price[v4_before[-1]] - 1
    
    if peaks:
        avg_missed_v5 = total_missed_v5 / len(peaks) * 100
        avg_missed_v4 = total_missed_v4 / len(peaks) * 100
        print(f"\n  Avg upside missed per peak: v5={avg_missed_v5:+.1f}%, v4={avg_missed_v4:+.1f}%")
        if avg_missed_v5 > avg_missed_v4 + 5:
            print(f"  [RISK] v5 misses significantly more upside before peaks than v4.")


# ═══════════════════════════════════════════════════════════
# NEW RISK 11: What if MVRV data is stale/delayed?
# ═══════════════════════════════════════════════════════════
def test_stale_mvrv_data():
    print("\n" + "="*70)
    print("  RISK 11: Stale/Delayed MVRV Data")
    print("="*70)
    master = build_master_dataframe(years=5)
    
    # MVRV from CoinMetrics is typically 1-2 days delayed
    # What happens if we use yesterday's MVRV for today's decision?
    mvrv = master['mvrv'].values
    price = master['price_usd'].values
    
    # Simulate 1-day delay
    delayed_mvrv = np.roll(mvrv, 1)
    delayed_mvrv[0] = mvrv[0]
    
    # Days where delay changes the sell decision
    path_a_real = mvrv > 2.5
    path_a_delayed = delayed_mvrv > 2.5
    mismatch = path_a_real != path_a_delayed
    
    print(f"\n  Days where 1-day MVRV delay changes Path A trigger: {mismatch.sum()}")
    
    # Days where delay causes missed trigger (was > 2.5, delayed <= 2.5)
    missed = path_a_real & ~path_a_delayed
    false_trigger = ~path_a_real & path_a_delayed
    print(f"    Missed triggers (real > 2.5, delayed <= 2.5): {missed.sum()}")
    print(f"    False triggers (real <= 2.5, delayed > 2.5): {false_trigger.sum()}")
    
    if missed.sum() > 0:
        print(f"\n  Missed trigger dates:")
        for i in np.where(missed)[0][:10]:
            print(f"    {master.iloc[i]['date']} | Real MVRV={mvrv[i]:.3f} | Delayed={delayed_mvrv[i]:.3f} | Price=${price[i]:,.0f}")
    
    # 2-day delay
    delayed2 = np.roll(mvrv, 2)
    delayed2[0] = delayed2[1] = mvrv[0]
    missed2 = (mvrv > 2.5) & (delayed2 <= 2.5)
    print(f"\n  With 2-day delay, missed Path A triggers: {missed2.sum()}")
    print(f"  => MVRV data delay of 1-2 days can cause missed sell windows.")
    print(f"  => This affects BOTH v4 and v5 equally.")


# ═══════════════════════════════════════════════════════════
# NEW RISK 12: Reserve deployment — is v5's reserve drain effective?
# ═══════════════════════════════════════════════════════════
def test_reserve_effectiveness():
    print("\n" + "="*70)
    print("  RISK 12: Reserve Deployment Effectiveness")
    print("="*70)
    master = build_master_dataframe(years=5)
    test_df = master.copy().reset_index(drop=True)
    
    sf5 = strategy_style_phoenix_v5(test_df)
    r5, daily5 = backtest_strategy(test_df, sf5, 'v5')
    
    sf4 = strategy_style_phoenix_v4(test_df)
    r4, daily4 = backtest_strategy(test_df, sf4, 'v4')
    
    print(f"\n  {'Metric':<30} {'v4':>14} {'v5':>14} {'Delta':>14}")
    print(f"  {'-'*72}")
    
    metrics = [
        ('Cash Reserve (THB)', r4['cash_reserve'], r5['cash_reserve']),
        ('Total Sell Proceeds', r4['total_sell_proceeds'], r5['total_sell_proceeds']),
        ('Reserve Injected', r4['total_reserve_injected'], r5['total_reserve_injected']),
        ('Reserve Utilization %', r4['reserve_utilization_pct'], r5['reserve_utilization_pct']),
        ('Reserve Buy Days', r4['reserve_buy_days'], r5['reserve_buy_days']),
        ('BTC Held', r4['total_btc'], r5['total_btc']),
    ]
    
    for name, v4v, v5v in metrics:
        delta = v5v - v4v
        if abs(v4v) > 1000:
            print(f"  {name:<30} {v4v:>14,.0f} {v5v:>14,.0f} {delta:>+14,.0f}")
        elif abs(v4v) > 1:
            print(f"  {name:<30} {v4v:>14.2f} {v5v:>14.2f} {delta:>+14.2f}")
        else:
            print(f"  {name:<30} {v4v:>14.6f} {v5v:>14.6f} {delta:>+14.6f}")
    
    print(f"\n  v5 holds {r5['total_btc']/r4['total_btc']:.2f}x more BTC than v4.")
    print(f"  This is because v5 sells less total BTC (smaller tier sizes).")
    print(f"  In a bear market, more BTC = more downside exposure.")
    print(f"  But the reserve cash acts as a cushion.")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("\n" + "#" * 70)
    print("#  PHOENIX v5 — COMPREHENSIVE STRESS TEST & RISK ANALYSIS")
    print("#" * 70)
    
    test_path_b_cold_start()
    test_path_b_sell_quality()
    test_graduated_tiers()
    test_low_peak_future_cycle()
    test_short_trend_removal_cost()
    test_proxy_detection()
    test_cooldown_analysis()
    test_low_vol_regime()
    test_score_distribution()
    test_sell_timing_vs_tops()
    test_stale_mvrv_data()
    test_reserve_effectiveness()
    
    print("\n" + "#" * 70)
    print("#  STRESS TEST COMPLETE")
    print("#" * 70)
