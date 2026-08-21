# Phoenix v5.1 DCA Bot — Version Changelog

ไฟล์นี้บันทึกประวัติการแก้ไขปัญหาทั้งหมด เพื่อให้ AI agent ที่เข้ามาทำงานใหม่เข้าใจบริบทได้เร็ว

---

## 2026-08-21 — Critical + High + Medium Bug Fix Wave

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
