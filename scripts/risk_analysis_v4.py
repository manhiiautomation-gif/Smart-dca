#!/usr/bin/env python3
"""Phoenix v4 Risk Analysis — Stress tests and edge case probing."""

import sys, os
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smart_dca.config import DOWNLOAD_DIR, USD_THB_RATE
from smart_dca.data_pipeline import build_master_dataframe
from smart_dca.backtest_engine import backtest_strategy
from smart_dca.strategies._shared import precompute_mvrv_percentile
from smart_dca.strategies.style_phoenix_v4 import strategy_style_phoenix_v4
from smart_dca.strategies.style_phoenix import strategy_style_phoenix

# ═══════════════════════════════════════════════════════════
# RISK 1: Path B cold-start (first 365 days = no percentile)
# ═══════════════════════════════════════════════════════════
def test_path_b_cold_start():
    print("\n" + "="*70)
    print("  RISK 1: Path B Cold-Start Problem")
    print("="*70)
    master = build_master_dataframe(years=5)
    mvrv_pct = precompute_mvrv_percentile(master, window=365)
    
    # First 365 values should all be 0
    first_365_zero = (mvrv_pct[:365] == 0).all()
    first_nonzero_idx = np.argmax(mvrv_pct > 0)
    print(f"  First 365 days all zero: {first_365_zero}")
    print(f"  First non-zero percentile at day index: {first_nonzero_idx} (day ~{first_nonzero_idx})")
    print(f"  => Path B is COMPLETELY BLIND for the first ~365 days")
    print(f"  => Only Path A (MVRV > 2.5) can trigger sells in year 1")
    print(f"  => If cycle peaks in < 365 days from start, Path B is useless")

# ═══════════════════════════════════════════════════════════
# RISK 2: Percentile false-trigger in low-volatility
# ═══════════════════════════════════════════════════════════
def test_low_vol_false_trigger():
    print("\n" + "="*70)
    print("  RISK 2: Percentile False-Trigger in Low-Volatility")
    print("="*70)
    master = build_master_dataframe(years=5)
    mvrv_pct = precompute_mvrv_percentile(master, window=365)
    
    # Find days where Path B activates (pct >= 0.92 AND mvrv > 1.8) but MVRV < 2.5
    path_b_only = (mvrv_pct >= 0.92) & (master['mvrv'] > 1.8) & (master['mvrv'] <= 2.5)
    path_b_days = master[path_b_only]
    
    print(f"  Days where Path B activates (MVRV 1.8-2.5 + pct >= 92%): {len(path_b_days)}")
    if len(path_b_days) > 0:
        print(f"  MVRV range in Path B zone: {path_b_days['mvrv'].min():.3f} - {path_b_days['mvrv'].max():.3f}")
        for _, row in path_b_days.iterrows():
            idx = master.index.get_loc(row.name) if row.name in master.index else -1
            pct = mvrv_pct[idx] if idx >= 0 else 0
            print(f"    {row['date']} | MVRV={row['mvrv']:.3f} | Pct={pct:.3f} | Price=${row['price_usd']:,.0f}")
    else:
        print("  => No Path B activations found in historical data")
        print("  => This means Path B was NEVER the sole trigger in 5 years")
        print("  => The backtest ONLY validates Path A. Path B is UNTESTED.")

