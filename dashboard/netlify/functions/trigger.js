const headers = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Content-Type': 'application/json',
};

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
  // Handle CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers };
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

  // Validate reason length for kill action
  if (action === 'kill' && reason && reason.length > 200) {
    return { statusCode: 400, headers, body: JSON.stringify({ error: 'Reason too long (max 200 chars)' }) };
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
