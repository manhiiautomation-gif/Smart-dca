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

---
Task ID: 2-a
Agent: Data Flow Agent
Task: Investigate git push issue — bot_state.json 404 on raw.githubusercontent.com

Work Log:
- Read /home/z/my-project/live_bot/sync_state.py (147 lines) fully
- Checked git remote -v in /home/z/btc-signal-analyzer: origin → https://github.com/manhiiautomation-gif/btc-signal-analyzer.git (no auth)
- Checked git branch -vv: `* main 7e200a5 ...` with NO `[origin/main]` tracking — upstream was NEVER set
- Checked git log --oneline -5: 4 local commits (initial + 3 bot state syncs), reflog shows only local commits
- Verified .git/refs/remotes/origin/ directory does NOT EXIST — git fetch has never succeeded
- Confirmed git for-each-ref refs/remotes/ returns nothing — zero remote tracking refs in the entire repo
- Tested git fetch origin: FAILS with `fatal: could not read Username for 'https://github.com': No such device or address` (no auth, no credential helper)
- Verified git config --list: remote.origin.fetch=+refs/heads/*:refs/remotes/origin/* IS configured, but never executed
- Checked push.default: not set (defaults to `simple` for git 2.47.3)
- Checked credential.helper: not set globally or locally
- Verified token extraction from my-project: ghp_ token (40 chars), extraction logic works correctly
- Built local bare-repo test: confirmed `git push <url> main` IS syntactically valid and pushes correctly
- Confirmed `git push <url> main` does NOT create remote tracking refs (refs/remotes/origin/main) — this is by design
- Verified output/bot_state.json exists in local main branch (git ls-tree, git show)

Stage Summary:

## ROOT CAUSE ANALYSIS

### (a) Exact Root Cause

**The problem has TWO layers:**

**Layer 1 — Remote tracking refs are non-existent.**
The btc-signal-analyzer repo was created via `git init` locally (reflog shows `commit (initial)`) and was NEVER cloned from GitHub. Consequently:
- `git fetch origin` has never been successfully run
- `.git/refs/remotes/origin/` directory does not exist at all
- `origin/main` does not exist (`git rev-parse origin/main` → fatal: unknown revision)
- No upstream tracking is configured (`git branch -vv` shows bare `main` with no `[origin/main]`)
- `git fetch origin` CANNOT work because the remote URL (`https://github.com/...`) has no authentication and no credential helper is configured

**Layer 2 — `git push <auth_url> main` (line 120) does NOT update remote tracking refs.**
When `git push` is given a raw URL instead of a remote name, git pushes the objects and updates the REMOTE refs, but it does NOT create or update any local remote tracking refs (`refs/remotes/origin/*`). This is by design in git. The script's approach of pushing via authenticated URL bypasses the remote configuration entirely, so `origin/main` is never born.

**Why the file is 404 on raw.githubusercontent.com:**
The push syntax `git push <url> main` IS valid (confirmed via local bare-repo testing — it correctly pushes `refs/heads/main` to the remote). If the push is reaching GitHub with a valid token, the most likely reason for 404 is that **the btc-signal-analyzer repo is PRIVATE** — raw.githubusercontent.com returns 404 (not 403) for private repos to avoid information leakage. If the repo is public and the push is failing, the error would be in `push_result.stderr` (exit code non-zero) and the script would return False. Investigate the actual stderr output from a live push run to confirm.

### (b) Minimal Fix in sync_state.py

Replace the URL-based push (lines 107-127) with remote-name-based push. The key change: temporarily set the remote's push URL to include the token, push using the remote name (which DOES update tracking refs), then restore the URL.

```python
# CURRENT (broken):
push_result = subprocess.run(
    ['git', 'push', auth_url, 'main'],  # pushes via URL — no tracking ref update
    cwd=repo, capture_output=True, text=True, timeout=60
)

# FIXED:
# Temporarily set push URL with token, push via remote name, restore
subprocess.run(
    ['git', 'remote', 'set-url', '--push', 'origin', auth_url],
    cwd=repo, capture_output=True, text=True, timeout=10
)
push_result = subprocess.run(
    ['git', 'push', 'origin', 'main'],  # pushes via remote name — updates tracking refs
    cwd=repo, capture_output=True, text=True, timeout=60
)
# Restore clean push URL (no token in config)
subprocess.run(
    ['git', 'remote', 'set-url', '--push', 'origin', base_url],
    cwd=repo, capture_output=True, text=True, timeout=10
)
```

Also remove the `else` branch (lines 123-127) since the token path should always be used, and remove the URL-based push entirely. The `--push` flag ensures only the push URL is modified, keeping the fetch URL clean (or alternatively, also set the fetch URL for `git fetch` to work).

### (c) One-Time Git Commands to Fix btc-signal-analyzer Repo State

```bash
cd /home/z/btc-signal-analyzer

# Step 1: Extract token from my-project and configure origin with auth
TOKEN=$(git -C /home/z/my-project config --get remote.origin.url | sed 's|https://||;s|@.*||')
git remote set-url origin "https://${TOKEN}@github.com/manhiiautomation-gif/btc-signal-analyzer.git"

# Step 2: Push all local commits AND set up upstream tracking
# (this creates origin/main and sets the tracking branch)
git push -u origin main

# Step 3: Verify tracking is set up
git branch -vv   # should now show [origin/main]
git rev-parse origin/main   # should succeed

# Step 4 (optional, recommended): Strip token from stored URL and use credential helper
git remote set-url origin "https://github.com/manhiiautomation-gif/btc-signal-analyzer.git"
# Then either configure a credential helper, or rely on the script's set-url --push approach
```

**Note:** Step 1 stores the token in the git config. If security is a concern, use Step 4 to remove it and rely on the script's `set-url --push` approach for future pushes. Alternatively, configure `git credential-store` or `GIT_ASKPASS` for persistent auth.

## KEY EVIDENCE TABLE

| Check | Result | Implication |
|-------|--------|-------------|
| `git branch -vv` | `main` with no `[origin/main]` | No upstream tracking ever set |
| `git rev-parse origin/main` | fatal: unknown revision | Remote tracking ref does not exist |
| `ls .git/refs/remotes/origin/` | No such file or directory | git fetch never succeeded |
| `git for-each-ref refs/remotes/` | (empty) | Zero remote refs in entire repo |
| `git reflog` | Only local commits, no fetch/pull | Confirms no remote interaction ever |
| `git fetch origin` | fatal: could not read Username | No auth in remote URL, no credential helper |
| `git config push.default` | (unset, defaults to `simple`) | Not the issue |
| `git config credential.helper` | (unset) | Not configured |
| `git remote -v` | https://github.com/.../btc-signal-analyzer.git | No token in URL |
| Token extraction | ghp_ token, 40 chars, works | Token is available |
| Local `git push <url> main` test | Succeeds, creates remote branch | Syntax is valid |
| `git push <url> main` tracking update | Does NOT update refs/remotes/origin/* | Confirmed by design |

---
Task ID: 2-b
Agent: Integration Agent
Task: Dashboard URLs check — verify all 5 data source endpoints, repo visibility, and graceful failure handling

## URL TEST RESULTS

| # | URL | HTTP Status | Verdict |
|---|-----|-------------|---------|
| 1 | `https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT` | **200** | ✅ Working. Returns valid JSON with lastPrice, priceChangePercent, quoteVolume |
| 2 | `https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=30` | **200** | ✅ Working. Returns 30 daily candles for sparkline |
| 3 | `https://api.bitkub.com/api/market/ticker?sym=THB_BTC` | **200** (body: `{"error": 99}`) | ⚠️ HTTP 200 but returns API error 99. The `sym=` query parameter appears broken/deprecated. THB_BTC data IS available when calling the endpoint WITHOUT `sym=` (returns full ticker with THB_BTC.last = 2,563,428.73) |
| 4 | `https://api.alternative.me/fng/?limit=1` | **200** | ✅ Working. Returns value=65, classification="Greed" |
| 5 | `https://raw.githubusercontent.com/manhiiautomation-gif/btc-signal-analyzer/main/output/signal_score.json` | **404** | ❌ Not Found. File has NOT been pushed to GitHub yet |
| 6 | `https://raw.githubusercontent.com/manhiiautomation-gif/btc-signal-analyzer/main/output/bot_state.json` | **404** | ❌ Not Found. Expected — push fix in progress |

## REPO VISIBILITY

- `curl -s https://api.github.com/repos/manhiiautomation-gif/btc-signal-analyzer` → HTTP 404 `"Not Found"`
- This is GitHub's standard response for **private repos** when called unauthenticated (to prevent leaking existence)
- **Conclusion: The `btc-signal-analyzer` repo is PRIVATE.** Raw GitHub URLs will return 404 for any file until the repo is made public OR the dashboard is served with authentication.
- **This is a BLOCKER for both signal_score.json and bot_state.json** — no amount of pushing will fix this without making the repo public.

## GRACEFUL FAILURE ANALYSIS

| Data Source | Wrapped in try/catch? | Fallback Behavior | Dashboard Crashes? |
|-------------|----------------------|-------------------|-------------------|
| Binance (ticker + klines) | **NO** | None. Error propagates to `init()` global catch → shows full-page error screen | ⚠️ If Binance fails, ENTIRE dashboard shows error (not just price). However, `Promise.allSettled` at line 1017 prevents one failure from blocking others — the error is swallowed by allSettled, but `state.price.usd` stays 0, causing renderers to show $0 |
| Bitkub | **YES** (line 562) | Falls back to `USD * 35` estimate. Actual BTC/THB ~2,563,428 vs estimate ~2,733,920 (≈6.6% high) | ✅ No crash |
| Fear & Greed | **YES** (line 574) | `renderFearGreed()` checks `if (!fg)` → shows "Fear & Greed data not available" | ✅ No crash |
| signal_score.json | **YES** (line 589) | `renderOnChain()` shows MVRV/NUPL at 0.000 (defaults). `renderMomentum()` shows "On-chain signal data not available yet" | ✅ No crash, but shows misleading 0.000 values |
| bot_state.json | **YES** (line 617) | `state.bot = null`. `renderBot()` shows badge "NO DATA" + message "Push bot_state.json to btc-signal-analyzer repo to enable live status" | ✅ No crash. Correctly shows NO DATA |

## ISSUES FOUND

### CRITICAL: Repo is Private — Raw GitHub URLs Will Never Work
- **Both `signal_score.json` and `bot_state.json` are hosted on a PRIVATE repo**
- `raw.githubusercontent.com` requires the repo to be public for unauthenticated access
- The dashboard (a static HTML opened in browser) has no auth mechanism
- **Fix: Make `manhiiautomation-gif/btc-signal-analyzer` repo PUBLIC on GitHub**

### MEDIUM: Bitkub `sym=` Parameter Returns Error 99
- URL `https://api.bitkub.com/api/market/ticker?sym=THB_BTC` returns `{"error": 99}` with HTTP 200
- Bitkub API may have deprecated the `sym` query parameter
- Without `sym=`, calling `https://api.bitkub.com/api/market/ticker` returns all pairs including THB_BTC
- **Fix options:** (a) Remove `?sym=THB_BTC` and filter client-side, or (b) keep as-is (fallback works)

### LOW: Binance Fetcher Not Individually try/caught
- `fetchBinancePrice()` (line 547) lacks try/catch — relies on `Promise.allSettled` to prevent total failure
- If Binance is down, price shows as $0 and `renderPrice()` still runs (no crash, but shows $0 everywhere)
- The global `catch(e)` in `init()` is never reached because `Promise.allSettled` never rejects
- **Impact:** Dashboard shows $0 price instead of a clear error message for just the price section

### LOW: renderBriefing Always Shows MVRV Text Even With No Data
- When signal_score.json is 404, `state.onchain.mvrv` defaults to 0
- `renderBriefing()` unconditionally says "MVRV at 0.00 is in deep accumulation zone" which is misleading
- **Fix:** Guard the MVRV briefing text with a check like `if (mvrv > 0)`

### LOW: Signal Score Fetch Failure Leaves MVRV/NUPL at Defaults
- When signal_score.json fails, MVRV shows 0.000, NUPL shows 0.000, Z-Score shows 0.00
- These look like real values to the user
- **Fix:** Show "N/A" or "waiting for data" instead of 0.000 when signal data is unavailable

## SUMMARY

| Category | Status |
|----------|--------|
| Public API URLs (Binance, FG) | ✅ All working |
| Bitkub URL | ⚠️ Returns error 99 (fallback active) |
| GitHub Raw URLs (signal, bot_state) | ❌ 404 — repo is PRIVATE |
| Dashboard crash on failures | ✅ No crashes — all handled gracefully |
| NO DATA display for bot_state | ✅ Correctly shows "NO DATA" badge and message |
| Blocking issue | **Repo must be made PUBLIC** for dashboard to work fully |

---
Task ID: 5-review
Agent: Code Reviewer
Task: Review all code changes (sync_state.py, main.py, index.html)

## REVIEW FINDINGS

### File 1: `live_bot/sync_state.py` — Git push via `set-url --push`

**Verdict: ✅ CORRECT — No regressions detected**

Changes reviewed:
- L117-119: `git remote set-url --push origin <auth_url>` — sets push-only URL with token
- L122-125: `git push origin main` — pushes via the configured push URL
- L128-132: Restore push URL to clean `base_url` (no token)

**Correctness:**
- The `--push` flag correctly sets only the push URL, leaving the fetch URL untouched. This is the right approach for injecting auth without polluting the config.
- Token extraction from my-project's remote (L24-36) and cleanup of btc-signal-analyzer's remote (L112-113) are logically sound.
- The `if token:` guard (L115, L128) correctly skips set-url operations when no token is available.

**Edge cases & issues found:**
- **LOW — Token leak on process kill (L117-132):** If the process is killed between the auth set-url (L117) and the restore (L130), the GitHub PAT will remain in the btc-signal-analyzer repo's git config as the push URL. Since this is on a trusted CI/runner machine, the practical risk is low, but it's worth noting. Mitigation: the outer `except Exception` (L143) won't catch SIGKILL.
- **INFO — No-op commit handling (L100-103):** If `git commit` fails (e.g., nothing to commit after the add), the subsequent push still runs harmlessly. This is acceptable behavior.
- **INFO — Hardcoded branch `main` (L123):** If the btc-signal-analyzer repo ever switches default branch, this would need updating. Acceptable for current setup.

### File 2: `live_bot/main.py` — Sync call in finally block (L318-323)

**Verdict: ✅ CORRECT — No regressions detected**

Changes reviewed:
- L318-323: Lazy import of `sync_state` and non-fatal call in the `finally` block

**Correctness:**
- `bot_state` is assigned at L219, before the `try` block (L258), so it's always defined when the `finally` runs. No `NameError` risk.
- The lazy `from live_bot import sync_state` avoids circular imports and loading overhead when sync isn't needed (e.g., demo mode exits before this point).
- `except Exception` catches all import/runtime errors, printing a non-fatal message. `SystemExit` (from L310's `sys.exit(1)`) is a `BaseException` and won't be caught here — it propagates correctly, but the `finally` block still executes first.
- `_release_lock()` (L324) runs after sync attempt, ensuring lock cleanup always happens.

**Edge cases & issues found:**
- **NONE.** This is a clean, safe pattern. The sync is fire-and-forget, fully decoupled from bot operation.
- **INFO — Loop mode sync timing (L272-293):** In loop mode, state is saved per iteration (L291) but sync only happens once in the `finally` block when the loop ends (Ctrl+C or error). This means intermediate loop states are NOT synced to GitHub. This is acceptable — only the final state matters for the dashboard.

### File 3: `btc-briefing/index.html` — Bitkub API fix, MVRV/NUPL guards

**Verdict: ✅ CORRECT — No regressions. One pre-existing issue noted.**

#### 3a. Bitkub API fix (L462, L562-573)
- CONFIG.BITKUB_API changed to base endpoint `https://api.bitkub.com/api/market/ticker`
- Parsing changed from `data.result.THB_BTC.last` → `data.THB_BTC.last`

**Correctness:** ✅ Matches Bitkub's documented flat response format `{ THB_BTC: { last, ... }, ... }`
- Guard `if (data && data.THB_BTC)` prevents crash on unexpected format
- `parseFloat()` handles string values from the API
- Fallback to `usd * 35` on fetch failure is reasonable (rough THB approximation)

#### 3b. MVRV/NUPL rendering guards (L704, L722, L979)
- `renderOnChain()` L704: `if (state.onchain.mvrv > 0)` — shows metrics or "Waiting for on-chain data..."
- `renderOnChain()` L722: `if (state.onchain.nupl !== 0 || state.signal)` — shows NUPL or "N/A"
- `renderBriefing()` L979: `if (mvrv > 0)` — shows MVRV narrative or "On-chain data not yet available..."
- `renderKeyLevels()` L872: `state.onchain.mvrv > 0 ? usd / state.onchain.mvrv : 0` — already guarded

**Correctness:** ✅ All guards are consistent. When on-chain data is unavailable, users see informative placeholders instead of misleading "MVRV at 0.00" or "NUPL: 0.000".

**Edge cases & issues found:**
- **LOW — MVRV Z-Score shown as 0.00 inside MVRV block (L711):** When `mvrv > 0` but `mvrv_z` is still 0 (e.g., NUPL was available but z-score wasn't in signal_score.json), the UI shows "Z-Score: 0.00" which could be misread as a real value. Consider adding a guard like `state.onchain.mvrv_z > 0 ? ... : 'N/A'`.
- **PRE-EXISTING BUG — `renderKeyLevels` sparse array overwrite (L887-893):** When `mvrv === 0`, `levels` contains only `[ATH]` (length 1). If `bot.last_indicators.realized_price > 0`, then `levels[0]` overwrites ATH with Realized Price, and `levels[1]` assignment creates a sparse array. The ATH entry is silently lost. This is NOT a regression from the current changes — it's a pre-existing issue that becomes more visible now that the MVRV=0 state is properly handled (previously MVRV might have shown 0.00 but still produced a derived RP).
- **INFO — Hardcoded USD/THB rate (L571, L888, L891):** The fallback rate of 35 and bot-state division by 35 are hardcoded in multiple places. If the THB rate drifts significantly, these will be inaccurate. Not a regression.

## OVERALL SUMMARY

| Change | Correctness | Regressions | Severity Issues |
|--------|-------------|-------------|------------------|
| sync_state.py — push via set-url --push | ✅ | None | LOW: token leak on SIGKILL |
| main.py — sync in finally block | ✅ | None | None |
| index.html — Bitkub flat response | ✅ | None | None |
| index.html — MVRV/NUPL guards | ✅ | None | LOW: z-score 0.00 display; PRE-EXISTING: key levels sparse array |

**Conclusion: All three changes are correct and safe to deploy.** No regressions found. Two LOW-severity items and one pre-existing bug are documented for future improvement.

---
Task ID: 2-a
Agent: UI/Display Agent
Task: F&G meter bug investigation + full UI bug scan

Work Log:
- Read worklog.md (existing entries through Task 2-b review)
- Read full /home/z/btc-briefing/index.html (1122 lines)
- Tested F&G API: curl https://api.alternative.me/fng/?limit=1 → 200, valid JSON, CORS headers present (access-control-allow-origin: *)
- Tested all 5 APIs — ALL return HTTP 200
- Verified signal_score.json structure: 17 indicators, each with raw_value/percentile/direction (all floats, no nulls)
- Verified bot_state.json structure: has last_indicators.realized_price (1743217.98 THB) and lth_realized_price (2004700.67 THB)
- Verified Bitkub API returns THB_BTC.last = 2,555,163.05
- Verified Binance API returns valid ticker data
- Traced full F&G data flow: fetchFearGreed() → state.onchain.fng → renderFearGreed() → DOM
- Analyzed gauge CSS: conic-gradient color positions vs needle angle mapping
- Audited all 7 render functions for null/undefined access, division-by-zero, wrong field names

Stage Summary:

## 1. FEAR & GREED METER — ROOT CAUSE

**The F&G data loads correctly.** The API returns 200 with valid CORS. The `fetchFearGreed()` function (line 575-588) correctly parses `data.data[0].value` (string "65") via `parseInt()`. The `renderFearGreed()` function (line 887-911) correctly builds the gauge DOM.

**The bug is a GAUGE COLOR INVERSION** (lines 226-230 CSS + line 894 JS).

The conic-gradient (line 226-228) is:
```css
conic-gradient(#ef4444 0deg, #f97316 72deg, #eab308 144deg, #22c55e 216deg, #06b6d4 360deg)
```
Conic-gradient goes clockwise from 12 o'clock (0deg). The visible semicircle spans 270deg→360deg→90deg (left to right). Color mapping on the visible arc:
- **LEFT edge (270deg)**: green-cyan (#22c55e→#06b6d4) = Greed colors
- **TOP center (0deg)**: sharp cyan→red jump (visual seam)
- **RIGHT edge (90deg)**: red-orange (#ef4444→#f97316) = Fear colors

The needle angle (line 894): `(fg.value / 100) * 180 - 90` maps value=0 → -90° (LEFT) and value=100 → +90° (RIGHT).

**Result**: When F&G=65 (Greed), needle points RIGHT into the RED/ORANGE zone. When F&G=20 (Fear), needle points LEFT into the GREEN/CYAN zone. The colors are the exact OPPOSITE of what they should be.

**Fix (1 line)**: Change line 894 from:
```javascript
const angle = (fg.value / 100) * 180 - 90;
```
to:
```javascript
const angle = 90 - (fg.value / 100) * 180;
```
This makes value=0 (Fear) point RIGHT (red) and value=100 (Greed) point LEFT (cyan).

**Secondary issue**: There is a sharp color discontinuity at the top center of the gauge (0deg/360deg boundary) where cyan meets red. The gradient should be designed so the color transition is smooth across the visible semicircle.

## 2. FULL BUG SCAN RESULTS

| # | Severity | Function | Lines | Description |
|---|----------|----------|-------|-------------|
| 1 | **CRITICAL** | renderFearGreed + CSS | 226-230, 894 | **F&G gauge colors inverted** — Fear colors (red) on right, Greed colors (cyan) on left. Needle points wrong way relative to color band. Fix: flip needle angle formula. |
| 2 | **HIGH** | renderKeyLevels | 933-941 | **Array index overwrite loses ATH** — When `state.onchain.mvrv <= 0` (on-chain data not loaded), `levels` only has [ATH] at index 0. Bot state code then does `levels[0] = {realized_price}` which OVERWRITES ATH. ATH disappears from the dashboard. Fix: use `find()` or push instead of direct index assignment. |
| 3 | **MEDIUM** | renderKeyLevels | 936, 939 | **Hardcoded THB/USD rate (35)** for bot state price conversion. Should use actual rate: `state.price.thb > 0 ? state.price.usd / state.price.thb : 35`. Current rate is ~32.8, so levels are off by ~6.7%. |
| 4 | **MEDIUM** | renderMomentum | 818 | **Missing percentile null guard** — `fr.percentile * 100` will produce `NaN%` if `percentile` field is absent from a future API response. Current data is fine, but no defensive check. Other indicators in this function guard `raw_value` but not `percentile`. |
| 5 | **MEDIUM** | fetchBinancePrice | 547-560 | **No try/catch** — Unlike other fetchers, this one has no error handling. If Binance fails, it throws into `Promise.allSettled` (caught), but `state.price` stays at defaults (usd=0). `renderPrice()` then shows $0 with no error indication. Should wrap in try/catch like `fetchBitkubPrice()`. |
| 6 | **MEDIUM** | CSS gauge | 226-228 | **Sharp color seam at top center** — The conic-gradient has a hard boundary between #06b6d4 (at 360deg) and #ef4444 (at 0deg) exactly where the needle sits for neutral (value≈50). Creates a visible vertical line in the gauge. |
| 7 | **LOW** | renderBot | 986 | **Dead code**: `const thbPrice = price || state.price.thb;` is declared but never used in the rest of renderBot(). |
| 8 | **LOW** | renderOnChain | 621-624 | **Fetched but never displayed**: `state.onchain.fund_flow` is populated from `btc_fund_flow_ratio` but `renderOnChain()` never renders it. Only MVRV, NUPL, Puell, and Signal Score are shown. |
| 9 | **LOW** | renderBriefing | 1022-1071 | **Minimal briefing when data partial** — If only MVRV is available (no F&G, no signal score, no funding rate), the briefing is just one sentence. Not a bug, but a thin experience. |
| 10 | **LOW** | fetchBitkubPrice | 571 | **Hardcoded THB/USD fallback of 35** — Current actual rate is ~32.8. Fallback estimate is 6.7% off. Should use a recent rate or at least update the constant. |

## 3. API STATUS

| API | HTTP | CORS | Data Valid | Notes |
|-----|------|------|------------|-------|
| api.alternative.me/fng | 200 | ✅ `*` | ✅ value="65" | Working correctly |
| api.binance.com/ticker/24hr | 200 | ✅ | ✅ price=77880.70 | Working correctly |
| raw.githubusercontent.com/.../signal_score.json | 200 | ✅ | ✅ 17 indicators | Working correctly |
| raw.githubusercontent.com/.../bot_state.json | 200 | ✅ | ✅ 29 top-level keys | Working correctly |
| api.bitkub.com/market/ticker | 200 | ✅ | ✅ THB_BTC.last=2555163.05 | Working correctly |

**All 5 APIs return HTTP 200 with valid data and proper CORS headers. No API connectivity issues.**

## 4. RECOMMENDED FIXES

### Fix #1 (CRITICAL): F&G Gauge Color Inversion
**File**: `/home/z/btc-briefing/index.html`, line 894
**Change**:
```javascript
// OLD:
const angle = (fg.value / 100) * 180 - 90;
// NEW:
const angle = 90 - (fg.value / 100) * 180;
```
**Also fix the conic-gradient** (lines 226-228) to eliminate the seam and make colors flow correctly left-to-right (Fear→Greed):
```css
/* OLD: */
conic-gradient(#ef4444 0deg, #f97316 72deg, #eab308 144deg, #22c55e 216deg, #06b6d4 360deg)
/* NEW: */
conic-gradient(from 180deg, #ef4444 0deg, #f97316 72deg, #eab308 144deg, #22c55e 216deg, #06b6d4 360deg)
```
Adding `from 180deg` rotates the gradient start to the bottom (clipped), so the visible semicircle reads Red (left) → Orange → Yellow → Green → Cyan (right).

### Fix #2 (HIGH): Key Levels Array Overwrite
**File**: line 933-941
**Change**: Replace direct index assignment with safe lookup:
```javascript
if (state.bot && state.bot.last_indicators) {
  const bi = state.bot.last_indicators;
  const rate = state.price.thb > 0 ? state.price.usd / state.price.thb : 35;
  const rpIdx = levels.findIndex(l => l.label.includes('Realized Price'));
  const lthIdx = levels.findIndex(l => l.label.includes('LTH'));
  if (bi.realized_price > 0 && rpIdx >= 0) {
    const rpUsd = bi.realized_price / rate;
    levels[rpIdx] = { label: 'Realized Price', value: rpUsd, dist: ((usd - rpUsd) / rpUsd) * 100 };
  }
  if (bi.lth_realized_price > 0 && lthIdx >= 0) {
    const lthUsd = bi.lth_realized_price / rate;
    levels[lthIdx] = { label: 'LTH Realized Price', value: lthUsd, dist: ((usd - lthUsd) / lthUsd) * 100 };
  }
}
```

### Fix #3 (MEDIUM): Hardcoded THB/USD rate
Already addressed in Fix #2 above by computing `rate` dynamically.

### Fix #4 (MEDIUM): Percentile null guard
**File**: line 818
**Change**: Add guard: `${(fr.percentile != null ? fr.percentile * 100 : 0).toFixed(1)}%`

### Fix #5 (MEDIUM): Binance fetch error handling
**File**: lines 547-560
**Change**: Wrap `fetchBinancePrice()` body in try/catch like `fetchBitkubPrice()`.

### Fix #6 (MEDIUM): Gauge seam
Already addressed in Fix #1 by using `from 180deg`.

### Fix #7 (LOW): Dead code
**File**: line 986
**Change**: Remove `const thbPrice = price || state.price.thb;`

### Fix #8 (LOW): Fund Flow not displayed
**File**: renderOnChain() function
**Change**: Add a section to display `state.onchain.fund_flow` if available, similar to the Puell Multiple section.

**Conclusion: The #1 user-reported issue (F&G meter not working) is caused by inverted gauge colors — data loads fine but the visual is backwards. One primary fix (needle angle + gradient rotation) resolves it. One HIGH-severity bug (key levels array overwrite) and several MEDIUM bugs were also found. All 5 APIs are healthy.**
