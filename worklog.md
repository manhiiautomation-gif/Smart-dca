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

---
Task ID: 2-a (re-investigation)
Agent: Data Flow Agent
Task: Investigate data pipeline for dashboard not showing DCA data after live buy

Work Log:
- Read worklog.md for prior investigation context (B1-B5 already fixed)
- Traced engine.py trade logging: lines 710-719 (buy append), 721-728 (sell append), 237-259 (D3 transition)
- Traced state.py: load_trade_log() (lines 204-228), append_trade_log() (lines 231-282), clear_trade_log() (lines 285-310)
- Traced generate_dashboard.py: data flow (lines 87-172), D1 filter (line 98), is_empty (line 221), DCA card (lines 267-374), trade rows (lines 645-665), HTML rendering (lines 1098-1242)
- Inspected actual trade_log.json: 3 entries (2 dry-run from Aug 18, 1 live from Aug 22 with dry_run: false)
- Inspected actual state.json: last_dry_run=false, last_decision={buy_amount:200, multiplier:2.0}, buy_count=1
- Traced main.py: path config (line 179 absolute), post-run flow (lines 294-318 finally block)
- Traced GHA workflow: dca-bitkub.yml steps 69-168, deploy-pages.yml, dashboard-trigger.yml
- Verified no shadowing of load_trade_log in generate_dashboard.py
- Verified config.py path defaults and env var handling
- Analyzed all 8 specific questions + additional edge cases

Stage Summary:
- Q1 (dry_run:false write): CORRECT — engine.py L717 passes dry_run=False, state.py L253-254 merges via record.update(extra), json.dump serializes to false. Confirmed by trade_log.json entry 3.
- Q2 (D1 filter is False): CORRECT — JSON false→Python False, False is False==True. Entries with dry_run:false pass, dry_run:true and missing field are excluded.
- Q3 (D3 clear then append): CORRECT ORDER — clear (L256) before buy, append (L713) after buy. Current trade_log.json still has 2 stale dry-run entries because D3 clear was added AFTER first live run (B1 fix). D1 filter compensates. LOW: one-time manual cleanup recommended.
- Q4 (path mismatch): NO BUG — main.py L179 uses os.path.join(PROJECT_ROOT, 'trade_log.json') (absolute), generate_dashboard.py defaults to 'trade_log.json' (relative from CWD). In GHA both resolve to $GITHUB_WORKSPACE/trade_log.json.
- Q5 (timing: dashboard after trade_log update): CORRECT ORDER — bot run → commit state → generate dashboard (all same job, sequential steps). But: if Commit dashboard step fails to push, deploy-pages.yml checks out stale main.
- Q6 (is_empty check): CORRECT — L221: (buy_count==0 and sell_count==0 and invested==0). With live buy, is_empty=False. NOT a bug.
- Q7 (last_decision through D3): CORRECT — D3 does NOT reset last_decision. It is OVERWRITTEN every run at L808. After D3+live buy, state.json shows correct live decision.
- Q8 (CRITICAL path question): NOT A BUG — CWD in GHA = PROJECT_ROOT, so relative and absolute paths resolve to same file.

ADDITIONAL FINDINGS:
- A1 (MEDIUM): deploy-pages.yml does actions/checkout ref:main. If Commit dashboard step (dca-bitkub.yml L151) fails to push (git conflict/network), deploy deploys stale dashboard. No if:always() on deploy job, so if dca job fails, deploy is skipped entirely → dashboard stays stale until next successful run.
- A2 (LOW): Commit step git stash/rebase retry loop has no git rebase --abort before retry. A rebase conflict leaves repo in broken state, all 3 retries fail.
- A3 (LOW): dashboard-trigger.yml uses concurrency group dashboard-action (separate from dca-any-exchange). Update action and DCA run can run concurrently on separate runners, causing git push conflicts.
- A4 (LOW): trade_log.json contains 2 stale dry-run entries (Aug 18) that predate D3 clear fix. Harmless (D1 filter excludes them) but should be cleaned.

