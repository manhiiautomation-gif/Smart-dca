# Phoenix DCA Bot — Work Log

---
Task ID: Wave-12-Phase3
Agent: main
Task: Phase 3 Code Quality — ลด code duplication, แก้ circular import, ใช้ named constants

Work Log:
- Phase 1: อ่านไฟล์ทั้งหมด (engine.py, strategy.py, state.py, notifier.py, config.py, bitkub_client.py, binance_client.py, indicators.py)
- Phase 2: ระบุ Code Quality issues 10 รายการ (CQ-1 ถึง CQ-10)
- Phase 3: Execute refactoring:
  - CQ-1 (HIGH): ลบ duplicate constant definitions ใน strategy.py (-48 lines)
  - CQ-2 (HIGH): ลบ circular import (strategy.py ไม่ import จาก engine แล้ว)
  - CQ-3 (MEDIUM): Refactor _snapshot_indicators ใช้ _resolve_onchain_metrics + _build_indicators_snapshot (-30 lines)
  - CQ-4 (MEDIUM): load_trade_log ใช้ _load_json_locked แทน inline lock pattern
  - CQ-5 (MEDIUM): append_trade_log ใช้ _atomic_json_write สำหรับ write step (-15 lines)
  - CQ-6 (MEDIUM): append_indicator_history ใช้ _atomic_json_write (-15 lines)
  - CQ-7 (HIGH): False positive — parenthesis ถูกต้องอยู่แล้ว
  - CQ-8 (LOW): ใช้ named DEPLOY_RATE_* constants แทน inline magic numbers
  - CQ-9 (LOW): ลบ duplicate metric unpacking ใน refresh_dashboard + run_demo (-40 lines)
  - CQ-10 (LOW): False positive
  - Bonus: แก้ pre-existing IndentationError ใน strategy.py path_a_ext
- Phase 4: Verify — ทุก import ผ่าน, integration test ผ่าน, RSI compute ผ่าน
- Phase 5: Commit + push (377e3a2)

Stage Summary:
- CQ-1: Duplicate constants removed (-48 lines)
- CQ-2: Circular import removed (strategy self-contained)
- CQ-3: _snapshot_indicators uses shared helpers (-30 lines)
- CQ-4: load_trade_log uses _load_json_locked
- CQ-5: append_trade_log uses _atomic_json_write
- CQ-6: append_indicator_history uses _atomic_json_write
- CQ-8: Inline deploy_rate replaced with named constants
- CQ-9: refresh_dashboard + run_demo unpacking removed (-40 lines)
- Net: -122 lines, 0 regressions
- Quality score: 93/100 PASS

---
Task ID: Wave-11-Phase2
Agent: main + 3 analysis sub-agents + 1 reviewer
Task: Phase 2 Data Integrity — แก้ไข 11 ปัญหาที่ข้อมูลไม่ตรงค่าจริง

Work Log:
- Phase 1: ส่ง 3 sub-agents วิเคราะห์ parallel (engine.py, strategy.py, state/client/notifier)
- พบ 11 ปัญหา Data Integrity: 1 HIGH, 8 MEDIUM, 2 LOW
- Phase 3: อ่านไฟล์ที่เกี่ยวข้องยืนยัน line numbers + วางแผนแก้ 11 issues
- Phase 4: Execute ทีละ issue:
  - DI-1 (HIGH): Timeout-unverified buy → zero decision['buy_amount'] ทั้ง 2 path
  - H3: คำนวณ buy_fill_price/sell_fill_price จาก actual fills ส่งไป trade_log + update_state
  - DI-2: adjusted_invested sell fraction ใช้ actual_sell แทน decision['sell_amount']
  - DI-3: Binance market_sell return net-of-fee (cummulativeQuoteQty - fee)
  - C7: เพิ่ม _fetch_monthly_usd_thb_rates() ดึง historical rates จาก CoinGecko BTC price ratio
  - S1: searchsorted side='left' → side='right' ทั้ง 4 ที่ (live + 3 backtest files)
  - S2: เพิ่ม nupl_valid NaN guard (same pattern as B24)
  - S3: เพิ่ม rp_valid sanity check (realized_price < 5x price)
  - DI-6: mvrv_pct/mvrv_z default 0 → float('nan') ทั้ง 4 ที่
  - DI-4: format_report() รับ actual_buy/actual_sell, แสดงเมื่อต่างจาก intended
  - DI-5: MVRV NaN แสดง 'N/A' แทน 'nan' ใน Telegram
