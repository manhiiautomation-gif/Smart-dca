# Phoenix DCA Bot — Work Log

---
Task ID: Research-DCA-TimeWindow-MondayMultiplier
Agent: investigator
Task: Analyze how adding a DCA time window (10:00-11:00 THB = 03:00-04:00 UTC) and Monday 1.2x multiplier would interact with existing code

Findings:

## 1. run_daily() Buy Decision Flow & Monday Multiplier Placement

**Key line numbers (engine.py):**
- L570-571: `base_budget = config.get_daily_budget()`, `max_buy = config.get_max_buy()` — budget/mx resolved
- L592-609: `decision = strategy.phoenix_v5_1_decision(...)` — strategy called with `base_budget` + `max_buy`
- L611-613: Decision logged (buy_amount, sell_amount, score, path)
- L624: `_original_buy_amt = decision['buy_amount']` — snapshot before any adjustment
- L628-640: Min buy check, insufficient cash adjustment
- L647+: Trade execution
- L743-749: Trade log recording (buy)
- L831-844: `last_decision` saved to state (includes `calc_multiplier`)
- L882-885: Notification via `notifier.format_report(decision, ...)`

**CRITICAL: max_buy cap is INSIDE the strategy (strategy.py L157):**
```python
buy_amount = min(base_budget * multiplier, max_buy)
```
This means the Monday multiplier placement MATTERS:
- **If applied BEFORE strategy (multiply base_budget L570):** max_buy cap still works correctly. The `calc_multiplier` at L835 would show `strategy_mult * 1.2` combined (e.g., 3.6x instead of 3.0x) — indistinguishable from a higher strategy multiplier.
- **If applied AFTER strategy (multiply decision['buy_amount'] post-L609):** BYPASSES the max_buy cap! E.g., if strategy returns 1000 (capped at max_buy), 1.2x → 1200 exceeds cap. Must re-apply `min(..., max_buy)`.
- **RECOMMENDED: Apply BEFORE strategy at L570**, by replacing `base_budget` with `base_budget * monday_mult` when it's Monday. This keeps the max_buy cap intact inside strategy.

## 2. Idempotency Guard (L347) & Time-of-Day Dependency

- L347: `if not force and bot_state.get('last_run_date') == today.isoformat():`
- `_thai_today()` (L20-22) returns a `date` object — **no time component**.
- **Nothing in the guard depends on time of day**, only the date.
- **Time window impact:** The current cron runs at 13:00/13:10/13:30 UTC. A new 03:00-04:00 UTC window would be a DIFFERENT time but SAME Thai date. The idempotency guard would **block** the second window because `last_run_date` is already set from the 13:00 UTC run.
- **Fix needed:** Either (a) remove idempotency guard and rely solely on `MAX_DCA_BUYS_PER_DAY` (L412-437), or (b) make the guard time-window-aware, or (c) use `MAX_DCA_BUYS_PER_DAY >= 2` to allow the daily count guard to be the primary limiter.
- The daily buy count guard (L417-437) counts actual buys per Thai date from trade_log — this WOULD allow a second buy if `MAX_DCA_BUYS_PER_DAY >= 2`. This is the safer guard.

## 3. run_demo() (L1095-1275)

- L1190-1206: Calls `strategy.phoenix_v5_1_decision()` DIRECTLY with `base_budget` from L1180.
- **Monday multiplier in engine.py would NOT automatically apply to demo mode** because run_demo() has its own `base_budget = config.get_daily_budget()` at L1180 and its own strategy call at L1190.
- **Changes needed in run_demo():** Same Monday multiplier logic must be duplicated at L1180 (or extracted to a shared helper function).
- **Time window:** Demo mode has its own idempotency guard at L1115 (also date-based via `_thai_today()`). Same issue as live mode if time windows are added.
- **Trade recording:** Demo uses `dp.process_demo_trade()` (L1213) which calls `_append_demo_trade()` (demo_portfolio.py L637). The demo trade log record includes `extra` dict with `slippage` and `reserve`. Monday boost should be added to `extra`.

## 4. refresh_dashboard() (L895-1037)

- **Does NOT call strategy.** Only fetches price, indicators, and balances.
- **Should NOT be affected by time window or Monday multiplier.** No changes needed.
- It stores `last_indicators` but NOT `last_decision` (no trading decision is made).

## 5. _snapshot_indicators (L1040-1092)

- Only called when the bot is KILLED (L474).
- Stores indicators only, no decision or trade data.
- **No changes needed for Monday boost.**

## 6. Trade Log Recording

