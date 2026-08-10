# Work Log

---
Task ID: 1
Agent: Main
Task: Fix currency unit mismatch, configurable DCA params, reserve separation

Work Log:
- Rewrote config.py: Added CURRENCY auto-derivation from EXCHANGE, helper functions (thb_to_local, get_daily_budget, get_max_buy, get_reserve_floor, get_max_reserve_injection, get_max_reserve_boosted), configurable DCA/reserve params via env vars
- Rewrote strategy.py v5.1.1: Removed hardcoded THB values (200/900/1200), added reserve_floor/max_reserve_injection/max_reserve_boosted/reserve_boost_multiplier/reserve_boost_price_ratio parameters
- Updated demo_portfolio.py: Added currency integrity validation on load (raises ValueError on mismatch), added sell_proceeds_reserve tracking, added buy_status tracking, added low balance warning
- Updated engine.py: Strategy calls pass reserve config params, cash_reserve changed to sell_proceeds_reserve only, added BUY STATUS reporting, added low balance warning with Telegram alert, tracks sell_proceeds_reserve in state
- Updated dca-demo.yml: Passes new config env vars
- Reset corrupted demo data (THB/USDT mixed)
- All syntax and unit tests passed, pushed to main

Stage Summary:
- Root cause of 33x over-buying FIXED: strategy.py hardcoded 200/900/1200 THB values used directly as USDT
- 6 files modified, 1 new file (scripts/reset_demo.py), pushed as commit 79b0100
- Config now fully configurable: DAILY_BUDGET_THB, MAX_BUY_THB, MAX_DCA_BUYS_PER_DAY, RESERVE_FLOOR, MAX_RESERVE_INJECTION, RESERVE_BOOST_MULTIPLIER, RESERVE_BOOST_PRICE_RATIO, LOW_BALANCE_THRESHOLD, LOW_BALANCE_DAYS
- Currency integrity lock prevents future THB/USDT data corruption
