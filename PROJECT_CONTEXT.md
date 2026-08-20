# Phoenix v5.1 — AI Agent Context Document

> **Purpose:** อ่านไฟล์นี้อย่างเดียวแล้วเข้าใจระบบทั้งหมด พร้อมทำงานต่อได้ทันที ไม่ต้องการ context เพิ่มเติม
>
> Last updated: 2026-08-20

---

## 1. Project Overview

**Phoenix v5.1** เป็น Bitcoin DCA (Dollar-Cost Averaging) trading bot ที่ทำงานอัตโนมัติบน GitHub Actions ซื้อขาย BTC รายวัน โดยใช้ on-chain metrics + technical indicators ในการตัดสินใจ

### Core Idea
- **DCA แบบ dynamic:** ไม่ซื้อที่เท่าเดิมทุกวัน แต่ปรับยอดซื้อตามสภาพตลาด (MVRV, SOPR, RSI, MACD)
- **ขายแบบ tiered:** ใช้ sell scoring system + triple-trigger gate ขายเป็นสัดส่วนตามระดับ euphoria
- **Reserve deployment:** เก็บกำไรจากการขาย BTC ไว้ deploy ซื้อเพิ่มตอนตลาดถดถอย

### Architecture Summary

```
GitHub Actions (cron 20:00 THB)
  → main.py (CLI)
    → engine.run_daily()
      ├── config.py          — ตั้งค่าทั้งหมด
      ├── bitkub_client.py   — API ซื้อขาย/ดึงราคา
      ├── indicators.py      — SMA, RSI, MACD (pure numpy)
      ├── strategy.py        — Phoenix v5.1 decision logic
      ├── bg_metrics.py      — BGeometrics on-chain cache
      ├── mvrv_fetcher.py    — MVRV web fallback
      ├── state.py           — state persistence (JSON + fcntl lock)
      ├── kill_switch.py     — L1 (env) + L2 (JSON) safety
      └── notifier.py        — Telegram alerts
    → generate_dashboard.py
    → git push → GitHub Pages
```

### Concurrency Protection
- **`.bot_lock` file** (in `live_bot/`): `main.py` creates `fcntl.flock(LOCK_EX)` on startup
  - Lock age > 30 min = stale, auto-removed (previous crash)
  - Prevents overlapping GitHub Actions runs from trading simultaneously
- **State file locking** (`state.py`): `load_state()` uses `LOCK_SH` (shared/read), `save_state()` uses `LOCK_EX` (exclusive/write)
  - Lock file: `state.json.lock`
  - Atomic writes via `tempfile.mkstemp()` + `os.replace()` — readers always see valid JSON

### Design Principles
- **Zero pandas** — pure numpy + stdlib only (lightweight for GitHub Actions)
- **No TA-Lib** — all indicators hand-rolled in `indicators.py`
- **File-based state** — JSON committed to repo (no database)
- **Thai timezone** — all date logic uses UTC+7 (`_thai_today()`)
- **Idempotent** — same day re-runs are no-ops (unless `--force`)

---

## 2. Architecture & File Map

### Live Bot (`live_bot/`)

