# Phoenix DCA Bot — Work Log

---
Task ID: 2-b
Agent: Explore
Task: Investigate existing dashboard implementation for BTC Daily Briefing Dashboard

Work Log:
- Read worklog.md (existing entries for Wave-9/10/11/12)
- Read scripts/generate_dashboard.py (1820 lines) — full dashboard generator
- Checked /download/ — no dashboard HTML files (only CSV/PNG/JSON data files)
- Checked indicator_history.json — file does NOT exist locally (created only on GitHub Actions runs)
- Read trade_log.json — 4 live buy trades (Aug 22-26, 2026), Bitkub THB, no sells
- Read .github/workflows/ — 9 workflows: dca-bitkub, dca-binance, dca-bot, dca-demo, dca-test, dashboard-trigger, dashboard-manual, deploy-pages, heartbeat
- Read PROJECT_CONTEXT.md — full architecture overview
- Read version.md — latest Wave 11 (Phase 2 Data Integrity), quality 95/100
- Read dashboard/netlify.toml + netlify/functions/trigger.js — Netlify config exists but deployment is GitHub Pages
- Read live_bot/state.py — found indicator_history schema definition
- Examined dashboard/dist/index.html — 61,442 bytes, 1138 lines

Stage Summary:

## EXISTING DASHBOARD ANALYSIS

### 1. GENERATOR: scripts/generate_dashboard.py (1820 lines)

**How it works:**
- Loads: state.json, trade_log.json (filtered to dry_run=False only), kill_switch.json, indicator_history.json
- Computes: portfolio value, ROI, avg buy price, unrealized P&L, change since last trade, next action prediction, DCA multiplier estimate
- Outputs: single-file HTML to `dashboard/dist/index.html`
- Uses ECharts library (CDN) for all charts

### 2. HTML STRUCTURE & SECTIONS (top to bottom)

