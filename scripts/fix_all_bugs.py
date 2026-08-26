#!/usr/bin/env python3
"""Fix all remaining dashboard bugs.
Bug list:
1. CRITICAL: F&G gauge colors inverted + seam
2. HIGH: Key Levels array overwrite
3. MEDIUM: Hardcoded THB/USD=35
4. MEDIUM: fr.percentile null guard
5. MEDIUM: Binance no try/catch
6. LOW: Dead code thbPrice
7. LOW: fund_flow fetched but not displayed
"""

import re

FILE = '/home/z/btc-briefing/index.html'

with open(FILE, 'r') as f:
    content = f.read()

changes = 0

# ============================================================
# BUG 1 (CRITICAL): F&G gauge colors inverted + seam
# Fix: Reverse the conic-gradient so Fear(red) is LEFT, Greed(cyan) is RIGHT
# Fix: Start from 180deg to eliminate the seam at top
# Fix: Needle angle formula: 90 - (value/100)*180 so 0=left(Fear), 100=right(Greed)
# ============================================================
old_gradient = """    background: conic-gradient(
      #ef4444 0deg, #f97316 72deg, #eab308 144deg, #22c55e 216deg, #06b6d4 360deg
    );"""
new_gradient = """    background: conic-gradient(
      from 180deg, #06b6d4 0deg, #22c55e 72deg, #eab308 144deg, #f97316 216deg, #ef4444 360deg
    );"""
if old_gradient in content:
    content = content.replace(old_gradient, new_gradient)
    changes += 1
    print('OK: BUG1a - F&G conic-gradient reversed and seam fixed')
else:
    print('WARN: BUG1a - conic-gradient not found')

# Fix needle angle
old_angle = 'const angle = (fg.value / 100) * 180 - 90; // -90 to +90'
new_angle = 'const angle = 90 - (fg.value / 100) * 180; // 0=left(Fear), 100=right(Greed)'
if old_angle in content:
    content = content.replace(old_angle, new_angle)
    changes += 1
    print('OK: BUG1b - F&G needle angle fixed')
else:
    print('WARN: BUG1b - angle formula not found')

# ============================================================
# BUG 2 (HIGH): Key Levels array index overwrite
# Fix: Use findIndex to match by label, not hardcoded index
# ============================================================
old_bot_levels = """  // Add from bot state if available
  if (state.bot && state.bot.last_indicators) {
    const bi = state.bot.last_indicators;
    if (bi.realized_price > 0) {
      levels[0] = { label: 'Realized Price', value: bi.realized_price / 35, dist: ((usd - bi.realized_price/35) / (bi.realized_price/35)) * 100 };
    }
    if (bi.lth_realized_price > 0) {
      levels[1] = { label: 'LTH Realized Price', value: bi.lth_realized_price / 35, dist: ((usd - bi.lth_realized_price/35) / (bi.lth_realized_price/35)) * 100 };
    }
  }"""

new_bot_levels = """  // Compute THB/USD rate dynamically if possible
  const thbUsdRate = (state.price.thb > 0 && state.price.usd > 0) ? state.price.usd / state.price.thb : 35;

  // Add from bot state if available (match by label, never overwrite ATH)
  if (state.bot && state.bot.last_indicators) {
    const bi = state.bot.last_indicators;
    if (bi.realized_price > 0) {
      const rpUsd = bi.realized_price / thbUsdRate;
      const idx = levels.findIndex(l => l.label.includes('Realized Price') && !l.label.includes('LTH'));
      if (idx >= 0) { levels[idx] = { label: 'Realized Price', value: rpUsd, dist: ((usd - rpUsd) / rpUsd) * 100 }; }
      else { levels.splice(levels.length - 1, 0, { label: 'Realized Price', value: rpUsd, dist: ((usd - rpUsd) / rpUsd) * 100 }); }
    }
    if (bi.lth_realized_price > 0) {
      const lthUsd = bi.lth_realized_price / thbUsdRate;
      const idx = levels.findIndex(l => l.label.includes('LTH'));
      if (idx >= 0) { levels[idx] = { label: 'LTH Realized Price', value: lthUsd, dist: ((usd - lthUsd) / lthUsd) * 100 }; }
      else { levels.splice(levels.length - 1, 0, { label: 'LTH Realized Price', value: lthUsd, dist: ((usd - lthUsd) / lthUsd) * 100 }); }
    }
  }"""

