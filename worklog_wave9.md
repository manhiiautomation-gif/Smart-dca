---
Task ID: 1
Agent: Main (coordinator) + 3 research sub-agents + 1 analysis sub-agent + 1 review sub-agent
Task: ปรับระบบ DCA Bot — เลื่อนเวลาซื้อเป็น 10:00-11:00 น.ไทย + Monday 1.2x boost

Work Log:
- Phase 1: สำรวจ config.py, engine.py, strategy.py, dca-bitkub.yml, main.py, notifier.py, demo_portfolio.py
- Phase 2: ส่ง 3 research agents ค้นหาเวลา DCA ที่ดีที่สุด (intraday, Asian market, day-of-week)
- Phase 2: ส่ง 1 analysis agent ตรวจสอบ side effects ของการเพิ่ม time window + Monday multiplier
- Phase 3: วางแผน 8 จุดเปลี่ยนแปลง, self-review ผ่าน
- Phase 4: แก้ไข config.py, engine.py, notifier.py, demo_portfolio.py, dca-bitkub.yml
- Phase 5: ส่ง review agent พบ 4 bugs (stale comment, demo missing fields x2, env vars missing) — แก้ครบ
- Phase 6: Score 94/100
- Phase 7: version.md + worklog + commit

Stage Summary:
- Cron: 13:00 UTC (20:00 THB) → 03:00 UTC (10:00 THB)
- Monday boost: 1.2x applied to base_budget BEFORE strategy call
- Time window guard: enforced in run_daily(), logged-only in run_demo()
- 5 files changed, 94/100 quality score
