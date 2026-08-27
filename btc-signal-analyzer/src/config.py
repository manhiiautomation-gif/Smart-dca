"""Configuration: metric definitions, weights, zones, and data source URLs.

All indicator weights are grounded in research:
- Dubey et al. (2025): 196 on-chain metrics evaluated
- Omole et al. (2024): Boruta feature selection, 82.44% accuracy
- Chi et al. (2024): Exchange netflow predicts returns significantly
- Fear & Greed Index methodology: weighted composite approach
- BitcoinFoundation (2026): On-Chain + Technical confluence strategy
"""

from __future__ import annotations

# ── Data Source ──────────────────────────────────────────────────────────
DATA_SOURCE_BASE = (
    "https://raw.githubusercontent.com/ErcinDedeoglu/crypto-market-data/main/data/daily"
)
ATTRIBUTION = "On-chain data: Ercin Dedeoglu - Crypto Market Data (CC BY 4.0)"

# ── Percentile lookback for normalization ────────────────────────────────
PERCENTILE_WINDOW = 365  # days

# ── Score Zones ──────────────────────────────────────────────────────────
SCORE_ZONES: list[dict] = [
    {"min": 0,  "max": 20, "label": "Extreme Fear",     "color": "#ff3333"},
    {"min": 20, "max": 40, "label": "Fear",              "color": "#ff8800"},
    {"min": 40, "max": 60, "label": "Neutral",           "color": "#ffcc00"},
    {"min": 60, "max": 80, "label": "Greed",             "color": "#88cc00"},
    {"min": 80, "max": 101,"label": "Extreme Greed",     "color": "#00cc44"},
]

# ── Trend windows (days) ────────────────────────────────────────────────
TREND_WINDOWS = [7, 14, 30]

# ── Group Definitions ───────────────────────────────────────────────────
GROUPS: dict[str, dict] = {
    "g1_onchain_valuation": {
        "label": "On-Chain Valuation",
        "weight": 0.30,
        "description": "MVRV, SOPR, NUPL, Exchange Reserve — valuation & holder behavior",
    },
    "g2_derivatives_sentiment": {
        "label": "Derivatives Sentiment",
        "weight": 0.25,
        "description": "Funding Rate, OI, Taker Ratio, Liquidations — leverage & futures positioning",
    },
    "g3_supply_flow": {
        "label": "Supply Flow",
        "weight": 0.25,
        "description": "Exchange Netflow, Stablecoin Reserve, Whale Ratio — supply/demand pressure",
    },
    "g4_technical_momentum": {
        "label": "Technical Momentum",
        "weight": 0.20,
        "description": "RSI, MACD, Price vs SMA-200 — price trend & momentum",
    },
}

# ── Indicator Definitions ────────────────────────────────────────────────
# Each indicator has:
#   file:       JSON filename in crypto-market-data (None = computed locally from price)
#   group:      parent group key
#   weight:     weight within the composite (sums to 1.0)
#   inverted:   True if high value = bearish (score flipped)
#   source:     "onchain" = from crypto-market-data, "technical" = computed from price closes
#   description: human-readable explanation
#   evidence:   research backing for this indicator
#   transform:  optional transform on raw value before scoring (e.g., "7d_ma", "7d_sum", "ratio_7d")

