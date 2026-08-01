#!/usr/bin/env python3
"""
Smart DCA Backtest Suite - Main Entry Point

Usage:
  python scripts/run_backtest.py

Architecture:
  smart_dca/               <- package
    config.py              <- constants (budget, fees, paths)
    data_pipeline.py       <- data fetching, cache, technical indicators
    backtest_engine.py     <- generic backtest runner
    visualization.py       <- charts, tables, CSV export
    strategies/            <- one file per strategy
      __init__.py          <- STRATEGY_REGISTRY (add new strategies here)
      _shared.py           <- shared signal precomputation
      standard_dca.py
      style_c.py
      style_beta.py
      style_omega.py
      style_phoenix.py
"""

import sys
import os

# Add parent dir so we can import the smart_dca package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smart_dca.config import DOWNLOAD_DIR, CACHE_DIR
from smart_dca.data_pipeline import build_master_dataframe
from smart_dca.backtest_engine import backtest_strategy
from smart_dca.visualization import print_summary_table, generate_charts, save_results_csv
from smart_dca.strategies import STRATEGY_REGISTRY


def main():
    strategy_names = [s[0] for s in STRATEGY_REGISTRY]
    print("=" * 70)
    print("  SMART DCA BACKTEST SUITE (Modular v3)")
    print(f"  Strategies: {' | '.join(strategy_names)}")
    print("=" * 70)

    print("\n[PHASE 1] Building data pipeline (with CSV cache)...")
    master_df = build_master_dataframe(years=5)

    for years in [3, 5]:
        label = f'{years}-Year'
        print(f"\n{'=' * 70}")
        print(f"  RUNNING {label.upper()} BACKTEST")
        print(f"{'=' * 70}")

        if years == 3:
            test_df = master_df.tail(int(3 * 365.25)).reset_index(drop=True)
        else:
            test_df = master_df.copy()
        print(f"  Period: {test_df['date'].iloc[0]} to {test_df['date'].iloc[-1]} ({len(test_df)} days)")

        all_results = []
        all_daily_dfs = []
        for name, func_or_factory, needs_precompute in STRATEGY_REGISTRY:
            if needs_precompute:
                strategy_func = func_or_factory(test_df)
            else:
                strategy_func = func_or_factory

            print(f"\n  Backtesting {name}...", end=' ', flush=True)
            results, daily_df = backtest_strategy(test_df, strategy_func, name)
            all_results.append(results)
            all_daily_dfs.append(daily_df)
            print(f"Done. Value: {results['final_value']:,.0f} THB | True ROI: {results['true_roi_pct']:.1f}% | DD: {results['max_drawdown_pct']:.1f}%")

        print_summary_table(all_results)
        generate_charts(all_daily_dfs, all_results, label)
        save_results_csv(all_results, label)

    print("\n[COMPLETE] All backtests finished.")
    print(f"  Charts  : {DOWNLOAD_DIR}/smart_dca_comparison_*.png")
    print(f"  CSV     : {DOWNLOAD_DIR}/smart_dca_results_*.csv")
    print(f"  Cache   : {CACHE_DIR}/ (delete to force re-fetch)")
    print("=" * 70)


if __name__ == '__main__':
    main()
