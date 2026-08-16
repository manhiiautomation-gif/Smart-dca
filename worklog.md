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

---
Task ID: 2
Agent: Main
Task: Blind spot analysis — fix C1-C4 (Critical) + H1-H5 (High) before go-live

Work Log:
- C1: bitkub_client.py — Added `_check_response()` method, all API methods now check for Bitkub application-level errors (HTTP 200 with `"error": 42` in body)
- C2: main.py — Moved `save_state()` into try block + error handler (finally), prevents state loss on crash → no double-buy
- C3: bitkub_client.py — `market_buy()` returns `executed_qty` (from `recv` field), `market_sell()` returns standardized fields. Engine reads `executed_qty`/`cummulative_quote_qty`/`fee` — compatible with both Binance and Bitkub
- C4: config.py — Changed fee from 0.15% to 0.25% (Bitkub basic tier). Actual fee from API response preferred via new field mapping
- H1: engine.py + state.py — Replaced `date.today()` with `_thai_today()` (UTC+7) for idempotency guard, MVRV lookup, and trade log timestamps
- H2: notifier.py — Changed Telegram `parse_mode` from `Markdown` to `HTML`, `*bold*` → `<b>bold</b>`
- H3: generate_dashboard.py — L1 (BOT_ENABLED) now read from env var at dashboard gen time (available in same workflow), `bot_alive = l1_ok AND l2_ok`
- H4: main.py + dca-bitkub.yml — Added `.bot_lock` file mechanism (30min stale timeout), `cancel-in-progress: true` in workflow
- H5: state.py — `update_state_after_run()` now accepts `btc_balance`/`cash_balance`, reduces `adjusted_invested` proportionally on sell

Stage Summary:
- 7 files modified: bitkub_client.py, main.py, config.py, engine.py, state.py, notifier.py, generate_dashboard.py, dca-bitkub.yml
- All syntax checks passed, integration tests passed (_check_response, Thai TZ, adjusted_invested reduction, fee rate)
- System ready for dry-run testing on Bitkub before going live