INDICATORS: dict[str, dict] = {
    # ── G1: On-Chain Valuation (30%) ─────────────────────────────────────
    "mvrv_z_score": {
        "file": "btc_mvrv_ratio.json",
        "group": "g1_onchain_valuation",
        "weight": 0.10,
        "inverted": True,  # high MVRV = overvalued = bearish
        "source": "onchain",
        "description": "MVRV Z-Score: market value vs realized value, normalized. High = overvalued.",
        "evidence": "Grobys et al.; CryptoQuant; LookIntoBitcoin — top/bottom predictor",
        "transform": None,
    },
    "sopr": {
        "file": None,  # computed from BG batch or proxy; not in crypto-market-data daily
        "group": "g1_onchain_valuation",
        "weight": 0.08,
        "inverted": True,  # SOPR > 1 = profit-taking = bearish pressure
        "source": "external",
        "description": "STH-SOPR: spent output profit ratio. >1 = selling at profit.",
        "evidence": "BitcoinFoundation 2026; Glassnode — profit-taking detection",
        "transform": None,
    },
    "nupl": {
        "file": None,  # derived from MVRV: NUPL = 1 - 1/MVRV
        "group": "g1_onchain_valuation",
        "weight": 0.07,
        "inverted": True,  # high NUPL = unrealized profit = potential selling
        "source": "derived",
        "description": "NUPL: net unrealized profit/loss. Derived from MVRV.",
        "evidence": "Correlated with MVRV (NUPL = 1 - 1/MVRV), cross-check validation",
        "transform": None,
    },
    "exchange_reserve": {
        "file": "btc_exchange_reserve.json",
        "group": "g1_onchain_valuation",
        "weight": 0.05,
        "inverted": True,  # rising reserve = more supply on exchanges = selling pressure
        "source": "onchain",
        "description": "BTC Exchange Reserve: total BTC held on exchanges.",
        "evidence": "On-chain supply pressure metric; rising = potential selling",
        "transform": "7d_ma",  # compare current to 7d MA for trend
    },

    # ── G2: Derivatives Sentiment (25%) ───────────────────────────────────
    "funding_rate": {
        "file": "btc_funding_rates.json",
        "group": "g2_derivatives_sentiment",
        "weight": 0.10,
        "inverted": True,  # high funding = overleveraged longs = bearish
        "source": "onchain",
        "description": "BTC Funding Rate (7d avg): cost of holding longs in futures.",
        "evidence": "WhalePortal: 'funding rates are most powerful'; real-time leverage sentiment",
        "transform": "7d_ma",
    },
    "taker_buy_sell_ratio": {
        "file": "btc_taker_buy_sell_ratio.json",
        "group": "g2_derivatives_sentiment",
        "weight": 0.08,
        "inverted": False,  # high ratio = more aggressive buying = bullish
        "source": "onchain",
        "description": "Taker Buy/Sell Ratio (7d avg): aggressive market buying vs selling.",
        "evidence": "Spot market pressure indicator; high = buyers in control",
        "transform": "7d_ma",
    },
    "liquidation_ratio": {
        "file": None,  # derived from long + short liquidations
        "group": "g2_derivatives_sentiment",
        "weight": 0.07,
        "inverted": False,  # high long liquidations = bearish already flushed = bullish recovery signal
        "source": "derived",
        "description": "Long/Short Liquidation Ratio: long liqs / (long + short liqs).",
        "evidence": "Crowded positioning + cascade risk detection",
        "transform": "7d_ma",
    },

    # ── G3: Supply Flow (25%) ────────────────────────────────────────────
    "exchange_netflow": {
        "file": "btc_exchange_netflow.json",
        "group": "g3_supply_flow",
        "weight": 0.10,
        "inverted": True,  # positive netflow = depositing to sell = bearish
        "source": "onchain",
        "description": "BTC Exchange Netflow (7d sum): inflow - outflow. Positive = selling pressure.",
        "evidence": "Chi et al. (2024): exchange flow predicts BTC returns significantly",
        "transform": "7d_sum",
    },
    "stablecoin_reserve": {
        "file": "stablecoin_exchange_reserve.json",
        "group": "g3_supply_flow",
        "weight": 0.08,
        "inverted": False,  # rising stablecoin reserve = dry powder for buying = bullish
        "source": "onchain",
        "description": "Stablecoin Exchange Reserve (7d change): proxy for incoming capital.",
        "evidence": "BitcoinFoundation 2026: 'stablecoin supply growth = proxy for incoming capital'",
        "transform": "7d_pct_change",
    },
    "whale_ratio": {
        "file": "btc_exchange_whale_ratio.json",
        "group": "g3_supply_flow",
        "weight": 0.07,
        "inverted": True,  # high whale ratio = whales depositing = potential selling
        "source": "onchain",
        "description": "Exchange Whale Ratio (7d avg): top 10 inflows / total inflows.",
        "evidence": "Whale activity → selling/buying pressure measurement",
        "transform": "7d_ma",
    },

    # ── G4: Technical Momentum (20%) ─────────────────────────────────────
    "rsi": {
        "file": None,  # computed from price data
        "group": "g4_technical_momentum",
        "weight": 0.07,
        "inverted": False,  # high RSI = bullish momentum
        "source": "technical",
        "description": "RSI-14: relative strength index.",
        "evidence": "Classic momentum indicator; used in every quantitative framework",
        "transform": None,
    },
    "macd_hist": {
        "file": None,  # computed from price data
        "group": "g4_technical_momentum",
        "weight": 0.07,
        "inverted": False,  # positive histogram = bullish momentum
        "source": "technical",
        "description": "MACD Histogram (7d MA trend): momentum direction and strength.",
        "evidence": "Trend confirmation; widely used in quantitative strategies",
        "transform": "7d_ma",
    },
    "price_vs_sma200": {
        "file": None,  # computed from price data
        "group": "g4_technical_momentum",
        "weight": 0.06,
        "inverted": False,  # price > SMA200 = bullish regime
        "source": "technical",
        "description": "Price vs SMA-200 ratio: regime detection (bull/bear).",
        "evidence": "Long-term trend indicator; institutional standard for regime detection",
        "transform": None,
    },
}

# ── Derived indicator source files (for computing derived metrics) ───────
DERIVED_SOURCES: dict[str, str] = {
    "liquidation_ratio": {
        "long_liqs": "btc_long_liquidations.json",
        "short_liqs": "btc_short_liquidations.json",
    },
}


def get_group_weight(group_key: str) -> float:
    """Return the weight of a group."""
    return GROUPS[group_key]["weight"]


def get_indicators_in_group(group_key: str) -> list[str]:
    """Return list of indicator keys belonging to a group."""
    return [k for k, v in INDICATORS.items() if v["group"] == group_key]


def get_onchain_files() -> list[str]:
    """Return list of JSON filenames to fetch from crypto-market-data."""
    files: list[str] = []
    for ind_def in INDICATORS.values():
        if ind_def["file"] is not None:
            files.append(ind_def["file"])
    # Also fetch derived source files
    for derived in DERIVED_SOURCES.values():
        for f in derived.values():
            if f not in files:
                files.append(f)
    return files


def get_zone(score: float) -> dict:
    """Return the zone dict for a given score."""
    for zone in SCORE_ZONES:
        if zone["min"] <= score < zone["max"]:
            return zone
    return SCORE_ZONES[-1]  # fallback to last zone


def validate_weights() -> bool:
    """Verify all weights sum to 1.0 within tolerance."""
    total = sum(v["weight"] for v in INDICATORS.values())
    return abs(total - 1.0) < 0.001
