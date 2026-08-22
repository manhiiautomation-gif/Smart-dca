# Version Changelog

## v1.1.0 - 2025-01-15 (Dashboard Fix Wave)

### ปัญหาที่แก้ไข

| Bug ID | Severity | File | Description |
|--------|----------|------|-------------|
| BUG-1 | CRITICAL | scripts/generate_dashboard.py | สถิติรวม (Total Trades, PnL ฯลฯ) นับรวม dry_run trades ด้วย ทำให้แสดงข้อมูลเก่าจากการทดสอบ dry run แทนที่จะแสดงค่าปัจจุบันจาก state.json |
| BUG-2 | HIGH | scripts/generate_dashboard.py | Last Exchange และ Last Trade Time ดึงจาก trade_log.json (มีข้อมูล dry_run เก่า) แทนที่จะดึงจาก state.json |
| BUG-3 | MEDIUM | scripts/generate_dashboard.py | ตาราง Trade Log ไม่มีตัวบ่งชี้ว่า entry ใดเป็น dry run ทำให้สับสน |
| BUG-4 | LOW | scripts/generate_dashboard.py | ไม่มีการแสดงวันที่ข้อมูลอัปเดตล่าสุด ทำให้ไม่รู้ว่า dashboard เป็นข้อมูลเมื่อไหร่ |
| R1 | MEDIUM | scripts/generate_dashboard.py | load_json คืนค่า default={} สำหรับ trade_log ซึ่ง reversed({}) จะ error (พบจาก Code Review) |

### สรุปสถานะปัจจุบัน
- Dashboard อ่านค่าสถิติรวมจาก `state.json` ซึ่งเป็น single source of truth สำหรับ real trades
- ตาราง trade log แสดงทุก entry พร้อมตัวบ่งชี้ DRY RUN / LIVE
- มี Data as of footer แสดงเวลาอัปเดตล่าสุด
- จัดการ edge cases (ไฟล์หาย, JSON เสีย) ด้วย try/except

### Quality Score: 92/100 (ผ่านเกณฑ์ 80)