| File | Lines | Purpose | Key Functions |
|------|-------|---------|--------------|
| `main.py` | ~150 | CLI entry, concurrency lock, error handler | `main()`, `create_exchange_client()` |
| `engine.py` | ~965 | Main orchestrator, 13-step run cycle | `run_daily()`, `run_demo()` |
| `strategy.py` | ~400 | Buy/sell decision logic, scoring | `phoenix_v5_1_decision()` |
| `config.py` | ~260 | All config from env vars | `get_daily_budget()`, `get_usd_thb_rate()` |
| `bitkub_client.py` | ~300 | Bitkub API v3 (THB) | `get_price()`, `get_balances()`, `market_buy()`, `market_sell()` |
| `binance_client.py` | ~450 | Binance Spot API (USDT) + geo-fallback | `get_price()`, `market_buy()`, `market_sell()` |
| `bg_metrics.py` | ~630 | BGeometrics on-chain metrics cache | `get_all_metrics_today()`, `get_cached_value()` |
| `mvrv_fetcher.py` | ~200 | MVRV web fetcher (CoinMetrics, ahasignals) | `try_update_mvrv()` |
| `indicators.py` | ~150 | SMA, EMA, RSI, MACD (pure numpy) | `sma()`, `rsi()`, `macd()`, `rsi_divergence()` |
| `state.py` | ~200 | JSON state persistence, file locking | `load_state()`, `save_state()` |
| `kill_switch.py` | ~80 | L1 (env) + L2 (JSON) emergency stop | `is_killed()`, `get_full_status()` |
| `notifier.py` | ~100 | Telegram message formatting | `send_telegram()`, `format_report()` |
| `demo_portfolio.py` | ~100 | Simulated portfolio for demo mode | `process_demo_trade()` |
| `_mvrv_history.py` | ~4000+ | Embedded MVRV daily data (2015–present) | `get_mvrv_for_date()`, `MVRV_HISTORY` dict |

### Data Files (committed to repo)

| File | Purpose | Updated by |
|------|---------|-----------|
| `live_bot/state.json` | Bot state (balances, run count, indicators) | engine.py every run |
| `trade_log.json` | Trade history (max 500 entries) | state.py on each trade |
| `kill_switch.json` | L2 kill switch state | kill_switch.py / dashboard trigger |
| `live_bot/bg_cache.json` | BGeometrics 5-year cache (up to 8 metrics) | bg_metrics.py on fetch |
| `live_bot/usd_thb_rate.json` | USD/THB rate cache | config.py |
| `dashboard/dist/index.html` | Generated dashboard SPA | generate_dashboard.py |

### Backtest (`scripts/smart_dca/`)

| File | Purpose |
|------|---------|
| `strategies/style_phoenix_v5_1.py` | Backtest version of Phoenix v5.1 (pandas-based) |
| `strategies/_shared.py` | Shared backtest utilities |
| `strategies/standard_dca.py` | Baseline DCA for comparison |
| `backtest_engine.py` | Backtest runner |
| `data_pipeline.py` | Data fetcher for backtest |
| `visualization.py` | Chart generation |

### Dependency Graph

```
main.py
  ├── config.py                    (no deps)
  ├── state.py                     (stdlib: json, fcntl, tempfile)
  ├── engine.py
  │   ├── config.py
  │   ├── indicators.py            (numpy only)
  │   ├── strategy.py
  │   │   └── _mvrv_history.py       (data only, ~4000 lines)
  │   ├── bitkub_client.py / binance_client.py
  │   ├── bg_metrics.py             (stdlib: urllib, json, hmac)
  │   ├── mvrv_fetcher.py           (stdlib: urllib, re)
  │   ├── state.py
  │   ├── notifier.py              (requests)
  │   ├── kill_switch.py            (stdlib only)
  │   └── demo_portfolio.py         (stdlib only)
  ├── kill_switch.py
  └── notifier.py

External only: requests, numpy (requirements.txt)
```

---

## 3. Data Flow — One Complete Run

### `run_daily()` 13-Step Pipeline

