# Smart DCA Backtest — Work Log

---
Task ID: 1
Agent: Main Agent
Task: Design and implement Style Omega strategy (7-strategy backtest suite)

Work Log:
- Read and analyzed existing 6-strategy backtest script (1180 lines)
- Analyzed Beta v3 results: wins on ROI but leaves 20-30K THB unused cash
- Tested LTH Realized Price proxies (k=0.65, SMA180, EMA90 of RP)
  - ALL proxies 99%+ correlated with MVRV — zero marginal signal as primary
  - Decision: Use LTH RP as CONFIRMATION only, pivot to reserve optimization
- Designed Style Omega with 3-round process:
  - Round 1: LTH RP research → pivot to reserve drain optimization
  - Round 2: Root cause = Beta's fixed 100 THB/day → % based drain
  - Round 3: Safety guards (SMA200 bear confirm, floor, cooldown tuning)
- Added lth_realized_price and price_to_lth_rp to compute_technical_indicators()
- Implemented strategy_style_omega() with 6 key improvements over Beta
- Fixed backtest engine to track net_capital and true_roi_pct
- Updated Beta to report reserve_injection for accurate net_capital
- Updated console table, chart table, and CSV to show True ROI

Stage Summary:
- Style Omega CRUSHES all strategies in both periods:
  - 3-Year: True ROI 81.4% (Beta 27.3%, C 16.6%)
  - 5-Year: True ROI 410.7% (Beta 135.3%, C 97.7%)
  - 5-Year Final Value: 1,337,030 THB (2x Beta, 2.4x C)
  - Same Net Capital as Beta (user cost identical)
- Key innovation: % based reserve drain (5-20%/day) vs Beta's fixed 100 THB/day
- Charts: download/smart_dca_comparison_3-Year.png, 5-Year.png
- CSV: download/smart_dca_results_3-Year.csv, 5-Year.csv
- Script: scripts/smart_dca_backtest.py (now ~1420 lines, 7 strategies)