# ═══════════════════════════════════════════════════════════
# RISK 3: 50% sell timing — what if top is higher?
# ═══════════════════════════════════════════════════════════
def test_50pct_sell_missed_upside():
    print("\n" + "="*70)
    print("  RISK 3: 50% Single-Sell — Missed Upside After Top")
    print("="*70)
    master = build_master_dataframe(years=5)
    test_df = master.tail(int(5 * 365.25)).reset_index(drop=True)
    
    strategy_func = strategy_style_phoenix_v4(test_df)
    results, daily_df = backtest_strategy(test_df, strategy_func, 'Phoenix v4')
    
    # Find sell events
    prev_st = 0
    sell_events = []
    for i, row in daily_df.iterrows():
        cur_st = row['sell_event_thb']
        if cur_st > prev_st:
            sell_amt = cur_st - prev_st
            sell_events.append({
                'date': row['date'], 'price_usd': row['price_usd'],
                'amount_thb': sell_amt, 'portfolio': row['portfolio_value'],
                'btc_before': row['btc'] + sell_amt / row['price_thb'],
            })
        prev_st = cur_st
    
    print(f"  Total sells: {len(sell_events)}")
    for i, ev in enumerate(sell_events):
        # Find max price AFTER this sell (within 90 days)
        sell_idx = daily_df[daily_df['date'] == ev['date']].index[0]
        future = daily_df.iloc[sell_idx:min(sell_idx+90, len(daily_df))]
        max_future_price = future['price_usd'].max()
        price_gain_after = ((max_future_price / ev['price_usd']) - 1) * 100 if ev['price_usd'] > 0 else 0
        btc_sold = ev['amount_thb'] / ev['price_usd'] / USD_THB_RATE
        missed_profit = btc_sold * (max_future_price - ev['price_usd']) * USD_THB_RATE
        
        print(f"  Sell #{i+1}: {ev['date']} | ${ev['price_usd']:,.0f} | "
              f"Amt={ev['amount_thb']:,.0f}THB | "
              f"90d max after=${max_future_price:,.0f} ({price_gain_after:+.1f}%) | "
              f"Missed upside={missed_profit:,.0f}THB")
    
    print(f"\n  => If any sell happened BEFORE the actual top, the 50% size")
    print(f"     means significant BTC was sold too early.")

# ═══════════════════════════════════════════════════════════
# RISK 4: Score composition when Path B activates
# ═══════════════════════════════════════════════════════════
def test_score_at_path_b():
    print("\n" + "="*70)
    print("  RISK 4: Score Analysis at Path B Activation Zone")
    print("="*70)
    master = build_master_dataframe(years=5)
    
    # Simulate what score would look like at various MVRV levels
    print("\n  Simulated score at different scenarios (Path B zone: MVRV 1.8-2.5):")
    print(f"  {'MVRV':>6} {'Pct':>6} {'RSI':>5} {'MACD':>5} {'Div':>4} {'LTH':>5} {'ATH':>4} {'NUPL':>6} {'TOTAL':>6} {'Sell?':>6}")
    print("  " + "-" * 65)
    
    scenarios = [
        # (mvrv, pct, rsi, macd_cross, divergence, lth_ratio, at_ath, nupl)
        (2.0, 0.92, 70, True,  False, 3.0, True,  0.70),  # Best case Path B
        (2.0, 0.92, 65, True,  False, 2.5, True,  0.60),  # Moderate
        (1.9, 0.93, 60, False, False, 2.0, False, 0.55),  # Weak signals
        (2.2, 0.95, 75, True,  True,  3.5, True,  0.75),  # Strong Path B
        (1.8, 0.92, 72, True,  False, 2.8, True,  0.65),  # Borderline MVRV
        (2.4, 0.94, 68, False, False, 3.0, True,  0.70),  # Near Path A
    ]
    
    for mvrv, pct, rsi, macd, div, lth, ath, nupl in scenarios:
        score = 0
        # MVRV absolute
        if mvrv > 2.5: score += 20
        if mvrv > 3.0: score += 15
        if mvrv > 3.5: score += 10
        if mvrv > 4.0: score += 10
        # Percentile
        if pct >= 0.92: score += 12
        if pct >= 0.97: score += 8
        # Momentum
        if rsi > 70: score += 10
        if rsi > 80: score += 7
        if macd: score += 10
        # LTH
        if lth > 3.0: score += 8
        if lth > 3.5: score += 5
        if lth > 4.0: score += 5
        # ATH
        if ath: score += 7
        # NUPL
        if nupl > 0.70: score += 5
        if nupl > 0.80: score += 5
        # Divergence
        if div: score += 15
        
        can_sell = "YES" if score >= 40 else "NO"
        print(f"  {mvrv:>6.2f} {pct:>6.2f} {rsi:>5} {str(macd):>5} {str(div):>4} {lth:>5.1f} {str(ath):>4} {nupl:>6.2f} {score:>6} {can_sell:>6}")
    
    print(f"\n  => Path B needs MULTIPLE confirmations to reach score 40")
    print(f"  => If MVRV is low (1.8-2.0), even 92nd percentile may not be enough")
    print(f"  => Requires: pct(12) + RSI>70(10) + MACD(10) + ATH(7) + NUPL(5) = 44 (barely)")
    print(f"  => Missing any one signal drops below 40 threshold")