**Live mode (engine.py L743-749):**
```python
state_mod.append_trade_log(trade_log_path, 'buy', buy_cost_actual, buy_btc_got,
    price, buy_fee,
    extra={'dry_run': dry_run, 'reserve': round(decision.get('reserve_injection', 0), 2)})
```
- `buy_cost_actual` = actual amount spent (after Monday boost if applied)
- The `extra` dict should include `'monday_boost': True` (or the multiplier value) for auditability.
- Currently only `dry_run` and `reserve` are in `extra`.

**Demo mode (demo_portfolio.py L324-329):**
```python
_append_demo_trade(project_root, scenario, 'buy', cost_with_slippage, btc_got, price, fee,
    extra={'slippage': ..., 'reserve': ...})
```
- Same: should add `'monday_boost': True` to extra.

**state.py append_trade_log (L231-282):** Generic function, no changes needed — it just passes through `extra`.

## 7. Notification (notifier.py L25-53)

```python
def format_report(decision, price, mvrv, btc_balance, cash, exchange_currency, is_dry_run):
    # Shows: decision['buy_amount'], decision['reserve_injection']
```
- If Monday boost is applied to `base_budget` before strategy, then `decision['buy_amount']` already includes the boost.
- **Should explicitly mention Monday boost** in the notification for clarity, e.g., "BUY: 120.00 USDT (Monday 1.2x boost)".
- Requires adding a `monday_boost` flag to the `decision` dict, OR checking in `format_report`.
- `format_report` signature would need a new parameter (e.g., `monday_boost=False`).

## 8. Dashboard (generate_dashboard.py L298-384)

- Shows `ld_mult` = `buy_amount / base_budget` (calculated at engine.py L835).
- If Monday boost is applied by multiplying `base_budget`, then `ld_mult` = strategy_mult * 1.2 (combined).
- **Problem:** Dashboard can't distinguish "3.0x strategy + Monday boost" from "3.6x strategy".
- **Recommendation:** Store `monday_boost_applied` flag in `last_decision` dict (engine.py L838-844) so dashboard can show it separately (e.g., "3.0x + Monday 1.2x").
- Dashboard's "Next round estimate" (L305-331) would NOT show Monday boost (it's date-dependent, not indicator-dependent). This is correct behavior.

## 9. demo_portfolio.py — Does it call phoenix_v5_1_decision directly?

- **No.** `demo_portfolio.py` does NOT call `phoenix_v5_1_decision`.
- It calls `dp.process_demo_trade()` (engine.py L1213), which receives the already-computed `decision` dict from the strategy call in `run_demo()` (engine.py L1190).
- So if the Monday multiplier is applied in `run_demo()` before `process_demo_trade()`, it flows through automatically.

## 10. Summary: Exact Line Numbers Where Changes Are Needed

| Location | File | Line(s) | Change | Priority |
|----------|------|---------|--------|----------|
| Monday multiplier calc | engine.py | ~L570 (run_daily) | Apply 1.2x to `base_budget` on Monday | HIGH |
| Monday multiplier calc | engine.py | ~L1180 (run_demo) | Same 1.2x logic duplicated | HIGH |
| Time window guard | engine.py | ~L347 (idempotency) | Allow re-run if in different time window | HIGH |
| Time window guard | engine.py | ~L1115 (demo idempotency) | Same for demo | HIGH |
| Monday flag in decision | engine.py | ~L838-844 (last_decision) | Add `monday_boost: True` field | MEDIUM |
| Monday flag in decision | engine.py | ~L1250-1256 (demo last_decision) | Same for demo | MEDIUM |
| Trade log extra | engine.py | ~L747-748 | Add `'monday_boost': True` to extra | MEDIUM |
| Trade log extra | demo_portfolio.py | ~L326-329 | Add `'monday_boost': True` to extra | MEDIUM |
| Notification | notifier.py | ~L25-53 | Add Monday boost mention to report | LOW |
| Notification caller | engine.py | ~L882-885 | Pass monday_boost flag to format_report | LOW |
| Dashboard | generate_dashboard.py | ~L298-384 | Show Monday boost badge if applicable | LOW |
| Config | config.py | ~L148 area | Add MONDAY_BOOST_MULTIPLIER, TIME_WINDOW_* | HIGH |

## 11. Potential Side Effects

