## 2026-08-24 (Wave 8) — Dashboard Indicator Charts & f-string Fix

แก้ไขปัญหา dashboard จากการตรวจสอบ session ก่อน

### CRITICAL (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| D6 | generate_dashboard.py SyntaxError | `scripts/generate_dashboard.py` | commit 6d4543b แนะนำ IIFE indicator charts ด้วย f-string มี {{/}} จัดสมดุลผิด 5 จุด (gridBase, MVRV/RSI/SOPR yAxis, MVRV markLine) ทำให้ไฟล์ compile ไม่ได้เลย — แยกเป็น `_build_indicator_charts_js()` ใช้ regular string + `.replace()` |

### MEDIUM (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| D7 | Indicator charts มีเพียง 3 กราฟ | `scripts/generate_dashboard.py` | เพิ่มกราฟ Price (สีเขียว) และ NUPL (สีตามค่า) รวมเป็น 5 กราฟ, เพิ่ม responsive grid 2 columns ที่ 900px |

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| B18 | ไม่มีประวัติ indicator แบบ time-series | `state.py`, `engine.py` | เพิ่ม `append_indicator_history()` + `load_indicator_history()` ใน state.py, เรียกจาก run_daily() และ refresh_dashboard() เก็บ indicator_history.json (730 entries, ~2 ปี) |
| B19 | _lookup_from_snapshot อ่าน disk ซ้ำซ้อน | `bg_metrics.py` | เพิ่ม `_daily_series_cache` (in-memory) ลด disk read 5 ครั้ง/rerun → 0 ครั้ง, รวมทั้ง no-token path ด้วย |

### MEDIUM (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| B20 | ไม่มี proxy accuracy tracking | `engine.py` | เพิ่ม SOPR proxy vs actual comparison log เมื่อมีค่าจริงจาก BG (print diagnostic, non-intrusive) |
| B21 | Daily snapshot guard ใช้ UTC ผิด timezone | `bg_metrics.py` | เปลี่ยนจาก `datetime.now(timezone.utc)` เป็น `datetime.now(timezone(timedelta(hours=7)))` ให้ตรง Thai TZ |
| B23 | LTH-RP proxy ใช้ค่าคงที่ 1.15x | `engine.py` | เปลี่ยนเป็น dynamic: bear=1.25, bull(MVRV>2.5)=1.10, neutral=1.15 ทุก location (run_daily, refresh, idempotency-skip, run_demo) |

### LOW (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| B24 | NaN SOPR ทำให้ได้ multiplier ผิดโดยไม่รู้ | `strategy.py` | เพิ่ม explicit `sopr_valid` NaN guard ก่อนเปรียบเทียบ SOPR < 0.95 (behavior ไม่เปลี่ยน แต่ code ชัดเจนขึ้น) |

### ตรวจสอบแล้วแต่ไม่ต้องแก้ (deferred)

| # | ปัญหา | เหตุผล skip |
|---|--------|--------------|
| B22 | Code duplication (fallback chain x3) | `engine.py` | ✅ แก้แล้วใน Wave 7 — สร้าง `_resolve_onchain_metrics()` + `_sopr_proxy()` + `_lth_rp_proxy()` เรียกจาก 4 ที่ (run_daily, idempotency-skip, refresh_dashboard, run_demo) |
| B25 | CoinMetrics MVRV ไม่มี file cache | ใช้บ่อยไม่พอ (เฉพาะ embedded stale case) — trade-off ความเรียบง่าย vs optimization |

### Quality Score: 88/100
- Correctness: 27/30 | Completeness: 18/20 | Edge Cases: 13/15 | No Regressions: 13/15 | Code Quality: 9/10 | Documentation: 8/10

---

## 2026-08-22 (Wave 6) — Dashboard Deployment Reliability Fix

ใช้ team-dev skill 7-phase workflow ตรวจสอบปัญหา Dashboard ไม่แสดงข้อมูล DCA ทั้งที่บอทซื้อสำเร็จ พบว่า data pipeline ถูกต้อง แต่ GHA deployment pipeline มีช่องโหว่ แก้ไข 6 ปัญหา คะแนน quality 92/100

### Root Cause
Data pipeline (engine → trade_log → dashboard) ถูกต้อง ✓ แต่ GHA workflow มี 2 จุดที่ทำให้ deploy stale dashboard:
1. `git pull --rebase` conflict ไม่มี `git rebase --abort` → ทุก retry ล้มเหลว → working tree เสีย → dashboard gen อ่าน JSON เสีย → fail
2. `continue-on-error: true` บน dashboard gen step → ซ่อน error → job สำเร็จ → deploy stale HTML