# ═══════════════════════════════════════════════════════════
# RISK 5: Slow-grinding bear (above SMA200)
# ═══════════════════════════════════════════════════════════
def test_slow_grinding_bear():
    print("\n" + "="*70)
    print("  RISK 5: Slow-Grinding Bear (price above SMA200, no sell triggers)")
    print("="*70)
    master = build_master_dataframe(years=5)
    
    # Find periods where price is declining but still above SMA200
    # and MVRV is low (no sell trigger)
    price = master['price_usd'].values
    sma200 = master['sma_200'].values
    mvrv = master['mvrv'].values
    dates = master['date'].values
    
    declining_above_sma200 = 0
    max_streak = 0
    current_streak = 0
    worst_period = None
    worst_start = None
    
    for i in range(200, len(price)):
        if (not np.isnan(sma200[i]) and price[i] > sma200[i]
                and mvrv[i] < 2.5 and i > 0 and price[i] < price[i-1]):
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
                worst_period = dates[i]
                worst_start = dates[i - max_streak]
        else:
            declining_above_sma200 += current_streak
            current_streak = 0
    declining_above_sma200 += current_streak
    
    print(f"  Total days: price declining + above SMA200 + MVRV < 2.5: {declining_above_sma200}")
    print(f"  Longest streak: {max_streak} days ({worst_start} to {worst_period})")
    print(f"  => During these periods, v4 will NOT sell (no trigger met)")
    print(f"  => v1 would sell via short-trend sell at 2% portfolio")
    print(f"  => v4 relies only on MVRV-based triggers")

# ═══════════════════════════════════════════════════════════
# RISK 6: MVRV proxy degradation
# ═══════════════════════════════════════════════════════════
def test_mvrv_proxy_risk():
    print("\n" + "="*70)
    print("  RISK 6: MVRV Data Source Dependency")
    print("="*70)
    master = build_master_dataframe(years=5)
    
    # Check how much of the data uses proxy vs real MVRV
    # Real MVRV comes from CoinMetrics, proxy = Price/SMA365
    # They behave differently
    price = master['price_usd'].values
    sma365 = master['sma_365'].values
    real_mvrv = master['mvrv'].values
    proxy_mvrv = price / sma365
    
    # In the current data, MVRV is primarily from CoinMetrics
    # But if API fails, proxy takes over
    # Compare behavior at cycle tops
    
    # Find top 10 MVRV days
    top_indices = np.argsort(real_mvrv)[-10:][::-1]
    print(f"\n  Top 10 MVRV days — Real vs Proxy comparison:")
    print(f"  {'Date':>12} {'Real MVRV':>10} {'Proxy MVRV':>11} {'Diff':>8}")
    for idx in top_indices:
        d = master.iloc[idx]['date']
        rm = real_mvrv[idx]
        pm = proxy_mvrv[idx]
        diff = rm - pm
        print(f"  {str(d):>12} {rm:>10.3f} {pm:>11.3f} {diff:>+8.3f}")
    
    # How different are they?
    diff_arr = np.abs(real_mvrv - proxy_mvrv)
    print(f"\n  Mean |Real - Proxy|: {np.nanmean(diff_arr):.3f}")
    print(f"  Max  |Real - Proxy|: {np.nanmax(diff_arr):.3f}")
    print(f"  Correlation: {np.corrcoef(real_mvrv[~np.isnan(diff_arr)], proxy_mvrv[~np.isnan(diff_arr)])[0,1]:.4f}")
    print(f"  => If CoinMetrics API fails, proxy MVRV triggers at WRONG levels")
    print(f"  => Path B percentile would be calculated on proxy data (different distribution)")

