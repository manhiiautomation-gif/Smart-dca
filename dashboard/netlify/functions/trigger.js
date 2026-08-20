// S-10: CORS allowlist — replaces the previous static `headers` const with
// `Access-Control-Allow-Origin: "*"`.
//
// Allowlist of dashboard origins. The Netlify dashboard URL is the primary
// (override via DASHBOARD_URL env var); the GitHub Pages mirror is for
// redundancy; localhost for dev only.
//
// NOTE: Replace the placeholder `https://PLACEHOLDER.netlify.app` after first
// deployment by setting the `DASHBOARD_URL` Netlify env var to the actual
// dashboard URL. The same value should also be set in `dashboard/netlify.toml`.
const ALLOWED_ORIGINS = new Set([
  process.env.DASHBOARD_URL || 'https://PLACEHOLDER.netlify.app',  // prod (override via env)
  'https://manhiiautomation-gif.github.io',                        // GitHub Pages mirror
  'http://localhost:3000',                                          // dev only
]);

function get_origin(event) {
  // Netlify normalizes request headers to lowercase, but accept both cases.
  return (event.headers && (event.headers.origin || event.headers.Origin)) || '';
}

function cors_headers(origin) {
  return {
    // Echo back the origin only if allowlisted; empty string otherwise (browser blocks).
    'Access-Control-Allow-Origin': ALLOWED_ORIGINS.has(origin) ? origin : '',
    'Vary': 'Origin',  // critical: response cache key must include origin
    'Access-Control-Allow-Headers': 'Content-Type',  // S-01 will add X-Phoenix-Signature here
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Content-Type': 'application/json',
  };
}

// Simple in-memory rate limiter (per IP)
const rateLimits = {};
const RATE_WINDOW = 60_000; // 1 minute
const RATE_MAX = 5; // max 5 calls per minute per IP

function isRateLimited(ip) {
  const now = Date.now();
  if (!rateLimits[ip] || now - rateLimits[ip].start > RATE_WINDOW) {
    rateLimits[ip] = { start: now, count: 1 };
    return false;
  }
  rateLimits[ip].count++;
  return rateLimits[ip].count > RATE_MAX;
}

const ALLOWED_ACTIONS = ['update', 'kill', 'resume'];

export const handler = async (event) => {
  const origin = get_origin(event);
  const headers = cors_headers(origin);

  // Handle CORS preflight (always return 204 with CORS headers — even for
  // disallowed origins, so the browser's preflight sees an empty ACAO and
  // blocks the subsequent actual request).
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers };
  }

  // S-10: reject cross-site requests from untrusted origins BEFORE doing any
  // work — saves cycles and prevents CSRF in case CORS preflight is bypassed.
  if (!ALLOWED_ORIGINS.has(origin)) {
    return { statusCode: 403, headers, body: JSON.stringify({ error: 'Forbidden origin' }) };
  }

  // Only POST allowed
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }

  // Rate limiting
  const ip = (event.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'unknown';
  if (isRateLimited(ip)) {
    return { statusCode: 429, headers, body: JSON.stringify({ error: 'Rate limited. Try again later.' }) };
  }

  // Validate input
  let body;
  try {
    body = JSON.parse(event.body || '{}');
  } catch {
    return { statusCode: 400, headers, body: JSON.stringify({ error: 'Invalid JSON' }) };
  }

  const { action, reason } = body;
  if (!ALLOWED_ACTIONS.includes(action)) {
    return { statusCode: 400, headers, body: JSON.stringify({ error: `Invalid action. Allowed: ${ALLOWED_ACTIONS.join(', ')}` }) };
  }

  // S-02 (defense in depth): reject reasons containing HTML/JS metacharacters
  // or exceeding 200 chars. The Python `activate_kill_switch()` re-validates.
  if (action === 'kill' && reason) {
    if (typeof reason !== 'string' || reason.length > 200) {
      return { statusCode: 400, headers, body: JSON.stringify({ error: 'Reason too long (max 200 chars)' }) };
    }
    if (/[<>&"'\/]/.test(reason)) {
      return { statusCode: 400, headers, body: JSON.stringify({ error: 'Reason contains forbidden characters' }) };
    }
  }

  // Get PAT from environment variable
  const pat = process.env.GH_PAT;
  if (!pat) {
    console.error('[TRIGGER] GH_PAT environment variable not set');
    return { statusCode: 500, headers, body: JSON.stringify({ error: 'Server not configured' }) };
  }

  // Call GitHub Actions workflow dispatch
  const repo = process.env.GH_REPO || 'manhiiautomation-gif/Smart-dca';
 const workflow = 'dashboard-trigger.yml';
  const apiUrl = `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`;

  const dispatchBody = {
    ref: 'main',
    inputs: { action },
  };
  if (action === 'kill' && reason) {
    dispatchBody.inputs.reason = reason;
  }

  try {
    const resp = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${pat}`,
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(dispatchBody),
    });

    if (resp.status === 204) {
      const labels = {
        update: 'Bot update + dashboard refresh started',
        kill: 'Kill switch activated',
        resume: 'Bot resumed',
      };
      return {
        statusCode: 200, headers,
        body: JSON.stringify({ success: true, message: labels[action] }),
      };
    }

    // Handle errors from GitHub
    let errorMsg = `GitHub API error: ${resp.status}`;
    try {
      const errData = await resp.json();
      errorMsg = errData.message || errorMsg;
    } catch {}
    console.error(`[TRIGGER] GitHub error: ${resp.status} ${errorMsg}`);
    return { statusCode: resp.status, headers, body: JSON.stringify({ error: errorMsg }) };

  } catch (err) {
    console.error(`[TRIGGER] Fetch error: ${err.message}`);
    return { statusCode: 502, headers, body: JSON.stringify({ error: 'Failed to reach GitHub' }) };
  }
};
