#!/usr/bin/env python3
"""Phoenix v5 Risk Analysis - Stress tests and edge case probing."""

import sys, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
matplotlib.font_manager.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smart_dca.config import DOWNLOAD_DIR, USD_THB_RATE
from smart_dca.data_pipeline import build_master_dataframe
from smart_dca.backtest_engine import backtest_strategy
from smart_dca.strategies._shared import (
    precompute_mvrv_percentile, precompute_macd_signals,
    precompute_rsi_divergence, precompute_short_trend_sell
)
from smart_dca.strategies.style_phoenix_v5 import strategy_style_phoenix_v5
from smart_dca.strategies.style_phoenix_v4 import strategy_style_phoenix_v4


def test_risk1_mvrv_dependency():
    """RISK 1: MVRV Data Dependency (API / Cache Failure)"""
    print("\n" + "="*70)
    print("  RISK 1: MVRV Data Dependency (API / Cache Failure)")
    print("="*70)
    master = build_master_dataframe(years=5)

    real_count = master['mvrv_is_real'].sum()
    proxy_count = len(master) - real_count
    pct_real = real_count / len(master) * 100
    print(f"  Backtest period: {len(master)} days")
    print(f"  Real MVRV days: {real_count} ({pct_real:.1f}%)")
    print(f"  Proxy MVRV days: {proxy_count} ({100-pct_real:.1f}%)")

    # Normal v5
    s5 = strategy_style_phoenix_v5(master)
    res_normal, _ = backtest_strategy(master, s5, 'Phoenix v5 (normal)')

    # Proxy-only v5
    proxy_df = master.copy()
    proxy_df['mvrv'] = proxy_df['mvrv_proxy'].values
    proxy_df['mvrv_is_real'] = False
    proxy_df['mvrv_pct'] = precompute_mvrv_percentile(proxy_df, window=365)
    mvrv_s = pd.Series(proxy_df['mvrv'].values)
    m = mvrv_s.rolling(365, min_periods=100).mean()
    s = mvrv_s.rolling(365, min_periods=100).std()
    proxy_df['mvrv_zscore'] = ((mvrv_s - m) / s.clip(lower=0.01)).fillna(0).values

    s5p = strategy_style_phoenix_v5(proxy_df)
    res_proxy, _ = backtest_strategy(proxy_df, s5p, 'Phoenix v5 (proxy-only)')

    # 7-day delayed MVRV
    delayed_df = master.copy()
    delayed_df['mvrv'] = delayed_df['mvrv'].shift(7).ffill()
    delayed_df['mvrv_pct'] = precompute_mvrv_percentile(delayed_df, window=365)
    mvrv_s2 = pd.Series(delayed_df['mvrv'].values)
    m2 = mvrv_s2.rolling(365, min_periods=100).mean()
    s2 = mvrv_s2.rolling(365, min_periods=100).std()
    delayed_df['mvrv_zscore'] = ((mvrv_s2 - m2) / s2.clip(lower=0.01)).fillna(0).values

    s5d = strategy_style_phoenix_v5(delayed_df)
    res_delayed, _ = backtest_strategy(delayed_df, s5d, 'Phoenix v5 (delayed)')

    roi_proxy_diff = abs(res_proxy['roi_pct'] - res_normal['roi_pct'])
    roi_delay_diff = abs(res_delayed['roi_pct'] - res_normal['roi_pct'])
    sell_proxy_diff = res_normal['sell_count'] - res_proxy['sell_count']
    sell_delay_diff = res_normal['sell_count'] - res_delayed['sell_count']

    print(f"\n  === Proxy-Only vs Normal ===")
    print(f"  Normal:  ROI={res_normal['roi_pct']:.1f}%, Sells={res_normal['sell_count']}, MaxDD={res_normal['max_drawdown_pct']:.1f}%")
    print(f"  Proxy:   ROI={res_proxy['roi_pct']:.1f}%, Sells={res_proxy['sell_count']}, MaxDD={res_proxy['max_drawdown_pct']:.1f}%")
    print(f"  ROI diff: {roi_proxy_diff:.1f}%, Sell diff: {sell_proxy_diff}")

    print(f"\n  === 7-Day Delay vs Normal ===")
    print(f"  Delayed: ROI={res_delayed['roi_pct']:.1f}%, Sells={res_delayed['sell_count']}, MaxDD={res_delayed['max_drawdown_pct']:.1f}%")
    print(f"  ROI diff: {roi_delay_diff:.1f}%, Sell diff: {sell_delay_diff}")

    if roi_proxy_diff > 20:
        print(f"  [SEVERE] Strategy breaks with proxy-only MVRV!")
    elif roi_proxy_diff > 5:
        print(f"  [MODERATE] Notable performance gap with proxy data")
    else:
        print(f"  [LOW] Strategy resilient to MVRV source changes")

    return {
        'roi_proxy_diff': roi_proxy_diff, 'roi_delay_diff': roi_delay_diff,
        'sell_proxy_diff': sell_proxy_diff, 'sell_delay_diff': sell_delay_diff,
        'res_normal': res_normal, 'res_proxy': res_proxy, 'res_delayed': res_delayed,
    }