```
Step 0:  Idempotency check — skip if last_run_date == today (THB timezone)
Step -1: Kill switch — L1 (env BOT_ENABLED) + L2 (kill_switch.json)
Step 1:  Fetch BTC price from exchange
Step 2:  Fetch 500-day price history (Binance Vision ZIP → CoinGecko fallback)
Step 3:  Compute indicators: SMA200, SMA365, RSI(14), MACD, MACD series, RSI divergence, ATH
Step 4:  Get MVRV value (priority chain):
          1. BG cache (disk-only via `get_cached_value()`, 0 API calls)
          2. Embedded `_mvrv_history.py` — 4000+ days, exact lookup → 7-day nearest fallback
          3. CoinMetrics Community API (free, no key, metric `CapMVRVCur`)
          4. ahasignals.com scrape (regex on HTML, last resort)
          If ALL fail → skip trade + Telegram warning
          Source tracked as: 'BG-cache', 'BG', 'embedded', 'CoinMetrics', 'ahasignals'

Step 4b: BGeometrics batch fetch (only if cache stale >3 days):
          `get_all_metrics_today()` — the ONLY place BG API is called
          Fetches 5 metrics: sth_sopr, lth_realized_price, realized_price, mvrv, mvrv_zscore
          Fallbacks if BG unavailable:
            - STH-SOPR: SMA14 proxy (price/sma14)
            - LTH-RP: realized_price × 1.15 proxy
            - MVRV Z-Score: embedded 365d rolling Z-Score (computed from _mvrv_history.py)
          Source tracked as: 'BG', 'cache-stale', 'proxy-sma14', 'embedded-365d'
Step 5:  Get balances (live: exchange API / dry-run: virtual from state)
Step 6:  Convert budget THB → exchange currency
Step 6b: Calculate usable reserve (sell_proceeds - invested_from_reserve)
Step 7:  Decrement cooldown (if > 0)
Step 8:  Run phoenix_v5_1_decision() → {buy_amount, sell_amount, sell_score, path}
Step 9:  Execute trades:
          Buy: check min order (10 THB), check cash
          Sell: never sell >99% of BTC
Step 10: Update state (portfolio value, peak, max drawdown, adjusted_invested)
Step 11: Snapshot all indicators to state (for dashboard)
Step 12: Low balance warning if cash/budget <= 7 days
Step 13: Telegram notification with daily report
```

### Critical Order Dependencies
- **Step 4 (MVRV)** must run before **Step 4b (BG batch)** — MVRV from cache is used for early NUPL calculation
- **Step 4b** is the ONLY place that calls BG API — uses daily guard to prevent duplicate fetches
- **Step 5 (balances)** needs working exchange auth — if it fails, balances default to 0
- **Step 10** updates `adjusted_invested` on sell: `adjusted_invested *= (1 - sell_fraction)`

---

## 4. Strategy Logic — Phoenix v5.1

### Buy Decision (Dynamic DCA)

Buy amount = `min(base_budget × multiplier, max_buy)`

#### MVRV-Based Tiers

| MVRV Range | Extra Condition | Multiplier | Zone |
|------------|----------------|------------|------|
| < 1.0 | SOPR < 0.95 | **4.5×** | Heavy accumulation (underwater) |
| < 1.0 | SOPR ≥ 0.95 | **3.0×** | Strong accumulation |
| 1.0 – 1.5 | NUPL < 0.25 | **3.0×** | Early bull |
| 1.0 – 1.5 | NUPL ≥ 0.25 | **2.0×** | Moderate bull |
| 1.5 – 2.0 | — | **1.0×** | Normal DCA |
| 2.0 – 2.5 | — | **0.3×** | Reduced |
| ≥ 2.5 | — | **0.0×** | No buying |

#### Reserve Deployment (from BTC sale profits only)

| Condition | Deploy Rate |
|-----------|-------------|
| MVRV < 0.8 + bear | 25% of usable reserve |
| MVRV < 0.9 + bear | 20% |
| MVRV < 1.0 | 15% |
| MVRV < 1.1 | 10% |
| MVRV < 1.3 | 6% |
| MVRV 1.3 – 1.5 | 3% |

**Boost:** If `price < realized_price × 1.05` → injection × 1.8 (capped at `max_reserve_boosted`)

### Sell Decision (Scoring + Triple-Trigger Gate)

#### Scoring Table