1. **max_buy cap bypass:** If Monday multiplier is applied AFTER strategy returns (post-L609), the max_buy cap inside strategy is defeated. Must apply BEFORE (L570) or re-cap after.
2. **Idempotency conflict:** Current idempotency guard blocks same-day re-runs. Adding a second time window requires relaxing this guard while keeping `MAX_DCA_BUYS_PER_DAY` as the real limiter.
3. **Daily buy count guard interaction:** The guard at L417-437 counts buys from trade_log. If `MAX_DCA_BUYS_PER_DAY` is increased to 2, the 13:00 UTC run consumes 1 slot and the 03:00 UTC run can use the 2nd. This is safe.
4. **calc_multiplier accuracy:** L835 `calc_multiplier = buy_amt / base_budget`. If base_budget is boosted, the displayed multiplier is inflated. Store original base_budget separately for accurate display.
5. **Low balance warning (L866-879):** Uses `config.get_daily_budget()` (un-boosted). On Mondays, actual spend is 1.2x higher, so remaining days calculation is slightly optimistic. Minor issue.
6. **Reserve deployment:** The reserve injection is added AFTER the base buy (strategy.py L183). Monday boost on base_budget would also boost the relative size of the buy but reserve deployment is independent of base_budget. No conflict.
7. **Timeout estimation (L675-678):** Uses `decision['buy_amount']` (post-Monday boost). This is correct — the actual sent amount is what matters.

Stage Summary:
- Monday 1.2x multiplier: Apply to `base_budget` BEFORE strategy call (L570 for live, L1180 for demo)
- Time window: Requires relaxing idempotency guard (L347, L1115) + increasing MAX_DCA_BUYS_PER_DAY to >= 2
- Trade log: Add `monday_boost` to `extra` dict (engine.py L748, demo_portfolio.py L328)
- Dashboard: Add `monday_boost` flag to `last_decision` (engine.py L838, L1250)
- Notification: Add Monday boost mention (notifier.py L39, engine.py L882)
- Demo mode: Needs parallel changes (not automatic)
- refresh_dashboard + _snapshot_indicators: NO changes needed

---
Task ID: Wave-8-D6-D7
Agent: main
Task: ตรวจสอบ TODO จาก session ก่อน และทำต่อให้เสร็จ

Work Log:
- อ่าน worklog.md + version.md จาก session ก่อน
- พบว่า B22 ถูก implement แล้วใน Wave 7 (แต่ version.md เขียนผิดว่า deferred)
- พบว่า dashboard indicator_history integration ถูก implement แล้ว (โค้ดครบ ทั้ง load, pass, render ECharts)
- แต่พบ commit 6d4543b ทำให้ generate_dashboard.py compile ไม่ได้ (f-string {{/}} จัดสมดุลผิด 5 จุด)
- แยก ECharts indicator JS เป็น `_build_indicator_charts_js()` ใช้ regular string + .replace()
- เพิ่มกราฟ Price + NUPL (จากเดิม 3 กราฟ → 5 กราฟ)
- เพิ่ม responsive grid 2 columns ที่ 900px breakpoint
- แก้ version.md ให้ B22 แสดงสถานะถูกต้อง

Stage Summary:
- D6 (CRITICAL): generate_dashboard.py SyntaxError — แยก f-string IIFE เป็น regular string function
- D7 (MEDIUM): เพิ่มกราฟ Price + NUPL พร้อม responsive grid
- B22: ยืนยันว่าถูก implement แล้วใน Wave 7, แก้ version.md
- indicator_history pipeline: พร้อมใช้งาน รอ bot รันครั้งต่อไปเพื่อสร้างข้อมูล

---
Task ID: Wave-7-B18-B24
Agent: main + 1 investigator + 1 reviewer
Task: ตรวจสอบและปรับปรุงระบบ indicator DCA, BGeometrics API caching, ประวัติ indicator, และ proxy accuracy

Work Log:
- Phase 1: อ่าน bg_metrics.py, engine.py, strategy.py, state.py, mvrv_fetcher.py, generate_dashboard.py
- Phase 2: ส่ง investigator subagent วิเคราะห์ 5 ด้าน (DCA indicator, BG API, caching, history, proxy fallback)
- Phase 3: สรุป 8 บัค (B18-B25), วางแผนแก้ 6 บัค, defer 2 บัค (B22, B25)
- Phase 4: Implement ทีละบัค:
  - B19: เพิ่ม _daily_series_cache ใน bg_metrics.py ลด disk read 5→0 ครั้ง
  - B18: เพิ่ม append_indicator_history() + load_indicator_history() ใน state.py
  - B18b: เรียก append จาก run_daily() + refresh_dashboard() ใน engine.py
  - B20: เพิ่ม proxy accuracy logging (SOPR actual vs proxy)
  - B21: เปลี่ยน daily guard จาก UTC เป็น Thai TZ (UTC+7)
  - B23: ปรับ LTH-RP proxy เป็น dynamic (bear=1.25, bull=1.10, neutral=1.15)
  - B24: เพิ่ม explicit NaN guard สำหรับ SOPR ใน strategy.py
