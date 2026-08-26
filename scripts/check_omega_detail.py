#!/usr/bin/env python3
"""Quick diagnostic: compare Omega vs Beta cash reserve behavior."""
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '/home/z/my-project/scripts')
from smart_dca_backtest import (
    build_master_dataframe, backtest_strategy, strategy_style_beta, strategy_style_omega
)

master_df = build_master_dataframe(years=5)

for years in [3, 5]:
    if years == 3:
        test_df = master_df.tail(int(3 * 365.25)).reset_index(drop=True)
    else:
        test_df = master_df.copy()
    
    _, daily_beta = backtest_strategy(test_df, strategy_style_beta(test_df), 'Beta')
    _, daily_omega = backtest_strategy(test_df, strategy_style_omega(test_df), 'Omega')
    
    print(f'\n=== {years}-YEAR ===')
    print(f'Beta final cash:  {daily_beta["cash_reserve"].iloc[-1]:,.0f} THB')
    print(f'Omega final cash: {daily_omega["cash_reserve"].iloc[-1]:,.0f} THB')
    print(f'Beta max cash:    {daily_beta["cash_reserve"].max():,.0f} THB')
    print(f'Omega max cash:   {daily_omega["cash_reserve"].max():,.0f} THB')
    
    # Check how much was sold vs bought from reserve
    beta_invested = daily_beta['total_invested'].iloc[-1]
    omega_invested = daily_omega['total_invested'].iloc[-1]
    beta_btc = daily_beta['btc'].iloc[-1]
    omega_btc = daily_omega['btc'].iloc[-1]
    
    print(f'\nBeta  invested: {beta_invested:,.0f}, BTC: {beta_btc:.6f}')
    print(f'Omega invested: {omega_invested:,.0f}, BTC: {omega_btc:.6f}')
    print(f'Omega extra invested vs Beta: {omega_invested - beta_invested:,.0f} THB')
    print(f'Omega extra BTC vs Beta:      {omega_btc - beta_btc:.6f} BTC')
    
    # True ROI: (final_value - base_budget * days) / (base_budget * days)
    # since reserve is self-funding, the real cost is just the daily budget
    days = len(test_df)
    base_cost = 100 * days
    beta_final = daily_beta['portfolio_value'].iloc[-1]
    omega_final = daily_omega['portfolio_value'].iloc[-1]
    print(f'\nBase cost (100 THB x {days}d): {base_cost:,.0f} THB')
    print(f'Beta  True ROI:  {(beta_final - base_cost) / base_cost * 100:.1f}%')
    print(f'Omega True ROI:  {(omega_final - base_cost) / base_cost * 100:.1f}%')
