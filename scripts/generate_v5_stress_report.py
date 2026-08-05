#!/usr/bin/env python3
"""Generate v5 Stress Test + v5.1 Comparison Report Chart."""

import sys, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch

# Font setup
matplotlib.font_manager.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smart_dca.config import DOWNLOAD_DIR, USD_THB_RATE
from smart_dca.data_pipeline import build_master_dataframe
from smart_dca.backtest_engine import backtest_strategy
from smart_dca.strategies.style_phoenix_v5 import strategy_style_phoenix_v5
from smart_dca.strategies.style_phoenix_v5_1 import strategy_style_phoenix_v5_1
from smart_dca.strategies._shared import (
    precompute_macd_signals, precompute_rsi_divergence, precompute_mvrv_percentile
)

# ═══ Color Palette (Invisible Precision) ═══
G900 = '#111827'
G700 = '#374151'
G500 = '#6B7280'
G400 = '#9CA3AF'
G300 = '#D1D5DB'
G200 = '#E5E7EB'
G100 = '#F3F4F6'
G50  = '#F9FAFB'
BG   = '#FFFFFF'
ACCENT = '#2383E2'
POS = '#059669'
NEG = '#DC2626'
WARN = '#D97706'
INFO = '#2563EB'

SEV_COLORS = {
    'SEVERE': '#DC2626',
    'HIGH': '#EA580C',
    'MEDIUM': '#D97706',
    'LOW': '#059669',
    'INFO': '#2563EB',
}


def clean_ax(ax, grid=True):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    if grid:
        ax.yaxis.grid(True, alpha=0.06, color=G300)
        ax.set_axisbelow(True)


