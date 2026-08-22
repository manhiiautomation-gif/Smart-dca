# Phase 3: Fix Plan (2 Rounds)

## 3a. Consolidated Issue List

| ID | Severity | File | Description |
|----|----------|------|-------------|
| BUG-1 | **CRITICAL** | scripts/generate_dashboard.py:24-29 | Aggregate stats (total_trades, successful_trades, profit, loss, net_pnl) computed from ALL trade_log entries without filtering `dry_run=true` |
| BUG-2 | **HIGH** | scripts/generate_dashboard.py:30-31 | `last_exchange` and `last_trade_time` prefer trade_log over state.json, showing dry_run data when state has correct values |
| BUG-3 | **MEDIUM** | scripts/generate_dashboard.py:35-47 | Trade log table has no visual indicator for dry_run entries |
| BUG-4 | **LOW** | scripts/generate_dashboard.py (missing) | No "data as of" timestamp showing dashboard generation time or state update time |

### Root Cause
The dashboard was originally written assuming all trade_log entries were real trades. When dry_run support was added to the engine (engine.py), the dashboard was not updated to filter or distinguish dry_run entries.

---

## 3b. Fix Plan (Round 1)

### BUG-1: Filter dry_run from aggregate stats
- **What:** In `generate_dashboard()`, add a `dry_run` filter when computing aggregate stats. Use `state.json` as the primary source for summary statistics.
- **Why:** state.json is only updated for real trades (engine.py line 40-45). It's the single source of truth for cumulative stats.
- **How:** Replace lines 24-29 with values from `state` dictionary:
  ```python
  total_trades = state.get("total_trades", 0)
  successful_trades = state.get("successful_trades", 0)
  failed_trades = state.get("failed_trades", 0)
  total_profit = state.get("total_profit", 0.0)
  total_loss = state.get("total_loss", 0.0)
  net_pnl = state.get("net_pnl", 0.0)
  ```
- **Risk:** Low. state.json already has all these fields with defaults.

### BUG-2: Fix last exchange/time priority
- **What:** Use state.json values for `last_exchange` and `last_trade_time`. Fall back to trade_log (filtered to non-dry_run only) if state values are empty.
- **Why:** state.json is updated immediately after each real trade (engine.py lines 44-45).
- **How:**
  ```python
  last_exchange = state.get("last_exchange_name", "") or ""
  last_trade_time = state.get("last_trade_time", "") or ""
  ```
- **Risk:** None.

### BUG-3: Add dry_run indicator to trade table
- **What:** Add a "Dry Run" column or badge in the trade log table.
- **Why:** Users need to distinguish test trades from real ones.
- **How:** Add a column "Mode" that shows "DRY RUN" (with red/yellow styling) or "LIVE" (with green styling).
- **Risk:** Low - purely visual addition.

### BUG-4: Add data freshness timestamp
- **What:** Show `state["updated_at"]` on the dashboard.
- **Why:** Users need to know when data was last refreshed.
- **How:** Add a footer or info line showing "Data as of: {state['updated_at']}".
- **Risk:** None.

---

## 3c. Self-Review (Round 2)

1. **Re-read code at change points:** Yes, confirmed line numbers are correct.
2. **Verify assumptions:**
   - state.json has all needed fields? YES (total_trades, successful_trades, failed_trades, total_profit, total_loss, net_pnl, last_exchange_name, last_trade_time, updated_at)
   - trade_log entries have `dry_run` boolean field? YES
3. **Side effects:**
   - Switching from trade_log aggregation to state.json means the dashboard no longer independently verifies trade counts. This is acceptable because state.json IS the engine's own counter.
   - The trade log table still shows ALL entries (including dry_run) which is correct - it's a log.
4. **Ordering:** BUG-1 and BUG-2 are the same code block, fix together. BUG-3 is separate (table rendering). BUG-4 is independent (footer).
5. **All findings addressed?** YES - all 3 agents' findings are covered.
6. **Edge cases:**
   - Empty trade_log: Dashboard falls back to state values -> handled
   - Empty state (all zeros): Dashboard shows zeros -> correct after reset
   - Corrupt/missing state.json: Should add error handling -> add try/except around load_json

### Revised Plan After Self-Review
Added: Error handling for missing/corrupt JSON files (wrap load_json calls with try/except, provide defaults).

---

## Final Plan: Changes per File

**File: `scripts/generate_dashboard.py`**
1. Lines 14-16: Make `load_json` handle errors gracefully
2. Lines 23-31: Replace trade_log-based aggregation with state.json values for all summary stats
3. Lines 33-47: Add "Mode" column to trade table with dry_run/live badge
4. After line 48: Add data freshness footer
5. HTML table header: Add "Mode" column
