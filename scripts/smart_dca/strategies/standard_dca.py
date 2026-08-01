"""Strategy: Standard DCA (Benchmark).

Buy 100 THB of BTC every single day, unconditionally. No selling, no reserve.
"""

from ..config import BASE_BUDGET_THB


def strategy_standard_dca(state):
    """Buy 100 THB of BTC every single day, unconditionally."""
    return {'buy_thb': BASE_BUDGET_THB, 'sell_btc_pct': 0, 'to_reserve': 0}