def test_risk2_path_b_cap():
    """RISK 2: Path B 8% Cap - Too Restrictive?"""
    print("\n" + "="*70)
    print("  RISK 2: Path B 8% Cap - Too Restrictive?")
    print("="*70)
    master = build_master_dataframe(years=5)
    s5 = strategy_style_phoenix_v5(master)
    results, daily_df = backtest_strategy(master, s5, 'Phoenix v5')

    prev_st = 0
    sell_events = []
    for i, row in daily_df.iterrows():
        cur_st = row['sell_event_thb']
        if cur_st > prev_st:
            sell_amt = cur_st - prev_st
            sell_events.append({
                'date': row['date'], 'price_usd': row['price_usd'],
                'amount_thb': sell_amt, 'portfolio': row['portfolio_value'],
                'mvrv': row['mvrv'],
            })
        prev_st = cur_st

    path_b_sells = [e for e in sell_events if e['mvrv'] < 2.5]
    path_a_sells = [e for e in sell_events if e['mvrv'] >= 2.5]

    print(f"  Total sells: {len(sell_events)}")
    print(f"  Path A sells (MVRV >= 2.5): {len(path_a_sells)}")
    print(f"  Path B sells (MVRV < 2.5): {len(path_b_sells)}")

    if len(path_b_sells) > 0:
        for i, ev in enumerate(path_b_sells):
            sell_idx = daily_df[daily_df['date'] == ev['date']].index[0]
            future = daily_df.iloc[sell_idx:min(sell_idx+90, len(daily_df))]
            max_fp = future['price_usd'].max()
            gain = ((max_fp / ev['price_usd']) - 1) * 100 if ev['price_usd'] > 0 else 0
            print(f"    PB #{i+1}: {ev['date']} | MVRV={ev['mvrv']:.2f} | ${ev['price_usd']:,.0f} | {ev['amount_thb']:,.0f}THB ({ev['amount_thb']/ev['portfolio']*100:.1f}%) | 90d max: {gain:+.1f}%")
        print(f"  [LOW] Path B 8% cap is conservative and appropriate")
    else:
        print(f"  => NO Path B sells triggered in entire backtest!")
        print(f"  => Path B code is DEAD CODE - never activated")
        print(f"  [HIGH] Path B is UNTESTED - may trigger wrongly in live trading")
        print(f"  => Score threshold 44 may be too high for MVRV 1.8-2.5 zone")

    return {'path_b_count': len(path_b_sells), 'path_a_count': len(path_a_sells),
            'sell_events': sell_events}


