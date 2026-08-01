"""
Smart DCA Backtest Suite — Modular Architecture

Structure:
  config.py          — Global constants (budget, fees, paths)
  data_pipeline.py   — Data fetching, CSV cache, technical indicators, master DF
  backtest_engine.py — Generic backtest runner (fee logic, state tracking)
  visualization.py   — Charts (3-panel PNG), summary table, CSV export
  strategies/        — One file per strategy, auto-registered via __init__.py
  run_backtest.py    — Main entry point (outside package, in scripts/)
"""