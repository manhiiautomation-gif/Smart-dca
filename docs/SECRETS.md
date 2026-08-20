# Required Secrets

This document lists all secrets needed by Smart-DCA.

## GitHub Secrets (for GitHub Actions)

| Secret Name | Purpose | How to Generate |
|-------------|---------|-----------------|
| `BGEOMETRICS_TOKEN` | BGeometrics API token for on-chain metrics | Sign up at bgeometrics.com, get API token |
| `BITKUB_API_KEY` | Bitkub exchange API key | Bitkub account → API keys |
| `BITKUB_API_SECRET` | Bitkub exchange API secret | Bitkub account → API keys |
| `BINANCE_API_KEY` | Binance exchange API key | Binance account → API Management |
| `BINANCE_API_SECRET` | Binance exchange API secret | Binance account → API Management |
| `TELEGRAM_BOT_TOKEN` | Telegram bot for alerts | BotFather → /newbot |
| `TELEGRAM_CHAT_ID` | Telegram chat to send alerts to | @userinfobot |
| `BOT_ENABLED` | L1 kill switch (true/false) | Manual |
| `GH_PAT` | GitHub PAT for state pushback | (WILL BE REPLACED by PHOENIX_PUSH_PAT in Wave 4) |
| `DRY_RUN` | Simulate trades (true/false) | Manual |

## Netlify Environment Variables (for dashboard function)

| Env Var | Purpose |
|---------|---------|
| `GH_PAT` | GitHub PAT for webhook dispatch (will be replaced by PHOENIX_DISPATCH_PAT in Wave 2) |

## Secrets needed in Future Waves (NOT YET)

Wave 2+ will require additional secrets — they will be documented here as they are introduced:
- `TRIGGER_SECRET` (Wave 2) — HMAC shared secret for webhook auth
- `STATE_SIGNING_KEY` (Wave 5) — HMAC key for state file signatures
- `PHOENIX_READ_PAT` (Wave 4) — fine-grained PAT for checkout
- `PHOENIX_PUSH_PAT` (Wave 4) — fine-grained PAT for state pushback
- `PHOENIX_DISPATCH_PAT` (Wave 2) — fine-grained PAT for webhook dispatch
- `HEALTHCHECKS_IO_UUID` (Wave 3) — dead-man's switch ping URL

## Token Rotation

The previous BGeometrics token (`7NqNRwWhyc`) was hardcoded in source and is considered compromised. After deploying this fix:
1. Log into BGeometrics account
2. Revoke old token
3. Generate new token
4. Add as GitHub Secret: `BGEOMETRICS_TOKEN`