# ═══════════════════════════════════════════════════════════
# RISK 7: Cooldown blockage during extended tops
# ═══════════════════════════════════════════════════════════
def test_cooldown_blockage():
    print("\n" + "="*70)
    print("  RISK 7: Cooldown Blockage During Extended Tops")
    print("="*70)
    master = build_master_dataframe(years=5)
    test_df = master.copy().reset_index(drop=True)
    
    # Find periods where MVRV > 2.5 (sell zone) — how long do they last?
    mvrv = master['mvrv'].values
    dates = master['date'].values
    
    in_zone = False
    zone_start = None
    zones = []
    
    for i in range(len(mvrv)):
        if mvrv[i] > 2.5 and not in_zone:
            in_zone = True
            zone_start = dates[i]
        elif mvrv[i] <= 2.5 and in_zone:
            in_zone = False
            zones.append((zone_start, dates[i], i - (np.searchsorted(dates, zone_start))))
    if in_zone:
        zones.append((zone_start, dates[-1], len(dates) - np.searchsorted(dates, zone_start)))
    
    print(f"  MVRV > 2.5 zones found: {len(zones)}")
    for start, end, length in zones:
        sells_possible = 1 + length // 20  # assuming 20-day cooldown min
        print(f"    {start} to {end} ({length} days) -> max ~{sells_possible} sells with 20d CD")
    
    print(f"\n  => With 50d cooldown after 50% sell, only 1 big sell per zone")
    print(f"  => If top lasts 100+ days, remaining upside is uncaptured")
    print(f"  => v1's 20d CD + 4% size allows 5 sells in same period")

# ═══════════════════════════════════════════════════════════
# RISK 8: Regime change — what if BTC becomes less volatile?
# ═══════════════════════════════════════════════════════════
def test_volatility_regime():
    print("\n" + "="*70)
    print("  RISK 8: BTC Volatility Regime Change")
    print("="*70)
    master = build_master_dataframe(years=5)
    
    # Calculate rolling 90-day volatility
    returns = master['price_usd'].pct_change()
    rolling_vol = returns.rolling(90).std() * np.sqrt(365) * 100
    
    print(f"  90-day annualized volatility over time:")
    for i in range(0, len(master), 180):
        v = rolling_vol.iloc[i] if not np.isnan(rolling_vol.iloc[i]) else 0
        print(f"    {master.iloc[i]['date']} | Vol={v:.1f}%")
    
    print(f"\n  Current volatility: {rolling_vol.iloc[-1]:.1f}%")
    print(f"  Historical range: {rolling_vol.min():.1f}% - {rolling_vol.max():.1f}%")
    print(f"  => If BTC stabilizes (vol < 40%), MVRV may never reach 2.5")
    print(f"  => Path B (percentile) would be the ONLY sell trigger")
    print(f"  => But Path B has score threshold issues (see Risk 4)")

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("\n" + "#" * 70)
    print("#  PHOENIX v4 — COMPREHENSIVE RISK ANALYSIS")
    print("#" * 70)
    
    test_path_b_cold_start()
    test_low_vol_false_trigger()
    test_50pct_sell_missed_upside()
    test_score_at_path_b()
    test_slow_grinding_bear()
    test_mvrv_proxy_risk()
    test_cooldown_blockage()
    test_volatility_regime()
    
    print("\n" + "#" * 70)
    print("#  RISK ANALYSIS COMPLETE")
    print("#" * 70)