### CRITICAL (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| G1 | Dashboard gen fail ซ่อนด้วย continue-on-error | `dca-bitkub.yml` L146-149, `dca-binance.yml` L55-58 | เอา `continue-on-error: true` ออก, เพิ่ม `id: gen_dash`, commit dashboard มี `if: always() && steps.gen_dash.outcome == 'success'` |

### HIGH (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| G2 | Rebase conflict ไม่ abort → retry ทั้งหมด fail | ทุก workflow files, ทุก commit steps | เพิ่ม `git rebase --abort 2>/dev/null || true` ก่อนแต่ละ retry |
| G3 | dashboard-trigger `|| true` ซ่อน refresh fail → save incomplete state | `dashboard-trigger.yml` L86 | เอา `|| true` ออก, เพิ่ม `id: handle_action`, dashboard gen มี `if: success() || steps.handle_action.outcome == 'skipped'` |

### MEDIUM (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| G6 | Dashboard commit fail → ไม่มี alert → deploy skip เงียบๆ | `dca-bitkub.yml` L173-188 | เพิ่ม "Alert on dashboard failure" step + Telegram notification |

### LOW (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| G7 | Email typo | `dca-bitkub.yml` L155 | `phoenix-bot@users.noreply.github.io` → `.github.com` |
| A4 | Stale dry-run entries ใน trade_log | `trade_log.json` | ลบ 2 dry-run entries (Aug 18) ที่เหลืออยู่ก่อน D3 clear fix |

### ปรับปรุงเพิ่มเติม
- แยก commit state และ commit dashboard เป็น steps ต่างหากใน `dca-binance.yml` (ป้องกัน dashboard fail บล็อก state push)
- เพิ่ม `id: gen_dash`, `id: commit_dash`, `id: bot_run` สำหรับ step outcome referencing
- ทุก deploy jobs เพิ่ม `if: success() || failure()` เพื่อ deploy ได้แม้ non-critical step fail
- dashboard-trigger "Commit & push" เปลี่ยนเป็น `if: always()` เพื่อ kill/resume ยัง push ได้แม้ dashboard gen fail

---

## 2026-08-22 (Wave 5) — Full System Bug Sweep (team-dev Skill)

ใช้ team-dev skill 7-phase workflow ส่ง sub-agents 4 ตัวตรวจสอบ DCA engine, dashboard, workflows, และ data pipeline พบบั๊กใหม่ 11 รายการ (B6-B16) แก้ไข 11 รายการ คะแนน quality 94/100

### MEDIUM (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| B6 | `_no_trade()` รีเซ็ต sell cooldown เป็น 0 | `strategy.py` L282-288, L129 | เดิม: ถ้า MVRV=NaN `_no_trade()` ตั้ง `new_cooldown:0` ทำลาย cooldown ที่กำลังนับ → เพิ่ม `cooldown` param, preserve ค่าเดิม |
| B7 | BG batch MVRV override ทำลายค่าที่ถูกต้อง | `engine.py` L466-476, L952-957 | เดิม: BG ส่ง MVRV≤0 → override ค่าจาก embedded history ด้วย NaN → เพิ่ม `bg_mvrv_val > 0` guard ก่อน override (ทั้ง run_daily + refresh_dashboard) |
| B9 | Freshness indicator timezone ผิด | `generate_dashboard.py` L480,1492-1504 | เดิม: ใช้ `datetime.now().strftime()` → browser parse เป็น local time → diff ผิด 7 ชม. → เปลี่ยนใช้ Unix timestamp |
| B11 | JS comma operator ทำลาย kill confirm dialog | `generate_dashboard.py` L1419-1420 | เดิม: `fmt_num()` output มี comma ฝังใน JS ไม่ quote → JS ตีความ comma เป็น operator → ครอบด้วย single quote |
| B12 | `load_trade_log()` ไม่ handle corrupted JSON | `state.py` L202-226 | เดิม: `json.load()` ไม่มี try/except → corrupted file = crash → เพิ่ม JSONDecodeError handling + backup (เทียบเท่า load_state) |
| B14 | dashboard-trigger.yml kill ขาด `import os` | `dashboard-trigger.yml` L76 | เดิม: `os.environ.get(...)` ใช้โดยไม่ import → NameError → L2 kill switch ใช้งานไม่ได้ |
| B15 | Telegram failure alert ขาด env block | `dca-bitkub.yml` L108-113 | เดิม: step "Alert on failure" ไม่มี `env:` block → secrets ไม่ส่งถึง → alert ถูก skip เงียบๆ |

