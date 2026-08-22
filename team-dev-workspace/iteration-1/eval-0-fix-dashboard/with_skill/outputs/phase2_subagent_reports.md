# Phase 2: Sub-Agent Investigation Reports

---

## Task 2-a: Data Flow Agent
**Focus:** State management, data persistence, data flow between files

### Findings

1. **Two data sources with inconsistent data:**
   - `live_bot/state.json`: All counters at 0 (total_trades=0, net_pnl=0, last_exchange_name="", last_trade_time="")
   - `trade_log.json`: Contains 2 entries, both with `dry_run: true`, PnL values 210.0 and 220.0

2. **Engine behavior (engine.py lines 40-49):** When `dry_run=True`, the engine:
   - Sets `status="dry_run_completed"`
   - Does NOT call `increment_trade_counters()` (state.json stays zeroed)
   - Does NOT update `last_trade_time` or `last_exchange_name` in state
   - But DOES append to `trade_log.json` (line 49)

3. **Data flow bug location (generate_dashboard.py lines 23-31):** The dashboard computes aggregate stats entirely from `trade_log.json`:
   ```python
   total_trades = len(trades)  # Counts ALL entries including dry_run
   successful_trades = sum(1 for t in trades if t["status"] in ("completed", "dry_run_completed"))
   ```
   - `state.json` is loaded (line 20) but its values are ONLY used as fallbacks when `trades` is empty (lines 30-31)
   - The `dry_run` field is never checked when computing stats
   - The `state` dictionary is essentially ignored for summary statistics

4. **Secondary issue (engine.py line 35-36):** When `dry_run=True`, the engine sets `pnl: 0.0` but the trade_log.json entries have `pnl: 210.0` and `pnl: 220.0`. This is inconsistent - either the dry_run entries in trade_log were manually modified, or there's an older version of the engine that computed PnL even for dry runs. Either way, the dashboard reads these PnL values.

### Conclusion
The dashboard uses `trade_log.json` as the source of truth for aggregate stats but does not filter out `dry_run=true` entries. Since `state.json` is the correct source (only incremented for real trades), the dashboard should use `state.json` for summary stats.

---

## Task 2-b: Logic Agent
**Focus:** Business logic, aggregation, filtering, data consistency

### Findings

1. **Critical Bug - No dry_run filtering (generate_dashboard.py line 24-29):**
   ```python
   total_trades = len(trades)                    # Bug: counts dry_run entries
   successful_trades = sum(1 for t in trades if t["status"] in ("completed", "dry_run_completed"))  # Bug: includes dry_run_completed
   total_profit = sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0)  # Bug: includes dry_run PnL
   ```
   None of these aggregations check `t.get("dry_run", False)`. Every computation includes dry_run trades.

2. **Status string mismatch:** The dashboard line 25 treats `"dry_run_completed"` as a success status. This means even if we added a `dry_run` filter on the `status` field alone, it wouldn't work because dry_run entries have a different status string.

3. **Wrong fallback priority (lines 30-31):**
   ```python
   last_exchange = trades[-1]["exchange"] if trades else state.get("last_exchange_name", "")
   last_trade_time = trades[-1]["timestamp"] if trades else state.get("last_trade_time", "")
   ```
   When trades exist, it always takes from the last trade log entry (even dry_run). Should prefer state.json (which reflects real trades) and only fall back to trade_log.

4. **Trade log table (line 35-47):** The table shows ALL trades including dry_run, but has no column or visual indicator distinguishing dry_run from real trades. Users cannot tell which entries are test data.

### Conclusion
Three categories of bugs: (a) aggregate stats include dry_run data, (b) last exchange/time uses trade_log instead of state, (c) trade table doesn't distinguish dry_run entries.

---

## Task 2-c: UI/Display Agent
**Focus:** Dashboard rendering, visual output, user-facing data accuracy

### Findings

1. **Dashboard shows wrong numbers (confirmed by running generate_dashboard.py):**
   - Dashboard displays: Total Trades=2, Successful=2, Net PnL=430.00, Last Exchange=binance, Last Trade=2025-01-10T11:30:00Z
   - Actual state.json: total_trades=0, successful_trades=0, net_pnl=0.0, last_exchange_name="", last_trade_time=""
   - **Every single metric on the dashboard is wrong.**

2. **Trade log table has no dry_run indicator:** Users see trade rows with status "dry_run_completed" but no explicit "DRY RUN" badge or styling. The word "dry_run" is buried in the status column, easy to miss.

3. **Missing data freshness indicator:** No timestamp showing when the dashboard was generated or when the underlying data was last updated (`state.json` has `updated_at` field that could be displayed).

### Conclusion
The dashboard is visually displaying stale/incorrect data because it sources from the wrong data. Even after the user reset the state (all zeros), the dashboard still shows dry_run test data.
