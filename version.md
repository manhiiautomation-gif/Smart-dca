## 2026-08-21 (Wave 3) — Dashboard Stale Dry-Run Data Fix

Dashboard แสดงข้อมูลเก่าจาก dry-run testing (2026-08-18) แทนข้อมูลจริงจาก exchange
Root cause: trade_log ขาด `dry_run` flag + `last_dry_run` ถูก overwrite โดย refresh-only paths

### CRITICAL (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| D1 | trade_log dry-run ไม่มี flag | `trade_log.json` | 2 รายการ buy จาก dry-run ขาด `dry_run: true` → dashboard เข้าใจว่าเป็น trade จริง → เพิ่ม flag + เปลี่ยน filter เป็น strict check `t.get('dry_run') is False` |
| D2 | `last_dry_run` ถูก overwrite | `engine.py` L196,989,1055 | refresh-only paths (idempotency, refresh_dashboard, kill snapshot) เขียน `last_dry_run = dry_run` ทับ → ลบออกจากทั้ง 3 ที่ |
| D3 | dry-run→live transition | `engine.py` L233-252 | เพิ่ม auto-reset: พอ first live run หลัง dry-run จะ reset peak_value, counters, invested ทั้งหมด |

### HIGH (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| D4 | state.json เป็น virtual balance | `state.json` | dry-run virtual balances (9,998 THB) อยู่ใน `last_btc_balance`/`last_cash_balance` → reset สู่ค่าเริ่มต้น |
| D5 | peak_value ติดค่า dry-run | `engine.py` | `peak_value: 10000` (= DRY_RUN_INITIAL_CASH) จาก dry-run ไม่ลด — D3 reset แก้ปัญหานี้ |

### CRITICAL (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|------------|
| C10 | Retry loop ตาย | `main.py` L310 | `except Exception` ไม่มี `sys.exit(1)` → workflow retry ไม่ทำงาน เพิ่ม `sys.exit(1)` |
| C11 | Buy timeout → double buy | `engine.py` L601-606 | หาก API timeout แต่ order ไปถึง exchange แล้ว bot จะ retry ซื้อซ้ำ — เพิ่ม guard: timeout/connection → `trade_succeeded = True` |
| C12 | API response ไม่มี result key | `bitkub_client.py` L70 | Bitkub ส่ง `{"error": 0}` โดยไม่มี `result` → KeyError → phantom failed trade — เพิ่ม validation |

### HIGH (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|------------|
| H4 | Stored XSS ใน dashboard | `generate_dashboard.py` L196-198,635 | Kill reason, path ฝัง HTML โดยไม่ escape — เพิ่ม `html.escape()` ทุก user-derived string |
| H5 | kill_switch.json corrupt ทำให้ bot crash | `kill_switch.py` L22-33 | `json.load` ไม่มี try/except — เพิ่ม corruption recovery กลับไปใช้ defaults |
| H6 | MVRV=0 trigger 4.5x buy | `engine.py` (12 จุด) | BGeometrics ส่ง 0 → strategy เห็น `mvrv < 1.0` → ซื้อ 4.5x budget — เพิ่ม `if mvrv_val <= 0: nan` |

### MEDIUM (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|------------|
| M9 | Dashboard ROI เพี้ยน (รวม cash) | `generate_dashboard.py` L127-129 | ROI = (total_balance - invested) / invested → เปลี่ยนเป็น (btc_value - invested) / invested |
| M10 | Dashboard ใช้ adjusted_invested | `generate_dashboard.py` L135 | avg_buy_price ใช้ `adjusted_invested` จาก state แทน recomputed จาก trade log |
| M11 | P&L หัก fee ซ้ำ buy side | `generate_dashboard.py` L149 | `net_cash_out += amount + fee` → `net_cash_out += amount` (fee embedded) |
| M12 | Dashboard USD/THB rate เก่า | `generate_dashboard.py` L368-377 | ใช้ `cfg.USD_THB_RATE` (module constant) → เรียก `cfg.get_usd_thb_rate()` แบบ live |
| M13 | CoinGecko parse error | `bitkub_client.py` | JSON parse error จาก CoinGecko fallback — มี try/except แล้ว (ตรวจสอบซ้ำ) |
| M14 | Trade log truncation 500 → 5000 | `state.py` L249 | ที่ 1 trade/day จะเต็ม 500 ใน 1.4 ปี — เพิ่มเป็น 5000 (~13.7 ปี) |