ROOT CAUSE ASSESSMENT:
- The in-code data pipeline (write→read→filter→display) is CORRECT. No code bug prevents live trade data from appearing on the dashboard.
- The original bug was most likely caused by the MISSING D1 filter + MISSING D3 clear (both fixed in B1). Before B1: dashboard showed all trades including dry-run, OR if trade_log was empty before first live run, dashboard showed empty state.
- Residual risk: deployment failures (A1) can prevent the updated dashboard from reaching GitHub Pages even when the data pipeline works correctly.

---
Task ID: 2-b
Agent: GHA Workflow Agent
Task: Investigate GHA workflows for dashboard deployment issues

Work Log:
- Read worklog.md for prior investigation context (B1-B5 fixed, A1-A4 noted)
- Read all 4 workflow files: dca-bitkub.yml, deploy-pages.yml, dashboard-trigger.yml, dca-binance.yml
- Traced generate_dashboard.py imports and dependencies (config.py → requests, state.py → fcntl, kill_switch.py)
- Verified EXCHANGE env var is NOT required for generate_dashboard.py (uses state.json last_exchange_name with cfg.EXCHANGE fallback)
- Verified config.py imports requests (potential issue for deploy-pages.yml skip_build=false path)
- Traced full execution flow: bot run → commit state → generate dashboard → commit dashboard → deploy
- Analyzed git stash push -k flow in both commit steps
- Analyzed concurrency group interactions between workflows
- Analyzed dashboard-trigger.yml "update" action with || true error suppression
- Verified fmt_btc/fmt_num handle edge cases (7.957e-05 BTC renders correctly)
- Verified trade_log.json D1 filter: dry_run:false entries pass, dry_run:true excluded
- Verified is_empty logic: buy_count=1, invested=200 → is_empty=False
- Checked rebase conflict cascading failure scenario
- Checked cross-workflow race condition (dashboard-action vs dca-any-exchange concurrency groups)

Stage Summary:
- G1 (CRITICAL): Silent dashboard generation failure → deploy succeeds with stale HTML
  - File: dca-bitkub.yml L146-149
  - `continue-on-error: true` swallows ANY generate_dashboard.py failure
  - If dashboard isn't regenerated, "Commit dashboard" (L151) sees no diff → exits 0 → job SUCCEEDS
  - deploy job RUNS but deploys STALE dashboard from remote main
  - Most likely root cause of the user's reported bug
  - Fix: Add explicit error check after generate_dashboard.py, set output variable, gate deploy on successful generation

- G2 (HIGH): Rebase conflict in "Commit state" step corrupts working tree → cascading dashboard failure
  - File: dca-bitkub.yml L125-144
  - If `git pull --rebase` (L137) conflicts, no `git rebase --abort` before retry
  - All 3 retries fail, repo left in broken rebase state
  - Working tree files (state.json, trade_log.json) may contain <<<< conflict markers
  - `git stash pop` (L143) may fail (hidden by || true)
  - "Generate dashboard" (L146) reads corrupted JSON → load_state/load_trade_log return empty defaults → empty dashboard
  - Fix: Add `git rebase --abort 2>/dev/null || true` at start of each retry iteration

- G3 (HIGH): dashboard-trigger.yml "update" with || true can save INCOMPLETE state, then generate wrong dashboard
  - File: dashboard-trigger.yml L86
  - `python live_bot/main.py $FLAGS || true` — if refresh_dashboard() crashes mid-way, main.py's finally block (L311-317) saves PARTIALLY UPDATED bot_state
  - This can overwrite valid state.json with data missing last_price, last_indicators, etc.
  - Dashboard generation (L89-90) then runs on incomplete state → missing/wrong display data
  - Fix: Remove || true, add proper error handling, or skip dashboard generation if refresh failed