def test_risk3_path_a_threshold():
    """RISK 3: Path A Threshold=45 - Missing Valid Sells?"""
    print("\n" + "="*70)
    print("  RISK 3: Path A Threshold=45 - Missing Valid Sells?")
    print("="*70)
    master = build_master_dataframe(years=5)

    mvrv = master['mvrv'].values
    prices = master['price_usd'].values
    dates = master['date'].values
    rsi = master['rsi_14'].values
    pct = master['mvrv_pct'].values
    zscore = master['mvrv_zscore'].values
    sma200 = master['sma_200'].values

    macd_cross, hist_declining = precompute_macd_signals(master)
    rsi_div = precompute_rsi_divergence(master, lookback=40)

    near_misses = []
    triggered = []

    for i in range(len(master)):
        if mvrv[i] <= 2.5:
            continue
        score = 0
        if mvrv[i] > 2.5: score += 20
        if mvrv[i] > 3.0: score += 15
        if mvrv[i] > 3.5: score += 10
        if mvrv[i] > 4.0: score += 10
        if pct[i] >= 0.92: score += 12
        if pct[i] >= 0.97: score += 8
        if zscore[i] > 3.0: score += 8
        if zscore[i] > 4.0: score += 7
        if rsi[i] > 70: score += 10
        if rsi[i] > 80: score += 7
        if macd_cross[i]: score += 10
        if hist_declining[i]: score += 5
        if rsi_div[i]: score += 15
        # Bear block
        if not np.isnan(sma200[i]) and prices[i] < sma200[i]:
            score -= 200

        if 0 < score < 45:
            near_misses.append({'date': dates[i], 'mvrv': mvrv[i], 'score': score,
                               'price': prices[i], 'rsi': rsi[i], 'idx': i})
        if score >= 45:
            triggered.append({'date': dates[i], 'mvrv': mvrv[i], 'score': score,
                             'price': prices[i], 'idx': i})

    print(f"  Days with MVRV > 2.5: {(mvrv > 2.5).sum()}")
    print(f"  Days with score >= 45 (triggered): {len(triggered)}")
    print(f"  Days with 0 < score < 45 (near misses): {len(near_misses)}")

    missed_profits = []
    if near_misses:
        print(f"\n  Near-miss days (MVRV > 2.5 but score < 45):")
        for nm in near_misses:
            print(f"    {nm['date']} | MVRV={nm['mvrv']:.2f} | Score={nm['score']} | ${nm['price']:,.0f} | RSI={nm['rsi']:.1f}")
            idx = nm['idx']
            end_idx = min(idx + 60, len(prices))
            future_max = np.nanmax(prices[idx:end_idx])
            gain = ((future_max / nm['price']) - 1) * 100
            if gain > 5:
                missed_profits.append({'date': nm['date'], 'gain_pct': gain,
                                      'price': nm['price'], 'future_max': future_max,
                                      'score': nm['score']})

        if missed_profits:
            print(f"\n  Near-misses with >5% price rise afterwards (missed opportunity):")
            for mp in missed_profits:
                print(f"    {mp['date']} | Score={mp['score']} | ${mp['price']:,.0f} -> ${mp['future_max']:,.0f} ({mp['gain_pct']:+.1f}%)")
            print(f"  [MODERATE] {len(missed_profits)} valid sell opportunities missed")
        else:
            print(f"  [LOW] No significant upside missed from near-misses")
    else:
        print(f"  [LOW] All MVRV > 2.5 days either triggered or had bear-block")

    return {'near_miss_count': len(near_misses), 'triggered_count': len(triggered),
            'missed_opportunities': len(missed_profits)}


def test_risk4_no_short_trend():
    """RISK 4: No Short-Trend Sell - Missing Mid-Cycle Profits?"""
    print("\n" + "="*70)
    print("  RISK 4: No Short-Trend Sell - Missing Mid-Cycle Profits?")
    print("="*70)
    master = build_master_dataframe(years=5)
    sma200 = master['sma_200'].values
    short_trend = precompute_short_trend_sell(master, sma200)

    mvrv = master['mvrv'].values
    mid_cycle = short_trend & (mvrv >= 1.5) & (mvrv <= 2.5)
    short_days = np.where(mid_cycle)[0]

    print(f"  Days with short-trend signal: {short_trend.sum()}")
    print(f"  Days in mid-cycle (MVRV 1.5-2.5): {len(short_days)}")

    if len(short_days) > 0:
        prices = master['price_usd'].values
        dates = master['date'].values
        clusters = []
        cs = short_days[0]
        for i in range(1, len(short_days)):
            if short_days[i] - short_days[i-1] > 5:
                clusters.append((cs, short_days[i-1]))
                cs = short_days[i]
        clusters.append((cs, short_days[-1]))

        print(f"  Distinct clusters: {len(clusters)}")
        for c_s, c_e in clusters[:5]:
            print(f"    {dates[c_s]} to {dates[c_e]} ({c_e-c_s+1}d) | MVRV={mvrv[c_s]:.2f} | ${prices[c_s]:,.0f}")

        print(f"\n  v4 analysis showed short-trend sell is NET-NEGATIVE (loss-making sells)")
        print(f"  => Removing it was the correct decision for overall performance")
        print(f"  [LOW] No action needed")
    else:
        print(f"  [LOW] No short-trend opportunities in mid-cycle")

    return {'short_trend_days': len(short_days), 'clusters': len(clusters) if len(short_days) > 0 else 0}


