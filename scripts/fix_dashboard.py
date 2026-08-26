#!/usr/bin/env python3
"""Fix field mapping in btc-briefing/index.html to match actual signal_score.json structure."""

import re

FILE = '/home/z/btc-briefing/index.html'

with open(FILE, 'r') as f:
    content = f.read()

# ============================================================
# 1. Replace renderOnChain function
# ============================================================
old_render_onchain = r'''function renderOnChain\(\) \{
  const \{ mvrv, nupl, sopr \} = state\.onchain;
  const mv = getMvrvZone\(mvrv\);.*?document\.getElementById\('onchain-content'\)\.innerHTML = html;\n\}'''

new_render_onchain = '''function renderOnChain() {
  const { mvrv, nupl, puell } = state.onchain;
  const mv = getMvrvZone(mvrv);
  const indCount = Object.keys(state.signal?.indicators || {}).length;

  let html = '';

  // MVRV
  if (state.onchain.mvrv > 0) {
    html += `<div class="metric">`;
    html += `  <div class="metric-header">`;
    html += `    <span class="metric-label">MVRV Ratio</span>`;
    html += `    <span class="zone-badge" style="color:${mv.color};border-color:${mv.color}40;background:${mv.color}20">${mv.zone}</span>`;
    html += `  </div>`;
    html += `  <div class="metric-value lg">${mvrv.toFixed(3)}</div>`;
    html += `  <div class="metric-sub"><span>Pct: ${((state.onchain.mvrv_z + 5) / 10 * 100).toFixed(1)}%</span></div>`;
    html += `</div>`;
  } else {
    html += `<div class="metric">`;
    html += `  <div class="metric-header"><span class="metric-label">MVRV Ratio</span></div>`;
    html += `  <div class="no-data">Waiting for on-chain data...</div>`;
    html += `</div>`;
  }

  // NUPL (derived from MVRV)
  html += `<div class="metric-divider"></div>`;
  if (state.onchain.nupl !== null && state.onchain.nupl !== undefined && !isNaN(state.onchain.nupl)) {
    html += `<div class="metric">`;
    html += `  <div class="metric-header">`;
    html += `    <span class="metric-label">NUPL <span style="font-size:10px;color:var(--text-muted)">(derived)</span></span>`;
    html += `    <span style="font-size:11px;color:var(--text-secondary)">${getNuplPhase(nupl)}</span>`;
    html += `  </div>`;
    html += `  <div class="metric-value">${nupl.toFixed(3)}</div>`;
    html += `</div>`;
  } else {
    html += `<div class="metric"><div class="metric-header"><span class="metric-label">NUPL</span></div><div class="no-data">N/A</div></div>`;
  }

  // Puell Multiple (mining metric, replaces SOPR)
  html += `<div class="metric-divider"></div>`;
  html += `<div class="metric">`;
  html += `  <div class="metric-header">`;
    html += `    <span class="metric-label">Puell Multiple</span>`;
    if (puell !== null && puell !== undefined) {
      const puellSignal = puell < 0.5 ? 'Strong Buy (Miners Capitulating)' : puell < 0.8 ? 'Buy Zone' : puell < 1.2 ? 'Normal' : puell < 2.0 ? 'Overheating' : 'Sell Signal';
      const puellColor = puell < 0.8 ? 'var(--green)' : puell < 1.2 ? 'var(--text-secondary)' : 'var(--red)';
      html += `    <span style="font-size:11px;color:${puellColor}">${puellSignal}</span>`;
    }
  html += `  </div>`;
  if (puell !== null && puell !== undefined) {
    const puellColor = puell < 0.8 ? 'var(--green)' : puell < 1.2 ? 'var(--text-primary)' : 'var(--red)';
    html += `  <div class="metric-value" style="color:${puellColor}">${puell.toFixed(3)}</div>`;
  } else {
    html += `  <div class="no-data">N/A</div>`;
  }
  html += `</div>`;

  // Signal Score from btc-signal-analyzer
  if (state.signal && state.signal.score !== undefined) {
    html += `<div class="metric-divider"></div>`;
    html += `<div class="metric">`;
    html += `  <div class="metric-header">`;
    html += `    <span class="metric-label">Signal Score</span>`;
    const sc = state.signal.score;
    const scColor = sc < 30 ? '#22c55e' : sc < 50 ? '#86efac' : sc < 70 ? '#eab308' : sc < 85 ? '#f97316' : '#ef4444';
    html += `    <span class="zone-badge" style="color:${scColor};border-color:${scColor}40;background:${scColor}20">${state.signal.zone?.label || 'Neutral'}</span>`;
    html += `  </div>`;
    html += `  <div class="metric-value">${sc.toFixed(1)}<span style="font-size:14px;color:var(--text-muted)"> / 100</span></div>`;
    html += `  <div class="source-tag">Source: btc-signal-analyzer (${indCount} indicators) | ${state.signal.date || 'N/A'}</div>`;
    html += `</div>`;
  }

  document.getElementById('onchain-content').innerHTML = html;
}'''

