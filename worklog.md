---
Task ID: 1
Agent: main
Task: Refactor monolithic smart_dca_backtest.py (1620 lines) into modular package architecture

Work Log:
- Read and analyzed the full 1620-line monolithic file
- Designed modular architecture: config, data_pipeline, backtest_engine, visualization, strategies/
- Created package structure: scripts/smart_dca/ with 10 files
- Extracted shared MACD/RSI divergence/short-trend signal code into strategies/_shared.py
- Created STRATEGY_REGISTRY in strategies/__init__.py for auto-discovery
- Verified all 5 strategies produce identical results to original
- Old file preserved as scripts/smart_dca_backtest.py (backup)

Stage Summary:
- Refactored into 10 modular files under scripts/smart_dca/
- All results verified identical (3yr + 5yr, all 5 strategies)
- New entry point: python scripts/run_backtest.py
- To add new strategy: create file in strategies/, add 1 line to STRATEGY_REGISTRY
