import os

import matplotlib
import matplotlib.font_manager as fm
fm.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

from .config import DOWNLOAD_DIR, USD_THB_RATE


def print_summary_table(all_results):
    n = len(all_results)
    print()
    print("=" * 150)
    print("  PERFORMANCE OVERVIEW")
    print("=" * 150)
    h1 = (f'{"Strategy":<16} {"Portfolio":>12} {"True ROI":>9} {"ROI%":>8} {"Max DD":>7} '
          f'{"BTC Held":>10} {"Avg Cost":>10} {"BTC Sold":>8}')
    print(h1)
    print("-" * 150)
    for r in all_results:
        ac = f'{r["avg_cost_thb"]:,.0f}' if r['avg_cost_thb'] > 0 else '-'
        line = (f'{r["strategy"]:<16} {r["final_value"]:>12,.0f} {r["true_roi_pct"]:>8.1f}% {r["roi_pct"]:>7.1f}% {r["max_drawdown_pct"]:>6.1f}% '
                f'{r["total_btc"]:>10.6f} {ac:>10} {r["btc_sell_pct"]:>7.1f}%')
        print(line)

    print()
    print("=" * 150)
    print("  CAPITAL FLOW ANALYSIS")
    print("=" * 150)
    h2 = (f'{"Strategy":<16} {"DCA Money":>12} {"Sell Profit":>12} {"Reserve Used":>13} {"Reserve Left":>13} '
          f'{"Reserve Use%":>12} {"Fees Paid":>11} {"Sells":>6} {"Reserve Days":>12}')
    print(h2)
    print("-" * 150)
    for r in all_results:
        line = (f'{r["strategy"]:<16} {r["net_capital"]:>12,.0f} {r["total_sell_proceeds"]:>12,.0f} '
                f'{r["total_reserve_injected"]:>13,.0f} {r["cash_reserve"]:>13,.0f} '
                f'{r["reserve_utilization_pct"]:>11.1f}% {r["total_fees_paid"]:>11,.0f} '
                f'{r["sell_count"]:>6} {r["reserve_buy_days"]:>12}')
        print(line)
    print("=" * 150)

    best_val = max(all_results, key=lambda x: x["final_value"])
    best_roi = max(all_results, key=lambda x: x["true_roi_pct"])
    best_btc = max(all_results, key=lambda x: x["total_btc"])
    lowest_dd = min(all_results, key=lambda x: x["max_drawdown_pct"])
    lowest_cost = min(all_results, key=lambda x: x["avg_cost_thb"] if x["avg_cost_thb"] > 0 else float('inf'))
    lowest_fee = min(all_results, key=lambda x: x["total_fees_paid"])

    print(f"  >> Best Portfolio   : {best_val['strategy']} ({best_val['final_value']:,.0f} THB)")
    print(f"  >> Best True ROI    : {best_roi['strategy']} ({best_roi['true_roi_pct']:.1f}%)")
    print(f"  >> Most BTC Held    : {best_btc['strategy']} ({best_btc['total_btc']:.6f} BTC)")
    print(f"  >> Lowest Drawdown  : {lowest_dd['strategy']} ({lowest_dd['max_drawdown_pct']:.1f}%)")
    print(f"  >> Lowest Avg Cost  : {lowest_cost['strategy']} ({lowest_cost['avg_cost_thb']:,.0f} THB/BTC)")
    print(f"  >> Lowest Fees      : {lowest_fee['strategy']} ({lowest_fee['total_fees_paid']:,.0f} THB)")
    print()
    print("  Metrics Key:")
    print("    DCA Money     = money from your pocket (excl. reserve recycling)")
    print("    Sell Profit   = cash from BTC sells (goes into reserve)")
    print("    Reserve Used  = reserve cash used to buy BTC at lower prices")
    print("    Reserve Left  = remaining reserve cash (not yet deployed)")
    print("    Reserve Use%  = % of sell proceeds recycled back into buys")
    print("    Fees Paid     = total fees across all trades (buy + sell)")
    print("    Reserve Days  = days where reserve was used for buying")
    print()


