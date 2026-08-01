"""Strategy registry -- import all strategies here.

To add a new strategy:
  1. Create a new file: strategies/my_strategy.py
  2. It must expose a function matching one of two signatures:
     - Simple:   def strategy_xxx(state) -> dict
     - Factory:  def strategy_xxx(df_precomputed) -> callable(state) -> dict
  3. Import and add to STRATEGY_REGISTRY below
  4. run_backtest.py auto-discovers from this registry
"""

from .standard_dca import strategy_standard_dca
from .style_c import strategy_style_c
from .style_beta import strategy_style_beta
from .style_omega import strategy_style_omega
from .style_phoenix import strategy_style_phoenix
from .style_phoenix_v2 import strategy_style_phoenix_v2
from .style_phoenix_v3 import strategy_style_phoenix_v3
from .style_phoenix_v4 import strategy_style_phoenix_v4
from .style_phoenix_v5 import strategy_style_phoenix_v5

# ============================================================
# STRATEGY REGISTRY
# ============================================================
# Each entry: (display_name, factory_or_func, needs_precompute)
#
# needs_precompute=True  -> engine calls factory(df) to get strategy_func
# needs_precompute=False -> engine uses func directly as strategy_func
#
# To add a new strategy: just append a tuple here.
# ============================================================
STRATEGY_REGISTRY = [
    ('Standard DCA',      strategy_standard_dca,      False),
    ('Style C',           strategy_style_c,           False),
    ('Style Beta',        strategy_style_beta,        True),
    ('Style Omega',       strategy_style_omega,       True),
    ('Style Phoenix',     strategy_style_phoenix,     True),
    ('Phoenix v2',        strategy_style_phoenix_v2,  True),
    ('Phoenix v3',        strategy_style_phoenix_v3,  True),
    ('Phoenix v4',        strategy_style_phoenix_v4,  True),
    ('Phoenix v5',        strategy_style_phoenix_v5,  True),
]