if old_bot_levels in content:
    content = content.replace(old_bot_levels, new_bot_levels)
    changes += 1
    print('OK: BUG2+3 - Key Levels fixed (findIndex + dynamic THB rate)')
else:
    print('WARN: BUG2 - bot levels block not found')

# ============================================================
# BUG 4 (MEDIUM): fr.percentile null guard
# ============================================================
old_fr_pct = 'html += `  <div class="metric-sub"><span>Pct: ${(fr.percentile * 100).toFixed(1)}%</span></div>`;'
new_fr_pct = 'html += `  <div class="metric-sub"><span>Pct: ${((fr.percentile || 0) * 100).toFixed(1)}%</span></div>`;'
if old_fr_pct in content:
    content = content.replace(old_fr_pct, new_fr_pct)
    changes += 1
    print('OK: BUG4 - fr.percentile null guard added')
else:
    print('WARN: BUG4 - fr.percentile line not found')

# ============================================================
# BUG 5 (MEDIUM): Binance fetch no try/catch
# ============================================================
old_binance = """async function fetchBinancePrice() {
  // 24h ticker
  const ticker = await fetchJSON(`${CONFIG.BINANCE_API}/ticker/24hr?symbol=BTCUSDT`);
  state.price.usd = parseFloat(ticker.lastPrice);
  state.price.change24h = parseFloat(ticker.priceChangePercent);
  state.price.volume = parseFloat(ticker.quoteVolume);

  // Market cap (approximate: price * 19.8M circulating supply)
  state.price.mcap = state.price.usd * 19_800_000;

  // 30-day klines for sparkline
  const klines = await fetchJSON(`${CONFIG.BINANCE_API}/klines?symbol=BTCUSDT&interval=1d&limit=30`);
  state.sparkline = klines.map(k => parseFloat(k[4])); // close prices
}"""

new_binance = """async function fetchBinancePrice() {
  try {
    // 24h ticker
    const ticker = await fetchJSON(`${CONFIG.BINANCE_API}/ticker/24hr?symbol=BTCUSDT`);
    state.price.usd = parseFloat(ticker.lastPrice);
    state.price.change24h = parseFloat(ticker.priceChangePercent);
    state.price.volume = parseFloat(ticker.quoteVolume);

    // Market cap (approximate: price * 19.8M circulating supply)
    state.price.mcap = state.price.usd * 19_800_000;

    // 30-day klines for sparkline
    const klines = await fetchJSON(`${CONFIG.BINANCE_API}/klines?symbol=BTCUSDT&interval=1d&limit=30`);
    state.sparkline = klines.map(k => parseFloat(k[4])); // close prices
  } catch (e) {
    console.warn('Binance API failed:', e);
  }
}"""

if old_binance in content:
    content = content.replace(old_binance, new_binance)
    changes += 1
    print('OK: BUG5 - Binance try/catch added')
else:
    print('WARN: BUG5 - Binance function not found')

# ============================================================
# BUG 6 (LOW): Dead code thbPrice in renderBot
# ============================================================
old_dead = '  const thbPrice = price || state.price.thb;\n  const btcBal'
new_dead = '  const btcBal'
if old_dead in content:
    content = content.replace(old_dead, new_dead)
    changes += 1
    print('OK: BUG6 - Dead code thbPrice removed')
else:
    print('WARN: BUG6 - thbPrice line not found')

# ============================================================
# BUG 9 (LOW): Bitkub fallback rate 35 → 33
# ============================================================
old_fallback = 'state.price.thb = state.price.usd * 35;'
new_fallback = 'state.price.thb = state.price.usd * 33;'
if old_fallback in content:
    content = content.replace(old_fallback, new_fallback)
    changes += 1
    print('OK: BUG9 - Fallback THB rate updated to 33')

# Write
with open(FILE, 'w') as f:
    f.write(content)

print(f'\nTotal changes applied: {changes}')
print(f'File: {FILE} ({len(content)} chars)')
