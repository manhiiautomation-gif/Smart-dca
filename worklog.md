# Phoenix DCA Bot — Work Log

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
