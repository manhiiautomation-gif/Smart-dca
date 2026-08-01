#!/usr/bin/env python3
"""Generate comprehensive v4 vs v5 comparison report chart."""
import sys
sys.path.insert(0, 'scripts')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker as mticker
from matplotlib.patches import FancyBboxPatch
from datetime import datetime

# Font setup
fm.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

from smart_dca.data_pipeline import build_master_dataframe
from smart_dca.backtest_engine import backtest_strategy
from smart_dca.strategies.style_phoenix_v4 import strategy_style_phoenix_v4
from smart_dca.strategies.style_phoenix_v5 import strategy_style_phoenix_v5

# ═══ BUILD DATA ═══
print('Building data...')
master = build_master_dataframe(years=5)

results = {}
daily_logs = {}
for years in [3, 5]:
    label = f'{years}yr'
    if years == 3:
        test_df = master.tail(int(3 * 365.25)).reset_index(drop=True)
    else:
        test_df = master.copy()
    
    for name, func in [('v4', strategy_style_phoenix_v4),
                          ('v5', strategy_style_phoenix_v5)]:
        key = f'{name}_{label}'
        sf = func(test_df)
        r, log = backtest_strategy(test_df, sf, f'Phoenix {name}')
        results[key] = r
        daily_logs[key] = log
        print(f'  {key}: Portfolio={r["final_value"]:,.0f} ROI={r["true_roi_pct"]:.1f}%')