- Phase 5: Code review → พบ 3 บัคเพิ่มเติม:
  - CRITICAL: state_path undefined ใน run_daily() → แก้ใช้ trade_log_path
  - MODERATE: no-token path ไม่ set _daily_series_cache → เพิ่ม
  - MINOR: dynamic LTH-RP ขาดที่ idempotency-skip + run_demo → เพิ่ม
- Phase 6: Quality scoring 88/100 PASS
- Phase 7: อัปเดต version.md Wave 7, commit

Stage Summary:
- B18 (HIGH): indicator_history.json เก็บ time-series 730 วัน, atomic write + LOCK_EX
- B19 (HIGH): _daily_series_cache ลด disk I/O, รวม no-token path
- B20 (MEDIUM): SOPR proxy accuracy log เมื่อมีค่าจริงจาก BG
- B21 (MEDIUM): Daily guard ใช้ Thai TZ ตรงกับ bot timezone
- B23 (MEDIUM): Dynamic LTH-RP proxy 4 ที่ (run_daily, refresh, idempotency-skip, run_demo)
- B24 (LOW): Explicit sopr_valid NaN guard ใน strategy.py
- Deferred: B22 (code duplication), B25 (CoinMetrics file cache)

---
Task ID: 2-a, 2-b, 2-c, 8
Agent: main + 3 subagents + 1 reviewer
Task: ตรวจสอบ dashboard data pipeline ทั้งหมด (state.json → trade_log → dashboard → deploy)

Work Log:
- สร้าง subagent ตรวจสอบโครงสร้างโปรเจกต์ (Explore)
- สร้าง subagent 3 ตัว parallel:
  - 2-a: ตรวจ state.json/trade_log.json write pipeline (engine.py + state.py)
  - 2-b: ตรวจ generate_dashboard.py read/filter/display logic
  - 2-c: ตรวจ GitHub Actions workflows + deploy pipeline
- รวบรวมผล → พบบั๊ก 5 รายการ (B1-B5)
- วางแผนแก้ไขรอบที่ 1 → ทบทวนรอบที่ 2
- แก้ไข B1: state.py clear_trade_log() + engine.py D3-ext
- แก้ไข B2: engine.py timeout buy ใช้ actual sent amount
- แก้ไข B3: generate_dashboard.py ใช้ state.json exchange_name/currency
- แก้ไข B5: state.py actual_buy_cost parameter
- สร้าง reviewer subagent ตรวจโค้ดทั้งหมด → พบ B2 bug (insufficient cash + timeout) → แก้ซ้ำ
- เขียน version.md Wave 4

Stage Summary:
- B1 (HIGH): D3 reset ล้าง trade_log.json ด้วย clear_trade_log() (atomic, LOCK_EX)
- B2 (HIGH): Timeout buy ประมาณ trade details จาก amount ที่ส่งจริง (รวมกรณี insufficient cash)
- B3 (MEDIUM): Dashboard Config section ใช้ exchange_name จาก state.json แทน cfg.EXCHANGE default
- B5 (LOW): total_invested ใช้ actual_buy_cost จาก exchange แทน decision amount
- Review ยืนยัน: ไม่มี regression, locking ถูกต้อง, fallback ปลอดภัย

---
Task ID: U1-U12
Agent: main
Task: ปรับปรุง UX Dashboard ทั้ง 12 จุด

Work Log:
- อ่าน generate_dashboard.py (1,423 บรรทัด) ทั้งไฟล์
- ใช้ VLM วิเคราะห์ screenshot 2 ภาพ (dashboard_full.png, dashboard_bottom1.png)
- ระบุปัญหา UX 12 จุด (U1-U12) แบ่ง 3 ระดับความรุนแรง
- แก้ไขทั้งหมดใน scripts/generate_dashboard.py
- ทดสอบ generate สำเร็จ (51,206 bytes)

Stage Summary:
- U1-U12: ปรับปรุง UX Dashboard ทั้ง 12 จุด (responsive, empty state, labels, colors, formatting, chart, freshness, config, contrast)

---
Task ID: 1
Agent: main
Task: Optimize BGeometrics API usage - batch fetch, daily guard, fallback for all indicators

Work Log:
- Analyzed current API usage: 3 separate get_*() calls per bot run
- Added get_all_metrics_today() to bg_metrics.py with in-memory daily snapshot guard
- API usage reduced from 3 calls/run to 3 calls/day (first run) then 0 calls/day
- All 5 on-chain indicators now have fallback calculation chains

Stage Summary:
- bg_metrics.py: new get_all_metrics_today() + invalidate_daily_snapshot()
- engine.py: both live and demo sections use batch fetch + full fallback chain
- API usage reduced from 3 calls/run to 3 calls/day then 0 calls/day