- G4 (MEDIUM): Cross-workflow race condition — dashboard-trigger.yml can OVERWRITE fresh dashboard
  - File: dashboard-trigger.yml concurrency group `dashboard-action` vs dca-bitkub.yml `dca-any-exchange`
  - DIFFERENT concurrency groups → both CAN run simultaneously on separate runners
  - Scenario: user clicks "Update" right after DCA run completes
    1. dca-bitkub: checkout, bot, commit, generate dashboard, push dashboard, deploy
    2. dashboard-trigger: checkout (may get pre-push main), refresh (may fail || true), generate dashboard from stale/old state, push, deploy
    3. dashboard-trigger's deploy OVERWRITES dca-bitkub's fresh dashboard
  - Fix: Unify concurrency groups, or have dashboard-trigger skip deploy if a DCA workflow ran recently

- G5 (MEDIUM): deploy-pages.yml `skip_build: false` path would crash (latent bug)
  - File: deploy-pages.yml L39-41
  - If skip_build=false, runs `python scripts/generate_dashboard.py` WITHOUT `pip install -r live_bot/requirements.txt`
  - config.py imports `requests` → ImportError → dashboard not generated → empty/stale deploy
  - Currently not triggered (all callers pass skip_build=true), but a trap for future changes
  - Fix: Add `pip install -r live_bot/requirements.txt` before the conditional generate step, or remove the skip_build=false path entirely

- G6 (MEDIUM): "Commit dashboard" step failure silently prevents deploy
  - File: dca-bitkub.yml L151-168
  - Step has `if: always()` but NO `continue-on-error: true`
  - If it fails (git conflict, network), dca job FAILS → deploy SKIPPED
  - No Telegram alert for this failure (L108 only alerts on bot step failure)
  - Dashboard stays stale silently until next successful run
  - Fix: Add `continue-on-error: true` to prevent job failure, AND add Telegram alert step

- G7 (LOW): Email typo in "Commit dashboard" step
  - File: dca-bitkub.yml L155
  - `phoenix-bot@users.noreply.github.io` should be `phoenix-bot@users.noreply.github.com`
  - Inconsistent with L128 and dca-binance.yml L62
  - Fix: Change .github.io → .github.com

- G8 (LOW): `git stash push -k` in "Commit dashboard" step is unnecessary and risky
  - File: dca-bitkub.yml L158
  - Only dashboard/dist/index.html was staged (L156); no other files should be unstaged
  - If a previous failed stash pop left dangling stashes, this creates nested stashes
  - Fix: Remove the git stash push -k / git stash pop from the "Commit dashboard" step

ANSWERS TO SPECIFIC QUESTIONS:

Q1 (generate_dashboard.py failure causes): EXCHANGE env var is NOT needed (uses state.json). Possible failures: (a) corrupted JSON from rebase conflict (G2), (b) template rendering error on unexpected data, (c) missing directory (handled by makedirs). Most likely cause in practice: corrupted JSON from G2 cascading failure.

Q2 (deploy job checks out latest?): YES — deploy-pages.yml L35-37 does `actions/checkout@v4 ref:main`. Since deploy runs AFTER dca job completes (needs: dca), and the dca job's push returned 200, the deploy should see the latest commit. HOWEVER, if "Commit dashboard" (L151) failed to push, main still has the OLD dashboard HTML, and deploy deploys stale content.

Q3 (deploy-pages.yml stale checkout): LOW RISK — GitHub API provides read-after-write consistency. Once push returns 200, subsequent checkout sees the commit. The prior investigation's A1 finding about this was LOW severity.

Q4 (race condition between bitkub/binance): Both share `concurrency: group: dca-any-exchange` with `cancel-in-progress: false`. They CANNOT run simultaneously — one queues. No dashboard conflict between these two. The REAL race is with dashboard-trigger.yml (G4) which has a SEPARATE concurrency group.

Q5 (git stash push -k affecting dashboard generation): In the NORMAL success path, NO — stash pop restores all files before dashboard generation. In the CONFLICT path (G2), YES — rebase leaves repo broken, stash pop fails, working tree has conflict markers, dashboard reads corrupted JSON.

Q6 (scenario analysis):
  a. Commit step fails (data not pushed): deploy skipped (G6) — dashboard stays stale
  b. Dashboard generation fails (continue-on-error): job succeeds, deploy runs, deploys STALE dashboard (G1) — MOST LIKELY ROOT CAUSE
  c. Deploy gets stale data: unlikely due to read-after-write consistency (Q3)

