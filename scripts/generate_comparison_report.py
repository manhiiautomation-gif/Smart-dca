#!/usr/bin/env python3
"""
Phoenix Strategy Comparison Report Generator

Generates comprehensive charts comparing Phoenix v1, v3, v4 strategies:
- Portfolio value over time with SELL and BUY-BACK markers
- BTC price with MVRV overlay
- Full metrics comparison tables
- Dual-trigger activation zones (v4 only)

Output: multi-panel PNG report in /home/z/my-project/download/
"""

import sys
import os
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
from datetime import datetime

# Add parent dir for package import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smart_dca.config import DOWNLOAD_DIR, USD_THB_RATE, CACHE_DIR
from smart_dca.data_pipeline import build_master_dataframe
from smart_dca.backtest_engine import backtest_strategy
from smart_dca.strategies._shared import precompute_mvrv_percentile

# ═══ FONT & STYLE SETUP ═══
fm.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
fm.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
plt.rcParams.update({
    'font.sans-serif': ['DejaVu Sans'],
    'axes.unicode_minus': False,
    'figure.facecolor': '#FFFFFF',
    'axes.facecolor': '#FFFFFF',
    'axes.edgecolor': '#E5E7EB',
    'axes.linewidth': 0.8,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.grid': False,
    'xtick.major.size': 0,
    'ytick.major.size': 0,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'axes.labelsize': 10,
    'axes.titlesize': 14,
    'axes.titleweight': 'bold',
    'axes.titlepad': 12,
    'legend.frameon': False,
    'legend.fontsize': 9,
    'figure.dpi': 200,
    'savefig.dpi': 200,
    'savefig.bbox': 'tight',
    'savefig.facecolor': '#FFFFFF',
    'savefig.pad_inches': 0.3,
})

# ═══ COLOR PALETTE ═══
C_PHOENIX_V1 = '#0077BB'   # Blue
C_PHOENIX_V3 = '#EE7733'   # Orange
C_PHOENIX_V4 = '#CC3311'   # Red
C_STD_DCA = '#9CA3AF'      # Gray
C_SELL = '#EF4444'
C_BUYBACK = '#10B981'
C_MVRV_ZONE = '#FBBF24'
C_PRICE = '#374151'
G900 = '#111827'
G700 = '#374151'
G500 = '#6B7280'
G400 = '#9CA3AF'
G300 = '#D1D5DB'
G200 = '#E5E7EB'
G100 = '#F3F4F6'
G50 = '#F9FAFB'

STRAT_COLORS = {
    'Standard DCA': C_STD_DCA,
    'Phoenix v1': C_PHOENIX_V1,
    'Phoenix v3': C_PHOENIX_V3,
    'Phoenix v4': C_PHOENIX_V4,
}

# Selected strategies to compare
SELECTED = [
    ('Standard DCA', False),
    ('Phoenix v1', True),
    ('Phoenix v3', True),
    ('Phoenix v4', True),
]


# Import strategies
from smart_dca.strategies.standard_dca import strategy_standard_dca
from smart_dca.strategies.style_phoenix import strategy_style_phoenix
from smart_dca.strategies.style_phoenix_v3 import strategy_style_phoenix_v3
from smart_dca.strategies.style_phoenix_v4 import strategy_style_phoenix_v4

STRAT_MAP = {
    'Standard DCA': (strategy_standard_dca, False),
    'Phoenix v1': (strategy_style_phoenix, True),
    'Phoenix v3': (strategy_style_phoenix_v3, True),
    'Phoenix v4': (strategy_style_phoenix_v4, True),
}


def clean_axis(ax, grid=True):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    if grid:
        ax.yaxis.grid(True, alpha=0.08, color=G300)
        ax.xaxis.grid(True, alpha=0.08, color=G300)
        ax.set_axisbelow(True)