| Signal | Points | Notes |
|--------|--------|-------|
| MVRV > 2.5 | +20 | |
| MVRV > 3.0 | +15 | |
| MVRV > 3.5 | +10 | |
| MVRV > 4.0 | +10 | |
| RSI > 65 | +5 | Partial credit |
| RSI > 70 | +5 | |
| RSI > 80 | +7 | |
| MVRV pct ≥ 92% | +12 | 365-day percentile |
| MVRV pct ≥ 97% | +8 | |
| MVRV Z > 3.0 | +8 | BG Z-Score or embedded 365d |
| MVRV Z > 4.0 | +7 | |
| MACD bear cross | +10 | Histogram crossed below 0 |
| MACD declining 4 bars | +5 | Consecutive decline |
| RSI divergence | +15 | Price high + RSI lagging |
| Price/LTH-RP > 3.0 | +8 | |
| Price/LTH-RP > 3.5 | +5 | |
| Price/LTH-RP > 4.0 | +5 | |
| ATH proximity >97% | +7 | |
| NUPL > 0.70 | +5 | |
| NUPL > 0.80 | +5 | |
| **In bear market** | **−200** | **Blocks ALL sells** |

#### Triple-Trigger Gate (paths)

```
Path A:       MVRV > 2.5 AND score ≥ 45
Path A-Ext:   MVRV 2.0–2.5 AND pct ≥ 95% AND Z ≥ 2.5 AND score ≥ 48
Path B:       MVRV > 2.0 AND pct ≥ 92% AND score ≥ 48

If NO path active → sell_score forced to 0 (no sell)
```

#### Sell Execution Tiers

| Path | Score Range | Sell % | Cooldown |
|------|------------|--------|----------|
| A | ≥ 75 | 40% | 35 days |
| A | 60–74 | 18% | 28 days |
| A | 50–59 | 8% | 22 days |
| A | 45–49 | 4% | 18 days |
| A-Ext | ≥ 48 | 8% | 22 days |
| B | ≥ 56 | 8% | 28 days |
| B | 48–55 | 4% | 22 days |

### Bear Market Detection

```python
in_bear = price < sma_200  # Simple: price below 200-day SMA
```

**Effects of `in_bear = True`:**
- Sell scoring: −200 points (blocks ALL sells regardless of other signals)
- Reserve deployment: higher rates for MVRV < 0.8/0.9 tiers (25%/20% vs 15%/10%)
- This is a simple but effective guard against selling in a downtrend

### Return Dict

```python
{
    'buy_amount': float,        # THB/USDT to buy (0 = no buy)
    'sell_amount': float,       # BTC to sell (0 = no sell)
    'sell_score': int,          # 0-200+
    'new_cooldown': int,        # days to wait after sell
    'sell_path': str,           # 'A', 'A-Ext', 'B', or 'none'
    'reserve_injection': float, # from sale profits
    'in_bear': bool,            # bear market flag
}
```

---

## 5. Exchange Clients

### Bitkub (`bitkub_client.py`) — Primary, THB

**Auth Formula (CRITICAL — ถ้าผิดจะได้ 400 Bad Request):**

```python
# Signature = HMAC-SHA256(timestamp + METHOD + path + body, api_secret)
# NOTE: NO api_key in payload! MUST include HTTP method!

ts = str(int(time.time() * 1000))  # milliseconds
msg = ts + 'POST' + '/api/v3/market/wallet' + '{}'
sig = hmac.new(api_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()

# Headers:
# X-BTK-APIKEY: api_key
# X-BTK-TIMESTAMP: ts
# X-BTK-SIGN: sig          ← NOT 'X-BTK-SIGNATURE'
# Accept: application/json
# Content-Type: application/json
```

**Endpoints:**

| Method | Path | Purpose | Auth? |
|--------|------|---------|-------|
| GET | `/api/v3/market/ticker?sym=BTC_THB` | Price | No |
| POST | `/api/v3/market/wallet` | Balance | Yes |
| POST | `/api/v3/market/place-bid` | Buy (amt=THB) | Yes |
| POST | `/api/v3/market/place-ask` | Sell (amt=BTC) | Yes |

**Response Gotchas:**
- HTTP 200 with `error: 0` = **SUCCESS** (not failure!)
- HTTP 200 with `error: 42` = application error (e.g., insufficient balance)
- Wallet response: `result.BTC = 8.9` (flat number, NOT `result.BTC.available`)
- Buy response: `result.recv` = BTC received, `result.cost` = THB spent
- Sell response: `result.recv` = THB received (after fee)
- Min order: **10 THB** (not 100)