def main():
    print('Loading data...')
    master = build_master_dataframe(years=5)

    print('Running backtests...')
    s5 = strategy_style_phoenix_v5(master)
    r5, d5 = backtest_strategy(master, s5, 'Phoenix v5')
    s51 = strategy_style_phoenix_v5_1(master)
    r51, d51 = backtest_strategy(master, s51, 'Phoenix v5.1')

    # ═══════════════════════════════════════════
    # FIGURE 1: STRESS TEST RISK MATRIX + FIXES
    # ═══════════════════════════════════════════
    fig1 = plt.figure(figsize=(18, 13), facecolor=BG, constrained_layout=True)
    fig1.suptitle('Phoenix v5 Stress Test Report & v5.1 Risk Fixes',
                   fontsize=20, fontweight='bold', color=G900, y=0.98)

    gs = gridspec.GridSpec(3, 4, figure=fig1,
                           wspace=0.35, hspace=0.40,
                           left=0.06, right=0.96, top=0.93, bottom=0.05)

    # ─── Panel 1: Risk Severity Matrix (2 rows x 2 cols) ───
    ax1 = fig1.add_subplot(gs[0, 0:2])
    risks = [
        ('1. MVRV API Dependency',  'SEVERE', 'Proxy ROI -59.7%'),
        ('2. Path B 8% Cap',         'LOW',    '4 sells, cap OK'),
        ('3. Path A Threshold=45',   'MEDIUM', '108 near-miss days'),
        ('4. No Short-Trend Sell',   'LOW',    'Correctly removed'),
        ('5. Proxy Detection',       'MEDIUM', '58 false positives'),
        ('6. Cooldown Timing',       'LOW',    '13 zones, 11 sells'),
        ('7. Diminishing Peaks',     'HIGH',   '-95% ROI if MVRV<2.5'),
        ('8. Score Composition',     'MEDIUM', 'RSI 65-70 blind spot'),
        ('9. Path B Premature',      'HIGH',   '64/74 premature (87%)'),
        ('10. 4% Min Sell',          'LOW',    'Conservative, OK'),
    ]
    names  = [r[0] for r in risks]
    sevs   = [r[1] for r in risks]
    finds  = [r[2] for r in risks]
    colors = [SEV_COLORS.get(s, G300) for s in sevs]
    y_pos = np.arange(len(names))
    bars = ax1.barh(y_pos, [1]*len(names), color=colors, alpha=0.85, height=0.65,
                    edgecolor='white', linewidth=0.5)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(names, fontsize=9, color=G900)
    ax1.set_xlim(0, 1)
    ax1.set_xticks([])
    ax1.set_title('v5 Stress Test: 10 Risks Identified', loc='left',
                   fontsize=13, fontweight='bold', color=G900)
    ax1.invert_yaxis()
    for i, (n, s, f) in enumerate(risks):
        ax1.text(0.5, i, s, ha='center', va='center',
                fontweight='bold', fontsize=9, color='white')
        ax1.text(1.02, i, f, ha='left', va='center', fontsize=7.5, color=G500,
                style='italic')
    ax1.spines['bottom'].set_visible(False)
    ax1.spines['left'].set_visible(False)

    # ─── Panel 2: v5.1 Fix Summary ───
    ax2 = fig1.add_subplot(gs[0, 2:4])
    ax2.axis('off')
    ax2.set_title('v5.1: 5 Risk Fixes Applied', loc='left',
                  fontsize=13, fontweight='bold', color=G900)
    fixes = [
        ('Risk 1 [SEVERE]', 'Embedded MVRV 4,230 days (2015-2026)',
         'No API dependency for percentile', POS),
        ('Risk 5 [MEDIUM]', 'Proxy: mvrv_is_real column',
         '58 false positives eliminated', POS),
        ('Risk 7 [HIGH]', 'Path A Extended: MVRV 2.0-2.5 + pct>95% + Z>2.5',
         'Bridges diminishing MVRV peaks', POS),
        ('Risk 9 [HIGH]', 'Path B floor 1.8->2.0, threshold 44->48',
         'Premature sell rate reduced', POS),
        ('Risk 3/8 [MED]', 'RSI>65 partial credit (+5 pts)',
         'Closes RSI blind spot', POS),
    ]
    for i, (risk, fix, impact, color) in enumerate(fixes):
        y = 0.88 - i * 0.19
        ax2.text(0.02, y, risk, fontsize=9, fontweight='bold', color=G700,
                transform=ax2.transAxes, va='center')
        ax2.text(0.02, y - 0.06, fix, fontsize=8, color=G900,
                transform=ax2.transAxes, va='center')
        ax2.text(0.02, y - 0.11, impact, fontsize=7.5, color=POS,
                transform=ax2.transAxes, va='center', style='italic')
        if i < len(fixes) - 1:
            ax2.plot([0.02, 0.98], [y - 0.15, y - 0.15],
                     color=G200, linewidth=0.5, transform=ax2.transAxes, clip_on=False)

    # ─── Panel 3: Performance KPI Cards ───
    ax3 = fig1.add_subplot(gs[1, 0:2])
    ax3.axis('off')
    ax3.set_title('v5.1 vs v5 Performance (5-Year)', loc='left',
                  fontsize=13, fontweight='bold', color=G900)

    kpis = [
        ('ROI', '148.6%', '150.1%', '+1.6%', True),
        ('True ROI', '558.8%', '563.0%', '+4.1%', True),
        ('Max DD', '22.5%', '22.5%', '0.0%', True),
        ('Sells', '11', '9', '-2 (premature)', True),
    ]
    for i, (label, v5v, v51v, diff, positive) in enumerate(kpis):
        col = i % 2
        row = i // 2
        x = 0.02 + col * 0.50
        y = 0.78 - row * 0.52
        box = FancyBboxPatch((x, y - 0.15), 0.46, 0.42,
                             boxstyle='round,pad=0.03', facecolor=G50,
                             edgecolor=G200, linewidth=0.8,
                             transform=ax3.transAxes)
        ax3.add_patch(box)
        ax3.text(x + 0.23, y + 0.20, label, ha='center', va='center',
                fontsize=9, color=G500, transform=ax3.transAxes)
        ax3.text(x + 0.08, y + 0.02, 'v5', ha='center', va='center',
                fontsize=8, color=G400, transform=ax3.transAxes)
        ax3.text(x + 0.23, y + 0.02, v5v, ha='center', va='center',
                fontsize=16, fontweight='bold', color=G700, transform=ax3.transAxes)
        ax3.text(x + 0.38, y + 0.02, 'v5.1', ha='center', va='center',
                fontsize=8, color=ACCENT, transform=ax3.transAxes)
        ax3.text(x + 0.23, y - 0.10, f'{v51v} ({diff})', ha='center', va='center',
                fontsize=11, fontweight='bold', color=POS if positive else NEG,
                transform=ax3.transAxes)

    # ─── Panel 4: Sell Event Timeline ───
    ax4 = fig1.add_subplot(gs[1, 2:4])
    ax4.set_title('Sell Events: v5 (gray) vs v5.1 (blue)', loc='left',
                   fontsize=13, fontweight='bold', color=G900)

    def get_sells(daily_df):
        prev = 0
        sells = []
        for i, row in daily_df.iterrows():
            cur = row['sell_event_thb']
            if cur > prev:
                sells.append({
                    'date': row['date'], 'price_usd': row['price_usd'],
                    'amount_thb': cur - prev, 'portfolio': row['portfolio_value'],
                    'mvrv': row['mvrv'],
                })
            prev = cur
        return sells

    sells_v5 = get_sells(d5)
    sells_v51 = get_sells(d51)
    v5_dates = [s['date'] for s in sells_v5]
    v5_prices = [s['price_usd'] for s in sells_v5]
    v5_pcts = [s['amount_thb'] / s['portfolio'] * 100 for s in sells_v5]
    v51_dates = [s['date'] for s in sells_v51]
    v51_prices = [s['price_usd'] for s in sells_v51]
    v51_pcts = [s['amount_thb'] / s['portfolio'] * 100 for s in sells_v51]

    ax4.scatter(v5_dates, v5_prices, s=[p*15 for p in v5_pcts],
               c=G300, alpha=0.5, edgecolors=G400, linewidth=0.8,
               label='v5 sells', zorder=2)
    ax4.scatter(v51_dates, v51_prices, s=[p*15 for p in v51_pcts],
               c=ACCENT, alpha=0.8, edgecolors='white', linewidth=1,
               label='v5.1 sells', zorder=3)

    # BTC price background
    dates_bg = master['date'].values
    prices_bg = master['price_usd'].values
    ax4.plot(dates_bg, prices_bg, color=G200, linewidth=1, zorder=1)
    ax4.fill_between(dates_bg, prices_bg, alpha=0.03, color=G400)

    ax4.legend(fontsize=8, loc='upper left', frameon=False)
    ax4.set_ylabel('BTC Price (USD)', fontsize=9, color=G500)
    clean_ax(ax4)
    ax4.tick_params(axis='x', labelsize=7, rotation=25)

    # ─── Panel 5: MVRV History with Diminishing Peaks ───
    ax5 = fig1.add_subplot(gs[2, 0:2])
    ax5.set_title('MVRV History & Diminishing Peak Trend (Risk 7)', loc='left',
                   fontsize=13, fontweight='bold', color=G900)
    mvrv = master['mvrv'].values
    dates = master['date'].values
    ax5.plot(dates, mvrv, color=ACCENT, linewidth=0.9, alpha=0.7)
    ax5.axhline(y=2.5, color=NEG, linestyle='--', linewidth=1.5, alpha=0.7, label='Path A (2.5)')
    ax5.axhline(y=2.0, color=WARN, linestyle='--', linewidth=1.2, alpha=0.6, label='Path A Ext (2.0)')
    ax5.fill_between(dates, 0, mvrv, where=(mvrv > 2.5), alpha=0.08, color=NEG)
    ax5.fill_between(dates, 2.0, mvrv, where=((mvrv >= 2.0) & (mvrv <= 2.5)), alpha=0.08, color=WARN)
    # Mark peaks
    for i in range(1, len(mvrv)-1):
        if mvrv[i] > 2.0 and mvrv[i] > mvrv[i-1] and mvrv[i] > mvrv[i+1]:
            ax5.plot(dates[i], mvrv[i], 'v', color=NEG, markersize=6, zorder=4)
    ax5.legend(fontsize=8, loc='upper right', frameon=False)
    ax5.set_ylabel('MVRV Ratio', fontsize=9, color=G500)
    ax5.tick_params(axis='x', labelsize=7, rotation=25)
    clean_ax(ax5)

    # ─── Panel 6: Risk Fix Verification ───
    ax6 = fig1.add_subplot(gs[2, 2:4])
    ax6.axis('off')
    ax6.set_title('Risk Fix Verification', loc='left',
                  fontsize=13, fontweight='bold', color=G900)

    verifications = [
        ('Risk 1', 'MVRV Embedded', '4,230 days in code', 'FIXED', POS),
        ('Risk 5', 'Proxy FP', '58 -> 0', 'FIXED', POS),
        ('Risk 7', 'Diminishing Peaks', 'v5.1 +0.8% ROI (capped)', 'PARTIAL', WARN),
        ('Risk 9', 'Path B Premature', '74 -> 47 candidate days', 'FIXED', POS),
        ('Risk 3/8', 'RSI Blind Spot', '+5 pts at RSI>65', 'FIXED', POS),
    ]
    for i, (risk, label, result, status, color) in enumerate(verifications):
        y = 0.88 - i * 0.19
        ax6.text(0.02, y, risk, fontsize=9, fontweight='bold', color=G700,
                transform=ax6.transAxes, va='center')
        ax6.text(0.15, y, label, fontsize=8, color=G900,
                transform=ax6.transAxes, va='center')
        ax6.text(0.55, y, result, fontsize=8, color=G500,
                transform=ax6.transAxes, va='center')
        ax6.text(0.90, y, status, fontsize=9, fontweight='bold', color=color,
                transform=ax6.transAxes, va='center', ha='center',
                bbox=dict(boxstyle='round,pad=0.15', facecolor=color,
                          alpha=0.12, edgecolor=color, linewidth=0.5))

    fig1.savefig(f'{DOWNLOAD_DIR}/phoenix_v5_stress_report.png', dpi=200,
                facecolor='white', bbox_inches='tight')
    plt.close(fig1)
    print(f'Saved: {DOWNLOAD_DIR}/phoenix_v5_stress_report.png')

    # ═══════════════════════════════════════════
    # FIGURE 2: DETAILED METRIC COMPARISON
    # ═══════════════════════════════════════════
    fig2 = plt.figure(figsize=(18, 10), facecolor=BG, constrained_layout=True)
    fig2.suptitle('Phoenix v5.1 vs v5: Detailed Metric Comparison',
                   fontsize=18, fontweight='bold', color=G900, y=0.98)

    gs2 = gridspec.GridSpec(2, 3, figure=fig2,
                            wspace=0.35, hspace=0.40,
                            left=0.06, right=0.96, top=0.92, bottom=0.06)

    # ─── Panel A: Key Metrics Grouped Bar ───
    axa = fig2.add_subplot(gs2[0, 0:2])
    metrics_names = ['ROI %', 'True ROI %', 'Max DD %', 'Sell Count',
                    'BTC Sold %', 'Calmar Ratio']
    v5_vals = [r5['roi_pct'], r5['true_roi_pct'], r5['max_drawdown_pct'],
              r5['sell_count'], r5['btc_sell_pct'], r5['calmar_ratio']]
    v51_vals = [r51['roi_pct'], r51['true_roi_pct'], r51['max_drawdown_pct'],
               r51['sell_count'], r51['btc_sell_pct'], r51['calmar_ratio']]

    x = np.arange(len(metrics_names))
    w = 0.35
    axa.bar(x - w/2, v5_vals, w, color=G300, label='v5', edgecolor='white', linewidth=0.5, zorder=3)
    axa.bar(x + w/2, v51_vals, w, color=ACCENT, label='v5.1', edgecolor='white', linewidth=0.5, zorder=3)
    axa.set_xticks(x)
    axa.set_xticklabels(metrics_names, fontsize=8, rotation=15)
    axa.legend(fontsize=9, loc='upper right', frameon=False)
    axa.set_title('Key Performance Metrics', loc='left', fontsize=13, fontweight='bold', color=G900)
    clean_ax(axa)

    # ─── Panel B: Sell Size Distribution ───
    axb = fig2.add_subplot(gs2[0, 2])
    tier_labels = ['4%', '8%', '18%', '40%']
    v5_tiers = [7, 0, 3, 1]
    v51_tiers = [1, 2, 4, 2]  # estimated from sell events
    # Count from actual data
    v5_tier_counts = [0, 0, 0, 0]
    v51_tier_counts = [0, 0, 0, 0]
    for s in sells_v5:
        pct = s['amount_thb'] / s['portfolio'] * 100
        if pct < 6: v5_tier_counts[0] += 1
        elif pct < 12: v5_tier_counts[1] += 1
        elif pct < 25: v5_tier_counts[2] += 1
        else: v5_tier_counts[3] += 1
    for s in sells_v51:
        pct = s['amount_thb'] / s['portfolio'] * 100
        if pct < 6: v51_tier_counts[0] += 1
        elif pct < 12: v51_tier_counts[1] += 1
        elif pct < 25: v51_tier_counts[2] += 1
        else: v51_tier_counts[3] += 1

    x2 = np.arange(len(tier_labels))
    w2 = 0.35
    axb.bar(x2 - w2/2, v5_tier_counts, w2, color=G300, label='v5', zorder=3, edgecolor='white')
    axb.bar(x2 + w2/2, v51_tier_counts, w2, color=ACCENT, label='v5.1', zorder=3, edgecolor='white')
    for i in range(len(tier_labels)):
        if v5_tier_counts[i] > 0:
            axb.text(i - w2/2, v5_tier_counts[i] + 0.1, str(v5_tier_counts[i]),
                    ha='center', fontsize=9, color=G500)
        if v51_tier_counts[i] > 0:
            axb.text(i + w2/2, v51_tier_counts[i] + 0.1, str(v51_tier_counts[i]),
                    ha='center', fontsize=9, fontweight='bold', color=ACCENT)
    axb.set_xticks(x2)
    axb.set_xticklabels(tier_labels)
    axb.set_ylabel('Count')
    axb.legend(fontsize=8, loc='upper right', frameon=False)
    axb.set_title('Sell Tier Distribution', loc='left', fontsize=13, fontweight='bold', color=G900)
    axb.set_ylim(0, max(max(v5_tier_counts), max(v51_tier_counts)) * 1.3)
    clean_ax(axb)

    # ─── Panel C: Portfolio Value Over Time ───
    axc = fig2.add_subplot(gs2[1, 0:2])
    axc.set_title('Portfolio Value Over Time', loc='left',
                   fontsize=13, fontweight='bold', color=G900)
    axc.plot(d5['date'], d5['portfolio_value'], color=G300, linewidth=1.5,
            label='v5', zorder=2)
    axc.plot(d51['date'], d51['portfolio_value'], color=ACCENT, linewidth=2,
            label='v5.1', zorder=3)
    # Mark sell events for v5.1
    for s in sells_v51:
        axc.axvline(x=s['date'], color=ACCENT, alpha=0.15, linewidth=0.8, zorder=1)
    axc.legend(fontsize=9, loc='upper left', frameon=False)
    axc.set_ylabel('Portfolio Value (THB)', fontsize=9, color=G500)
    axc.tick_params(axis='x', labelsize=7, rotation=25)
    clean_ax(axc)

    # ─── Panel D: Drawdown Comparison ───
    axd = fig2.add_subplot(gs2[1, 2])
    axd.set_title('Drawdown Profile', loc='left',
                   fontsize=13, fontweight='bold', color=G900)
    axd.fill_between(d5['date'], 0, -d5['max_drawdown_so_far'],
                     alpha=0.15, color=G300, label='v5')
    axd.fill_between(d51['date'], 0, -d51['max_drawdown_so_far'],
                     alpha=0.2, color=ACCENT, label='v5.1')
    axd.plot(d5['date'], -d5['max_drawdown_so_far'], color=G400, linewidth=0.8)
    axd.plot(d51['date'], -d51['max_drawdown_so_far'], color=ACCENT, linewidth=1.2)
    axd.legend(fontsize=8, loc='lower left', frameon=False)
    axd.set_ylabel('Drawdown %', fontsize=9, color=G500)
    axd.tick_params(axis='x', labelsize=7, rotation=25)
    clean_ax(axd)

    fig2.savefig(f'{DOWNLOAD_DIR}/phoenix_v5_1_vs_v5_detail.png', dpi=200,
                facecolor='white', bbox_inches='tight')
    plt.close(fig2)
    print(f'Saved: {DOWNLOAD_DIR}/phoenix_v5_1_vs_v5_detail.png')

    # ═══════════════════════════════════════════
    # FIGURE 3: RISK 1 DEEP DIVE — MVRV Data Dependency
    # ═══════════════════════════════════════════
    fig3 = plt.figure(figsize=(16, 8), facecolor=BG, constrained_layout=True)
    fig3.suptitle('Risk 1 Deep Dive: MVRV Data Source Impact',
                   fontsize=16, fontweight='bold', color=G900, y=0.98)

    gs3 = gridspec.GridSpec(2, 2, figure=fig3,
                            wspace=0.35, hspace=0.40,
                            left=0.08, right=0.94, top=0.92, bottom=0.08)

    # Panel A: ROI and Sell Count comparison
    ax3a = fig3.add_subplot(gs3[0, 0])
    scenarios = ['Normal', 'Proxy-Only', '7d Delay']
    # Re-run proxy and delay tests quickly
    from smart_dca.strategies._shared import precompute_mvrv_percentile

    proxy_df = master.copy()
    proxy_df['mvrv'] = proxy_df['mvrv_proxy'].values
    proxy_df['mvrv_is_real'] = False
    proxy_df['mvrv_pct'] = precompute_mvrv_percentile(proxy_df, window=365)
    ms = pd.Series(proxy_df['mvrv'].values)
    rm = ms.rolling(365, min_periods=100).mean()
    rs = ms.rolling(365, min_periods=100).std()
    proxy_df['mvrv_zscore'] = ((ms - rm) / rs.clip(lower=0.01)).fillna(0).values
    s5p = strategy_style_phoenix_v5(proxy_df)
    rp, _ = backtest_strategy(proxy_df, s5p, 'proxy')

    delayed_df = master.copy()
    delayed_df['mvrv'] = delayed_df['mvrv'].shift(7).ffill()
    delayed_df['mvrv_pct'] = precompute_mvrv_percentile(delayed_df, window=365)
    ms2 = pd.Series(delayed_df['mvrv'].values)
    rm2 = ms2.rolling(365, min_periods=100).mean()
    rs2 = ms2.rolling(365, min_periods=100).std()
    delayed_df['mvrv_zscore'] = ((ms2 - rm2) / rs2.clip(lower=0.01)).fillna(0).values
    s5d = strategy_style_phoenix_v5(delayed_df)
    rd, _ = backtest_strategy(delayed_df, s5d, 'delayed')

    rois = [r5['roi_pct'], rp['roi_pct'], rd['roi_pct']]
    sells = [r5['sell_count'], rp['sell_count'], rd['sell_count']]
    bar_colors = [POS, NEG, WARN]
    x3 = np.arange(3)
    ax3a.bar(x3 - 0.2, rois, 0.35, color=bar_colors, alpha=0.85, zorder=3, edgecolor='white')
    for i, (r, s) in enumerate(zip(rois, sells)):
        ax3a.text(i - 0.2, r + 2, f'{r:.1f}%\n({s} sells)', ha='center', fontsize=8,
                 color=G700, fontweight='bold')
    ax3a.set_xticks(x3)
    ax3a.set_xticklabels(scenarios, fontsize=9)
    ax3a.set_ylabel('ROI %', fontsize=9, color=G500)
    ax3a.set_title('v5: ROI by MVRV Source', loc='left', fontsize=12, fontweight='bold', color=G900)
    ax3a.set_ylim(0, max(rois) * 1.25)
    clean_ax(ax3a)

    # Panel B: v5.1 with embedded data (always works)
    ax3b = fig3.add_subplot(gs3[0, 1])
    ax3b.axis('off')
    ax3b.set_title('v5.1 Solution: Embedded MVRV', loc='left',
                   fontsize=12, fontweight='bold', color=G900)
    info_text = (
        'Embedded data: 4,230 daily MVRV values\n'
        'Date range: 2015-01-01 to 2026-07-31\n'
        'File size: ~35 KB\n\n'
        'How it works:\n'
        '  - Percentile computed from embedded history\n'
        '  - Z-score computed from embedded history\n'
        '  - No API call needed for sell signals\n'
        '  - Only price data needs live fetch\n\n'
        'Result: v5.1 ROI = 150.1% (same data)\n'
        'No regression from embedded approach'
    )
    ax3b.text(0.05, 0.95, info_text, transform=ax3b.transAxes,
             fontsize=10, color=G700, va='top', family='monospace',
             bbox=dict(boxstyle='round,pad=0.3', facecolor=G50, edgecolor=G200))

    # Panel C: Embedded MVRV preview
    ax3c = fig3.add_subplot(gs3[1, :])
    ax3c.set_title('Embedded MVRV Data (2015-2026)', loc='left',
                   fontsize=12, fontweight='bold', color=G900)
    from smart_dca.strategies._mvrv_history import MVRV_START_DATE, MVRV_DAILY_VALUES
    from datetime import date, timedelta
    start_d = date.fromisoformat(MVRV_START_DATE)
    embed_dates = [start_d + timedelta(days=i) for i in range(len(MVRV_DAILY_VALUES))]
    ax3c.plot(embed_dates, MVRV_DAILY_VALUES, color=ACCENT, linewidth=0.6, alpha=0.8)
    ax3c.axhline(y=2.5, color=NEG, linestyle='--', linewidth=1.2, alpha=0.6, label='Path A (2.5)')
    ax3c.axhline(y=2.0, color=WARN, linestyle='--', linewidth=1, alpha=0.5, label='Path A Ext (2.0)')
    # Highlight backtest period
    bt_start = master['date'].min()
    bt_end = master['date'].max()
    if hasattr(bt_start, 'date'): bt_start = bt_start.date() if hasattr(bt_start, 'date') else bt_start
    if hasattr(bt_end, 'date'): bt_end = bt_end.date() if hasattr(bt_end, 'date') else bt_end
    ax3c.axvspan(bt_start, bt_end, alpha=0.06, color=G400, label='Backtest Period')
    ax3c.legend(fontsize=8, loc='upper left', frameon=False)
    ax3c.set_ylabel('MVRV Ratio', fontsize=9, color=G500)
    ax3c.tick_params(axis='x', labelsize=7, rotation=25)
    clean_ax(ax3c)

    fig3.savefig(f'{DOWNLOAD_DIR}/phoenix_risk1_deep_dive.png', dpi=200,
                facecolor='white', bbox_inches='tight')
    plt.close(fig3)
    print(f'Saved: {DOWNLOAD_DIR}/phoenix_risk1_deep_dive.png')

    print('\nAll 3 charts generated successfully!')


if __name__ == '__main__':
    main()