def extract_events(daily_df, prev_sell_total=None):
    """Extract sell events and reserve buy-back events from daily log."""
    events = {'sell': [], 'buyback': []}
    prev_st = 0.0
    for i, row in daily_df.iterrows():
        cur_st = row['sell_event_thb']
        if prev_st is not None and cur_st > prev_st:
            sell_amt = cur_st - prev_st
            events['sell'].append({
                'date': row['date'],
                'price_thb': row['price_thb'],
                'price_usd': row['price_usd'],
                'amount_thb': sell_amt,
                'portfolio': row['portfolio_value'],
            })
        if row['reserve_event_thb'] > 0:
            events['buyback'].append({
                'date': row['date'],
                'price_thb': row['price_thb'],
                'price_usd': row['price_usd'],
                'amount_thb': row['reserve_event_thb'],
                'portfolio': row['portfolio_value'],
            })
        prev_st = cur_st
    return events


def make_portfolio_chart(ax, all_data, dates, years_label):
    """Panel 1: Portfolio value over time with sell/buy markers."""
    ax.set_title('Portfolio Value (THB) with Sell & Buy-Back Events', loc='left', fontsize=13, fontweight='bold')

    for name, daily_df, results in all_data:
        color = STRAT_COLORS.get(name, G400)
        lw = 2.2 if 'v1' in name.lower() or 'v4' in name.lower() else 1.0
        alpha = 1.0 if 'v1' in name.lower() or 'v4' in name.lower() else 0.5
        ax.plot(daily_df['date'], daily_df['portfolio_value'],
                label=name, color=color, linewidth=lw, alpha=alpha, zorder=2)

        # Sell markers (only for Phoenix strategies)
        if 'Standard' not in name:
            events = extract_events(daily_df)
            if events['sell']:
                sell_dates = [e['date'] for e in events['sell']]
                sell_prices = [e['price_thb'] for e in events['sell']]
                # Plot on secondary x-axis conceptually — use portfolio value at sell time
                sell_port_vals = [e['portfolio'] for e in events['sell']]
                marker_size = max(15, min(60, 3000 // max(len(sell_dates), 1)))
                ax.scatter(sell_dates, sell_port_vals, color=C_SELL, s=marker_size,
                           marker='v', zorder=5, alpha=0.8, edgecolors='white', linewidths=0.5)

    ax.set_ylabel('Portfolio Value (THB)', fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x/1000:.0f}K'))
    ax.legend(loc='upper left', fontsize=9, framealpha=0.95)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years_label // 3)))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    clean_axis(ax)


def make_price_mvrv_chart(ax, df, mvrv_pct_arr, years_label):
    """Panel 2: BTC price (THB) + MVRV with dual-trigger zones."""
    ax.set_title('BTC Price (THB) & MVRV Ratio with Dual-Trigger Zones', loc='left', fontsize=13, fontweight='bold')

    # Price on left y-axis
    color_price = C_PRICE
    ax.plot(df['date'], df['price_thb'], color=color_price, linewidth=1.5, zorder=2)
    ax.set_ylabel('BTC Price (THB)', fontsize=10, color=color_price)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x/1000:.0f}K'))
    ax.tick_params(axis='y', labelcolor=color_price)

    # MVRV on right y-axis
    ax2 = ax.twinx()
    ax2.spines['top'].set_visible(False)
    color_mvrv = '#8B5CF6'
    ax2.plot(df['date'], df['mvrv'], color=color_mvrv, linewidth=1.2, alpha=0.8, zorder=3)
    ax2.set_ylabel('MVRV', fontsize=10, color=color_mvrv)
    ax2.tick_params(axis='y', labelcolor=color_mvrv)

    # Highlight dual-trigger zones (v4)
    # Path A: MVRV > 2.5
    path_a = df['mvrv'] > 2.5
    ax2.fill_between(df['date'], 0, df['mvrv'].values,
                     where=path_a.values, alpha=0.15, color=C_SELL, zorder=1,
                     label='Path A: MVRV > 2.5')

    # Path B: MVRV percentile >= 92% AND MVRV > 1.8
    if mvrv_pct_arr is not None:
        path_b = (mvrv_pct_arr >= 0.92) & (df['mvrv'] > 1.8) & (~path_a.values)
        ax2.fill_between(df['date'], 0, df['mvrv'].values,
                         where=path_b, alpha=0.20, color=C_MVRV_ZONE, zorder=1,
                         label='Path B: MVRV Pct >= 92% & MVRV > 1.8')

    # MVRV threshold lines
    ax2.axhline(y=2.5, color=C_SELL, linewidth=0.8, linestyle='--', alpha=0.5)
    ax2.axhline(y=1.8, color=C_MVRV_ZONE, linewidth=0.8, linestyle='--', alpha=0.5)

    # Combined legend
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    all_lines = lines1 + lines2
    all_labels = labels1 + labels2
    if all_lines:
        ax.legend(all_lines, all_labels, loc='upper left', fontsize=8, framealpha=0.95)

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years_label // 3)))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    ax.grid(True, alpha=0.05)


def make_avg_cost_chart(ax, all_data, years_label):
    """Panel 3: Average cost per BTC."""
    ax.set_title('Average Cost per BTC (THB) - Lower is Better', loc='left', fontsize=13, fontweight='bold')

    for name, daily_df, results in all_data:
        valid = daily_df[daily_df['avg_cost'] > 0]
        if len(valid) > 1:
            color = STRAT_COLORS.get(name, G400)
            lw = 2.0 if 'v4' in name.lower() else 1.0
            alpha = 1.0 if 'v4' in name.lower() else 0.5
            ax.plot(valid['date'], valid['avg_cost'],
                    label=name, color=color, linewidth=lw, alpha=alpha, zorder=2)

    ax.set_ylabel('Avg Cost / BTC (THB)', fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x/1000:.1f}K'))
    ax.legend(loc='upper right', fontsize=9, framealpha=0.95)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years_label // 3)))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    clean_axis(ax)


def make_drawdown_chart(ax, all_data, years_label):
    """Panel 4: Drawdown over time."""
    ax.set_title('Drawdown (%) Over Time - Lower is Better', loc='left', fontsize=13, fontweight='bold')

    for name, daily_df, results in all_data:
        dd = daily_df['max_drawdown_so_far'] * 100
        color = STRAT_COLORS.get(name, G400)
        lw = 1.5 if 'v1' in name.lower() or 'v4' in name.lower() else 0.8
        alpha = 1.0 if 'v1' in name.lower() or 'v4' in name.lower() else 0.4
        ax.fill_between(daily_df['date'], 0, -dd, color=color, alpha=alpha * 0.3, zorder=1)
        ax.plot(daily_df['date'], -dd, label=name, color=color, linewidth=lw, alpha=alpha, zorder=2)

    ax.set_ylabel('Drawdown (%)', fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x:.0f}%'))
    ax.legend(loc='lower left', fontsize=9, framealpha=0.95)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years_label // 3)))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    clean_axis(ax)


def make_sell_detail_chart(ax, all_data, years_label):
    """Panel 5: Sell events timeline (scatter) with MVRV context."""
    ax.set_title('Sell Events: Price at Sell vs MVRV (Higher = Sold at Better Price)',
                 loc='left', fontsize=13, fontweight='bold')

    for name, daily_df, results in all_data:
        if 'Standard' in name:
            continue
        events = extract_events(daily_df)
        if events['sell']:
            sell_dates = [e['date'] for e in events['sell']]
            sell_prices = [e['price_usd'] for e in events['sell']]
            color = STRAT_COLORS.get(name, G400)
            marker_size = max(30, min(80, 4000 // max(len(sell_dates), 1)))
            ax.scatter(sell_dates, sell_prices, color=color, s=marker_size,
                       label=f"{name} ({len(sell_dates)} sells)",
                       alpha=0.7, edgecolors='white', linewidths=0.5, zorder=3)

    # Overlay BTC price line faintly
    for name, daily_df, results in all_data:
        if 'Phoenix v1' in name:
            ax.plot(daily_df['date'], daily_df['price_usd'],
                    color=G300, linewidth=0.8, zorder=1, alpha=0.6)
            break

    ax.set_ylabel('BTC Price (USD) at Sell', fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    ax.legend(loc='upper left', fontsize=9, framealpha=0.95)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years_label // 3)))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    clean_axis(ax)


def make_metrics_table(ax, all_results, years_label):
    """Panel 6: Comprehensive metrics comparison table."""
    ax.axis('off')
    ax.set_title(f'Complete Metrics Comparison ({years_label})', loc='left', fontsize=13, fontweight='bold', pad=15)

    col_labels = [
        'Metric', 'Standard\nDCA', 'Phoenix\nv1', 'Phoenix\nv3', 'Phoenix\nv4'
    ]
    cell_data = []
    row_labels_raw = [
        ('Portfolio Value (THB)', lambda r: f"{r['final_value']:,.0f}", 'final_value', True),
        ('True ROI (%)', lambda r: f"{r['true_roi_pct']:.1f}%", 'true_roi_pct', True),
        ('Max Drawdown (%)', lambda r: f"{r['max_drawdown_pct']:.1f}%", 'max_drawdown_pct', False),
        ('Calmar Ratio', lambda r: f"{r['calmar_ratio']:.2f}", 'calmar_ratio', True),
        ('BTC Held', lambda r: f"{r['total_btc']:.6f}", 'total_btc', True),
        ('BTC Sold (%)', lambda r: f"{r['btc_sell_pct']:.1f}%", 'btc_sell_pct', None),
        ('Avg Cost (THB/BTC)', lambda r: f"{r['avg_cost_thb']:,.0f}" if r['avg_cost_thb'] > 0 else '-', 'avg_cost_thb', False),
        ('Sell Count', lambda r: f"{r['sell_count']}", 'sell_count', None),
        ('Avg Sell Price (THB)', lambda r: f"{r['avg_sell_price_thb']:,.0f}" if r['avg_sell_price_thb'] > 0 else '-', 'avg_sell_price_thb', True),
        ('Sell P/L Ratio', lambda r: f"{r['sell_profit_ratio']:.2f}x" if r['sell_profit_ratio'] > 0 else '-', 'sell_profit_ratio', True),
        ('DD Days (%)', lambda r: f"{r['days_in_drawdown_pct']:.1f}%", 'days_in_drawdown_pct', False),
        ('Worst Recovery (d)', lambda r: f"{r['worst_recovery_days']}", 'worst_recovery_days', False),
        ('DCA Money (THB)', lambda r: f"{r['net_capital']:,.0f}", 'net_capital', None),
        ('Sell Profit (THB)', lambda r: f"{r['total_sell_proceeds']:,.0f}", 'total_sell_proceeds', True),
        ('Reserve Used (THB)', lambda r: f"{r['total_reserve_injected']:,.0f}", 'total_reserve_injected', None),
        ('Reserve Left (THB)', lambda r: f"{r['cash_reserve']:,.0f}", 'cash_reserve', None),
        ('Reserve Use (%)', lambda r: f"{r['reserve_utilization_pct']:.1f}%", 'reserve_utilization_pct', True),
        ('Total Fees (THB)', lambda r: f"{r['total_fees_paid']:,.0f}", 'total_fees_paid', False),
    ]

    # Build data array
    results_map = {r['strategy']: r for r in all_results}
    for label, fmt, key, best_is_max in row_labels_raw:
        row = [label]
        for strat_name in ['Standard DCA', 'Phoenix v1', 'Phoenix v3', 'Phoenix v4']:
            r = results_map.get(strat_name, {})
            row.append(fmt(r))
        cell_data.append(row)

    table = ax.table(cellText=cell_data, colLabels=col_labels, cellLoc='center', loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1, 1.55)

    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor('#E5E7EB')
        if row_idx == 0:
            cell.set_facecolor('#1E293B')
            cell.set_text_props(color='white', fontweight='bold', fontsize=8.5)
            cell.set_height(0.055)
        else:
            cell.set_facecolor('#F8FAFC' if row_idx % 2 == 0 else 'white')
            cell.set_height(0.048)
            # First column (metric name) left-aligned and bold
            if col_idx == 0:
                cell.set_text_props(ha='left', fontweight='bold', fontsize=8.5, color=G700)

    # Highlight best values per row (green for best, light red for worst DD)
    for row_idx, (label, fmt, key, best_is_max) in enumerate(row_labels_raw, 1):
        if key is None or best_is_max is None:
            continue
        vals = {}
        for ci, sn in enumerate(['Standard DCA', 'Phoenix v1', 'Phoenix v3', 'Phoenix v4'], 1):
            r = results_map.get(sn, {})
            v = r.get(key, 0)
            if isinstance(v, (int, float)) and not np.isnan(v):
                vals[ci] = v
        if vals:
            if best_is_max:
                best_ci = max(vals, key=vals.get)
                table.get_celld()[(row_idx, best_ci)].set_facecolor('#DCFCE7')
                table.get_celld()[(row_idx, best_ci)].set_text_props(fontweight='bold', fontsize=8.5)
            else:
                best_ci = min(vals, key=vals.get)
                table.get_celld()[(row_idx, best_ci)].set_facecolor('#DCFCE7')
                table.get_celld()[(row_idx, best_ci)].set_text_props(fontweight='bold', fontsize=8.5)

    return table


def make_dual_trigger_info(ax):
    """Info box explaining dual-trigger system."""
    ax.axis('off')
    ax.set_title('Phoenix v4 Dual-Trigger System (Future-Proof for Diminishing MVRV Cycles)',
                 loc='left', fontsize=13, fontweight='bold', pad=15)

    info_text = (
        "PROBLEM: MVRV peaks diminish each BTC cycle: 7.0 -> 5.0 -> 4.0 -> 2.78"
        "\nFixed MVRV > 2.5 gate may fail in future cycles if peak drops below 2.5."
        "\n"
        "\nSOLUTION: Dual-Trigger Sell Activation"
        "\n  Path A (Absolute):    MVRV > 2.5 + Score >= 40"
        "\n         -> Proven gate from v3, catches normal cycle tops"
        "\n"
        "\n  Path B (Adaptive):    MVRV Percentile >= 92% of 365-day rolling window"
        "\n                         AND MVRV > 1.8 + Score >= 40"
        "\n         -> Activates when MVRV is at cycle extreme even if absolute value is lower"
        "\n         -> Example: If cycle 5 peaks at MVRV 2.2, percentile 92% still triggers"
        "\n"
        "\nSell Tiers (shared by v3 & v4):"
        "\n  Score >= 75  -> Sell 50% of portfolio (was 8% in v1), Cooldown 50d"
        "\n  Score >= 55  -> Sell 15% of portfolio (was 6% in v1), Cooldown 35d"
        "\n  Score >= 40  -> Sell  4% of portfolio (was 4% in v1), Cooldown 20d"
        "\n"
        "\nKey Differences:"
        "\n  v1: MVRV > 2.5 only, small sells (4/6/8%), has short-trend sell (2% port)"
        "\n  v3: MVRV > 2.5 only, larger sells (4/15/50%), boosted reserve deploy"
        "\n  v4: Dual-trigger (Path A + Path B), same sells as v3, no short-trend sell"
    )
    ax.text(0.03, 0.97, info_text, transform=ax.transAxes, fontsize=9.5,
            verticalalignment='top', fontfamily='monospace', color=G700,
            bbox=dict(boxstyle='round,pad=0.8', facecolor='#F8FAFC', edgecolor=G200, linewidth=1))


def generate_report(years):
    """Generate full comparison report for given year range."""
    label = f'{years}-Year'

    print(f"\n{'=' * 70}")
    print(f"  GENERATING COMPARISON REPORT: {label}")
    print(f"{'=' * 70}")

    # Load data
    print("\n[1/3] Loading data pipeline...")
    master_df = build_master_dataframe(years=5)

    if years == 3:
        test_df = master_df.tail(int(3 * 365.25)).reset_index(drop=True)
    else:
        test_df = master_df.copy()
    print(f"  Period: {test_df['date'].iloc[0]} to {test_df['date'].iloc[-1]} ({len(test_df)} days)")

    # Precompute MVRV percentile for chart overlay
    print("\n[2/3] Running backtests...")
    mvrv_pct = precompute_mvrv_percentile(test_df, window=365)

    all_results = []
    all_daily_dfs = []
    all_data = []  # (name, daily_df, results)

    for name, (func, needs_precompute) in STRAT_MAP.items():
        if needs_precompute:
            strategy_func = func(test_df)
        else:
            strategy_func = func

        print(f"  Backtesting {name}...", end=' ', flush=True)
        results, daily_df = backtest_strategy(test_df, strategy_func, name)
        all_results.append(results)
        all_daily_dfs.append(daily_df)
        all_data.append((name, daily_df, results))
        print(f"Done. Value: {results['final_value']:,.0f} | ROI: {results['true_roi_pct']:.1f}% | DD: {results['max_drawdown_pct']:.1f}% | Sells: {results['sell_count']}")

    # Generate charts
    print(f"\n[3/3] Generating {label} comparison charts...")

    # ═══ CHART 1: Main comparison (6 panels) ═══
    fig = plt.figure(figsize=(22, 34), constrained_layout=True)
    fig.suptitle(
        f'Smart DCA Strategy Comparison Report ({label})\n'
        f'Binance Real Price Data + On-Chain Metrics (MVRV, SOPR, NUPL) | Daily Budget: 100 THB',
        fontsize=18, fontweight='bold', y=1.005
    )

    gs = gridspec.GridSpec(7, 1, figure=fig, height_ratios=[1.2, 0.8, 0.8, 0.8, 0.8, 2.5, 1.2],
                           hspace=0.30)

    ax1 = fig.add_subplot(gs[0])
    make_portfolio_chart(ax1, all_data, test_df['date'].tolist(), years)

    ax2 = fig.add_subplot(gs[1])
    make_price_mvrv_chart(ax2, test_df, mvrv_pct, years)

    ax3 = fig.add_subplot(gs[2])
    make_avg_cost_chart(ax3, all_data, years)

    ax4 = fig.add_subplot(gs[3])
    make_drawdown_chart(ax4, all_data, years)

    ax5 = fig.add_subplot(gs[4])
    make_sell_detail_chart(ax5, all_data, years)

    ax6 = fig.add_subplot(gs[5])
    make_metrics_table(ax6, all_results, label)

    ax7 = fig.add_subplot(gs[6])
    make_dual_trigger_info(ax7)

    fname = os.path.join(DOWNLOAD_DIR, f'phoenix_comparison_report_{years}yr.png')
    plt.savefig(fname, dpi=180, facecolor='white', bbox_inches='tight')
    plt.close()
    print(f"\n  [CHART] Full report saved: {fname}")

    # ═══ CHART 2: Focused v1 vs v4 comparison ═══
    fig2, axes2 = plt.subplots(2, 2, figsize=(20, 14), constrained_layout=True)
    fig2.suptitle(f'Phoenix v1 vs v4 Head-to-Head ({label})', fontsize=17, fontweight='bold', y=1.01)

    v1_data = next((d for d in all_data if d[0] == 'Phoenix v1'), None)
    v4_data = next((d for d in all_data if d[0] == 'Phoenix v4'), None)

    if v1_data and v4_data:
        # Portfolio comparison
        ax_a = axes2[0, 0]
        ax_a.set_title('Portfolio Value', loc='left', fontsize=12, fontweight='bold')
        ax_a.plot(v1_data[1]['date'], v1_data[1]['portfolio_value'],
                  color=C_PHOENIX_V1, linewidth=2, label='Phoenix v1', zorder=2)
        ax_a.plot(v4_data[1]['date'], v4_data[1]['portfolio_value'],
                  color=C_PHOENIX_V4, linewidth=2, label='Phoenix v4', zorder=2)
        ax_a.fill_between(v1_data[1]['date'],
                          v1_data[1]['portfolio_value'], v4_data[1]['portfolio_value'],
                          alpha=0.1, color=G400)
        ax_a.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x/1000:.0f}K'))
        ax_a.legend(fontsize=10)
        ax_a.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax_a.xaxis.get_majorticklabels(), rotation=30, ha='right')
        clean_axis(ax_a)

        # Sell events comparison
        ax_b = axes2[0, 1]
        ax_b.set_title('Sell Event Prices (USD)', loc='left', fontsize=12, fontweight='bold')
        for name, daily_df, color in [('v1', v1_data[1], C_PHOENIX_V1), ('v4', v4_data[1], C_PHOENIX_V4)]:
            events = extract_events(daily_df)
            if events['sell']:
                sd = [e['date'] for e in events['sell']]
                sp = [e['price_usd'] for e in events['sell']]
                ms = max(25, min(70, 3000 // max(len(sd), 1)))
                ax_b.scatter(sd, sp, color=color, s=ms,
                             label=f'Phoenix {name} ({len(sd)} sells)',
                             alpha=0.7, edgecolors='white', linewidths=0.5, zorder=3)
        ax_b.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        ax_b.legend(fontsize=10)
        ax_b.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax_b.xaxis.get_majorticklabels(), rotation=30, ha='right')
        clean_axis(ax_b)

        # Drawdown comparison
        ax_c = axes2[1, 0]
        ax_c.set_title('Drawdown Over Time', loc='left', fontsize=12, fontweight='bold')
        for name, daily_df, color in [('v1', v1_data[1], C_PHOENIX_V1), ('v4', v4_data[1], C_PHOENIX_V4)]:
            dd = daily_df['max_drawdown_so_far'] * 100
            ax_c.fill_between(daily_df['date'], 0, -dd, color=color, alpha=0.2)
            ax_c.plot(daily_df['date'], -dd, color=color, linewidth=1.8, label=f'Phoenix {name}')
        ax_c.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x:.0f}%'))
        ax_c.legend(fontsize=10)
        ax_c.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax_c.xaxis.get_majorticklabels(), rotation=30, ha='right')
        clean_axis(ax_c)

        # Key metrics bar comparison
        ax_d = axes2[1, 1]
        ax_d.set_title('Key Metrics: v1 vs v4', loc='left', fontsize=12, fontweight='bold')
        r1 = next(r for r in all_results if r['strategy'] == 'Phoenix v1')
        r4 = next(r for r in all_results if r['strategy'] == 'Phoenix v4')

        metrics_names = ['Portfolio\n(THB)', 'True ROI\n(%)', 'Max DD\n(%)', 'Calmar', 'Sell\nCount', 'BTC\nHeld']
        v1_vals = [r1['final_value']/1000, r1['true_roi_pct'], r1['max_drawdown_pct'],
                   r1['calmar_ratio'], r1['sell_count'], r1['total_btc']*1000]
        v4_vals = [r4['final_value']/1000, r4['true_roi_pct'], r4['max_drawdown_pct'],
                   r4['calmar_ratio'], r4['sell_count'], r4['total_btc']*1000]

        x = np.arange(len(metrics_names))
        width = 0.35
        bars1 = ax_d.bar(x - width/2, v1_vals, width, color=C_PHOENIX_V1, alpha=0.85, label='Phoenix v1')
        bars2 = ax_d.bar(x + width/2, v4_vals, width, color=C_PHOENIX_V4, alpha=0.85, label='Phoenix v4')

        ax_d.set_xticks(x)
        ax_d.set_xticklabels(metrics_names, fontsize=8.5)
        ax_d.legend(fontsize=10)
        clean_axis(ax_d)

    fname2 = os.path.join(DOWNLOAD_DIR, f'phoenix_v1_vs_v4_{years}yr.png')
    plt.savefig(fname2, dpi=180, facecolor='white', bbox_inches='tight')
    plt.close()
    print(f"  [CHART] v1 vs v4 saved: {fname2}")

    # ═══ Print summary ═══
    print(f"\n{'='*80}")
    print(f"  SUMMARY: {label} COMPARISON")
    print(f"{'='*80}")
    for r in all_results:
        print(f"  {r['strategy']:<16} | Portfolio: {r['final_value']:>10,.0f} THB | "
              f"True ROI: {r['true_roi_pct']:>7.1f}% | DD: {r['max_drawdown_pct']:>5.1f}% | "
              f"Calmar: {r['calmar_ratio']:>6.2f} | Sells: {r['sell_count']:>3} | "
              f"BTC: {r['total_btc']:.6f}")
    print(f"{'='*80}\n")

    return all_results


def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print("\n" + "=" * 70)
    print("  PHOENIX STRATEGY COMPARISON REPORT GENERATOR")
    print("  Strategies: Standard DCA | Phoenix v1 | Phoenix v3 | Phoenix v4")
    print("=" * 70)

    results_3yr = generate_report(years=3)
    results_5yr = generate_report(years=5)

    print("\n[COMPLETE] All comparison reports generated.")
    print(f"  Full reports : {DOWNLOAD_DIR}/phoenix_comparison_report_*.png")
    print(f"  v1 vs v4     : {DOWNLOAD_DIR}/phoenix_v1_vs_v4_*.png")
    print("=" * 70)


if __name__ == '__main__':
    main()