Q7 (dashboard-trigger.yml || true): YES — if refresh_dashboard fails, state.json may be partially updated by finally block. Dashboard generation runs on incomplete state. Combined with G4 race condition, this can overwrite a valid dashboard with one showing stale/incomplete data.

MOST PROBABLE ROOT CAUSE FOR USER'S BUG:
The most likely scenario is G1: generate_dashboard.py failed silently (continue-on-error: true), the "Commit dashboard" step found no changes to commit, the dca job succeeded (green check), deploy ran and deployed the PREVIOUSLY committed dashboard HTML which didn't include the new trade data. The dashboard generation could have failed due to G2 (corrupted JSON from rebase conflict) or any transient error. Since the error was silenced, there's no trace in the GHA logs unless you click into the step and see the red warning icon.

---
Task ID: 5
Agent: Code Reviewer
Task: Review GHA workflow fixes for dashboard deployment reliability

Work Log:
- Read worklog.md (Tasks 1, 2-a, 2-b, 2-c, 8, U1-U12) for full context on prior findings
- Read all 3 modified workflow files: dca-bitkub.yml (202 lines), dca-binance.yml (87 lines), dashboard-trigger.yml (120 lines)
- Read deploy-pages.yml (reusable workflow called by all 3)
- Read trade_log.json (1 live entry, 2 stale dry-run entries removed per A4)
- Verified GHA expression syntax for all new conditions
- Traced execution paths for each workflow through success, failure, and edge-case scenarios
- Cross-compared patterns across all 3 workflows for consistency
- Verified concurrency groups unchanged
- Verified deploy resilience (if: success() || failure()) on all deploy jobs
- Checked retry loop logic with git rebase --abort addition

Stage Summary:

VERDICT: Changes are largely correct and address the critical issues. Two regressions found (one MEDIUM-HIGH, one LOW), plus cross-workflow consistency gaps.

=== ISSUES FOUND ===

**R1 (MEDIUM-HIGH) — REGRESSION: dca-binance.yml combined commit gated on gen_dash success**
- File: dca-binance.yml line 61
- Condition: `if: always() && steps.gen_dash.outcome == 'success'`
- Problem: The "Commit updated files" step commits BOTH state files (state.json, trade_log.json, _mvrv_history.py) AND dashboard/dist/index.html in a single step. If generate_dashboard.py fails for any reason (e.g., template bug, import error unrelated to state data), the entire commit is skipped and state files are NOT pushed. In dca-bitkub.yml this isn't an issue because state commit and dashboard commit are separate steps. In dca-binance.yml, a dashboard generation bug can prevent critical state data from being persisted.
- Suggested fix: Split into two steps (matching dca-bitkub.yml pattern), OR change condition to `if: always()` (the `git diff --staged --quiet` check handles the no-changes case safely).

**R2 (LOW-MEDIUM) — REGRESSION: dashboard-trigger.yml commit skipped on dashboard gen failure**
- File: dashboard-trigger.yml lines 94-107
- The "Commit & push" step has NO explicit `if:` condition (defaults to `if: success()`). If "Generate dashboard" fails, this step is skipped entirely. For kill/resume actions, only kill_switch.json changes — a dashboard gen failure (e.g., corrupted state.json from a prior bad run) prevents the kill/resume activation from being pushed. The bot could continue trading despite a kill switch being activated on the dashboard.
- Suggested fix: Add `if: always()` and move the `git rebase --abort` + commit+push for state files (excluding dashboard) to a separate unconditional step, or at minimum add `if: always() || steps.handle_action.outcome == 'success'`.

**R3 (MEDIUM) — INCONSISTENCY: dca-binance.yml lacks alert steps**
- dca-bitkub.yml has: "Alert on failure" (bot) + "Alert on dashboard failure" (dashboard)
- dca-binance.yml has: NO alert steps at all
- If Binance workflow fails, there is zero notification. Since Binance is workflow_dispatch only, the user wouldn't know without checking GHA manually.
- Not a regression (alerts were never there), but inconsistent with the pattern established in bitkub.