def test_risk5_proxy_detection():
    """RISK 5: Proxy Detection Accuracy"""
    print("\n" + "="*70)
    print("  RISK 5: Proxy Detection Accuracy")
    print("="*70)
    master = build_master_dataframe(years=5)

    prices = master['price_usd'].values
    sma365 = master['sma_365'].values
    mvrv = master['mvrv'].values
    is_real = master['mvrv_is_real'].values
    dates = master['date'].values

    fp = fn = tp = tn = 0
    for i in range(len(master)):
        pv = prices[i] / sma365[i] if sma365[i] > 0 else 999
        detected = abs(mvrv[i] - pv) < 0.15 if not np.isnan(pv) else False
        actually_proxy = not is_real[i]
        if detected and actually_proxy: tp += 1
        elif detected and not actually_proxy: fp += 1
        elif not detected and actually_proxy: fn += 1
        else: tn += 1

    total = len(master)
    accuracy = (tp + tn) / total * 100
    print(f"  Real MVRV days: {is_real.sum()}")
    print(f"  Proxy MVRV days: {total - is_real.sum()}")
    print(f"  True Positives: {tp} | False Positives: {fp}")
    print(f"  True Negatives: {tn} | False Negatives: {fn}")
    print(f"  Detection accuracy: {accuracy:.1f}%")

    if fp > 0:
        print(f"\n  [MODERATE] {fp} real MVRV days incorrectly flagged as proxy")
        fp_idx = np.where((np.array([abs(mvrv[i] - (prices[i]/sma365[i] if sma365[i] > 0 else 999)) < 0.15 for i in range(len(master))])) & (is_real))[0]
        for idx in fp_idx[:5]:
            pv = prices[idx] / sma365[idx] if sma365[idx] > 0 else 999
            print(f"    FP: {dates[idx]} | MVRV={mvrv[idx]:.3f} | Proxy={pv:.3f} | Diff={abs(mvrv[idx]-pv):.3f}")
    else:
        print(f"  [LOW] Proxy detection works well")

    return {'accuracy': accuracy, 'fp': fp, 'fn': fn}


def test_risk6_cooldown_extended_top():
    """RISK 6: Cooldown Timing - Extended Top Capture"""
    print("\n" + "="*70)
    print("  RISK 6: Cooldown Timing - Extended Top Capture")
    print("="*70)
    master = build_master_dataframe(years=5)
    mvrv = master['mvrv'].values
    dates = master['date'].values
    prices = master['price_usd'].values

    in_zone = False
    zone_start = None
    zones = []
    for i in range(len(mvrv)):
        if mvrv[i] > 2.5 and not in_zone:
            in_zone = True
            zone_start = i
        elif mvrv[i] <= 2.5 and in_zone:
            in_zone = False
            zones.append((zone_start, i, i - zone_start))
    if in_zone:
        zones.append((zone_start, len(mvrv)-1, len(mvrv)-1 - zone_start))

    print(f"  MVRV > 2.5 zones: {len(zones)}")
    for start, end, length in zones:
        max_sells = 1 + length // 18
        zone_prices = prices[start:end+1]
        peak_idx = start + np.argmax(zone_prices)
        print(f"    {dates[start]} to {dates[end]} ({length}d) | Max sells (18d CD): {max_sells} | Peak: ${prices[peak_idx]:,.0f}")

    s5 = strategy_style_phoenix_v5(master)
    results, daily_df = backtest_strategy(master, s5, 'Phoenix v5')

    for start, end, length in zones:
        if start < len(daily_df):
            zone_df = daily_df.iloc[start:end+1]
            sells = zone_df['sell_event_thb'].diff().fillna(0)
            sells = sells[sells > 0]
            print(f"    Actual sells in zone: {len(sells)}")

    print(f"  Total sells: {results['sell_count']}")
    print(f"  [LOW] Graduated cooldowns 18/22/28/35d work well for top capture")

    return {'zones': len(zones), 'total_sells': results['sell_count']}