result = re.sub(old_render_onchain, new_render_onchain, content, flags=re.DOTALL)
if result == content:
    print('WARNING: renderOnChain NOT replaced')
else:
    print('OK: renderOnChain replaced')
content = result

# ============================================================
# 2. Replace renderMomentum function
# ============================================================
old_render_momentum = r'''function renderMomentum\(\) \{.*?document\.getElementById\('momentum-content'\)\.innerHTML = html;\n\}'''

new_render_momentum = '''function renderMomentum() {
  const s = state.signal;
  let html = '';

  if (s && s.indicators) {
    const ind = s.indicators;

    // Technical Momentum Group Score
    if (s.groups && s.groups.technical_momentum) {
      const tm = s.groups.technical_momentum;
      const tmPct = (tm.score * 100).toFixed(1);
      const tmColor = tm.score < 0.3 ? 'var(--green)' : tm.score < 0.6 ? 'var(--text-secondary)' : 'var(--red)';
      const tmLabel = tm.score < 0.3 ? 'Oversold/Bearish' : tm.score < 0.6 ? 'Neutral' : 'Overbought/Bullish';
      html += `<div class="metric">`;
      html += `  <div class="metric-header">`;
      html += `    <span class="metric-label">Momentum Score</span>`;
      html += `    <span style="font-size:11px;color:${tmColor}">${tmLabel}</span>`;
      html += `  </div>`;
      html += `  <div class="metric-value lg" style="color:${tmColor}">${tmPct}<span style="font-size:14px;color:var(--text-muted)">%</span></div>`;
      html += `</div>`;
    }

    // Funding Rate
    const fr = ind.btc_funding_rates;
    if (fr && fr.raw_value !== null && fr.raw_value !== undefined) {
      html += `<div class="metric-divider"></div>`;
      html += `<div class="metric">`;
      html += `  <div class="metric-header">`;
      html += `    <span class="metric-label">Funding Rate</span>`;
      const frColor = fr.raw_value > 0.01 ? 'var(--red)' : fr.raw_value < 0 ? 'var(--green)' : 'var(--text-secondary)';
      html += `    <span style="font-size:11px;color:${frColor}">${fr.raw_value > 0.01 ? 'High Long Bias' : fr.raw_value < 0 ? 'Short Bias' : 'Neutral'}</span>`;
      html += `  </div>`;
      html += `  <div class="metric-value">${(fr.raw_value * 100).toFixed(4)}%</div>`;
      html += `  <div class="metric-sub"><span>Pct: ${(fr.percentile * 100).toFixed(1)}%</span></div>`;
      html += `</div>`;
    }

    // Taker Buy/Sell Ratio
    const taker = ind.btc_taker_buy_sell_ratio;
    if (taker && taker.raw_value !== null && taker.raw_value !== undefined) {
      html += `<div class="metric-divider"></div>`;
      html += `<div class="metric">`;
      html += `  <div class="metric-header">`;
      html += `    <span class="metric-label">Taker Buy/Sell</span>`;
      const tColor = taker.raw_value > 1.1 ? 'var(--green)' : taker.raw_value < 0.9 ? 'var(--red)' : 'var(--text-secondary)';
      html += `    <span style="font-size:11px;color:${tColor}">${taker.raw_value > 1.1 ? 'Buyers Dominant' : taker.raw_value < 0.9 ? 'Sellers Dominant' : 'Balanced'}</span>`;
      html += `  </div>`;
      html += `  <div class="metric-value">${taker.raw_value.toFixed(3)}</div>`;
      html += `</div>`;
    }

    // Exchange Netflow
    const nf = ind.btc_exchange_netflow;
    if (nf && nf.raw_value !== null && nf.raw_value !== undefined) {
      html += `<div class="metric-divider"></div>`;
      html += `<div class="metric">`;
      html += `  <div class="metric-header">`;
      html += `    <span class="metric-label">Exchange Netflow</span>`;
      const nfColor = nf.raw_value > 0 ? 'var(--red)' : 'var(--green)';
      const nfLabel = nf.raw_value > 0 ? 'Inflow (Selling)' : 'Outflow (Accumulation)';
      html += `    <span style="font-size:11px;color:${nfColor}">${nfLabel}</span>`;
      html += `  </div>`;
      html += `  <div class="metric-value" style="color:${nfColor}">${nf.raw_value > 0 ? '+' : ''}${nf.raw_value.toFixed(0)} BTC</div>`;
      html += `</div>`;
    }

    // Whale Ratio
    const wr = ind.btc_exchange_whale_ratio;
    if (wr && wr.raw_value !== null && wr.raw_value !== undefined) {
      html += `<div class="metric-divider"></div>`;
      html += `<div class="metric">`;
      html += `  <div class="metric-header">`;
      html += `    <span class="metric-label">Whale Ratio</span>`;
      const wrColor = wr.raw_value > 0.5 ? 'var(--red)' : 'var(--green)';
      html += `    <span style="font-size:11px;color:${wrColor}">${wr.raw_value > 0.5 ? 'High Whale Activity' : 'Normal'}</span>`;
      html += `  </div>`;
      html += `  <div class="metric-value">${(wr.raw_value * 100).toFixed(1)}%</div>`;
      html += `</div>`;
    }

    // 7d / 30d Returns
    const r7 = ind.return_7d;
    const r30 = ind.return_30d;
    if (r7 && r30 && r7.raw_value !== null && r30.raw_value !== null) {
      html += `<div class="metric-divider"></div>`;
      html += `<div class="metric">`;
      html += `  <div class="metric-header"><span class="metric-label">Price Returns</span></div>`;
      html += `  <div style="display:flex;gap:16px">`;
      const r7c = r7.raw_value >= 0 ? 'var(--green)' : 'var(--red)';
      const r30c = r30.raw_value >= 0 ? 'var(--green)' : 'var(--red)';
      html += `    <div><span style="font-size:11px;color:var(--text-muted)">7d</span><div style="font-size:16px;font-weight:600;color:${r7c}">${(r7.raw_value >= 0 ? '+' : '')}${(r7.raw_value * 100).toFixed(1)}%</div></div>`;
      html += `    <div><span style="font-size:11px;color:var(--text-muted)">30d</span><div style="font-size:16px;font-weight:600;color:${r30c}">${(r30.raw_value >= 0 ? '+' : '')}${(r30.raw_value * 100).toFixed(1)}%</div></div>`;
      html += `  </div>`;
      html += `</div>`;
    }
  } else {
    html = `<div class="no-data">On-chain signal data not available yet. Waiting for btc-signal-analyzer update.</div>`;
  }

  document.getElementById('momentum-content').innerHTML = html;
}'''