- Phase 5: Code review → พบ 2 issues → แก้ทันที:
  - S1 backtest searchsorted ไม่ sync (3 files: _shared.py, data_pipeline.py, style_phoenix_v5_1.py)
  - C7 fragile float equality ใน month identification → เปลี่ยนใช้ derived_set
- Phase 6: Quality scoring 95/100 PASS

Stage Summary:
- DI-1 (HIGH): Timeout-unverified buy zero decision['buy_amount'] ป้องกัน phantom state counters
- H3 (MEDIUM): Actual fill prices ใน trade_log + update_state (cost/qty, proceeds/qty)
- DI-2 (MEDIUM): adjusted_invested sell fraction ใช้ actual proceeds
- DI-3 (MEDIUM): Binance sell proceeds normalized to net-of-fee
- C7 (MEDIUM): Historical USD/THB rates per month แทน single today's rate
- S1 (MEDIUM): MVRV percentile side='right' ทั้ง 4 ที่ (live + backtest sync)
- S2 (MEDIUM): NUPL explicit NaN guard
- S3 (MEDIUM): realized_price sanity check (< 5x price)
- DI-6 (MEDIUM): mvrv_pct/mvrv_z default NaN ไม่ใช่ 0
- DI-4 (LOW): Telegram แสดง actual exchange fill amounts
- DI-5 (LOW): MVRV NaN แสดง N/A ใน Telegram

---
Task ID: Wave-10-Phase1
Agent: main + 3 analysis sub-agents + 1 reviewer
Task: วิเคราะห์ระบบทั้งหมด 3 ทีม parallel + แก้ไข Phase 1 Stability & Correctness (6 issues)

Work Log:
- Phase 1: ส่ง 3 sub-agents วิเคราะห์ parallel (engine.py, config/strategy/notifier/clients, dashboard/workflows)
- พบปัญหารวม 50+ รายการ (Critical 7, High 27, Medium 34, Low 16)
- จัดเป็น 5-phase roadmap (24 tasks)
- Phase 3: อ่านโค้ดทุกไฟล์ที่เกี่ยวข้องยืนยัน line numbers + วางแผนแก้ 6 issues
- Phase 4: Execute ทีละ issue:
  - C4: Binance market_buy/sell ดึง fee จาก fills array + commissionAsset check (USDT only)
  - C3: เพิ่ม Binance app-level error check (code field in HTTP 200 response)
  - H9: เพิ่ม Bitkub _retry_request() (exponential backoff) wrap get_price, get_balances, market_sell
  - C5: เปลี่ยน MVRV percentile/zscore คืน NaN แทน 0.0 + NaN guard ทั้ง 5 ที่ใน engine.py
  - H1: bot_state['cooldown'] → .get('cooldown', 0)
  - H2: bot_state['peak_value'] → .get('peak_value', 0.0) + local variable
  - C2: Timeout buy verify ด้วย balance re-fetch (5s delay) แทน assume executed
- Phase 5: Code review → พบ 2 MEDIUM issues → แก้ทันที:
  - Missing NaN guards อีก 2 ที่ (idempotency-skip, kill-switch snapshot)
  - Binance fee ignore commissionAsset (เพิ่ม USDT-only filter)
- Phase 6: Quality scoring 93/100 PASS

Stage Summary:
- C2 (CRITICAL): Timeout buy ใช้ balance re-fetch verify แทน blind assumption
- C3 (CRITICAL): Binance app-level error check ใน market_buy + market_sell
- C4 (CRITICAL): Binance fee จาก fills array (USDT only, skip BNB)
- C5 (CRITICAL): MVRV NaN fallback แทน 0.0 + 5 location NaN guards
- H1 (HIGH): KeyError crash guard สำหรับ cooldown
- H2 (HIGH): KeyError crash guard สำหรับ peak_value
- H9 (HIGH): Bitkub retry logic สำหรับ get_price, get_balances, market_sell