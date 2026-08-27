"""Signal Score computation: normalize, weight, and composite 0-100 score.

Evidence-based scoring framework:
- Each indicator normalized via percentile rank over N-day window
- Raw score mapped to [-1, +1] (bearish → bullish)
- Weighted composite → [0, 100]

Based on:
- Fear & Greed Index methodology (weighted composite)
- Omole et al. (2024): Boruta feature selection for weights
- Chi et al. (2024): exchange flow predictive power
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Optional

from . import config
from .onchain_fetcher import OnchainFetcher


# ── Technical indicator helpers (no pandas/numpy dependency) ──────────


def _sma(values: list[float], period: int) -> list[float]:
    """Simple Moving Average series."""
    result: list[float] = [float("nan")] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        valid = [v for v in window if not math.isnan(v)]
        if valid:
            result[i] = sum(valid) / len(valid)
    return result


def _ema_single(values: list[float], period: int) -> float:
    """EMA of the last value."""
    if not values:
        return float("nan")
    k = 2.0 / (period + 1)
    val = float(values[0])
    for v in values[1:]:
        val = v * k + val * (1 - k)
    return val


def _rsi_series(values: list[float], period: int = 14) -> list[float]:
    """RSI series (Wilder smoothing)."""
    if len(values) < period + 1:
        return [float("nan")] * len(values)

    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    alpha = 1.0 / period
    result: list[float] = [float("nan")] * (period + 1)

    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100.0 - 100.0 / (1.0 + rs))

    for i in range(period, len(gains)):
        avg_gain = (1 - alpha) * avg_gain + alpha * gains[i]
        avg_loss = (1 - alpha) * avg_loss + alpha * losses[i]
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100.0 - 100.0 / (1.0 + rs))

    return result


def _macd_histogram_series(
    values: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> list[float]:
    """MACD histogram series."""
    if len(values) < slow + signal:
        return [float("nan")] * len(values)

    ema_fast = _ema_series(values, fast)
    ema_slow = _ema_series(values, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    sig = _ema_series(macd_line, signal)
    return [m - s for m, s in zip(macd_line, sig)]


def _ema_series(data: list[float], period: int) -> list[float]:
    """Full EMA series."""
    if not data:
        return []
    k = 2.0 / (period + 1)
    result = [float(data[0])]
    for v in data[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _rolling_mean(series: list[float], window: int) -> list[float]:
    """Rolling mean for smoothing."""
    result: list[float] = [float("nan")] * len(series)
    half = window // 2
    for i in range(half, len(series) - half):
        chunk = series[i - half : i + half + 1]
        valid = [v for v in chunk if not math.isnan(v)]
        if valid:
            result[i] = sum(valid) / len(valid)
    return result


# ── Percentile rank ────────────────────────────────────────────────────


def _percentile_rank(value: float, reference: list[float]) -> float:
    """Rank of value within reference list. Returns 0.0-1.0.

    Uses the empirical CDF method: fraction of reference values <= value.
    """
    if not reference or math.isnan(value):
        return float("nan")

    valid = [v for v in reference if not math.isnan(v)]
    if not valid:
        return float("nan")

    count_le = sum(1 for v in valid if v <= value)
    return count_le / len(valid)


def _percentile_rank_series(series: list[float], window: int) -> list[float]:
    """Rolling percentile rank for a series.

    For each point, compute its rank within the preceding `window` values.
    """
    result: list[float] = [float("nan")] * len(series)
    for i in range(window, len(series)):
        ref = series[i - window : i]
        result[i] = _percentile_rank(series[i], ref)
    return result


# ── Score computation ─────────────────────────────────────────────────


class SignalScorer:
    """Compute composite BTC Signal Score from on-chain + technical indicators.

    Usage:
        scorer = SignalScorer(fetcher)
        result = scorer.compute()
        # result["score"] = 65.2
        # result["zone"]["label"] = "Greed"
        # result["indicators"]["mvrv_z_score"] = {...}
    """

    def __init__(self, fetcher: OnchainFetcher, price_closes: Optional[list[float]] = None):
        self.fetcher = fetcher
        self.price_closes = price_closes or []
        self._metric_series_cache: dict[str, list[float]] = {}
        self._warnings: list[str] = []

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    def compute(self) -> dict[str, Any]:
        """Compute full signal score with breakdown.

        Returns dict with: score, zone, breakdown, indicators, trend_*d, meta.
        """
        # 1. Prepare all metric series
        indicator_scores: dict[str, dict] = {}
        group_scores: dict[str, dict] = {}

        for group_key, group_def in config.GROUPS.items():
            group_indicators = config.get_indicators_in_group(group_key)
            group_score = 0.0
            group_valid = False

            for ind_key in group_indicators:
                ind_def = config.INDICATORS[ind_key]
                ind_score = self._score_indicator(ind_key)
                indicator_scores[ind_key] = ind_score

                if ind_score["available"] and not math.isnan(ind_score["weighted_score"]):
                    group_score += ind_score["weighted_score"]
                    group_valid = True

            # Scale group score to group weight
            if group_valid:
                group_scores[group_key] = {
                    "score": round(group_score / group_def["weight"], 2) if group_def["weight"] > 0 else 0,
                    "weight": group_def["weight"],
                    "label": group_def["label"],
                    "description": group_def["description"],
                    "indicators": {
                        k: indicator_scores[k]
                        for k in config.get_indicators_in_group(group_key)
                    },
                }
            else:
                group_scores[group_key] = {
                    "score": None,
                    "weight": group_def["weight"],
                    "label": group_def["label"],
                    "description": group_def["description"],
                    "indicators": {
                        k: indicator_scores[k]
                        for k in config.get_indicators_in_group(group_key)
                    },
                }

        # 2. Composite score
        composite = sum(
            gs["score"] * gs["weight"]
            for gs in group_scores.values()
            if gs["score"] is not None
        )

        # Map to 0-100
        # composite is in [-1, +1] range (weighted sum of raw_scores)
        # Clamp to [-1, +1] first, then map
        composite = max(-1.0, min(1.0, composite))
        final_score = round(composite * 50 + 50, 1)

        # 3. Zone
        zone = config.get_zone(final_score)

        # 4. Trends
        trends = self._compute_trends()

        # 5. Meta
        total_indicators = len(config.INDICATORS)
        available_count = sum(1 for s in indicator_scores.values() if s["available"])

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": final_score,
            "zone": {
                "label": zone["label"],
                "min": zone["min"],
                "max": zone["max"],
                "color": zone["color"],
            },
            "breakdown": group_scores,
            "indicators": indicator_scores,
            "trend_7d": trends.get(7, []),
            "trend_14d": trends.get(14, []),
            "trend_30d": trends.get(30, []),
            "meta": {
                "total_indicators": total_indicators,
                "available_indicators": available_count,
                "missing_indicators": total_indicators - available_count,
                "percentile_window": config.PERCENTILE_WINDOW,
                "warnings": self._warnings,
                "attribution": config.ATTRIBUTION,
            },
        }

    def _score_indicator(self, ind_key: str) -> dict[str, Any]:
        """Score a single indicator.

        Returns: {available, value, percentile, raw_score, weighted_score, inverted, source}
        """
        ind_def = config.INDICATORS[ind_key]
        series = self._get_metric_series(ind_key)
        window = config.PERCENTILE_WINDOW

        result: dict[str, Any] = {
            "available": False,
            "value": None,
            "percentile": None,
            "raw_score": None,
            "weighted_score": float("nan"),
            "inverted": ind_def["inverted"],
            "source": ind_def["source"],
            "description": ind_def["description"],
            "evidence": ind_def["evidence"],
        }

        if not series or len(series) < window + 1:
            result["value"] = series[-1] if series else None
            self._warnings.append(f"{ind_key}: insufficient data ({len(series) if series else 0} points, need {window + 1})")
            return result

        # Get current value (last non-NaN)
        current_val = None
        for v in reversed(series):
            if not math.isnan(v):
                current_val = v
                break

        if current_val is None:
            self._warnings.append(f"{ind_key}: all NaN values")
            return result

        result["value"] = round(current_val, 6)
        result["available"] = True

        # Compute percentile rank
        pct = _percentile_rank_series(series, window)
        current_pct = None
        for v in reversed(pct):
            if not math.isnan(v):
                current_pct = v
                break

        if current_pct is None:
            self._warnings.append(f"{ind_key}: no valid percentile")
            return result

        result["percentile"] = round(current_pct, 4)

        # Map percentile to raw score [-1, +1]
        raw_score = 2.0 * current_pct - 1.0

        # Invert if needed (high value = bearish)
        if ind_def["inverted"]:
            raw_score = -raw_score

        result["raw_score"] = round(raw_score, 4)
        result["weighted_score"] = round(raw_score * ind_def["weight"], 4)

        return result

    def _get_metric_series(self, ind_key: str) -> list[float]:
        """Get or compute the value series for an indicator."""
        if ind_key in self._metric_series_cache:
            return self._metric_series_cache[ind_key]

        ind_def = config.INDICATORS[ind_key]
        series: list[float] = []

        if ind_def["source"] == "onchain":
            series = self.fetcher.get_metric_series(ind_key, days=500)

        elif ind_def["source"] == "derived":
            series = self._compute_derived(ind_key)

        elif ind_def["source"] == "technical":
            series = self._compute_technical(ind_key)

        elif ind_def["source"] == "external":
            # SOPR from external source — not available in Phase 1
            self._warnings.append(
                f"{ind_key}: external source, not available in Phase 1. "
                f"Will use proxy or omit from score."
            )

        self._metric_series_cache[ind_key] = series
        return series

    def _compute_derived(self, ind_key: str) -> list[float]:
        """Compute derived indicators from fetched data."""
        if ind_key == "nupl":
            # NUPL = 1 - 1/MVRV
            mvrv_series = self.fetcher.get_metric_series("mvrv_z_score", days=500)
            # mvrv_z_score in config actually points to btc_mvrv_ratio.json (ratio, not z-score)
            # NUPL = 1 - 1/MVRV
            result: list[float] = []
            for v in mvrv_series:
                if v and not math.isnan(v) and v != 0:
                    result.append(1.0 - 1.0 / v)
                else:
                    result.append(float("nan"))
            return result

        elif ind_key == "liquidation_ratio":
            # long_liqs / (long_liqs + short_liqs)
            src = config.DERIVED_SOURCES.get("liquidation_ratio", {})
            return self.fetcher.get_derived_ratio(
                src["long_liqs"], src["short_liqs"], days=500
            )

        return []

    def _compute_technical(self, ind_key: str) -> list[float]:
        """Compute technical indicators from price closes."""
        if not self.price_closes:
            return []

        closes = self.price_closes
        ind_def = config.INDICATORS[ind_key]
        transform = ind_def.get("transform")

        if ind_key == "rsi":
            series = _rsi_series(closes, 14)
            return _rolling_mean(series, 7) if transform == "7d_ma" else series

        elif ind_key == "macd_hist":
            series = _macd_histogram_series(closes)
            return _rolling_mean(series, 7) if transform == "7d_ma" else series

        elif ind_key == "price_vs_sma200":
            sma200 = _sma(closes, 200)
            result: list[float] = []
            for c, s in zip(closes, sma200):
                if not math.isnan(s) and s > 0:
                    result.append(c / s)
                else:
                    result.append(float("nan"))
            return result

        return []

    def _compute_trends(self) -> dict[int, list]:
        """Compute historical score trends for 7d, 14d, 30d.

        Re-runs scoring for each historical day (simplified: uses
        current percentile windows, not point-in-time — acceptable
        for trend visualization, not for backtest).
        """
        trends: dict[int, list] = {}
        window = config.PERCENTILE_WINDOW

        for days in config.TREND_WINDOWS:
            trend_scores: list[float] = []

            # Collect all indicator series
            all_series: dict[str, list[float]] = {}
            for ind_key in config.INDICATORS:
                series = self._get_metric_series(ind_key)
                if series and len(series) >= window + 1:
                    all_series[ind_key] = series

            if not all_series:
                trends[days] = []
                continue

            # Find the minimum length
            min_len = min(len(s) for s in all_series.values())
            start_idx = max(0, min_len - days)

            for i in range(start_idx, min_len):
                day_score = 0.0
                day_weight_sum = 0.0

                for ind_key, series in all_series.items():
                    ind_def = config.INDICATORS[ind_key]
                    if i < window:
                        continue
                    val = series[i]
                    if math.isnan(val):
                        continue
                    ref = series[i - window : i]
                    pct = _percentile_rank(val, ref)
                    if math.isnan(pct):
                        continue
                    raw = 2.0 * pct - 1.0
                    if ind_def["inverted"]:
                        raw = -raw
                    day_score += raw * ind_def["weight"]
                    day_weight_sum += ind_def["weight"]

                if day_weight_sum > 0:
                    normalized = day_score / day_weight_sum
                    normalized = max(-1.0, min(1.0, normalized))
                    trend_scores.append(round(normalized * 50 + 50, 1))

            trends[days] = trend_scores

        return trends


def compute_signal_score(
    fetcher: OnchainFetcher,
    price_closes: Optional[list[float]] = None,
) -> dict[str, Any]:
    """Convenience function: fetch data + compute score in one call.

    Returns the full score result dict.
    """
    scorer = SignalScorer(fetcher, price_closes=price_closes)
    return scorer.compute()


def main():
    """CLI entry point: fetch data, compute score, print summary, save JSON."""
    import sys

    print("=== BTC Signal Analyzer ===")
    print(f"Data source: {config.ATTRIBUTION}")
    print(f"Indicators: {len(config.INDICATORS)} ({config.get_onchain_files().__len__()} data files)")
    print(f"Weight validation: {'PASS' if config.validate_weights() else 'FAIL'}")
    print()

    # 1. Fetch data
    print("[1/3] Fetching on-chain data...")
    fetcher = OnchainFetcher()
    fetcher.fetch_all()
    for line in fetcher.fetch_log:
        print(f"  {line}")
    if fetcher.errors:
        print(f"  ERRORS ({len(fetcher.errors)}):")
        for e in fetcher.errors:
            print(f"    {e}")
    print()

    # 2. Compute score
    print("[2/3] Computing signal score...")
    scorer = SignalScorer(fetcher)
    result = scorer.compute()
    print()

    # 3. Print summary
    print(f"[3/3] Result:")
    print(f"  Signal Score: {result['score']}/100 ({result['zone']['label']})")
    print(f"  Indicators: {result['meta']['available_indicators']}/{result['meta']['total_indicators']} available")
    if scorer.warnings:
        print(f"  Warnings ({len(scorer.warnings)}):")
        for w in scorer.warnings:
            print(f"    - {w}")
    print()

    # Group breakdown
    print("  Group Breakdown:")
    for gk, gv in result["breakdown"].items():
        score_str = f"{gv['score']}" if gv['score'] is not None else "N/A"
        print(f"    {gv['label']:30s} {score_str:>6s} (weight: {gv['weight']:.0%})")
    print()

    # Indicator detail
    print("  Indicator Detail:")
    for ik, iv in result["indicators"].items():
        if iv["available"]:
            direction = "BEARISH" if iv.get("raw_score", 0) < -0.2 else ("BULLISH" if iv.get("raw_score", 0) > 0.2 else "NEUTRAL")
            print(
                f"    {ik:30s} val={iv['value']:>12}  pct={iv['percentile']:.2f}  "
                f"raw={iv['raw_score']:+.3f}  wt={iv['weighted_score']:+.4f}  {direction}"
            )
        else:
            print(f"    {ik:30s} UNAVAILABLE")
    print()

    # Trends
    for days in config.TREND_WINDOWS:
        trend = result.get(f"trend_{days}d", [])
        if trend:
            print(f"  Trend {days}d: {trend[0]:.1f} -> {trend[-1]:.1f} ({'up' if trend[-1] > trend[0] else 'down'})")
    print()

    # 4. Save output
    output_dir = os.environ.get("SIGNAL_OUTPUT_DIR", "./output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "signal_score.json")
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  Output saved to: {output_path}")

    return result


if __name__ == "__main__":
    main()
