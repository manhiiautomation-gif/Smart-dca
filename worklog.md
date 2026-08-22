# Phoenix DCA Bot — Work Log

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
- U1 (Mobile): เพิ่ม @media rules ลด padding/gap/font บนมือถือ
- U2 (Empty State): เพิ่ม Onboarding Hero แทน sea of zeros
- U3 (DRY RUN): เพิ่ม Banner ใหญ่ชัดเจน แทน tag เล็กๆ
- U4 (Labels): L1/L2 Kill → สวิตช์หยุดฉุกเฉิน, MVRV Z → Z-Score, STH-SOPR → SOPR (โปรดักซี่), Run Count → จำนวนรัน (ตลอดกาล)
- U5 (Max DD 0%): เปลี่ยนสีแดง → conditional (0%=dim, <5%=yellow, >5%=red)
- U6 (BTC decimals): เพิ่ม fmt_btc() — smart decimal (0→"0 BTC", >=1→4ตำแหน่ง, >=0.001→6ตำแหน่ง)
- U7 (Chart empty): เพิ่มไอคอน + ข้อความแนะนำ แทนข้อความเดี่ยวๆ
- U8 (Portfolio Value): เพิ่ม .hero class (1.8rem) + num-mono font + currency ย่อ
- U9 (Freshness): เพิ่ม JS แสดง "อัปเดต X นาทีก่อน" อัปเดตทุก 30 วินาที
- U10 (Config): ทำเป็น collapsible accordion (default ปิด)
- U11 (Next Run): เพิ่ม "รันถัดไป: 00:10 น." ใน System Status + Onboarding
- U12 (Contrast): ปรับ --text-dim จาก #8b949e → #9da5ae
- ผลลัพธ์: dashboard/dist/index.html (51,206 bytes)

---
Task ID: 1
Agent: main
Task: Optimize BGeometrics API usage - batch fetch, daily guard, fallback for all indicators

Work Log:
- Analyzed current API usage: 3 separate get_*() calls per bot run, each loading cache independently
- Added get_all_metrics_today() to bg_metrics.py with in-memory daily snapshot guard
- First run/day: max 3 API calls (1 per metric, shared cache); subsequent runs: 0 API calls
- Fixed daily guard to correctly update sopr_source when reusing snapshot
- Fixed no-token mode to still read from disk cache
- Updated engine.py live section: replaced 3 separate calls with 1 batch call
- Updated engine.py demo section: same batch pattern
- Added LTH Realized Price fallback: realized_price * 1.15
- Added rp_source, lth_source to state for dashboard visibility
- Verified with import test and batch test
- Committed and pushed to main

Stage Summary:
- bg_metrics.py: new get_all_metrics_today() + invalidate_daily_snapshot()
- engine.py: both live and demo sections use batch fetch + full fallback chain
- API usage reduced from 3 calls/run to 3 calls/day (first run) then 0 calls/day
- All 5 on-chain indicators now have fallback calculation chains