The dashboard is a **single-file static HTML** page with inline CSS + JS. Dark theme (#0d1117), max-width 960px, GitHub-dark aesthetic.

**Layout sections in order:**
1. **Modals/Overlays** (hidden by default): Toast container, Confirm overlay, Token Input Modal, Help Modal
2. **DRY RUN Banner** (conditional) — shown only when dry_run AND no real trades exist
3. **Header** — "Phoenix v5.1" + freshness badge + BOT ACTIVE/KILLED status badge
4. **Control Panel** — 3 buttons: Update (refresh), Kill/Resume Bot, Logs (link to GitHub Actions) + Token status
5. **Onboarding Hero** (conditional, empty state) — shown only when buy_count=0 and sell_count=0
6. **Row 1 (grid-2):**
   - **Portfolio Summary card:** Portfolio Value (hero), 24h/Since-last-trade change, BTC Holdings, Cash Balance, Avg Buy Price, Unrealized P&L, Avg Buy Size, ROI, Total Invested, Peak Value, Max Drawdown
   - **System Status card:** L1 Kill Switch, L2 Kill Switch, Exchange name, Last Run, Run Count, BTC Price, Next Run time
7. **DCA Status card:** "Last DCA" sub-card (multiplier, buy amount, base budget, reserve injection, sell amount) + "Next Round Estimate" sub-card (estimated multiplier, estimated buy amount, condition label)
8. **Row 2 (grid-2):**
   - **Indicators card:** MVRV (value + zone badge), MVRV %ile, MVRV Z-Score, RSI(14), MACD Hist, NUPL, SOPR (with source tag), SMA 200, SMA 365, Sell Path badge, Sell Score (with progress bar 0-100), Cooldown, ATH
   - **Sell Decision card:** "Next Expected Action" (color-coded: BUY EXPECTED/SELL WATCHING/HOLD/COOLDOWN), then Trade Statistics grid (Total Buys, Total Sells, BTC bought, BTC sold, Sell Proceeds, Total Reserve Used, Total Fees, Last Trade Date)
9. **Row 3: Portfolio Value Over Time** — ECharts line chart with buy/sell markers, colored by trade type
10. **Row 3b: Indicator History** — 5 ECharts mini-charts in 3-column grid: BTC Price (green), MVRV (blue, mark lines at 1.0 and 2.0), RSI (purple, mark lines at 30 and 70), SOPR (yellow, mark line at 1.0), NUPL (color by value, mark lines at 0 and 0.75)
11. **Row 4: Recent Trades** — Table with columns: Date, Type (BUY/SELL colored), Amount, BTC, Price, Fee. Shows last 10 trades, newest first
12. **Configuration card** (collapsible, purple border) — Exchange, Currency, USD/THB Rate, Daily DCA Budget, Max Buy/Trade, Max DCA Buys/Day, Reserve Floor, Max Reserve Inject, Boost Multiplier, Boost Price Ratio, Low Balance Alert, Buy Fee, Sell Fee. Has "วิธีตั้งค่า" (How to configure) button → Help Modal
13. **Footer** — "Phoenix v5.1 DCA Bot | Generated: {timestamp} | Auto-refresh: 5 min | GitHub link"

**JavaScript (inline, bottom):**
- Token management (localStorage, custom modal — no prompt/alert)
- GitHub Actions workflow dispatch (direct from browser, replaces Netlify serverless)
- Actions: doUpdate(), doKillSwitch() (with confirm dialog), toast notifications
- Freshness badge calculation (Unix timestamp-based, timezone-correct)
- ECharts: Portfolio chart (line + scatter markers) + 5 indicator history charts
- Auto-refresh: `<meta http-equiv="refresh" content="300">` (5 min)

### 3. INDICATOR_HISTORY.JSON SCHEMA

File does NOT exist locally (only created on GitHub Actions runs). Path: same dir as trade_log.json.

```json
[
  {
    "date": "2026-08-22 20:37",   // Thai TZ timestamp
    "price": 2513588.6,
    "mvrv": 1.85,
    "mvrv_source": "embedded",
    "mvrv_pct": 0.45,
    "mvrv_z": 0.82,
    "mvrv_z_source": "embedded",
    "rsi": 55.3,
    "macd_h": 120.5,
    "nupl": 0.46,
    "sopr": 1.02,
    "sopr_source": "bg",
    "sma_200": 2450000.0,
    "sma_365": 2300000.0,
    "macd_bear": false,
    "macd_declining": false,
    "rsi_divergence": false,
    "ath": 2650000.0,
    "sell_score": 15,
    "path_taken": "no-trade-mvrv-low",
    "in_bear": false,
    "cooldown": 0,
    "realized_price": 1350000.0,
    "lth_realized_price": 1550000.0,
    "lth_source": "bg",
    "rp_source": "bg",
    "refreshed": null,
    "killed": null,
    "kill_reason": null,
    "decision": {  // optional, only when trade occurred
      "buy_amount": 200.0,
      "sell_amount": 0.0,
      "multiplier": 2.0,
      ...
    }
  }
]
```
- Max 730 entries (~2 years daily data)
- Dashboard reads: date, price, mvrv, rsi, sopr, nupl (last 90 days for charts)
- Written by `append_indicator_history()` in state.py with fcntl LOCK_EX + atomic write

### 4. TRADE_LOG.JSON CONTENT

```json
[
  {"date":"2026-08-22 20:37","type":"buy","amount":200.0,"btc":7.957e-05,"price":2513588.6,"fee":0.0,"dry_run":false,"reserve":0.0},
  {"date":"2026-08-23 20:37","type":"buy","amount":200.0,"btc":7.912e-05,"price":2527820.13,"fee":0.0,"dry_run":false,"reserve":0.0},
  {"date":"2026-08-24 20:56","type":"buy","amount":200.0,"btc":7.795e-05,"price":2565875.22,"fee":0.0,"dry_run":false,"reserve":0.0},
  {"date":"2026-08-26 10:41","type":"buy","amount":200.0,"btc":7.743e-05,"price":2583089.58,"fee":0.0,"dry_run":false,"reserve":0.0}
]
```
- 4 live buys, all Bitkub THB, 200 THB each, no sells yet
- No `path`, `score` fields (only present on sell trades)
- Total invested: 800 THB, Total BTC: ~0.000315

### 5. NETLIFY / DEPLOYMENT CONFIG

**Dual deployment setup (Netlify exists but GitHub Pages is active):**

- **dashboard/netlify.toml** — Static site config, publish from `dist/`, serverless functions in `netlify/functions/`, security headers (X-Frame-Options: DENY, nosniff)
- **dashboard/netlify/functions/trigger.js** — Serverless function: rate-limited (5/min/IP), validates action (update/kill/resume), dispatches GitHub Actions workflow. Legacy — dashboard JS now calls GitHub API directly from browser
- **Actual deployment: GitHub Pages** via `deploy-pages.yml` (reusable workflow, skip_build=true)
- **dashboard-trigger.yml** — Manual dispatch from dashboard or GitHub UI. Handles: update (refresh-only run), kill (L2 kill switch), resume (deactivate L2). Commits state + dashboard + deploys

### 6. PROJECT VERSION & ARCHITECTURE

**Latest version:** Wave 11 (Phase 2 Data Integrity), Quality Score: 95/100
- 11 bug fixes in Wave 11 (data integrity: actual fill prices, historical FX rates, correct searchsorted side, NaN guards)
- 6 bug fixes in Wave 10 (stability: Binance fee from fills, app-level error check, MVRV NaN fallback, Bitkub retry)
- Code quality refactoring in Wave 12 (-122 lines, 0 regressions)

**Architecture:**
```
GitHub Actions (cron 03:00/03:20/03:40 UTC = 10:00/10:20/10:40 THB)
  → main.py (CLI)
    → engine.run_daily()
      ├── config.py          — env-var config, USD/THB rate
      ├── bitkub_client.py   — HMAC-SHA256 API, retry logic
      ├── binance_client.py  — Binance + 4 fallback price sources
      ├── indicators.py      — SMA, EMA, RSI, MACD (pure numpy)
      ├── strategy.py        — Phoenix v5.1 DCA + sell scoring
      ├── bg_metrics.py      — BGeometrics on-chain cache
      ├── mvrv_fetcher.py    — CoinMetrics + ahasignals web fallback
      ├── state.py           — JSON persistence, file locking
      ├── kill_switch.py     — L1 (env) + L2 (JSON) safety
      └── notifier.py        — Telegram alerts
    → generate_dashboard.py → dashboard/dist/index.html
    → git push → deploy-pages.yml → GitHub Pages
```

### 7. WHAT THE EXISTING DASHBOARD LOOKS LIKE

A **dark-themed single-page operations dashboard** (not a briefing/analysis report):
- **Purpose:** Real-time bot monitoring + remote control (kill/resume/refresh)
- **Focus:** Portfolio P&L, trade execution, system health, indicator values
- **Charts:** 1 portfolio value line chart + 5 indicator time-series mini-charts (Price, MVRV, RSI, SOPR, NUPL)
- **Language:** Thai (labels, status messages) + English (technical terms)
- **Data freshness:** Updated every bot run (3x/day), auto-refresh 5 min
- **Interactivity:** Kill/Resume bot, trigger refresh, set GitHub PAT token, collapsible config
- **NOT a briefing:** No market analysis, no narrative, no recommendations, no external news

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

---
Task ID: 2-a
Agent: Explore
Task: Investigate Phoenix bot data sources for BTC Daily Briefing Dashboard

Work Log:
- Read worklog.md (existing entries for Wave-10/11/12)
- Read live_bot/state.json — mapped full schema with 25+ fields
- Read live_bot/strategy.py — identified all indicators, sell scoring, reserve deployment
- Read live_bot/engine.py (1290 lines) — full pipeline: fetch→indicators→strategy→trade→notify
- Read live_bot/__init__.py — minimal (1-line comment)
- Read live_bot/config.py — env-var config, USD/THB rate fetching
- Read live_bot/indicators.py — pure numpy indicator calculations (SMA, EMA, RSI, MACD, divergence)
- Read live_bot/bg_metrics.py — BGeometrics API client with file cache (678 lines)
- Read live_bot/mvrv_fetcher.py — CoinMetrics + ahasignals web fallback for MVRV
- Read live_bot/binance_client.py — Binance + 4 fallback price/kline sources
- Read live_bot/bitkub_client.py — Bitkub API + Binance Vision for OHLCV
- Read live_bot/notifier.py — Telegram notification sender
- Read live_bot/state.py — state persistence, trade log, indicator history
- Read scripts/smart_dca/data_pipeline.py — backtest data pipeline
- Checked .github/workflows/ — 9 workflow files found
- Checked dashboard/ — Netlify-deployed static HTML + serverless trigger
- Checked trade_log.json, bg_cache.json, usd_thb_rate.json

Stage Summary:

## 1. STATE.JSON FULL SCHEMA
```json
{
  // Trading counters
  "cooldown": int,              // sell cooldown days remaining
  "total_invested": float,      // total THB/USDT spent on buys
  "adjusted_invested": float,   // cost basis after proportional sell reductions
  "total_sell_proceeds": float, // total received from sells (net-of-fee)
  "total_reserve_injected": float, // total reserve used for buy-the-dip
  "peak_value": float,          // all-time high portfolio value
  "max_drawdown": float,        // worst drawdown (0.0-1.0)
  "sell_count": int,
  "buy_count": int,
  "total_btc_bought": float,
  "total_btc_sold": float,
  "cumulative_fees": float,
  "run_count": int,
  "sell_proceeds_reserve": float, // cash from BTC sales available for dip buying

  // Timestamps
  "last_run_date": "YYYY-MM-DD",    // Thai TZ, idempotency guard
  "last_trade_date": "YYYY-MM-DD HH:MM",
  "last_sell_date": "YYYY-MM-DD HH:MM",

  // Last computed indicators (snapshot for dashboard)
  "last_indicators": {
    "price": float, "mvrv": float|null, "mvrv_source": str,
    "mvrv_pct": float|null, "mvrv_z": float|null, "mvrv_z_source": str,
    "rsi": float, "macd_h": float, "nupl": float,
    "sopr": float|null, "sopr_source": str,
    "sma_200": float|null, "sma_365": float|null,
    "macd_bear": bool, "macd_declining": bool, "rsi_divergence": bool,
    "ath": float, "sell_score": int, "path_taken": str,
    "in_bear": bool, "cooldown": int,
    "realized_price": float|null, "lth_realized_price": float|null,
    "lth_source": str, "rp_source": str,
    "refreshed": bool|null, "killed": bool|null, "kill_reason": str|null
  },

  // Portfolio state
  "last_btc_balance": float, "last_cash_balance": float,
  "last_portfolio_value": float, "last_price": float,
  "last_exchange_currency": "THB"|"USDT",
  "last_exchange_name": "BITKUB"|"BINANCE",
  "last_dry_run": bool,

  // Dry-run virtual balances
  "dry_run_cash": float|null, "dry_run_btc": float|null,
  "dry_run_sell_proceeds": float|null,

  // Misc
  "price_history": [],
  "last_decision": {
    "buy_amount": float, "sell_amount": float,
    "multiplier": float, "base_budget": float,
    "reserve_injection": float, "monday_boost": float,
    "in_dca_window": bool
  },
  "realized_price": float|null, "lth_realized_price": float|null,
  "lth_source": str|null, "rp_source": str|null
}
```

## 2. INDICATORS COMPUTED (14 total)

### Technical (from 500-day kline closes, pure numpy):
- **SMA-14**, **SMA-30**, **SMA-200**, **SMA-365** — Simple Moving Averages
- **RSI(14)** — Wilder smoothing, full series via compute_all_rsi()
- **MACD(12,26,9)** — line, signal, histogram + full histogram series
- **macd_cross_bear** — MACD crossed below signal on latest bar
- **macd_hist_declining** — histogram declining 4+ consecutive bars
- **rsi_divergence** — bearish RSI divergence (price near 40d high, RSI 8+ pts below its 40d high)
- **ATH** — all-time high from closes array

### On-Chain (external APIs with fallback chain):
- **MVRV** — BGeometrics cache → embedded history → CoinMetrics web → ahasignals scrape
- **MVRV Percentile** — 365-day rolling from embedded/BG history (searchsorted side='right')
- **MVRV Z-Score** — 365-day rolling (mean/std) from embedded/BG history
- **NUPL** — derived: 1 - 1/MVRV
- **Realized Price** — BGeometrics (BG) → derived: price/MVRV
- **LTH Realized Price** — BGeometrics (BG) → proxy: RP × dynamic multiplier (1.10-1.25x)
- **STH-SOPR** — BGeometrics (BG) → proxy: price/SMA14

## 3. SELL SCORING SYSTEM
Score 0-122+ possible, with triple-trigger gate:
- MVRV thresholds: +20 (>2.5), +15 (>3.0), +10 (>3.5), +10 (>4.0)
- RSI partial: +5 (>65), +5 (>70), +7 (>80)
- MVRV percentile: +12 (≥0.92), +8 (≥0.97)
- MVRV Z-score: +8 (>3.0), +7 (>4.0)
- MACD signals: +10 (bear cross), +5 (declining histogram)
- RSI divergence: +15
- LTH RP ratio: +8 (>3x), +5 (>3.5x), +5 (>4x)
- ATH proximity: +7 (>97% of ATH)
- NUPL: +5 (>0.70), +5 (>0.80)
- **BEAR BLOCK**: -200 if price < SMA-200 (kills sell in bear market)
- **Gate**: score zeroed unless Path A (MVRV>2.5), A-Ext (2.0-2.5 + pct/z≥48), or B (pct≥0.92 + MVRV>2.0)

## 4. EXTERNAL API ENDPOINTS

### Live Trading:
| API | Endpoint | Purpose | Auth |
|-----|----------|---------|------|
| **Binance** | `api.binance.com/api/v3/ticker/price` | BTC/USDT price | Public |
| **Binance** | `api.binance.com/api/v3/klines` | 500d daily klines | Public |
| **Binance** | `api.binance.com/api/v3/account` | Balances | HMAC-SHA256 |
| **Binance** | `api.binance.com/api/v3/order` | Market buy/sell | HMAC-SHA256 |
| **Bitkub** | `api.bitkub.com/api/v3/market/ticker` | BTC/THB price | Public |
| **Bitkub** | `api.bitkub.com/api/v3/market/wallet` | Balances | HMAC-SHA256 |
| **Bitkub** | `api.bitkub.com/api/v3/market/place-bid` | Market buy | HMAC-SHA256 |
| **Bitkub** | `api.bitkub.com/api/v3/market/place-ask` | Market sell | HMAC-SHA256 |

### On-Chain Data:
| API | Endpoint | Metrics | Auth |
|-----|----------|---------|------|
| **BGeometrics** | `api.bgeometrics.com/v1/{metric}?token=` | STH-SOPR, LTH-RP, RP, MVRV, MVRV-Z, aSOPR, LTH-SOPR, STH-RP | Bearer token (env) |
| **CoinMetrics** | `community-api.coinmetrics.io/v4/timeseries/asset-metrics` | CapMVRVCur (MVRV) | Free, no key |
| **ahasignals.com** | `ahasignals.com/current-bitcoin-mvrv-z-score` | MVRV (scrape) | None |

### Price Fallbacks (when Binance geo-blocked, 451):
| API | Endpoint | Purpose |
|-----|----------|---------|
| **Kraken** | `api.kraken.com/0/public/Ticker` | BTC/USD price |
| **Kraken** | `api.kraken.com/0/public/OHLC` | Daily klines |
| **KuCoin** | `api.kucoin.com/api/v1/market/orderbook/level1` | BTC/USDT price |
| **KuCoin** | `api.kucoin.com/api/v1/market/candles` | Daily klines |
| **CoinCap** | `api.coincap.io/v2/assets/bitcoin` | Price |
| **CoinCap** | `api.coincap.io/v2/assets/bitcoin/history` | Daily history |
| **CoinGecko** | `api.coingecko.com/api/v3/simple/price` | BTC/USD price |
| **CoinGecko** | `api.coingecko.com/api/v3/coins/bitcoin/market_chart` | Klines/OHLC |
| **Binance Vision** | `data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/` | Static CSV/ZIP klines (not geo-blocked) |

### FX Rate:
| API | Endpoint | Purpose |
|-----|----------|---------|
| **Bitkub** | `api.bitkub.com/api/v3/market/ticker?sym=USDT_THB` | Live USD/THB rate |
| **CoinGecko** | BTC/THB + BTC/USD market_chart ratio | Historical USD/THB monthly rates |

### Notifications:
| API | Endpoint | Purpose |
|-----|----------|---------|
| **Telegram** | `api.telegram.org/bot{token}/sendMessage` | Trade reports, alerts |

## 5. LOCAL DATA FILES / CACHES

| File | Format | Content | Updated |
|------|--------|---------|--------|
| `live_bot/state.json` | JSON | Full bot state (schema above) | Every run |
| `trade_log.json` | JSON array | Trade records: date, type, amount, btc, price, fee, dry_run, reserve, path, score | Every trade |
| `live_bot/bg_cache.json` | JSON | BGeometrics cache: {metrics: {sth_sopr: {date: val}, lth_realized_price, realized_price, mvrv, mvrv_zscore, ...}} | Incremental, immutable history |
| `live_bot/_mvrv_history.py` | Python array | Embedded MVRV daily values (~5 years) | Auto-updated from web |
| `live_bot/usd_thb_rate.json` | JSON | {rate, date, source} | Daily |
| `live_bot/indicator_history.json` | JSON array | Daily indicator snapshots (up to 730 entries = 2 years) | Every run + refresh |
| `kill_switch.json` | JSON | {active: bool, reason, activated_by, activated_at} | Manual |
| `dashboard/dist/index.html` | Static HTML | Full dashboard (single-file, ~97KB generator) | Every run |

## 6. EXISTING DASHBOARD / WEB INTERFACE
- **Dashboard**: Static HTML generated by `scripts/generate_dashboard.py` (97KB generator)
  - Reads: state.json, trade_log.json, kill_switch.json, indicator_history.json
  - Deployed to: Netlify (`dashboard/dist/index.html`)
  - Features: portfolio value, indicators, trade log, kill switch, refresh button
  - Serverless trigger: `dashboard/netlify/functions/trigger.js` (calls GitHub Actions workflow_dispatch)
  - Actions supported: update, kill, resume
  - Rate limited: 5 calls/min per IP
  - Protected by: Netlify password + GitHub PAT
- **GitHub Actions** runs the bot 3x/day (03:00, 03:20, 03:40 UTC = 10:00, 10:20, 10:40 THB)
  - Primary: `dca-bitkub.yml` (scheduled, live)
  - Secondary: `dca-bot.yml` (manual, Binance/Bitkub)
  - Dashboard: `dashboard-trigger.yml` (manual dispatch)
  - Demo: `dca-demo.yml`
  - Heartbeat: `heartbeat.yml`

## 7. KEY FINDINGS FOR BRIEFING DASHBOARD
- **All 14 indicators are already computed** and stored in `state.json` + `indicator_history.json`
- **state.json** is the single source of truth — updated every run with latest indicators, balances, decisions
- **indicator_history.json** has time-series data (up to 730 daily snapshots) — ideal for charts
- **bg_cache.json** has years of on-chain history (STH-SOPR from 2022, LTH-RP, RP, MVRV)
- **trade_log.json** has all trades with fill prices, fees, dry_run flag
- **Backtest pipeline** (data_pipeline.py) uses same sources: Binance + CoinMetrics + BGeometrics
- **No REST API exists** — all data is file-based (JSON), read by the static HTML dashboard
- **For a new briefing dashboard**, the data is ready: just read state.json + indicator_history.json + bg_cache.json + trade_log.json---
Task ID: 1
Agent: Main Agent (team-dev workflow)

Work Log:
- Analyzed existing Phoenix bot data sources (state.json, indicator_history.json, trade_log.json)
- Analyzed existing dashboard (generate_dashboard.py, 61KB HTML)
- Planned BTC Daily Briefing Dashboard architecture (Option A+C)
- Created /src/lib/btc-data.ts: data layer reading Phoenix bot state files
- Created /src/app/api/briefing/route.ts: API endpoint with 5-min cache
- Created /src/app/page.tsx: Full dashboard with 6 sections
- Fixed data-pipeline.py LTH-RP bug (master.get() on Series)
- Fixed trade_log.json field name mismatch (amount vs amount_thb)
- Fixed Turbopack JSX parsing issue with inline Date expression

Stage Summary:
- BTC Daily Briefing Dashboard running at localhost:3000
- Shows: Price hero, Phoenix bot status, On-Chain Pulse, Technical Momentum, Key Levels, Market Narrative, Recent Trades
- All data from Phoenix bot state.json (real-time, no new API calls needed)
- Screenshot saved: /home/z/my-project/download/btc-briefing-dashboard.png
