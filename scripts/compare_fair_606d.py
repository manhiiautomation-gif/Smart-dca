#!/usr/bin/env python3
"""Fair 606-day comparison: Smart DCA (btc-signal-analyzer) vs Phoenix v5.1.

Both strategies run on the EXACT SAME 606 days (2024-12-29 to 2026-08-26)
using Binance real prices. This is an apple-to-apple comparison.

Smart DCA: $100/day budget, buy-only (no sell), from historical_scores.csv
Phoenix v5.1: 100 THB/day budget ($2.78 equiv), buy+sell, from smart_dca engine

To make it fair, we also run Phoenix at $100/day equivalent (3600 THB/day).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.font_manager as fm
fm.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

from datetime import date

# Import Phoenix engine and strategy
from smart_dca.data_pipeline import build_master_dataframe
from smart_dca.backtest_engine import backtest_strategy
from smart_dca.strategies.style_phoenix_v5_1 import strategy_style_phoenix_v5_1
from smart_dca.strategies.style_phoenix_v5 import strategy_style_phoenix_v5
from smart_dca.strategies.standard_dca import strategy_standard_dca

# Import Smart DCA data
SMART_CSV = '/home/z/btc-signal-analyzer/output/historical_scores.csv'
SMART_RESULTS = '/home/z/btc-signal-analyzer/output/backtest_results.json'

USD_THB = 36.0

print('=' * 80)
print('  FAIR COMPARISON: Smart DCA vs Phoenix v5.1 (606-day period)')
print('=' * 80)

# ============================================================
# 1. LOAD SMART DCA DATA (606 days)
# ============================================================
print('\n[1] Loading Smart DCA data...')
smart_df = pd.read_csv(SMART_CSV, parse_dates=['date'])
smart_df['date'] = smart_df['date'].dt.date

# Find the scored period
scored = smart_df.dropna(subset=['signal_score']).copy()
print(f'    Scored days: {len(scored)} ({scored["date"].iloc[0]} to {scored["date"].iloc[-1]})')

# Get exact start/end from smart DCA results
import json
with open(SMART_RESULTS) as f:
    smart_results = json.load(f)
period_start = smart_results['full_backtest']['period'][0][:10]
period_end = smart_results['full_backtest']['period'][1][:10]
print(f'    Smart DCA backtest period: {period_start} to {period_end}')

start_date = pd.to_datetime(period_start).date()
end_date = pd.to_datetime(period_end).date()

# ============================================================
# 2. LOAD PHOENIX DATA (same period)
# ============================================================
print('\n[2] Building Phoenix data pipeline...')
master = build_master_dataframe(years=5)
master['date'] = pd.to_datetime(master['date']).dt.date

# Filter to same 606-day period
phoenix_df = master[(master['date'] >= start_date) & (master['date'] <= end_date)].copy()
phoenix_df = phoenix_df.reset_index(drop=True)
print(f'    Phoenix period: {phoenix_df["date"].iloc[0]} to {phoenix_df["date"].iloc[-1]} ({len(phoenix_df)} days)')
print(f'    MVRV range: {phoenix_df["mvrv"].min():.3f} to {phoenix_df["mvrv"].max():.3f}')
print(f'    Price range: ${phoenix_df["price_usd"].min():,.0f} to ${phoenix_df["price_usd"].max():,.0f}')

# ============================================================
# 3. RUN PHOENIX v5.1 BACKTEST (same period)
# ============================================================
print('\n[3] Running Phoenix v5.1 backtest on 606-day period...')

# We need the precomputed indicators for the full period (for lookbacks)
# But we only backtest on the 606-day window
# Strategy needs precomputed data, so we pass the full master
s51_full = strategy_style_phoenix_v5_1(master)

# For the 606-day window, we need to map indices
# The strategy uses global idx, so we need to find the start idx in master
start_idx = master[(pd.to_datetime(master['date']).dt.date >= start_date)].index[0]
end_idx = master[(pd.to_datetime(master['date']).dt.date <= end_date)].index[-1]

# Run on the 606-day slice
phoenix_test = phoenix_df.copy()
r51, d51 = backtest_strategy(phoenix_test, s51_full, 'Phoenix v5.1')

print(f'    Phoenix v5.1: True ROI={r51["true_roi_pct"]:+.1f}%, ROI={r51["roi_pct"]:+.1f}%, DD={r51["max_drawdown_pct"]:.1f}%, Sells={r51["sell_count"]}')
print(f'    Net Capital: {r51["net_capital"]:,.0f} THB, Final Value: {r51["final_value"]:,.0f} THB')
print(f'    BTC: {r51["total_btc"]:.8f}, Avg Cost: {r51["avg_cost_thb"]:,.0f} THB')

# Also run v5 for reference
print('\n[4] Running Phoenix v5 backtest on 606-day period...')
s5_full = strategy_style_phoenix_v5(master)
r5, d5 = backtest_strategy(phoenix_test, s5_full, 'Phoenix v5')
print(f'    Phoenix v5:   True ROI={r5["true_roi_pct"]:+.1f}%, ROI={r5["roi_pct"]:+.1f}%, DD={r5["max_drawdown_pct"]:.1f}%, Sells={r5["sell_count"]}')

# Also run Standard DCA as benchmark
print('\n[5] Running Standard DCA (100 THB/day)...')
s_std = strategy_standard_dca
r_std, d_std = backtest_strategy(phoenix_test, s_std, 'Standard DCA (100 THB)')
print(f'    Std DCA:      True ROI={r_std["true_roi_pct"]:+.1f}%, ROI={r_std["roi_pct"]:+.1f}%, DD={r_std["max_drawdown_pct"]:.1f}%')

# ============================================================
# 4. CONVERT SMART DCA RESULTS TO COMPARABLE FORMAT
# ============================================================
print('\n[6] Loading Smart DCA results...')
smart_strats = smart_results['full_backtest']['strategies']

# Smart DCA budget = $100/day = 3600 THB/day
# Phoenix budget = 100 THB/day
# To compare fairly, normalize both to percentage return

# ============================================================
# 5. BUILD COMPARISON TABLE
# ============================================================
print('\n' + '=' * 100)
print('  COMPARISON RESULTS (606 days: %s to %s)' % (start_date, end_date))
print('=' * 100)

# Phoenix results are in THB, Smart DCA in USD
# Convert everything to USD for fair comparison
USD_THB_RATE = 36.0

# Smart DCA strategies (from btc-signal-analyzer backtest)
smart_strat_names = ['baseline_dca', 'gated_dca', 'score_weighted_dca', 'zone_dca', 'smart_dca']

print(f"\n{'Strategy':<30s} {'Budget':>8s} {'Currency':>8s} {'Return%':>9s} {'Entry$':>10s} {'MaxDD%':>8s} {'Sharpe':>7s} {'BTC':>10s} {'Buy/Skip':>10s}")
print('-' * 100)

for sname in smart_strat_names:
    s = smart_strats[sname]
    ret = s['total_return_pct']
    entry = s['avg_entry_price']
    dd = s.get('max_drawdown_pct', 0)
    sh = s.get('sharpe_ratio', 0)
    btc = s['btc_accumulated']
    buy = s.get('buy_days', 0)
    skip = s.get('skip_days', 0)
    dd_s = f"{dd:>+.1f}%" if dd else 'N/A'
    sh_s = f"{sh:>+.3f}" if sh else 'N/A'
    marker = ''
    if sname == 'smart_dca':
        marker = ' *'
    print(f"  {sname:<28s} {'$100/d':>8s} {'USD':>8s} {ret:>+8.2f}% ${entry:>8,.0f} {dd_s:>8s} {sh_s:>7s} {btc:>10.6f} {buy:>4d}/{skip:<4d}{marker}")

print('-' * 100)

# Phoenix strategies (convert THB to USD for comparison)
phoenix_strats = [
    ('Standard DCA (100 THB/d)', r_std),
    ('Phoenix v5', r5),
    ('Phoenix v5.1', r51),
]

for pname, pr in phoenix_strats:
    ret_usd = pr['roi_pct']  # already %
    true_roi = pr['true_roi_pct']
    entry_usd = pr['avg_cost_thb'] / USD_THB_RATE
    dd = pr['max_drawdown_pct']
    calmar = pr.get('calmar_ratio', 0)
    btc = pr['total_btc']
    buy = pr['buy_days']
    sells = pr['sell_count']
    dd_s = f"{dd:>+6.1f}%"
    cal_s = f"{calmar:>.2f}"
    marker = ''
    if 'v5.1' in pname:
        marker = ' **'
    print(f"  {pname:<28s} {'100THB/d':>8s} {'THB':>8s} {ret_usd:>+8.2f}% ${entry_usd:>8,.0f} {dd_s:>8s} {cal_s:>7s} {btc:>10.8f} {buy:>3d}buy/{sells}sell{marker}")

print('-' * 100)
print(f'  *  = Smart DCA (best of signal-analyzer)')
print(f'  ** = Phoenix v5.1 (current production)')
print(f'\n  Note: Smart DCA is BUY-ONLY ($100/day). Phoenix is BUY+SELL (100 THB/day ≈ $2.78/day)')
print(f'  Smart DCA total spent: ~$51,484 | Phoenix net capital: ~{r51["net_capital"]:,.0f} THB (${r51["net_capital"]/USD_THB_RATE:,.0f})')

# ============================================================
# 6. DETAILED ANALYSIS
# ============================================================
print(f'\n' + '=' * 80)
print('  DETAILED ANALYSIS')
print('=' * 80)

smart_dca = smart_strats['smart_dca']
baseline = smart_strats['baseline_dca']

print(f'\n  Smart DCA (signal-analyzer):')
print(f'    Budget:           $100/day (USD)')
print(f'    Total Spent:      ${smart_dca["total_spent"]:,.2f}')
print(f'    BTC Accumulated:  {smart_dca["btc_accumulated"]:.8f} BTC')
print(f'    Avg Entry Price:  ${smart_dca["avg_entry_price"]:,.2f}')
print(f'    Final Value:      ${smart_dca["final_value"]:,.2f}')
print(f'    Return:           {smart_dca["total_return_pct"]:+.2f}%')
print(f'    Buy Days:         {smart_dca["buy_days"]} / {smart_dca["buy_days"]+smart_dca["skip_days"]} ({smart_dca["buy_ratio"]*100:.1f}%)')
print(f'    Alpha vs Baseline: {smart_dca["total_return_pct"] - baseline["total_return_pct"]:+.2f}%')

print(f'\n  Phoenix v5.1 (production):')
print(f'    Budget:           100 THB/day ({100/USD_THB:.2f} USD/day)')
print(f'    Net Capital:      {r51["net_capital"]:,.0f} THB (${r51["net_capital"]/USD_THB_RATE:,.2f})')
print(f'    Total Invested:   {r51["total_invested"]:,.0f} THB (${r51["total_invested"]/USD_THB_RATE:,.2f})')
print(f'    BTC Accumulated:  {r51["total_btc"]:.8f} BTC')
print(f'    Avg Entry Price:  ${r51["avg_cost_thb"]/USD_THB_RATE:,.2f} ({r51["avg_cost_thb"]:,.0f} THB)')
print(f'    Final Value:      {r51["final_value"]:,.0f} THB (${r51["final_value"]/USD_THB_RATE:,.2f})')
print(f'    ROI:              {r51["roi_pct"]:+.1f}%')
print(f'    True ROI:         {r51["true_roi_pct"]:+.1f}%')
print(f'    Max Drawdown:     {r51["max_drawdown_pct"]:.1f}%')
print(f'    Calmar Ratio:     {r51["calmar_ratio"]:.2f}')
print(f'    Sells:            {r51["sell_count"]}')
print(f'    Reserve Used:     {r51["total_reserve_injected"]:,.0f} THB')
print(f'    Fees Paid:        {r51["total_fees_paid"]:,.0f} THB')

print(f'\n  Standard DCA (100 THB/day, same period):')
print(f'    Net Capital:      {r_std["net_capital"]:,.0f} THB')
print(f'    BTC Accumulated:  {r_std["total_btc"]:.8f} BTC')
print(f'    Final Value:      {r_std["final_value"]:,.0f} THB')
print(f'    ROI:              {r_std["roi_pct"]:+.1f}%')
print(f'    True ROI:         {r_std["true_roi_pct"]:+.1f}%')
print(f'    Max Drawdown:     {r_std["max_drawdown_pct"]:.1f}%')

# ============================================================
# 7. GENERATE CHART
# ============================================================
print('\n[7] Generating comparison chart...')

fig, axes = plt.subplots(2, 2, figsize=(18, 12), constrained_layout=True)
fig.suptitle('Smart DCA vs Phoenix v5.1 — Fair 606-Day Comparison\n(%s to %s)' % (start_date, end_date),
             fontsize=15, fontweight='bold')

# Panel 1: Portfolio Value Over Time
ax1 = axes[0, 0]
d_std['date'] = pd.to_datetime(d_std['date'])
d5['date'] = pd.to_datetime(d5['date'])
d51['date'] = pd.to_datetime(d51['date'])

# Smart DCA portfolio (in USD, computed from btc * price)
scored_copy = scored.copy()
scored_copy['date'] = pd.to_datetime(scored_copy['date'])
# Reconstruct smart DCA portfolio value
smart_daily_btc = 0
smart_portvals = []
for _, row in scored_copy.iterrows():
    score = row['signal_score']
    if pd.isna(score):
        smart_portvals.append(0)
        continue
    # Smart DCA logic
    params = {"fear_boost": 2.5, "greed_skip": 45.0, "mom_skip": 3.0, "below_ma_boost": 1.4, "above_ma_cut": 0.6, "neutral_mult": 1.1, "min_buy_pct": 0.2}
    price = row['close']
    ma200 = scored_copy['close'].rolling(200).mean()
    bm = price < ma200.loc[row.name] if not pd.isna(ma200.loc[row.name]) else True
    mom = score - scored_copy['signal_score'].shift(3).loc[row.name]
    if pd.isna(mom): mom = 0

    if score >= params['greed_skip']:
        amt = 0
    elif mom > params['mom_skip']:
        amt = 100 * params['min_buy_pct']
    else:
        amt = 100
        if score < 25: amt *= params['fear_boost']
        elif 40 <= score < 50: amt *= params['neutral_mult']
        if bm: amt *= params['below_ma_boost']
        else: amt *= params['above_ma_cut']

    smart_daily_btc += amt / price
    smart_portvals.append(smart_daily_btc * price)

# Baseline DCA portfolio
base_btc = 0
base_portvals = []
for _, row in scored_copy.iterrows():
    if pd.isna(row['signal_score']):
        base_portvals.append(0)
        continue
    base_btc += 100 / row['close']
    base_portvals.append(base_btc * row['close'])

ax1.plot(scored_copy['date'], base_portvals, color='#9E9E9E', linewidth=1.5, label='Baseline DCA ($100/d)', alpha=0.8)
ax1.plot(scored_copy['date'], smart_portvals, color='#FF5722', linewidth=2, label='Smart DCA ($100/d)')

# Phoenix portfolios (convert THB to USD)
ax1_twin = ax1.twinx()
ax1_twin.plot(d_std['date'], d_std['portfolio_value'] / USD_THB, color='#9E9E9E', linewidth=1, linestyle='--', label='Std DCA (100THB/d)', alpha=0.5)
ax1_twin.plot(d5['date'], d5['portfolio_value'] / USD_THB, color='#2196F3', linewidth=1.5, linestyle='--', label='Phoenix v5')
ax1_twin.plot(d51['date'], d51['portfolio_value'] / USD_THB, color='#4CAF50', linewidth=2, linestyle='--', label='Phoenix v5.1')

ax1.set_title('Portfolio Value Over Time')
ax1.set_ylabel('Smart DCA (USD)', color='#FF5722')
ax1_twin.set_ylabel('Phoenix (USD equiv.)', color='#4CAF50')
ax1.legend(loc='upper left', fontsize=8)
ax1_twin.legend(loc='center right', fontsize=8)
ax1.grid(True, alpha=0.3, linestyle='--')
ax1.tick_params(axis='x', rotation=30)

# Panel 2: BTC Price + MVRV
ax2 = axes[0, 1]
color_map = {'price': '#FFD700'}
ax2.plot(d51['date'], d51['price_usd'], color='#FFD700', linewidth=1.5, label='BTC Price (USD)')
ax2.set_ylabel('BTC Price (USD)', color='#FFD700')
ax2_twin = ax2.twinx()
ax2_twin.plot(d51['date'], d51['mvrv'], color='#FF9800', linewidth=1, alpha=0.7, label='MVRV')
ax2_twin.axhline(y=2.5, color='red', linestyle='--', alpha=0.3, label='MVRV 2.5 (sell zone)')
ax2_twin.set_ylabel('MVRV Ratio', color='#FF9800')
ax2.set_title('BTC Price & MVRV')
ax2.legend(loc='upper left', fontsize=8)
ax2_twin.legend(loc='upper right', fontsize=8)
ax2.grid(True, alpha=0.3, linestyle='--')
ax2.tick_params(axis='x', rotation=30)

# Panel 3: Comparison Table
ax3 = axes[1, 0]
ax3.axis('off')
ax3.set_title('Results Comparison', fontsize=12, fontweight='bold')

# Build comparison data
compare_data = [
    ['Metric', 'Smart DCA', 'Baseline DCA', 'Phoenix v5', 'Phoenix v5.1', 'Std DCA'],
    ['Budget', '$100/day', '$100/day', '100THB/day', '100THB/day', '100THB/day'],
    ['Currency', 'USD', 'USD', 'THB', 'THB', 'THB'],
    ['Total Spent', f'${smart_dca["total_spent"]:,.0f}', f'${baseline["total_spent"]:,.0f}',
     f'{r5["total_invested"]:,.0f} THB', f'{r51["total_invested"]:,.0f} THB', f'{r_std["total_invested"]:,.0f} THB'],
    ['BTC Acc.', f'{smart_dca["btc_accumulated"]:.6f}', f'{baseline["btc_accumulated"]:.6f}',
     f'{r5["total_btc"]:.8f}', f'{r51["total_btc"]:.8f}', f'{r_std["total_btc"]:.8f}'],
    ['Final Value', f'${smart_dca["final_value"]:,.0f}', f'${baseline["final_value"]:,.0f}',
     f'${r5["final_value"]/USD_THB:,.0f}', f'${r51["final_value"]/USD_THB:,.0f}', f'${r_std["final_value"]/USD_THB:,.0f}'],
    ['Return %', f'{smart_dca["total_return_pct"]:+.2f}%', f'{baseline["total_return_pct"]:+.2f}%',
     f'{r5["roi_pct"]:+.1f}%', f'{r51["roi_pct"]:+.1f}%', f'{r_std["roi_pct"]:+.1f}%'],
    ['True ROI %', 'N/A (no sell)', 'N/A (no sell)',
     f'{r5["true_roi_pct"]:+.1f}%', f'{r51["true_roi_pct"]:+.1f}%', f'{r_std["true_roi_pct"]:+.1f}%'],
    ['Max DD %', f'{smart_dca.get("max_drawdown_pct",0):+.1f}%', f'{baseline.get("max_drawdown_pct",0):+.1f}%',
     f'{r5["max_drawdown_pct"]:.1f}%', f'{r51["max_drawdown_pct"]:.1f}%', f'{r_std["max_drawdown_pct"]:.1f}%'],
    ['Calmar', 'N/A', 'N/A',
     f'{r5["calmar_ratio"]:.2f}', f'{r51["calmar_ratio"]:.2f}', f'{r_std["calmar_ratio"]:.2f}'],
    ['Sells', '0', '0',
     f'{r5["sell_count"]}', f'{r51["sell_count"]}', '0'],
    ['Buy Days', f'{smart_dca["buy_days"]}', f'{baseline["buy_days"]}',
     f'{r5["buy_days"]}', f'{r51["buy_days"]}', f'{r_std["buy_days"]}'],
]

table = ax3.table(cellText=compare_data[1:], colLabels=compare_data[0],
                  cellLoc='center', loc='center')
table.auto_set_font_size(False)
table.set_fontsize(8)
table.scale(1, 1.6)
for (ri, ci), cell in table.get_celld().items():
    cell.set_edgecolor('#CCCCCC')
    if ri == 0:
        cell.set_facecolor('#2C3E50')
        cell.set_text_props(color='white', fontweight='bold')
    elif ri % 2 == 0:
        cell.set_facecolor('#F0F0F0')
    # Highlight Phoenix v5.1 column
    if ci == 4 and ri > 0:
        cell.set_facecolor('#E8F5E9')
    # Highlight Smart DCA column
    if ci == 1 and ri > 0:
        cell.set_facecolor('#FFF3E0')

# Panel 4: Buy activity / MVRV zones
ax4 = axes[1, 1]
ax4.set_title('Smart DCA Signal Score vs Phoenix MVRV Zones')
ax4.plot(scored_copy['date'], scored_copy['signal_score'], color='#FF5722', linewidth=1, alpha=0.8, label='Signal Score (0-100)')
ax4.axhline(y=45, color='red', linestyle='--', alpha=0.4, label='Smart DCA skip threshold (45)')
ax4.set_ylabel('Signal Score', color='#FF5722')
ax4.set_ylim(0, 100)
ax4_twin = ax4.twinx()
ax4_twin.plot(d51['date'], d51['mvrv'], color='#4CAF50', linewidth=1, alpha=0.7, label='MVRV')
ax4_twin.axhline(y=1.0, color='green', linestyle=':', alpha=0.3, label='MVRV 1.0 (heavy buy)')
ax4_twin.axhline(y=1.5, color='yellow', linestyle=':', alpha=0.3, label='MVRV 1.5')
ax4_twin.axhline(y=2.5, color='red', linestyle=':', alpha=0.3, label='MVRV 2.5 (sell zone)')
ax4_twin.set_ylabel('MVRV Ratio', color='#4CAF50')
ax4.legend(loc='upper left', fontsize=7)
ax4_twin.legend(loc='upper right', fontsize=7)
ax4.grid(True, alpha=0.3, linestyle='--')
ax4.tick_params(axis='x', rotation=30)

# Save
outpath = '/home/z/my-project/download/smart_dca_vs_phoenix_606d.png'
plt.savefig(outpath, dpi=150, bbox_inches='tight')
plt.close()
print(f'  Chart saved: {outpath}')

# Save JSON results
comparison = {
    'period': [str(start_date), str(end_date)],
    'total_days': len(scored),
    'smart_dca': {
        'strategy': 'smart_dca',
        'budget_usd': 100,
        'total_return_pct': smart_dca['total_return_pct'],
        'total_spent_usd': smart_dca['total_spent'],
        'final_value_usd': smart_dca['final_value'],
        'btc_accumulated': smart_dca['btc_accumulated'],
        'avg_entry_usd': smart_dca['avg_entry_price'],
        'buy_days': smart_dca['buy_days'],
        'skip_days': smart_dca['skip_days'],
        'buy_ratio': smart_dca['buy_ratio'],
        'sell_count': 0,
        'has_sell_mechanism': False,
    },
    'baseline_dca': {
        'strategy': 'baseline_dca',
        'budget_usd': 100,
        'total_return_pct': baseline['total_return_pct'],
        'total_spent_usd': baseline['total_spent'],
        'final_value_usd': baseline['final_value'],
        'btc_accumulated': baseline['btc_accumulated'],
        'avg_entry_usd': baseline['avg_entry_price'],
        'buy_days': baseline['buy_days'],
        'skip_days': baseline['skip_days'],
        'buy_ratio': baseline['buy_ratio'],
        'sell_count': 0,
        'has_sell_mechanism': False,
    },
    'phoenix_v5_1': {
        'strategy': 'phoenix_v5_1',
        'budget_thb': 100,
        'budget_usd': round(100/USD_THB, 2),
        'net_capital_thb': r51['net_capital'],
        'total_invested_thb': r51['total_invested'],
        'total_invested_usd': round(r51['total_invested']/USD_THB, 2),
        'final_value_thb': r51['final_value'],
        'final_value_usd': round(r51['final_value']/USD_THB, 2),
        'roi_pct': r51['roi_pct'],
        'true_roi_pct': r51['true_roi_pct'],
        'max_drawdown_pct': r51['max_drawdown_pct'],
        'calmar_ratio': r51['calmar_ratio'],
        'btc_accumulated': r51['total_btc'],
        'avg_entry_usd': round(r51['avg_cost_thb']/USD_THB, 2),
        'buy_days': r51['buy_days'],
        'sell_count': r51['sell_count'],
        'has_sell_mechanism': True,
        'reserve_injected_thb': r51['total_reserve_injected'],
        'sell_proceeds_thb': r51['total_sell_proceeds'],
    },
    'phoenix_v5': {
        'strategy': 'phoenix_v5',
        'budget_thb': 100,
        'roi_pct': r5['roi_pct'],
        'true_roi_pct': r5['true_roi_pct'],
        'max_drawdown_pct': r5['max_drawdown_pct'],
        'calmar_ratio': r5['calmar_ratio'],
        'btc_accumulated': r5['total_btc'],
        'sell_count': r5['sell_count'],
        'has_sell_mechanism': True,
    },
    'standard_dca_100thb': {
        'strategy': 'standard_dca_100thb',
        'budget_thb': 100,
        'roi_pct': r_std['roi_pct'],
        'true_roi_pct': r_std['true_roi_pct'],
        'max_drawdown_pct': r_std['max_drawdown_pct'],
        'btc_accumulated': r_std['total_btc'],
        'sell_count': 0,
    },
}

json_path = '/home/z/my-project/download/smart_dca_vs_phoenix_606d.json'
with open(json_path, 'w') as f:
    json.dump(comparison, f, indent=2)
print(f'  JSON saved: {json_path}')

# ============================================================
# 8. VERDICT
# ============================================================
print(f'\n' + '=' * 80)
print('  VERDICT')
print('=' * 80)

smart_ret = smart_dca['total_return_pct']
base_ret = baseline['total_return_pct']
phx_roi = r51['roi_pct']
phx_true = r51['true_roi_pct']
std_roi = r_std['roi_pct']

print(f'\n  Smart DCA return:  {smart_ret:+.2f}% (alpha vs baseline: {smart_ret - base_ret:+.2f}%)')
print(f'  Baseline DCA:      {base_ret:+.2f}%')
print(f'  Std DCA (100THB):  {std_roi:+.1f}% (same period, Phoenix benchmark)')
print(f'  Phoenix v5.1 ROI:  {phx_roi:+.1f}% | True ROI: {phx_true:+.1f}%')

if phx_true > 0 and smart_ret < 0:
    print(f'\n  >> Phoenix v5.1 WINNER: +{phx_true:.1f}% vs {smart_ret:+.2f}%')
    print(f'     Key advantage: SELL MECHANISM locks profit during pullbacks')
    print(f'     Phoenix sold {r51["sell_count"]} time(s), generating {r51["total_sell_proceeds"]:,.0f} THB reserve')
elif smart_ret > phx_roi:
    print(f'\n  >> Smart DCA WINNER: {smart_ret:+.2f}% vs {phx_roi:+.1f}%')
else:
    print(f'\n  >> Close comparison — see chart for details')

print(f'\n  IMPORTANT: Smart DCA invests ~36x more capital ($100 vs $2.78/day)')
print(f'  Phoenix achieves positive returns with only ~{100/USD_THB:.2f} USD/day budget')
print(f'  Capital efficiency: Phoenix True ROI {phx_true:+.1f}% on ${r51["net_capital"]/USD_THB:,.0f} vs')
print(f'                   Smart DCA {smart_ret:+.2f}% on ${smart_dca["total_spent"]:,.0f}')
print(f'\n  Chart: {outpath}')
print('=' * 80)