**Price History (OHLCV):**
1. Binance Vision (`data.binance.vision`) — ZIP/CSV, converts USDT→THB
2. CoinGecko — fallback, ~90 days on free tier

### Binance (`binance_client.py`) — Alternative, USDT

**Auth Formula:**
```python
# Signature = HMAC-SHA256(sorted_query_string, api_secret)
# query_string = timestamp=X&recvWindow=5000&symbol=BTCUSDT&...
# Header: X-MBX-APIKEY: api_key
```

**Geo-Block Fallback (HTTP 451):**
- Price: Kraken → KuCoin → CoinCap → CoinGecko
- Klines: Kraken (720/batch) → KuCoin (300/batch) → CoinCap → CoinGecko

**Key Differences from Bitkub:**
- Buy uses `quoteOrderQty` (USDT amount), not `amt`
- Sell uses `quantity` (BTC, 6 decimals)
- No `fee` in response — engine uses `cost × fee_pct`
- Pagination: max 1000 candles per request

---

## 6. BGeometrics Cache (`bg_metrics.py`)

### Design Goals
- **Minimize API calls** — BG free tier: 10 req/hr
- **Historical data is IMMUTABLE** — never re-fetched
- **Incremental only** — fetches only if cache newest > 3 days behind today

### Rate Limit Protection Layers

| Layer | Mechanism | Saves |
|-------|-----------|-------|
| 1 | `get_cached_value()` — disk only, 0 API calls | Used for early MVRV check in engine step 4 |
| 2 | Daily guard — in-memory snapshot, 0 API calls after 1st fetch/day | Same-process re-runs |
| 3 | Freshness check — skip fetch if cache < 3 days stale | Normal daily runs |
| 4 | Hourly counter — max 10 req/hr, hard stop | Emergency brake |

### Typical API Usage

| Scenario | API Calls |
|----------|-----------|
| Cache fresh (< 3d stale) | **0** |
| Cache stale + first run of day | **0–5** (one per metric) |
| 2nd+ run same day | **0** (daily guard) |

### Functions

```python
# CACHE ONLY — never calls API (use for early reads)
get_cached_value('mvrv', today)           # → float or NaN

# BATCH FETCH — calls API only if cache stale > 3 days
# Returns dict with: sth_sopr, lth_realized_price, realized_price, mvrv, mvrv_zscore
# Also sets: sopr_source, mvrv_source, mvrv_z_source
get_all_metrics_today(target_date=today)   # → dict

# FULL CACHE for backtest
ensure_cache()                             # → cache dict
get_cached_series('sth_sopr')               # → {date_str: float}
```

### Cache File (`bg_cache.json`)

```json
{
  "metrics": {
    "sth_sopr": {"2022-08-05": 1.02, ...},
    "mvrv_zscore": {"2022-08-20": -0.5, ...}
  },
  "last_fetch": {
    "sth_sopr": "2026-08-18T09:50:50+00:00"
  }
}
```

- Up to 5 years (1826 days) per metric
- Trimmed from oldest after merge
- Atomic writes via `tempfile + os.replace()`
- Smart key detection: if expected JSON key yields 0 results, auto-detects by scanning

### `_SINGLE_VALUE_METRICS`

Metrics where `min_days=1` is sufficient (API returns few values, not full history):
- Currently: `{'sth_realized_price'}` only
- `lth_realized_price` and `realized_price` were REMOVED from this set because BG now returns full history

---

## 7. Config & Secrets

### Environment Variables

