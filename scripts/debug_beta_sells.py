#!/usr/bin/env python3
"""Debug: Count and analyze Beta v3 sell events."""
import os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, '/home/z/my-project/scripts')

# Reuse data pipeline from main script
exec(open('/home/z/my-project/scripts/smart_dca_backtest.py').read().split("if __name__")[0])

master_df = build_master_dataframe(years=5)

for years in [3, 5]:
    if years == 3:
        test_df = master_df.tail(int(3 * 365.25)).reset_index(drop=True)
    else:
        test_df = master_df.copy()
    
    print(f"\n=== {years}-YEAR SELL EVENT ANALYSIS ===")
    
    # Simulate Beta and log sells
    from smart_dca_backtest import strategy_style_beta, backtest_strategy, BASE_BUDGET_THB, BUY_FEE_PCT, SELL_FEE_PCT, DOWNLOAD_DIR, CACHE_DIR
    beta_func = strategy_style_beta(test_df)
    
    btc = 0.0
    cash = 0.0
    invested = 0.0
    cooldown = 0
    sell_events = []
    
    for idx, row in test_df.iterrows():
        if cooldown > 0:
            cooldown -= 1
        state = {'btc': btc, 'cash_reserve': cash, 'total_invested': invested, 'cooldown': cooldown, 'row': row, 'idx': idx}
        action = beta_func(state)
        
        buy = action.get('buy_thb', 0)
        sell_thb = action.get('sell_thb', 0)
        sell_score = action.get('sell_score', 0)
        
        if buy > 0:
            actual = buy * (1 - BUY_FEE_PCT)
            btc += actual / row['price_thb'] if row['price_thb'] > 0 else 0
            invested += buy
        
        # Reserve deploy
        if row['mvrv'] < 1.2 and cash > 0:
            inj = min(100.0, cash)
            actual = inj * (1 - BUY_FEE_PCT)
            btc += actual / row['price_thb'] if row['price_thb'] > 0 else 0
            invested += inj
            cash -= inj
        
        if sell_thb > 0 and btc > 0:
            btc_sell = min(sell_thb / row['price_thb'], btc)
            proceeds = btc_sell * row['price_thb'] * (1 - SELL_FEE_PCT)
            btc -= btc_sell
            cash += proceeds
            cooldown = action.get('new_cooldown', cooldown)
            
            sell_events.append({
                'date': row['date'],
                'price_usd': row['price_usd'],
                'mvrv': row['mvrv'],
                'rsi': row['rsi_14'],
                'sell_score': sell_score,
                'sell_thb': sell_thb,
                'btc_sold': btc_sell,
                'proceeds_thb': proceeds,
                'btc_before': btc + btc_sell,
                'cash_after': cash,
            })
    
    print(f"Total sell events: {len(sell_events)}")
    print(f"Total proceeds: {sum(e['proceeds_thb'] for e in sell_events):,.0f} THB")
    print(f"Total BTC sold: {sum(e['btc_sold'] for e in sell_events):.6f} BTC")
    
    for e in sell_events:
        print(f"  {e['date']} | Price ${e['price_usd']:,.0f} | MVRV {e['mvrv']:.2f} | RSI {e['rsi']:.1f} | Score {e['sell_score']} | Sell {e['sell_thb']:,.0f} THB ({e['btc_sold']:.6f} BTC) | Cash→{e['cash_after']:,.0f}")

# Also check how many days score >= 50 but cooldown blocks it
print("\n=== DAYS WHERE SCORE >= 50 (potential sells) ===")
for years in [3, 5]:
    if years == 3:
        test_df = master_df.tail(int(3 * 365.25)).reset_index(drop=True)
    else:
        test_df = master_df.copy()
    
    macd_line = test_df['macd_line'].values
    macd_signal = test_df['macd_signal'].values
    macd_hist = test_df['macd_hist'].values
    cummax = pd.Series(test_df['price_usd']).cummax().values
    sma200 = test_df['sma_200'].values
    
    high_score_days = []
    for idx, row in test_df.iterrows():
        mvrv = row['mvrv']; rsi = row['rsi_14']; price = row['price_usd']
        score = 0
        if mvrv > 2.5: score += 25
        if mvrv > 3.0: score += 15
        if mvrv > 3.5: score += 10
        if rsi > 70: score += 15
        if rsi > 80: score += 10
        # MACD bear cross
        if idx > 0 and not np.isnan(macd_line[idx-1]) and not np.isnan(macd_signal[idx-1]) and not np.isnan(macd_line[idx]) and not np.isnan(macd_signal[idx]):
            if macd_line[idx-1] >= macd_signal[idx-1] and macd_line[idx] < macd_signal[idx]:
                score += 15
        # Histogram declining
        if idx >= 5:
            decl = True
            for j in range(4):
                if np.isnan(macd_hist[idx-j]) or np.isnan(macd_hist[idx-j-1]):
                    decl = False; break
                if macd_hist[idx-j] >= macd_hist[idx-j-1]:
                    decl = False; break
            if decl: score += 10
        # ATH
        ath = cummax[idx]
        if ath > 0 and price > 0.95 * ath: score += 10
        # Bear block
        s200 = sma200[idx]
        if not np.isnan(s200) and price < s200: score -= 200
        
        if score >= 25:  # Show any day with meaningful score
            high_score_days.append({'date': row['date'], 'price': price, 'mvrv': mvrv, 'rsi': rsi, 'score': score})
    
    print(f"\n{years}-Year: {len([d for d in high_score_days if d['score'] >= 50])} days with score >= 50")
    for d in high_score_days:
        if d['score'] >= 25:
            marker = ' >> SELL' if d['score'] >= 50 else ''
            print(f"  {d['date']} | ${d['price']:,.0f} | MVRV {d['mvrv']:.2f} | RSI {d['rsi']:.1f} | Score {d['score']}{marker}")