### LOW (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| B8 | D3 transition ไม่รีเซ็ต `total_reserve_injected` | `engine.py` L239-242 | เพิ่ม field ใน D3 reset tuple — ป้องกัน dashboard แสดงค่าผิดจาก dry-run |
| B10 | DCA card inline grid ไม่ responsive | `generate_dashboard.py` L311,341,755,757 | ย้าย inline `grid-template-columns:1fr 1fr 1fr` เป็น CSS class `.dca-grid` + `@media` responsive rule |
| B13 | Escape key toggle help พร้อมกับปิด confirm | `generate_dashboard.py` L1476-1484 | เปลี่ยนเป็น: ถ้า confirm เปิดอยู่ → ปิด confirm; ถ้าไม่ → toggle help |
| B16 | Binance dashboard ขาด `if: always()` | `dca-binance.yml` L54-57 | เพิ่ม `if: always()` + `continue-on-error: true` ให้ตรง pattern ของ Bitkub workflow |

### ตรวจสอบแล้วแต่ไม่ต้องแก้ (Latent)

| # | ปัญหา | เหตุผล skip |
|---|--------|--------------|
| B17 | deploy-pages ลอง build โดยไม่มี dependencies | ทุก caller ส่ง `skip_build: true` — จะแก้เมื่อมี caller ใช้ `skip_build: false` |

### Quality Score: 94/100
- Correctness: 28/30 | Completeness: 19/20 | Edge Cases: 14/15 | No Regressions: 15/15 | Code Quality: 9/10 | Documentation: 9/10

---

## 2026-08-22 (Wave 4) — Dashboard Data Pipeline Integrity Fix

สร้าง subagents 3 ตัวตรวจสอบ data pipeline ทั้งหมด (state.json → trade_log.json → generate_dashboard.py → deploy) หลังจาก dashboard แสดงข้อมูล 0 ทั้งหมด พบว่า D1 filter ทำงานถูก (ไม่ใช่แสดง dry-run เก่า) แต่มีบั๊กที่เกี่ยวข้องกับการบันทึก/แสดงข้อมูล

### HIGH (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| B1 | D3 reset ไม่ล้าง trade_log.json | `engine.py` L252-258, `state.py` L266-290 | D3 transition (dry-run→live) reset state.json แต่ไม่ล้าง trade_log.json → เพิ่ม `clear_trade_log()` ใน state.py (atomic write + LOCK_EX) และเรียกใน D3 block |
| B2 | Timeout buy ไม่บันทึก trade log | `engine.py` L636-656 | เดิม: timeout → `trade_succeeded=True` แต่ `decision['buy_amount']=0` → trade log ไม่บันทึก, counter ไม่เพิ่ม, ข้อมูลสูญหาย → แก้: ประมาณ `buy_btc_got`, `buy_cost_actual`, `buy_fee` จาก amount ที่ส่งไป exchange จริง (รวมกรณี insufficient cash ปรับ amount แล้ว) |

### MEDIUM (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| B3 | Dashboard แสดง Exchange: BINANCE ผิด | `generate_dashboard.py` L376-381 | Config section ใช้ `cfg.EXCHANGE` (default `'binance'` จาก env var) แทนข้อมูลจาก state.json → เปลี่ยนใช้ `exchange_name` จาก state (fallback เป็น cfg) และ `currency` จาก state |

### LOW (แก้ไขแล้ว)

| # | ปัญหา | ไฟล์ | รายละเอียด |
|---|--------|------|----------|
| B5 | total_invested ใช้ decision amount | `state.py` L151-183, `engine.py` L738 | เดิม: `total_invested += decision['buy_amount']` (ยอดที่ตั้งใจ) ไม่ใช่ยอดจริงจาก exchange → เพิ่ม param `actual_buy_cost` ใช้ `buy_cost_actual` จาก exchange response |

### สรุปสถานะ dashboard
- Dashboard ตอนนี้แสดง **ค่า 0 ทั้งหมด** (ไม่ใช่ข้อมูล dry-run เก่า) เพราะ D1 filter ทำงานถูก + ยังไม่มี live trade สำเร็จหลัง D3 reset
- หลัง live buy ครั้งแรกสำเร็จ: state.json จะอัปเดต (balances, indicators, exchange_name) + trade_log จะมี entry `dry_run: false` + dashboard จะแสดงข้อมูลจริง
- Config section จะแสดง **BITKUB / THB** ถูกต้อง (จาก state.json) แทน BINANCE/USDT

---

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