| Variable | Default | Description | Source |
|----------|---------|-------------|--------|
| `EXCHANGE` | `binance` | `binance` or `bitkub` | Secret |
| `BOT_ENABLED` | `true` | L1 kill switch | Secret |
| `DRY_RUN` | `false` | Simulate trades | Secret/Input |
| `DAILY_BUDGET_THB` | `100` | Daily DCA budget in THB | Secret |
| `MAX_BUY_THB` | `1000` | Max buy per order (THB) | Secret |
| `MAX_DCA_BUYS_PER_DAY` | `1` | Max buys per day | Secret |
| `RESERVE_FLOOR` | `0` (→200 THB) | Min cash reserve | Secret |
| `MAX_RESERVE_INJECTION` | `0` (→900 THB) | Max reserve deploy per run | Secret |
| `RESERVE_BOOST_MULTIPLIER` | `1.8` | Boost multiplier | Secret |
| `RESERVE_BOOST_PRICE_RATIO` | `1.05` | Price threshold for boost | Secret |
| `LOW_BALANCE_DAYS` | `7` | Days before low-balance alert | Secret |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token | Secret |
| `TELEGRAM_CHAT_ID` | — | Telegram chat ID | Secret |
| `BITKUB_API_KEY` | — | Bitkub API key | Secret |
| `BITKUB_API_SECRET` | — | Bitkub API secret | Secret |
| `BGEOMETRICS_TOKEN` | — | BGeometrics API token | Secret |
| `GH_PAT` | — | GitHub PAT for git push | Secret |

### Config Gotchas
- `RESERVE_FLOOR=0` does NOT mean "no floor" — code defaults to 200 THB equivalent
- `MAX_RESERVE_INJECTION=0` defaults to 900 THB equivalent
- All budget config is in THB; conversion to USDT happens at runtime via `get_usd_thb_rate()`
- USD/THB rate chain: Bitkub USDT_THB ticker → disk cache → fallback 33.426
- Empty string from GitHub Secrets ≠ "false" — unchecked boolean input = `""`, not `"false"`

### Budget Flow

```
DAILY_BUDGET_THB (env)
  → config.get_daily_budget()
  → thb_to_local(amount)      # THB → USDT if Binance
  → base_budget (local currency)
  → base_budget × multiplier   # from strategy tier
  → min(result, max_buy)       # cap
  → check min order (10)       # exchange minimum
  → check cash balance
  → EXECUTE BUY
```

---

## 8. GitHub Actions Workflow

### File: `.github/workflows/dca-bitkub.yml`

### Schedule
```
Cron: 13:00, 13:10, 13:30 UTC (= 20:00, 20:10, 20:30 THB)
Concurrency: group=bitkub-dca, cancel-in-progress=false
```

- 3 slots = redundancy (idempotency prevents duplicate trades)
- If all 3 fail → Telegram alert

### Pipeline

```
1. Checkout (with GH_PAT for push back)
2. Setup Python 3.11
3. pip install -r requirements.txt
4. Determine dry_run: workflow input > secret > default (live)
   ⚠️ Boolean unchecked = empty string "", NOT "false"
   Code: if [ "$INPUT" = "true" ]; then FLAGS="$FLAGS --dry-run"; fi
5. Run bot (3× retry, 60s backoff)
   python -m live_bot.main --exchange bitkub --state-file live_bot/state.json $FLAGS
6. On ALL 3 failures → Telegram alert
7. Generate dashboard (python scripts/generate_dashboard.py)
8. Git commit & push (3× retry, auto-stash, rebase)
   Files: state.json, trade_log.json, bg_cache.json, usd_thb_rate.json, dashboard/
9. Triggers deploy-pages.yml → GitHub Pages
```

### Workflow Inputs

| Input | Type | Description |
|-------|------|-------------|
| `dry_run` | boolean | Checkbox — unchecked = empty = LIVE mode |

### dry_run Detection (CRITICAL)

```bash
# WRONG: elif [ -n "$INPUT" ]  — empty string is truthy in -n!
# RIGHT:
if [ "$INPUT" = "true" ]; then
    FLAGS="$FLAGS --dry-run"
fi
```

---

## 9. Dashboard

### Generation
- `scripts/generate_dashboard.py` reads `state.json`, `trade_log.json`, `kill_switch.json`
- Outputs self-contained `dashboard/dist/index.html` (dark theme, auto-refresh 5 min)