# ═══ CHART GENERATION ═══
for years in [3, 5]:
    label = f'{years}yr'
    fig = plt.figure(figsize=(20, 24), facecolor='#0d1117')
    
    # Grid spec: 6 rows
    gs = fig.add_gridspec(6, 2, hspace=0.35, wspace=0.25,
                          left=0.06, right=0.94, top=0.94, bottom=0.03,
                          height_ratios=[1.2, 0.8, 0.8, 0.8, 0.8, 1.0])
    
    # Color palette
    C_V4 = '#58a6ff'  # blue
    C_V5 = '#f0883e'  # orange
    C_BG = '#0d1117'
    C_PANEL = '#161b22'
    C_TEXT = '#c9d1d9'
    C_GRID = '#21262d'
    C_GREEN = '#3fb950'
    C_RED = '#f85149'
    C_YELLOW = '#d29922'
    
    v4_key = f'v4_{label}'
    v5_key = f'v5_{label}'
    v4_r = results[v4_key]
    v5_r = results[v5_key]
    v4_log = daily_logs[v4_key]
    v5_log = daily_logs[v5_key]
    
    dates = pd.to_datetime(v4_log['date'])
    
    def style_ax(ax, title=''):
        ax.set_facecolor(C_PANEL)
        ax.tick_params(colors=C_TEXT, labelsize=8)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(C_GRID)
        ax.spines['bottom'].set_color(C_GRID)
        ax.grid(True, alpha=0.15, color=C_GRID)
        if title:
            ax.set_title(title, color=C_TEXT, fontsize=11, fontweight='bold', pad=8)
    
    # ═══ PANEL 1: Portfolio Value (full width) ═══
    ax1 = fig.add_subplot(gs[0, :])
    style_ax(ax1, 'Portfolio Value Over Time')
    ax1.plot(dates, v4_log['portfolio_value'], color=C_V4, linewidth=1.5, label=f'v4: {v4_r["final_value"]:,.0f} THB', alpha=0.9)
    ax1.plot(dates, v5_log['portfolio_value'], color=C_V5, linewidth=1.5, label=f'v5: {v5_r["final_value"]:,.0f} THB', alpha=0.9)
    
    # Sell markers for v4
    v4_sell_mask = v4_log['sell_event_thb'].diff() > 0
    if v4_sell_mask.any():
        v4_sell_dates = dates[v4_sell_mask]
        v4_sell_vals = v4_log.loc[v4_sell_mask, 'portfolio_value']
        ax1.scatter(v4_sell_dates, v4_sell_vals, color=C_V4, marker='v', s=60, zorder=5, alpha=0.8, edgecolors='white', linewidths=0.5)
    
    # Sell markers for v5
    v5_sell_mask = v5_log['sell_event_thb'].diff() > 0
    if v5_sell_mask.any():
        v5_sell_dates = dates[v5_sell_mask]
        v5_sell_vals = v5_log.loc[v5_sell_mask, 'portfolio_value']
        ax1.scatter(v5_sell_dates, v5_sell_vals, color=C_V5, marker='v', s=60, zorder=5, alpha=0.8, edgecolors='white', linewidths=0.5)
    
    ax1.legend(loc='upper left', fontsize=9, facecolor=C_PANEL, edgecolor=C_GRID, labelcolor=C_TEXT)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x/1000:.0f}K'))
    ax1.set_ylabel('THB', color=C_TEXT, fontsize=9)
    
    # ═══ PANEL 2: BTC Price + MVRV ═══
    ax2 = fig.add_subplot(gs[1, 0])
    style_ax(ax2, 'BTC Price (THB)')
    ax2_twin = ax2.twinx()
    ax2_twin.tick_params(colors=C_YELLOW, labelsize=8)
    ax2_twin.spines['right'].set_color(C_YELLOW)
    ax2_twin.spines['top'].set_visible(False)
    ax2_twin.spines['left'].set_visible(False)
    ax2_twin.spines['bottom'].set_visible(False)
    
    ax2.fill_between(dates, v4_log['price_usd'], alpha=0.15, color=C_GREEN)
    ax2.plot(dates, v4_log['price_usd'], color=C_GREEN, linewidth=1, alpha=0.8)
    ax2_twin.plot(dates, v4_log['mvrv'], color=C_YELLOW, linewidth=1, alpha=0.7)
    ax2_twin.axhline(y=2.5, color=C_RED, linestyle='--', alpha=0.4, linewidth=0.8)
    ax2_twin.axhline(y=1.8, color=C_YELLOW, linestyle=':', alpha=0.3, linewidth=0.8)
    ax2.set_ylabel('USD', color=C_TEXT, fontsize=9)
    ax2_twin.set_ylabel('MVRV', color=C_YELLOW, fontsize=9)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x/1000:.0f}K'))
    
    # ═══ PANEL 3: Drawdown Comparison ═══
    ax3 = fig.add_subplot(gs[1, 1])
    style_ax(ax3, 'Drawdown Over Time')
    v4_dd = v4_log['max_drawdown_so_far'] * 100
    v5_dd = v5_log['max_drawdown_so_far'] * 100
    ax3.fill_between(dates, v4_dd, alpha=0.2, color=C_V4)
    ax3.fill_between(dates, v5_dd, alpha=0.2, color=C_V5)
    ax3.plot(dates, v4_dd, color=C_V4, linewidth=1.2, label=f'v4 max: {v4_r["max_drawdown_pct"]:.1f}%')
    ax3.plot(dates, v5_dd, color=C_V5, linewidth=1.2, label=f'v5 max: {v5_r["max_drawdown_pct"]:.1f}%')
    ax3.invert_yaxis()
    ax3.legend(loc='lower left', fontsize=8, facecolor=C_PANEL, edgecolor=C_GRID, labelcolor=C_TEXT)
    ax3.set_ylabel('Drawdown %', color=C_TEXT, fontsize=9)
    
    # ═══ PANEL 4: Average Cost per BTC ═══
    ax4 = fig.add_subplot(gs[2, 0])
    style_ax(ax4, 'Adjusted Average Cost per BTC')
    ax4.plot(dates, v4_log['avg_cost'], color=C_V4, linewidth=1.2, label='v4')
    ax4.plot(dates, v5_log['avg_cost'], color=C_V5, linewidth=1.2, label='v5')
    ax4.plot(dates, v4_log['price_thb'], color=C_GREEN, linewidth=0.8, alpha=0.5, label='BTC Price')
    ax4.legend(loc='upper left', fontsize=8, facecolor=C_PANEL, edgecolor=C_GRID, labelcolor=C_TEXT)
    ax4.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x/1000:.1f}K'))
    ax4.set_ylabel('THB', color=C_TEXT, fontsize=9)
    
    # ═══ PANEL 5: Sell Events Scatter ═══
    ax5 = fig.add_subplot(gs[2, 1])
    style_ax(ax5, 'Sell Events (Price at Sell vs Date)')
    
    v4_sell_idx = v4_log.index[v4_sell_mask].tolist()
    v5_sell_idx = v5_log.index[v5_sell_mask].tolist()
    
    if v4_sell_idx:
        v4_sd = [dates[i] for i in v4_sell_idx]
        v4_sp = [v4_log.loc[i, 'price_usd'] for i in v4_sell_idx]
        ax5.scatter(v4_sd, v4_sp, color=C_V4, s=80, marker='v', zorder=5, 
                   edgecolors='white', linewidths=0.5, label=f'v4 ({len(v4_sell_idx)} sells)')
    if v5_sell_idx:
        v5_sd = [dates[i] for i in v5_sell_idx]
        v5_sp = [v5_log.loc[i, 'price_usd'] for i in v5_sell_idx]
        ax5.scatter(v5_sd, v5_sp, color=C_V5, s=80, marker='v', zorder=5,
                   edgecolors='white', linewidths=0.5, label=f'v5 ({len(v5_sell_idx)} sells)')
    
    ax5.legend(loc='upper left', fontsize=8, facecolor=C_PANEL, edgecolor=C_GRID, labelcolor=C_TEXT)
    ax5.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x/1000:.0f}K'))
    ax5.set_ylabel('USD', color=C_TEXT, fontsize=9)
    
    # ═══ PANEL 6: Cash Reserve Over Time ═══
    ax6 = fig.add_subplot(gs[3, 0])
    style_ax(ax6, 'Cash Reserve')
    ax6.plot(dates, v4_log['cash_reserve'], color=C_V4, linewidth=1.2, label=f'v4: {v4_r["cash_reserve"]:,.0f}')
    ax6.plot(dates, v5_log['cash_reserve'], color=C_V5, linewidth=1.2, label=f'v5: {v5_r["cash_reserve"]:,.0f}')
    ax6.legend(loc='upper left', fontsize=8, facecolor=C_PANEL, edgecolor=C_GRID, labelcolor=C_TEXT)
    ax6.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x/1000:.0f}K'))
    ax6.set_ylabel('THB', color=C_TEXT, fontsize=9)
    
    # ═══ PANEL 7: BTC Holdings Over Time ═══
    ax7 = fig.add_subplot(gs[3, 1])
    style_ax(ax7, 'BTC Holdings')
    ax7.plot(dates, v4_log['btc'], color=C_V4, linewidth=1.2, label=f'v4: {v4_r["total_btc"]:.6f}')
    ax7.plot(dates, v5_log['btc'], color=C_V5, linewidth=1.2, label=f'v5: {v5_r["total_btc"]:.6f}')
    ax7.legend(loc='upper left', fontsize=8, facecolor=C_PANEL, edgecolor=C_GRID, labelcolor=C_TEXT)
    ax7.set_ylabel('BTC', color=C_TEXT, fontsize=9)
    
    # ═══ PANEL 8: Metrics Comparison Table ═══
    ax8 = fig.add_subplot(gs[4, :])
    ax8.set_facecolor(C_PANEL)
    ax8.axis('off')
    ax8.set_title('Performance Metrics Comparison', color=C_TEXT, fontsize=11, fontweight='bold', pad=8)
    
    metrics = [
        ('Portfolio Value (THB)', v4_r['final_value'], v5_r['final_value'], 'higher'),
        ('True ROI (%)', v4_r['true_roi_pct'], v5_r['true_roi_pct'], 'higher'),
        ('Max Drawdown (%)', v4_r['max_drawdown_pct'], v5_r['max_drawdown_pct'], 'lower'),
        ('Calmar Ratio', v4_r['calmar_ratio'], v5_r['calmar_ratio'], 'higher'),
        ('Total BTC Held', v4_r['total_btc'], v5_r['total_btc'], 'higher'),
        ('BTC Sold (%)', v4_r['btc_sell_pct'], v5_r['btc_sell_pct'], 'context'),
        ('Number of Sells', v4_r['sell_count'], v5_r['sell_count'], 'context'),
        ('Sell P/L Ratio', v4_r['sell_profit_ratio'], v5_r['sell_profit_ratio'], 'higher'),
        ('Avg Sell Price (THB)', v4_r['avg_sell_price_thb'], v5_r['avg_sell_price_thb'], 'higher'),
        ('Cash Reserve (THB)', v4_r['cash_reserve'], v5_r['cash_reserve'], 'context'),
        ('Total Fees Paid (THB)', v4_r['total_fees_paid'], v5_r['total_fees_paid'], 'lower'),
        ('Days in Drawdown (%)', v4_r['days_in_drawdown_pct'], v5_r['days_in_drawdown_pct'], 'lower'),
        ('Worst Recovery (days)', v4_r['worst_recovery_days'], v5_r['worst_recovery_days'], 'lower'),
        ('Reserve Utilization (%)', v4_r['reserve_utilization_pct'], v5_r['reserve_utilization_pct'], 'higher'),
        ('Avg Daily DCA (THB)', v4_r['avg_daily_dca'], v5_r['avg_daily_dca'], 'context'),
        ('Net Capital Invested', v4_r['net_capital'], v5_r['net_capital'], 'context'),
    ]
    
    col_labels = ['Metric', 'v4', 'v5', 'Delta', 'Winner']
    cell_text = []
    
    for mname, v4v, v5v, direction in metrics:
        if abs(v4v) > 100000:
            v4s = f'{v4v:,.0f}'
            v5s = f'{v5v:,.0f}'
        elif abs(v4v) > 100:
            v4s = f'{v4v:,.1f}'
            v5s = f'{v5v:,.1f}'
        elif abs(v4v) > 1:
            v4s = f'{v4v:.2f}'
            v5s = f'{v5v:.2f}'
        else:
            v4s = f'{v4v:.6f}'
            v5s = f'{v5v:.6f}'
        
        delta = v5v - v4v
        if abs(v4v) > 1000:
            ds = f'{delta:+,.0f}'
        elif abs(v4v) > 1:
            ds = f'{delta:+.2f}'
        else:
            ds = f'{delta:+.6f}'
        
        if direction == 'higher':
            winner = 'v5' if v5v > v4v else ('v4' if v4v > v5v else 'Tie')
        elif direction == 'lower':
            winner = 'v5' if v5v < v4v else ('v4' if v4v < v5v else 'Tie')
        else:
            winner = '-'
        
        cell_text.append([mname, v4s, v5s, ds, winner])
    
    table = ax8.table(cellText=cell_text, colLabels=col_labels,
                      loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.35)
    
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(C_GRID)
        if row == 0:
            cell.set_facecolor('#1f6feb')
            cell.set_text_props(color='white', fontweight='bold')
        else:
            cell.set_facecolor(C_PANEL)
            cell.set_text_props(color=C_TEXT)
            # Highlight winner
            if col == 4:
                val = cell.get_text().get_text()
                if val == 'v5':
                    cell.set_facecolor('#1a3a1a')
                    cell.set_text_props(color=C_GREEN, fontweight='bold')
                elif val == 'v4':
                    cell.set_facecolor('#3a1a1a')
                    cell.set_text_props(color=C_RED, fontweight='bold')
            # Color delta
            if col == 3 and row > 0:
                val = cell.get_text().get_text()
                if val.startswith('+'):
                    cell.set_text_props(color=C_GREEN)
                elif val.startswith('-'):
                    cell.set_text_props(color=C_RED)
    
    # ═══ PANEL 9: Key Differences Text ═══
    ax9 = fig.add_subplot(gs[5, :])
    ax9.set_facecolor(C_PANEL)
    ax9.axis('off')
    ax9.set_title('v5 vs v4: Key Design Differences', color=C_TEXT, fontsize=11, fontweight='bold', pad=8)
    
    differences = [
        ('Risk 1 (Cold-Start)', 'v4: Blind first 365d', 'v5: Pre-warmed from 2015+ data'),
        ('Risk 2 (False Trigger)', 'v4: Path B up to 50%', 'v5: Path B capped at 8%'),
        ('Risk 3 (Oversell)', 'v4: 4/15/50% tiers', 'v5: 4/8/18/40% graduated'),
        ('Risk 4 (Path B Score)', 'v4: score >= 40 shared', 'v5: Path A>=45, Path B>=44'),
        ('Risk 5 (Short-Trend)', 'v4: None', 'v5: Removed (was net-negative)'),
        ('Risk 6 (Proxy)', 'v4: No proxy handling', 'v5: Proxy detection + threshold adj.'),
        ('Risk 7 (Cooldown)', 'v4: 20/35/50d', 'v5: 18/22/28/35d'),
        ('Risk 8 (Low Vol)', 'v4: Relies on MVRV > 2.5', 'v5: Path B adaptive at MVRV 1.8+'),
    ]
    
    headers = ['Risk', 'v4 Behavior', 'v5 Improvement']
    diff_text = [[d[0], d[1], d[2]] for d in differences]
    
    table2 = ax9.table(cellText=diff_text, colLabels=headers,
                       loc='center', cellLoc='left')
    table2.auto_set_font_size(False)
    table2.set_fontsize(8)
    table2.scale(1, 1.4)
    
    for (row, col), cell in table2.get_celld().items():
        cell.set_edgecolor(C_GRID)
        if row == 0:
            cell.set_facecolor('#1f6feb')
            cell.set_text_props(color='white', fontweight='bold')
        else:
            cell.set_facecolor(C_PANEL)
            if col == 2:
                cell.set_text_props(color=C_GREEN)
            elif col == 1:
                cell.set_text_props(color=C_RED)
            else:
                cell.set_text_props(color=C_TEXT)
    
    # Title
    fig.suptitle(f'Phoenix v4 vs v5 Comparison Report — {years}-Year Backtest',
                 color='white', fontsize=16, fontweight='bold', y=0.975)
    
    # Subtitle
    fig.text(0.5, 0.955, 
             f'v4: {v4_r["true_roi_pct"]:.1f}% ROI | {v4_r["max_drawdown_pct"]:.1f}% DD | Calmar {v4_r["calmar_ratio"]:.2f} | {v4_r["sell_count"]} sells    '
             f'v5: {v5_r["true_roi_pct"]:.1f}% ROI | {v5_r["max_drawdown_pct"]:.1f}% DD | Calmar {v5_r["calmar_ratio"]:.2f} | {v5_r["sell_count"]} sells',
             ha='center', color=C_TEXT, fontsize=9)
    
    outpath = f'/home/z/my-project/download/phoenix_v4_vs_v5_{label}_report.png'
    fig.savefig(outpath, dpi=150, facecolor=C_BG, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved: {outpath}')

print('\nDone! Reports saved to /home/z/my-project/download/')
