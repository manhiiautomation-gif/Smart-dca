"""Strategy: Style C — On-Chain Tiered Pure DCA.

Pure accumulation (long-only). Scales daily buy by MVRV tiers
with SOPR/NUPL boosters. No selling, no cash reserve.
"""

from ..config import BASE_BUDGET_THB


def strategy_style_c(state):
    row = state['row']
    mvrv = row['mvrv']
    sopr = row['sopr']
    nupl = row['nupl']

    if mvrv < 1.0:
        multiplier = 4.5 if sopr < 0.95 else 3.0
    elif mvrv < 1.5:
        multiplier = 3.0 if nupl < 0.25 else 2.0
    elif mvrv < 2.0:
        multiplier = 1.0
    elif mvrv < 2.5:
        multiplier = 0.5
    else:
        multiplier = 0.0

    return {'buy_thb': BASE_BUDGET_THB * multiplier, 'sell_btc_pct': 0, 'to_reserve': 0}