def generate_charts(all_daily_dfs, all_results, years_label):
    colors = ['#9E9E9E', '#2196F3', '#FF9800', '#4CAF50', '#E91E63', '#9C27B0']
    styles_names = [r['strategy'] for r in all_results]

    fig = plt.figure(figsize=(20, 22), constrained_layout=True)
    fig.suptitle(f'Smart DCA Strategy Comparison ({years_label})\nBinance REAL Price Data + On-Chain Metrics',
                 fontsize=17, fontweight='bold', y=1.01)

    gs = fig.add_gridspec(4, 1, height_ratios=[1, 0.9, 0.7, 0.7], hspace=0.32)

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

    # Table 3: Performance
    ax3 = fig.add_subplot(gs[2])
    ax3.axis('off')
    ax3.set_title('Performance Comparison', fontsize=13, fontweight='bold', pad=15)

    perf_cols = ['Strategy', 'Portfolio\nValue (THB)', 'True ROI\n(%)', 'Max DD\n(%)', 'BTC\nHeld', 'BTC\nSold (%)', 'Avg Cost\n(THB/BTC)', 'Fees\n(THB)']
    perf_data = []
    for r in all_results:
        ac = f"{r['avg_cost_thb']:,.0f}" if r['avg_cost_thb'] > 0 else "-"
        perf_data.append([
            r['strategy'],
            f"{r['final_value']:,.0f}",
            f"{r['true_roi_pct']:.1f}%",
            f"{r['max_drawdown_pct']:.1f}%",
            f"{r['total_btc']:.6f}",
            f"{r['btc_sell_pct']:.1f}%",
            ac,
            f"{r['total_fees_paid']:,.0f}",
        ])

    t3 = ax3.table(cellText=perf_data, colLabels=perf_cols, cellLoc='center', loc='center')
    t3.auto_set_font_size(False)
    t3.set_fontsize(9)
    t3.scale(1, 1.9)
    _style_table(t3, perf_cols, all_results, key_col='final_value')

    # Table 4: Capital Flow
    ax4 = fig.add_subplot(gs[3])
    ax4.axis('off')
    ax4.set_title('Capital Flow Analysis', fontsize=13, fontweight='bold', pad=15)

    cap_cols = ['Strategy', 'DCA Money\n(THB)', 'Sell Profit\n(THB)', 'Reserve Used\n(THB)', 'Reserve Left\n(THB)', 'Reserve\nUse%', 'Sell\nCount', 'Reserve\nBuy Days']
    cap_data = []
    for r in all_results:
        cap_data.append([
            r['strategy'],
            f"{r['net_capital']:,.0f}",
            f"{r['total_sell_proceeds']:,.0f}",
            f"{r['total_reserve_injected']:,.0f}",
            f"{r['cash_reserve']:,.0f}",
            f"{r['reserve_utilization_pct']:.1f}%",
            f"{r['sell_count']}",
            f"{r['reserve_buy_days']}",
        ])

    t4 = ax4.table(cellText=cap_data, colLabels=cap_cols, cellLoc='center', loc='center')
    t4.auto_set_font_size(False)
    t4.set_fontsize(9)
    t4.scale(1, 1.9)
    _style_table(t4, cap_cols, all_results, key_col='final_value')

    fname = os.path.join(DOWNLOAD_DIR, f'smart_dca_comparison_{years_label.replace(" ", "_")}.png')
    plt.savefig(fname, dpi=150, bbox_inches='tight')
    print(f'[CHART] Saved: {fname}')
    plt.close()


def _style_table(table, col_labels, all_results, key_col='final_value'):
    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor('#CCCCCC')
        if row_idx == 0:
            cell.set_facecolor('#2C3E50')
            cell.set_text_props(color='white', fontweight='bold', fontsize=8)
            cell.set_height(0.12)
        else:
            cell.set_facecolor('#F8F9FA' if row_idx % 2 == 0 else 'white')
            cell.set_height(0.1)

    best_idx = max(range(len(all_results)), key=lambda i: all_results[i][key_col]) + 1
    for col_idx in range(len(col_labels)):
        cell = table.get_celld()[(best_idx, col_idx)]
        cell.set_facecolor('#E8F5E9')
        cell.set_text_props(fontweight='bold')


def save_results_csv(all_results, years_label):
    df = pd.DataFrame(all_results)
    df['avg_cost_usd'] = df['avg_cost_thb'] / USD_THB_RATE
    fname = os.path.join(DOWNLOAD_DIR, f'smart_dca_results_{years_label.replace(" ", "_")}.csv')
    df.to_csv(fname, index=False)
    print(f'[DATA] Results saved: {fname}')