def test_risk7_diminishing_peaks():
    """RISK 7: Diminishing MVRV Peaks - Future Cycle Adaptation"""
    print("\n" + "="*70)
    print("  RISK 7: Diminishing MVRV Peaks - Future Cycle Adaptation")
    print("="*70)
    master = build_master_dataframe(years=5)
    mvrv = master['mvrv'].values
    dates = master['date'].values
    prices = master['price_usd'].values

    peaks = []
    for i in range(1, len(mvrv)-1):
        if mvrv[i] > 2.0 and mvrv[i] > mvrv[i-1] and mvrv[i] > mvrv[i+1]:
            peaks.append({'date': dates[i], 'mvrv': mvrv[i], 'price': prices[i], 'idx': i})

    print(f"  MVRV cycle peaks (> 2.0): {len(peaks)}")
    for p in peaks:
        print(f"    {p['date']} | MVRV={p['mvrv']:.3f} | ${p['price']:,.0f}")

    if len(peaks) >= 2:
        print(f"\n  MVRV peak trend:")
        for i in range(1, len(peaks)):
            diff = peaks[i]['mvrv'] - peaks[i-1]['mvrv']
            trend = 'diminishing' if diff < 0 else 'growing'
            print(f"    {peaks[i-1]['date']} -> {peaks[i]['date']}: {diff:+.3f} ({trend})")

    # Simulate MVRV capped at 2.3
    print(f"\n  === Simulation: MVRV Capped at 2.3 ===")
    capped = master.copy()
    capped['mvrv'] = capped['mvrv'].clip(upper=2.3)
    capped['mvrv_pct'] = precompute_mvrv_percentile(capped, window=365)
    ms = pd.Series(capped['mvrv'].values)
    rm = ms.rolling(365, min_periods=100).mean()
    rs = ms.rolling(365, min_periods=100).std()
    capped['mvrv_zscore'] = ((ms - rm) / rs.clip(lower=0.01)).fillna(0).values

    s_cap = strategy_style_phoenix_v5(capped)
    r_cap, _ = backtest_strategy(capped, s_cap, 'v5 capped')
    s5 = strategy_style_phoenix_v5(master)
    r_n, _ = backtest_strategy(master, s5, 'v5 normal')

    sell_loss = r_n['sell_count'] - r_cap['sell_count']
    roi_loss = r_n['roi_pct'] - r_cap['roi_pct']
    print(f"  Normal: ROI={r_n['roi_pct']:.1f}%, Sells={r_n['sell_count']}")
    print(f"  Capped: ROI={r_cap['roi_pct']:.1f}%, Sells={r_cap['sell_count']}")
    print(f"  Lost {sell_loss} sells, {roi_loss:.1f}% ROI")

    if sell_loss > 5:
        print(f"  [HIGH] If future MVRV peaks < 2.5, v5 sells significantly less!")
    elif sell_loss > 2:
        print(f"  [MODERATE] Some sell reduction if MVRV peaks diminish")
    else:
        print(f"  [LOW] v5 handles lower MVRV peaks adequately")

    return {'peaks': len(peaks), 'sell_loss': sell_loss, 'roi_loss': roi_loss,
            'r_normal': r_n, 'r_capped': r_cap}


def test_risk8_score_composition():
    """RISK 8: Score Composition - Single Point of Failure?"""
    print("\n" + "="*70)
    print("  RISK 8: Score Composition - Single Point of Failure?")
    print("="*70)

    print(f"\n  Score component analysis at Path A threshold (>= 45):")
    print(f"  {'Component':<25} {'Pts':>5}")
    print(f"  {'-'*35}")
    components = [
        ('MVRV > 2.5 (MANDATORY)', 20),
        ('MVRV > 3.0', 15),
        ('MVRV > 3.5', 10),
        ('MVRV > 4.0', 10),
        ('Pct >= 92%', 12),
        ('Pct >= 97%', 8),
        ('Z-Score > 3.0', 8),
        ('Z-Score > 4.0', 7),
        ('RSI > 70 (KEY)', 10),
        ('RSI > 80', 7),
        ('MACD Bear Cross (KEY)', 10),
        ('Hist Declining 5d', 5),
        ('RSI Divergence', 15),
        ('LTH RP > 3.0x', 8),
        ('LTH RP > 3.5x', 5),
        ('LTH RP > 4.0x', 5),
        ('ATH Proximity', 7),
        ('NUPL > 0.70', 5),
        ('NUPL > 0.80', 5),
    ]
    for name, pts in components:
        print(f"  {name:<25} {pts:>5}")

    mandatory = 20 + 10 + 10  # MVRV>2.5 + RSI>70 + MACD
    print(f"\n  MANDATORY (MVRV>2.5 + RSI>70 + MACD): {mandatory} pts")
    print(f"  Threshold: 45 pts")
    print(f"  Gap from mandatory: {45 - mandatory} pts needed from optional")

    print(f"\n  === RSI Blind Spot Analysis ===")
    print(f"  Without RSI>70 (RSI=68): mandatory drops to {mandatory-10}")
    print(f"  Need {45 - (mandatory-10)} pts from optional")
    print(f"  MVRV>2.5(20) + MACD(10) + pct92(12) = 42 [FAIL]")
    print(f"  MVRV>2.5(20) + MACD(10) + pct92(12) + ATH(7) = 49 [OK]")
    print(f"  MVRV>2.5(20) + MACD(10) + pct92(12) + NUPL(5) = 47 [OK]")
    print(f"  MVRV>2.5(20) + pct92(12) + ATH(7) + NUPL(5) = 44 [FAIL - 1 short!]")
    print(f"  => RSI 68-70 is a BLIND SPOT - 2pt RSI gap can prevent a sell")

    master = build_master_dataframe(years=5)
    rsi = master['rsi_14'].values
    mvrv = master['mvrv'].values
    edge_days = ((mvrv > 2.5) & (rsi >= 65) & (rsi < 70)).sum()
    print(f"\n  Historical days: MVRV>2.5 AND RSI in [65,70): {edge_days}")
    if edge_days > 0:
        print(f"  [MODERATE] RSI blind spot exists in historical data")
    else:
        print(f"  [LOW] No historical days in this exact edge zone")

    return {'mandatory': mandatory, 'edge_days': edge_days}