result = re.sub(old_render_momentum, new_render_momentum, content, flags=re.DOTALL)
if result == content:
    print('WARNING: renderMomentum NOT replaced')
else:
    print('OK: renderMomentum replaced')
content = result

# ============================================================
# 3. Fix renderBriefing to use correct field names
# ============================================================
# The briefing references state.signal.indicators.funding_rate — fix to btc_funding_rates
content = content.replace(
    'state.signal.indicators.funding_rate',
    'state.signal.indicators.btc_funding_rates'
)
# Also fix .value to .raw_value in the briefing
old_fr_briefing = '''const fr = state.signal.indicators.btc_funding_rates;
    if (fr && fr.value > 0.01) {
      parts.push(`High funding rate (${(fr.value*100).toFixed(4)}%) suggests crowded long positioning — potential for squeeze.`);'''
new_fr_briefing = '''const fr = state.signal.indicators.btc_funding_rates;
    if (fr && fr.raw_value > 0.01) {
      parts.push(`High funding rate (${(fr.raw_value*100).toFixed(4)}%) suggests crowded long positioning — potential for squeeze.`);'''
if old_fr_briefing in content:
    content = content.replace(old_fr_briefing, new_fr_briefing)
    print('OK: renderBriefing funding_rate fixed')
else:
    print('WARNING: renderBriefing funding_rate not found or already fixed')

# Write back
with open(FILE, 'w') as f:
    f.write(content)

print(f'Done. File written: {FILE}')
print(f'New size: {len(content)} chars, {content.count(chr(10))} lines')