**R4 (LOW) — INCONSISTENCY: dashboard-trigger.yml lacks gen_dash id and alerts**
- dashboard-trigger.yml "Generate dashboard" step (line 90) has no `id: gen_dash`, unlike the other two workflows. Not functionally broken (the ID isn't referenced by subsequent steps in this file), but breaks the consistent pattern.
- No failure alert steps for any failure scenario.

**R5 (TRIVIAL) — Dead code in alert step**
- File: dca-bitkub.yml line 185
- `gen = os.environ.get('GITHUB_STEP_SUMMARY', '')` is assigned but never used in the message.

=== VERIFIED CORRECT ===

- **G1 (CRITICAL fix)**: Removing `continue-on-error: true` + adding `id: gen_dash` + gating commit on success is CORRECT. GHA expression `if: always() && steps.gen_dash.outcome == 'success'` is valid syntax. The `always()` ensures the step runs even if bot_run fails; the outcome check prevents committing a non-existent/stale dashboard.

- **G2 (HIGH fix)**: `git rebase --abort 2>/dev/null || true` at the start of all retry loops (dca-bitkub L137/L164, dca-binance L70, dashboard-trigger L104) is CORRECT. Handles the no-ongoing-rebase case gracefully. Fixes the cascading failure from corrupted rebase state.

- **G3 (HIGH fix)**: Removing `|| true` from `python live_bot/main.py $FLAGS` in dashboard-trigger.yml is CORRECT. If the update action fails, we should NOT generate a dashboard from potentially incomplete state. The condition `if: success() || steps.handle_action.outcome == 'skipped'` correctly handles: (a) action succeeded → gen runs, (b) action failed → gen skipped, (c) prior step failed (handle_action skipped) → gen still attempts from existing files. Kill and resume actions are unaffected since they don't modify state.json.

- **G6 (MEDIUM fix)**: "Alert on dashboard failure" with `if: always() && (steps.gen_dash.outcome == 'failure' || steps.commit_dash.outcome == 'failure')` is CORRECT. Fires for either dashboard gen or commit failure. Does not double-fire with the bot alert (different conditions).

- **G7 (LOW fix)**: Email typo corrected to `phoenix-bot@users.noreply.github.com` in all files. Consistent.

- **Deploy resilience**: `if: success() || failure()` on all deploy jobs is CORRECT. Ensures dashboard deploys even when the dca/action job fails. Deploy will use the last committed HTML (skip_build: true), which is acceptable since the alert step notifies the user of staleness.

- **Removed git stash push -k**: Correct — only dashboard/dist/index.html is staged, no unstaged changes exist.

- **Refined bot alert**: `if: failure() && steps.bot_run.outcome == 'failure'` is CORRECT — only fires for actual bot failures, not dashboard issues.

- **A4 (trade_log cleanup)**: Correct — 2 stale dry-run entries removed, 1 live entry preserved.

- **Concurrency groups**: Unchanged. `dca-any-exchange` (bitkub+binance) and `dashboard-action` (trigger) remain separate. Cross-workflow race condition (G4 from investigation) is NOT addressed but was not in scope.

=== PRE-EXISTING ISSUES (not regressions, not fixed) ===

- **G4 (MEDIUM, unfixed)**: Cross-workflow race between dashboard-trigger and dca workflows (separate concurrency groups) can still overwrite fresh dashboard.
- **G5 (MEDIUM, unfixed)**: deploy-pages.yml `skip_build: false` path would crash (missing pip install).
- **dca-bitkub retry loop**: If `git commit` succeeds but `git pull --rebase` fails on attempt 1, the committed changes persist locally. Attempt 2's `git commit` fails (nothing to commit), chain breaks, all 3 retries exhaust. Changes committed locally but never pushed. The post-loop `git stash pop` runs but doesn't help. State files are lost for that run.

=== RECOMMENDATION ===
Fix R1 before merging (split dca-binance.yml commit or relax condition). R2 is low-probability but worth addressing for kill switch reliability. R3-R5 are consistency improvements that can be deferred.