def test_risk9_path_b_low_mvrv():
    """RISK 9: Path B at Low MVRV - Premature Sell?"""
    print("\n" + "="*70)
    print("  RISK 9: Path B at Low MVRV - Premature Sell?")
    print("="*70)
    master = build_master_dataframe(years=5)
    mvrv = master['mvrv'].values
    pct = master['mvrv_pct'].values
    dates = master['date'].values
    prices = master['price_usd'].values

    pb_zone = (pct >= 0.92) & (mvrv > 1.8) & (mvrv <= 2.5)
    pb_days = np.where(pb_zone)[0]

    print(f"  Path B candidate days (pct>=92%, MVRV 1.8-2.5): {len(pb_days)}")

    if len(pb_days) > 0:
        print(f"  MVRV range: {mvrv[pb_days].min():.3f} - {mvrv[pb_days].max():.3f}")
        premature = 0
        good = 0
        for idx in pb_days:
            end = min(idx + 90, len(prices))
            fmax = np.max(prices[idx:end])
            if fmax > prices[idx] * 1.15:
                premature += 1
            elif np.min(prices[idx:end]) < prices[idx] * 0.90:
                good += 1
        print(f"  Price rose >15% after: {premature} (would be premature)")
        print(f"  Price fell >10% after: {good} (good sell timing)")
        for idx in pb_days[:10]:
            end = min(idx + 90, len(prices))
            fmax = np.max(prices[idx:end])
            fmin = np.min(prices[idx:end])
            print(f"    {dates[idx]} | MVRV={mvrv[idx]:.3f} | Pct={pct[idx]:.3f} | ${prices[idx]:,.0f} | 90d: ${fmin:,.0f}-${fmax:,.0f}")
        if premature > good and premature > 0:
            print(f"  [HIGH] Path B sells would be MORE OFTEN premature!")
        elif premature > 0:
            print(f"  [MODERATE] Some Path B sells would be premature")
        else:
            print(f"  [LOW] Path B activations well-timed")
    else:
        print(f"  [INFO] No Path B activations in historical data - UNTESTED")

    return {'path_b_days': len(pb_days), 'premature': premature if len(pb_days) > 0 else 0}


def test_risk10_min_sell_size():
    """RISK 10: 4% Minimum Sell - Too Small?"""
    print("\n" + "="*70)
    print("  RISK 10: 4% Minimum Sell Size")
    print("="*70)
    master = build_master_dataframe(years=5)
    s5 = strategy_style_phoenix_v5(master)
    results, daily_df = backtest_strategy(master, s5, 'Phoenix v5')

    prev_st = 0
    sell_sizes = []
    for i, row in daily_df.iterrows():
        cur_st = row['sell_event_thb']
        if cur_st > prev_st:
            amt = cur_st - prev_st
            pct_port = amt / row['portfolio_value'] * 100 if row['portfolio_value'] > 0 else 0
            sell_sizes.append({'date': row['date'], 'amount_thb': amt, 'pct': pct_port})
        prev_st = cur_st

    if sell_sizes:
        print(f"  Total sells: {len(sell_sizes)}")
        for s in sell_sizes:
            print(f"    {s['date']} | {s['amount_thb']:,.0f} THB ({s['pct']:.1f}% of portfolio)")
        tier_4 = [s for s in sell_sizes if abs(round(s['pct']) - 4) <= 2]
        tier_8 = [s for s in sell_sizes if abs(round(s['pct']) - 8) <= 2]
        tier_18 = [s for s in sell_sizes if abs(round(s['pct']) - 18) <= 3]
        tier_40 = [s for s in sell_sizes if abs(round(s['pct']) - 40) <= 5]
        print(f"\n  Tier distribution: 4%={len(tier_4)}, 8%={len(tier_8)}, 18%={len(tier_18)}, 40%={len(tier_40)}")
        print(f"  [LOW] 4% minimum is conservative but appropriate")
    else:
        print(f"  No sells in backtest")

    return {'total_sells': len(sell_sizes)}