### ตรวจสอบแล้วแต่ไม่ต้องแก้ (Low/ไม่กระทบ)

| # | ปัญหา | เหตุผล skip |
|---|--------|--------------|
| — | workflow_dispatch force bypass | เป็น feature สำหรับ owner ที่มี PAT |
| — | kill switch write non-atomic | เป็น manual action เท่านั้น |
| — | dry-run cash/reserve drift | ไม่กระทบ live trading |
| — | Binance Vision timeout risk | ต้องเปลี่ยน architecture ใหญ่ |
| — | runner crash mid-trade | ต้อง commit ใน Python process |
| — | Telegram silent failure | ไม่กระทบการ trade |
| — | SMA200 NaN → bear disable | edge case ที่ data < 200 วัน |

---

## 2026-08-21 (Wave 1) — Critical + High + Medium Bug Fix Wave

### CRITICAL (แก้ไขแล้วทั้งหมด)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|------------|
| C1 | Auth 400 error | `bitkub_client.py` | HMAC-SHA256 signature ผิด format — แก้ให้ `ts + method.upper() + path + body` |
| C2 | BG API rate limit | `bg_metrics.py` | 3 req/run → 3 req/day (daily snapshot guard) + fallback chain |
| C3 | Buy amount ผิด (300 vs 20 THB) | `engine.py` | Budget ถูก hardcoded ที่ 300 แทนที่จะอ่านจาก config — แก้ให้อ่านจาก env/config |
| C4 | Duplicate buys | `engine.py` | ไม่มี guard จำกัดจำนวน buy/วัน — เพิ่ม `MAX_DCA_BUYS_PER_DAY` นับจาก trade_log.json |
| C5 | git stash ทำให้ trade ไม่ถูก commit | `dca-bitkub.yml` | `git stash push -k` ก่อน commit ทำให้ state.json ที่ bot เขียนถูก stash ไป — เอา stash ออก, commit state ก่อน dashboard |
| C6 | Dashboard ไม่แสดงค่าจริง | `generate_dashboard.py` + workflow | 3 root causes: (1) demo files แสดงแทน, (2) stale `last_dry_run: true`, (3) race condition deploy-pages push trigger |
| C7 | แยก commit state กับ dashboard | `dca-bitkub.yml` | state commit ก่อน (step 122), dashboard commit หลัง (step 148) — ป้องกัน duplicate trade |
| C8 | กู้คืน state.json เมื่อ corrupt | `state.py` | `save_state()` สร้าง `.bak` ก่อนเซฟ, `load_state()` อ่าน `.bak` เมื่อหลัก corrupt |
| C9 | Division by zero (price <= 0) | `engine.py` | เพิ่ม `if price <= 0` guard ที่ 3 จุด: dry-run buy, live sell, dry-run sell |

### HIGH (แก้ไขแล้วทั้งหมด)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|------------|
| H1 | Failed sell ตั้ง phantom cooldown | `engine.py` L638 | sell ล้มเหลวแต่ cooldown ยังคง — เพิ่ม `decision['new_cooldown'] = 0` หลัง sell error |
| H2 | State บันทึกก่อน trade log | `engine.py` L646-672 | ย้าย `append_trade_log()` ไว้ก่อน `update_state_after_run()` — ป้องกัน inconsistent data |
| H3 | TOCTOU race ใน trade log | `state.py` L184-235 | เปลี่ยนจาก LOCK_SH→read→release→LOCK_EX→write เป็น LOCK_EX เดียวครอบ read-modify-write ทั้งหมด |