### Netlify Trigger Function
- `dashboard/netlify/functions/trigger.js` — serverless POST endpoint
- Rate limit: 5 req/min per IP
- Actions: `update`, `kill`, `resume`
- Dispatches `dashboard-trigger.yml` GitHub Actions

### Dashboard Data Sources
- State indicators (last run's full snapshot)
- Trade log (recent trades)
- Kill switch status (L1 + L2 combined)

---

## 10. Common Pitfalls & Gotchas

### Bitkub API
1. **Signature formula**: `HMAC-SHA256(ts + METHOD + path + body, secret)` — NO api_key in payload
2. **Header name**: `X-BTK-SIGN` (not `X-BTK-SIGNATURE`)
3. **Error 0 = success**: `error: 0` in response body means OK, don't throw
4. **Wallet path**: `/api/v3/market/wallet` (POST, NOT `/api/v3/market/balances`)
5. **Wallet format**: flat numbers `{"BTC": 8.9}` not nested `{"BTC": {"available": 8.9}}`
6. **Buy amount**: in THB for place-bid, in BTC for place-ask

### BGeometrics
7. **Use `get_cached_value()` for early reads** — never `get_all_metrics_today()` for preview
8. **Rate limit**: 10 req/hr free tier — 5 metrics × 1 call each
9. **Data lag**: BG data is always 1-2 days behind (D-2 is normal)
10. **Freshness = 3 days**: cache within 3 days skips fetch entirely

### Engine / State
11. **Thai timezone**: all date logic uses `_thai_today()` (UTC+7)
12. **Never sell 100%**: hard cap at `btc_balance * 0.99`
13. **Kill switch skips idempotency**: `last_run_date` NOT updated when killed (allows re-run)
14. **Adjusted invested**: on sell, `adjusted_invested *= (1 - sell_fraction)` — keeps ROI accurate
15. **NaN in JSON**: `_sanitize_for_json()` converts NaN/Inf → null before saving

### GitHub Actions
16. **Boolean unchecked = empty string `""`**, NOT `"false"` — use `= "true"` comparison
17. **Git push may fail**: auto-stash + rebase handles uncommitted changes
18. **bg_cache.json must be in git add**: otherwise cache is lost between runs

### Config
19. **RESERVE_FLOOR=0 → 200 THB default** (not zero!)
20. **All budgets in THB**: conversion to USDT at runtime

### Indicators
21. **RSI uses Wilder smoothing**: alpha = 1/period (matches `pandas ewm(adjust=False)`)
22. **MACD bear cross**: histogram crossed below zero on LATEST bar only (not any historical cross)
23. **RSI divergence**: price ≥ 97% of 40-day high + RSI ≥ 8 pts below 40-day RSI high + RSI still ≥ 58

---

## 11. Operating Modes

| Mode | Trigger | Trades Real? | State File | Exchange Client |
|------|---------|-------------|------------|----------------|
| **Live** | `DRY_RUN` not set or empty | ✅ Real money | `state.json` | Real API keys |
| **Dry-run** | `DRY_RUN=true` or `--dry-run` | ❌ Simulated | `state.json` | Dummy keys (public API only) |
| **Demo** | `--demo` flag | ❌ Simulated + slippage | `demo_state.json` | Dummy keys |

**Dry-run vs Demo:**
- Dry-run: uses real prices, checks real min order sizes, but skips actual API calls for buy/sell. Virtual balance initialized to `DRY_RUN_INITIAL_CASH` (10,000)
- Demo: adds simulated slippage via `demo_portfolio.process_demo_trade()`, separate state file, never touches real state
---

## 12. Example Log (Annotated)

```
[BOT] Current price: 2,285,000.00 THB              ← Step 1: from Bitkub ticker
[BOT] Got 500 daily closes from Binance Vision     ← Step 2: OHLCV from data.binance.vision ZIP
[BOT] SMA200=2,341,541.27 RSI=44.2 MACD_H=-5795  ← Step 3: numpy indicators
[BG] sth_sopr: cache fresh (1474d, newest=2026-08-17) ← Step 4b: cache hit, 0 API calls
[BG] Batch complete: 0 API calls                  ← All 5 metrics fresh, NO BG API calls!
[BOT] MVRV from BG cache: 1.224                   ← Step 4: get_cached_value(), disk only
[BOT] STH-SOPR=1.0784 (BG)                        ← Step 4b: BG batch (daily guard)
[BOT] LIVE MODE: Real BTC=0.00321 Cash=1,234.56 THB ← Step 5: from Bitkub /api/v3/market/wallet
[BOT] Budget: 20.00 THB/run (max buy: 1,000.00)    ← Step 6: DAILY_BUDGET_THB × multiplier
[BOT] Decision: buy=60.00 sell=0.00 score=0 path=none ← Step 8: strategy output
[BOT] Bought 0.00002626 BTC for 60.00 THB          ← Step 9: Bitkub place-bid executed
[BOT] State saved to live_bot/state.json           ← Step 10: atomic JSON write
[BOT] Telegram notification sent                     ← Step 13
```

Key things to notice:
- `BG cache fresh` + `0 API calls` = rate limit optimization working
- `MVRV from BG cache` (not `get_all_metrics_today`) = early read uses `get_cached_value()`
- `score=0 path=none` = no sell gate activated (MVRV 1.224 < 2.0)
- `buy=60.00` = base 20 × 3.0 multiplier (MVRV 1.0–1.5, NUPL < 0.25)

---

## 13. Known Issues & Active Tasks

> **Last updated: 2026-08-20** — remove items when resolved

### Resolved ✅
- ~~Bitkub auth 400 Bad Request~~ — fixed signature formula (ts+METHOD+path+body), header X-BTK-SIGN
- ~~Bitkub wallet 404~~ — changed path from `/api/v3/market/balances` to `/api/v3/market/wallet`
- ~~`error: 0` treated as failure~~ — now correctly checks `error != 0`
- ~~5 BG API calls per run~~ — optimized to 0 calls when cache fresh
- ~~dry_run detection~~ — fixed boolean unchecked = empty string

### Pending 🔄
- **MVRV Z-Score source priority:** Currently uses BG Z-Score for sell scoring (+15pts). If BG rate-limited (429), falls back to embedded 365d Z-Score. Consider whether embedded Z-Score is reliable enough as sole source.
- **Embedded MVRV history update:** `mvrv_fetcher.py` can append new days to `_mvrv_history.py`, but only 1 day at a time via web scrape. May need manual update if bot is offline for weeks.
- **No `get_usdt_balance()` on Bitkub client:** Intentionally removed to prevent engine from getting 0.0 THB balance. If engine is refactored to check USDT balance, this will need attention.

---

## Quick Reference: Modifying the System

### ต้องการเปลี่ยน buy/sell logic?
→ แก้ `live_bot/strategy.py` — function `phoenix_v5_1_decision()`
→ แก้ sell scoring table, tiers, multiplier ตรงๆ

### ต้องการเพิ่ม indicator ใหม่?
→ เพิ่ม function ใน `live_bot/indicators.py` (pure numpy)
→ เรียกใช้ใน `engine.py` step 3
→ ส่งเข้า strategy เพื่อใช้ใน scoring

### ต้องการเพิ่ม on-chain metric ใหม่?
→ เพิ่มใน `_METRIC_DEFS` ใน `bg_metrics.py`
→ เพิ่มใน `metrics_to_fetch` list ใน `get_all_metrics_today()`
→ เพิ่มใน `ensure_cache()` defaults

### ต้องการย้าย exchange ใหม่?
→ สร้าง client ใหม่ตาม `bitkub_client.py` structure
→ ต้องมี: `get_price()`, `get_balances()`, `market_buy()`, `market_sell()`, `get_klines()`, `currency` property
→ เพิ่มใน `main.py:create_exchange_client()`

### ต้องการแก้ cron schedule?
→ `.github/workflows/dca-bitkub.yml` — ปรับ cron times
→ ระวัง timezone: cron = UTC, bot ใช้ Thai UTC+7