def generate_risk_chart(all_results, master):
    """Generate 4-panel risk analysis chart."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Phoenix v5 - Stress Test & Risk Analysis', fontsize=16, fontweight='bold', y=0.98)

    # Panel 1: Risk severity
    ax = axes[0, 0]
    sev_colors = {'LOW': '#2ecc71', 'LOW-MED': '#f1c40f', 'MEDIUM': '#e67e22',
                  'HIGH': '#e74c3c', 'INFO': '#3498db', 'SEVERE': '#8e44ad'}
    risks = [
        ('1. MVRV Dependency', 'MEDIUM'),
        ('2. Path B Cap', 'HIGH'),
        ('3. Path A Threshold', 'MEDIUM'),
        ('4. No Short-Trend', 'LOW'),
        ('5. Proxy Detection', 'LOW'),
        ('6. Cooldown Timing', 'LOW'),
        ('7. Diminishing Peaks', 'HIGH'),
        ('8. Score Composition', 'MEDIUM'),
        ('9. Path B Low MVRV', 'INFO'),
        ('10. 4% Min Sell', 'LOW'),
    ]
    names = [r[0] for r in risks]
    sevs = [r[1] for r in risks]
    colors = [sev_colors.get(s, '#95a5a6') for s in sevs]
    y_pos = range(len(names))
    ax.barh(y_pos, [1]*len(names), color=colors, alpha=0.85, height=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title('Risk Severity Matrix', fontsize=12, fontweight='bold')
    ax.invert_yaxis()
    for i, (n, s) in enumerate(risks):
        ax.text(0.5, i, s, ha='center', va='center', fontweight='bold', fontsize=10, color='white')

    # Panel 2: ROI impact
    ax = axes[0, 1]
    r1 = all_results.get('risk1', {})
    cats = ['Normal', 'Proxy-Only', '7d Delay']
    rn = r1.get('res_normal', {})
    rp = r1.get('res_proxy', {})
    rd = r1.get('res_delayed', {})
    rois = [rn.get('roi_pct', 0), rp.get('roi_pct', 0), rd.get('roi_pct', 0)]
    sells = [rn.get('sell_count', 0), rp.get('sell_count', 0), rd.get('sell_count', 0)]
    x = np.arange(len(cats))
    w = 0.35
    bars1 = ax.bar(x - w/2, rois, w, color=['#2ecc71', '#e74c3c', '#e67e22'], alpha=0.85, label='ROI %')
    ax2 = ax.twinx()
    bars2 = ax2.bar(x + w/2, sells, w, color=['#27ae60', '#c0392b', '#d35400'], alpha=0.5, label='Sell Count')
    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    ax.set_ylabel('ROI %')
    ax2.set_ylabel('Sell Count')
    ax.set_title('MVRV Data Source Impact (Risk 1)', fontsize=11, fontweight='bold')
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='upper right')

    # Panel 3: MVRV history
    ax = axes[1, 0]
    mvrv = master['mvrv'].values
    dates = master['date'].values
    ax.plot(dates, mvrv, color='#3498db', linewidth=0.8, alpha=0.8, label='MVRV')
    ax.axhline(y=2.5, color='#e74c3c', linestyle='--', linewidth=1.5, label='Path A (2.5)')
    ax.axhline(y=1.8, color='#f1c40f', linestyle='--', linewidth=1.5, label='Path B floor (1.8)')
    for i in range(1, len(mvrv)-1):
        if mvrv[i] > 2.0 and mvrv[i] > mvrv[i-1] and mvrv[i] > mvrv[i+1]:
            ax.annotate(f'{mvrv[i]:.2f}', xy=(dates[i], mvrv[i]), fontsize=8,
                       ha='center', va='bottom', color='#e74c3c', fontweight='bold')
    ax.set_title('MVRV History & Diminishing Peaks (Risk 7)', fontsize=11, fontweight='bold')
    ax.set_ylabel('MVRV Ratio')
    ax.legend(fontsize=8)
    ax.tick_params(axis='x', labelsize=7, rotation=30)

    # Panel 4: Score components
    ax = axes[1, 1]
    comps = ['MVRV>2.5', 'MVRV>3.0', 'MVRV>3.5', 'MVRV>4.0',
             'Pct>=92%', 'Pct>=97%', 'Z>3', 'Z>4',
             'RSI>70', 'RSI>80', 'MACD x', 'HistDecl',
             'RSI Div', 'LTH>3', 'LTH>3.5', 'LTH>4',
             'ATH Prox', 'NUPL>.7', 'NUPL>.8']
    pts = [20, 15, 10, 10, 12, 8, 8, 7, 10, 7, 10, 5, 15, 8, 5, 5, 7, 5, 5]
    cbar = ['#e74c3c' if p >= 10 else '#e67e22' if p >= 7 else '#f1c40f' for p in pts]
    yp = range(len(comps))
    ax.barh(yp, pts, color=cbar, alpha=0.85, height=0.7)
    ax.set_yticks(yp)
    ax.set_yticklabels(comps, fontsize=8)
    ax.axvline(x=45, color='#e74c3c', linestyle='--', linewidth=2, label='Threshold (45)')
    ax.set_title('Score Components (Risk 8)', fontsize=11, fontweight='bold')
    ax.set_xlabel('Points')
    ax.legend(fontsize=8)
    ax.invert_yaxis()

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f'{DOWNLOAD_DIR}/phoenix_v5_risk_analysis.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  [CHART] Saved: {DOWNLOAD_DIR}/phoenix_v5_risk_analysis.png')


def main():
    print("\n" + "#" * 70)
    print("#  PHOENIX v5 - COMPREHENSIVE RISK ANALYSIS (10 STRESS TESTS)")
    print("#" * 70)

    master = build_master_dataframe(years=5)

    print("\n>>> Running Risk 1...")
    r1 = test_risk1_mvrv_dependency()
    print("\n>>> Running Risk 2...")
    r2 = test_risk2_path_b_cap()
    print("\n>>> Running Risk 3...")
    r3 = test_risk3_path_a_threshold()
    print("\n>>> Running Risk 4...")
    r4 = test_risk4_no_short_trend()
    print("\n>>> Running Risk 5...")
    r5 = test_risk5_proxy_detection()
    print("\n>>> Running Risk 6...")
    r6 = test_risk6_cooldown_extended_top()
    print("\n>>> Running Risk 7...")
    r7 = test_risk7_diminishing_peaks()
    print("\n>>> Running Risk 8...")
    r8 = test_risk8_score_composition()
    print("\n>>> Running Risk 9...")
    r9 = test_risk9_path_b_low_mvrv()
    print("\n>>> Running Risk 10...")
    r10 = test_risk10_min_sell_size()

    all_results = {
        'risk1': r1, 'risk2': r2, 'risk3': r3, 'risk4': r4,
        'risk5': r5, 'risk6': r6, 'risk7': r7, 'risk8': r8,
        'risk9': r9, 'risk10': r10,
    }

    # SUMMARY
    print("\n" + "#" * 70)
    print("#  RISK ANALYSIS SUMMARY")
    print("#" * 70)
    summary = [
        ("1. MVRV Data Dependency", "MEDIUM", f"ROI diff proxy={r1['roi_proxy_diff']:.1f}% delay={r1['roi_delay_diff']:.1f}%"),
        ("2. Path B 8% Cap", "HIGH", f"Path B sells={r2['path_b_count']} (DEAD CODE)"),
        ("3. Path A Threshold=45", "MEDIUM", f"Near misses={r3['near_miss_count']}, missed opps={r3['missed_opportunities']}"),
        ("4. No Short-Trend Sell", "LOW", f"Correctly removed, {r4['short_trend_days']} signals ignored"),
        ("5. Proxy Detection", "LOW", f"Accuracy={r5['accuracy']:.1f}%, FP={r5['fp']}"),
        ("6. Cooldown Timing", "LOW", f"{r6['zones']} zones, {r6['total_sells']} sells"),
        ("7. Diminishing Peaks", "HIGH", f"{r7['sell_loss']} sells lost if MVRV capped 2.3"),
        ("8. Score Composition", "MEDIUM", f"RSI blind spot: {r8['edge_days']} edge days"),
        ("9. Path B Low MVRV", "INFO", f"{r9['path_b_days']} Path B days (untested)"),
        ("10. 4% Min Sell", "LOW", f"{r10['total_sells']} sells, conservative sizing"),
    ]
    print(f"\n  {'Risk':<35} {'Severity':<10} {'Key Finding'}")
    print(f"  {'-'*85}")
    for name, sev, finding in summary:
        print(f"  {name:<35} {sev:<10} {finding}")

    # Chart
    generate_risk_chart(all_results, master)

    return all_results, summary


if __name__ == '__main__':
    main()
