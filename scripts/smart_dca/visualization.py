"""Visualization - Charts, summary table, CSV export."""

import os

import matplotlib
import matplotlib.font_manager as fm
fm.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

from .config import DOWNLOAD_DIR, USD_THB_RATE


def print_summary_table(all_results):
    """Print a formatted comparison table in console."""
    print("\n" + "=" * 134)
    print("  BACKTEST RESULTS - STRATEGY COMPARISON")
    print("=" * 134)
    header = (f'{"Strategy":<16} {"Net Capital":>14} {"Invested":>14} {"BTC":>10} '
              f'{"FinalVal":>14} {"True ROI":>10} {"ROI%":>8} {"MaxDD%":>7} {"Cash":>10}')
    print(header)
    print("-" * 134)
    for r in all_results:
        line = (f'{r["strategy"]:<16} {r["net_capital"]:>14,.0f} {r["total_invested"]:>14,.0f} {r["total_btc"]:>10.6f} '
                f'{r["final_value"]:>14,.0f} {r["true_roi_pct"]:>9.1f}% {r["roi_pct"]:>7.1f}% {r["max_drawdown_pct"]:>6.1f}% {r["cash_reserve"]:>10,.0f}')
        print(line)
    print("=" * 134)

    best = max(all_results, key=lambda x: x["final_value"])
    print(f'\n  >> Best Final Value : {best["strategy"]} ({best["final_value"]:,.0f} THB)')
    best_profit = max(all_results, key=lambda x: x["true_net_profit"])
    print(f'  >> Best True Profit : {best_profit["strategy"]} ({best_profit["true_net_profit"]:,.0f} THB)')
    best_roi = max(all_results, key=lambda x: x["true_roi_pct"])
    print(f'  >> Best True ROI    : {best_roi["strategy"]} ({best_roi["true_roi_pct"]:.1f}%)')
    best_btc = max(all_results, key=lambda x: x["total_btc"])
    print(f'  >> Most BTC Acc.    : {best_btc["strategy"]} ({best_btc["total_btc"]:.6f} BTC)')
    lowest_cost = min(all_results, key=lambda x: x["avg_cost_thb"] if x["avg_cost_thb"] > 0 else float('inf'))
    print(f'  >> Lowest Avg Cost  : {lowest_cost["strategy"]} ({lowest_cost["avg_cost_thb"]:,.0f} THB/BTC)')
    lowest_dd = min(all_results, key=lambda x: x["max_drawdown_pct"])
    print(f'  >> Lowest Max DD    : {lowest_dd["strategy"]} ({lowest_dd["max_drawdown_pct"]:.1f}%)')
    print()
    print("  Note: Net Capital = user's actual money in. Invested includes reserve recycling.")
    print("        True ROI = profit vs net capital (fair comparison for reserve strategies).")
    print()


def generate_charts(all_daily_dfs, all_results, years_label):
    """Generate 3-panel chart: portfolio value, avg cost, results table."""
    colors = ['#9E9E9E', '#2196F3', '#FF9800', '#4CAF50', '#E91E63']
    styles_names = [r['strategy'] for r in all_results]

    fig = plt.figure(figsize=(18, 16), constrained_layout=True)
    fig.suptitle(f'Smart DCA Strategy Comparison ({years_label})\nBinance REAL Price Data + On-Chain Metrics',
                 fontsize=17, fontweight='bold', y=1.01)

    gs = fig.add_gridspec(3, 1, height_ratios=[1, 1, 0.85], hspace=0.35)

    # Chart 1: Portfolio Value
    ax1 = fig.add_subplot(gs[0])
    for i, (name, daily_df) in enumerate(zip(styles_names, all_daily_dfs)):
        ax1.plot(daily_df['date'], daily_df['portfolio_value'],
                 label=name, color=colors[i % len(colors)], linewidth=1.5, alpha=0.9)
    ax1.set_title('Portfolio Value (THB) Over Time', fontsize=13, fontweight='bold')
    ax1.set_xlabel('Date', fontsize=10)
    ax1.set_ylabel('Portfolio Value (THB)', fontsize=10)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    ax1.legend(loc='upper left', fontsize=9, framealpha=0.9)
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.tick_params(axis='x', rotation=30)

    # Chart 2: Average Cost per BTC
    ax2 = fig.add_subplot(gs[1])
    for i, (name, daily_df) in enumerate(zip(styles_names, all_daily_dfs)):
        valid = daily_df[daily_df['avg_cost'] > 0]
        if len(valid) > 0:
            ax2.plot(valid['date'], valid['avg_cost'],
                     label=name, color=colors[i % len(colors)], linewidth=1.5, alpha=0.9)
    ax2.set_title('Average Cost per BTC (THB) Over Time', fontsize=13, fontweight='bold')
    ax2.set_xlabel('Date', fontsize=10)
    ax2.set_ylabel('Avg Cost / BTC (THB)', fontsize=10)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    ax2.legend(loc='upper right', fontsize=9, framealpha=0.9)
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.tick_params(axis='x', rotation=30)

    # Chart 3: Results Comparison TABLE
    ax3 = fig.add_subplot(gs[2])
    ax3.axis('off')
    ax3.set_title('Results Comparison Table', fontsize=13, fontweight='bold', pad=15)

    col_labels = ['Strategy', 'Net Capital\n(THB)', 'BTC\nAccumulated', 'Portfolio\nValue (THB)', 'True ROI\n(%)', 'Max DD\n(%)']
    table_data = []
    for r in all_results:
        table_data.append([
            r['strategy'],
            f"{r['net_capital']:,.0f}",
            f"{r['total_btc']:.6f}",
            f"{r['final_value']:,.0f}",
            f"{r['true_roi_pct']:.1f}%",
            f"{r['max_drawdown_pct']:.1f}%",
        ])

    table = ax3.table(cellText=table_data, colLabels=col_labels,
                      cellLoc='center', loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.8)

    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor('#CCCCCC')
        if row_idx == 0:
            cell.set_facecolor('#2C3E50')
            cell.set_text_props(color='white', fontweight='bold', fontsize=9)
            cell.set_height(0.12)
        else:
            cell.set_facecolor('#F8F9FA' if row_idx % 2 == 0 else 'white')
            cell.set_height(0.1)

    best_idx = max(range(len(all_results)), key=lambda i: all_results[i]['final_value']) + 1
    for col_idx in range(len(col_labels)):
        cell = table.get_celld()[(best_idx, col_idx)]
        cell.set_facecolor('#E8F5E9')
        cell.set_text_props(fontweight='bold')

    fname = os.path.join(DOWNLOAD_DIR, f'smart_dca_comparison_{years_label.replace(" ", "_")}.png')
    plt.savefig(fname, dpi=150, bbox_inches='tight')
    print(f'[CHART] Saved: {fname}')
    plt.close()


def save_results_csv(all_results, years_label):
    """Save results to CSV for easy reference."""
    df = pd.DataFrame(all_results)
    df['avg_cost_usd'] = df['avg_cost_thb'] / USD_THB_RATE
    fname = os.path.join(DOWNLOAD_DIR, f'smart_dca_results_{years_label.replace(" ", "_")}.csv')
    df.to_csv(fname, index=False)
    print(f'[DATA] Results saved: {fname}')