### MEDIUM (แก้ไขแล้วทั้งหมด)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|------------|
| M1 | Reserve tracking ใช้ field ไม่มีอยู่ | `engine.py` | `total_invested_from_reserve` (ไม่มี) → `total_reserve_injected` (มีอยู่แล้ว) |
| M2 | P&L หัก fee ซ้ำสองครั้ง | `generate_dashboard.py` | Bitkub `amount` = net after fee — เปลี่ยนจาก `net_cash_out -= amount - fee` เป็น `net_cash_out -= amount` |
| M3 | เวลารันถัดไปผิด | `generate_dashboard.py` | 00:10 THB → 20:00 THB (ให้ตรง cron `0 13 * * *` UTC) |
| M4 | Dashboard refresh ขาด env vars | `dashboard-trigger.yml` | เพิ่ม `BGEOMETRICS_TOKEN`, `RESERVE_FLOOR`, `MAX_RESERVE_INJECTION`, `RESERVE_BOOST_*`, `LOW_BALANCE_DAYS` |
| M5 | Budget default ไม่ตรง | `dashboard-trigger.yml` | `DAILY_BUDGET_THB` default `'20'` → `'100'` ให้ตรง main workflow |
| M6 | YAML indent ผิด | `deploy-pages.yml` | ตรวจแล้ว — indent ถูกต้องอยู่แล้ว (false positive) |
| M7 | total_sell_proceeds ใช้ strategy amount | `state.py` + `engine.py` | เพิ่ม param `sell_proceeds_actual` ให้ใช้ยอดจริงจาก exchange แทนยอดที่ strategy คำนวณ |
| M8 | tempfile cleanup NameError | `state.py` + `bg_metrics.py` | เพิ่ม `tmp_path = None` ก่อน try block, เช็ค `tmp_path is not None` ใน except |

---

## สถาปัตยกรรมสำคัญที่ควรรู้

### Workflow Chain
```
dca-bitkub.yml (cron 13:00/13:10/13:30 UTC)
  ├─ Step: Run bot (main.py)
  ├─ Step: Commit state.json + trade_log.json (critical)
  ├─ Step: Generate dashboard (continue-on-error)
  ├─ Step: Commit dashboard/dist/index.html (non-critical)
  └─ Job: deploy → deploy-pages.yml (skip_build=true)

dashboard-trigger.yml (manual dispatch from dashboard)
  ├─ Step: Run main.py --refresh-only
  ├─ Step: Generate dashboard
  ├─ Step: Commit all
  └─ Job: deploy → deploy-pages.yml (skip_build=true)
```

### Key Files
- `live_bot/engine.py` — หัวใจหลัก: run_daily(), refresh_dashboard()
- `live_bot/state.py` — state persistence, trade log, file locking
- `live_bot/strategy.py` — Phoenix v5.1 DCA strategy (buy/sell signals)
- `live_bot/bitkub_client.py` — Bitkub exchange API (HMAC-SHA256 auth)
- `live_bot/bg_metrics.py` — BGeometrics on-chain metrics (MVRV, SOPR, LTH-RP)
- `scripts/generate_dashboard.py` — Static HTML dashboard generator

### Key Conventions
- Thai timezone (UTC+7) สำหรับทุกอย่าง: dates, cron, trade log
- `state.json` เก็บ bot state, `trade_log.json` เก็บ trade history
- File locking via `fcntl.flock` (LOCK_SH for read, LOCK_EX for write)
- Atomic writes via `tempfile.mkstemp` + `os.replace`
- BGeometrics API: max 10 req/hr free tier, daily snapshot guard
- Bitkub `amount` field = net after fee (cummulative_quote_qty/recv)
- ROI = (btc_value - invested) / invested, NOT (total_balance - invested) / invested
- `html.escape()` ต้องใช้กับทุก user-derived string ก่อนฝังใน HTML
- MVRV ≤ 0 ต้อง treat เป็น NaN (ป้องกัน 4.5x buy signal)
- Trade timeout → assume executed, consume daily slot to prevent double-buy
