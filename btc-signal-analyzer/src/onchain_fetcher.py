"""On-chain data fetcher for crypto-market-data (ErcinDedeoglu, CC BY 4.0).

Fetches daily JSON files from GitHub, caches locally, parses into
standardized time-series format. Handles all 27+ datasets.

Usage:
    from src.onchain_fetcher import OnchainFetcher
    f = OnchainFetcher()
    f.fetch_all()
    current = f.get_current("btc_exchange_netflow")
    history = f.get_history("btc_exchange_netflow", days=30)
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import config


# ── Constants ───────────────────────────────────────────────────────────
CACHE_DIR = Path(os.environ.get("SIGNAL_CACHE_DIR", "./cache"))
CACHE_TTL_SECONDS = 24 * 3600  # 24 hours
REQUEST_TIMEOUT = 30
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 2  # seconds


def _simple_rolling_mean(values: list[float], window: int) -> list[float]:
    """Compute rolling mean without pandas. Returns list same length as input (NaN-padded)."""
    result: list[float] = [float("nan")] * len(values)
    half_w = window // 2
    for i in range(half_w, len(values) - half_w):
        window_vals = values[i - half_w:i + half_w + 1]
        valid = [v for v in window_vals if not math.isnan(v)]
        if valid:
            result[i] = sum(valid) / len(valid)
    return result


def _rolling_sum(values: list[float], window: int) -> list[float]:
    """Compute rolling sum. Returns list same length (NaN-padded)."""
    result: list[float] = [float("nan")] * len(values)
    for i in range(window - 1, len(values)):
        window_vals = values[i - window + 1:i + 1]
        valid = [v for v in window_vals if not math.isnan(v)]
        if len(valid) == window:
            result[i] = sum(valid)
    return result


def _rolling_pct_change(values: list[float], window: int) -> list[float]:
    """Compute percentage change over window. result[i] = (val[i] - val[i-window]) / val[i-window]."""
    result: list[float] = [float("nan")] * len(values)
    for i in range(window, len(values)):
        if not math.isnan(values[i]) and not math.isnan(values[i - window]) and values[i - window] != 0:
            result[i] = (values[i] - values[i - window]) / abs(values[i - window]) * 100
    return result


class OnchainFetcher:
    """Fetch and parse on-chain data from crypto-market-data GitHub repo."""

    def __init__(self, base_url: Optional[str] = None, cache_dir: Optional[str] = None):
        self.base_url = base_url or config.DATA_SOURCE_BASE
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Raw parsed data: {filename: {"name": ..., "data": [{timestamp, value}, ...]}}
        self._raw: dict[str, dict] = {}
        self._fetch_log: list[str] = []
        self._errors: list[str] = []

    @property
    def fetch_log(self) -> list[str]:
        return list(self._fetch_log)

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    # ── Public API ───────────────────────────────────────────────────

    def fetch_all(self, files: Optional[list[str]] = None) -> None:
        """Fetch all required data files (or specified subset)."""
        target_files = files or config.get_onchain_files()
        self._fetch_log.append(f"[{self._ts()}] Fetching {len(target_files)} files...")

        for filename in target_files:
            self._fetch_file(filename)

        ok = len(self._raw)
        err = len(self._errors)
        self._fetch_log.append(f"[{self._ts()}] Done: {ok} OK, {err} errors")

    def get_current(self, filename: str) -> Optional[float]:
        """Get the latest value for a dataset."""
        parsed = self._raw.get(filename)
        if not parsed or not parsed["data"]:
            return None
        return parsed["data"][-1]["value"]

    def get_history(self, filename: str, days: int = 365) -> list[dict]:
        """Get last N days of data for a dataset.

        Returns list of {"timestamp": int, "date": str, "value": float}.
        """
        parsed = self._raw.get(filename)
        if not parsed or not parsed["data"]:
            return []
        return parsed["data"][-days:]

    def get_all_current(self) -> dict[str, Optional[float]]:
        """Get current values for all fetched datasets."""
        return {k: self.get_current(k) for k in self._raw}

    def get_values_array(self, filename: str, days: int = 400) -> list[float]:
        """Get raw values array for a dataset (for scoring computations)."""
        parsed = self._raw.get(filename)
        if not parsed or not parsed["data"]:
            return []
        return [p["value"] for p in parsed["data"][-days:]]

    def get_timestamps_array(self, filename: str, days: int = 400) -> list[int]:
        """Get timestamps array for a dataset."""
        parsed = self._raw.get(filename)
        if not parsed or not parsed["data"]:
            return []
        return [p["timestamp"] for p in parsed["data"][-days:]]

    def get_transformed(self, filename: str, transform: str, days: int = 400) -> list[float]:
        """Get values after applying a transform (7d_ma, 7d_sum, 7d_pct_change)."""
        raw = self.get_values_array(filename, days)
        if not raw:
            return []

        if transform == "7d_ma":
            return _simple_rolling_mean(raw, 7)
        elif transform == "7d_sum":
            return _rolling_sum(raw, 7)
        elif transform == "7d_pct_change":
            return _rolling_pct_change(raw, 7)
        else:
            return raw

    def get_derived_ratio(
        self, numerator_file: str, denominator_file: str, days: int = 400
    ) -> list[float]:
        """Compute ratio of two datasets: numerator/denominator.

        Used for liquidation_ratio = long_liqs / (long_liqs + short_liqs).
        """
        num = self.get_values_array(numerator_file, days)
        den = self.get_values_array(denominator_file, days)
        if not num or not den or len(num) != len(den):
            return []

        result: list[float] = []
        for n, d in zip(num, den):
            total = n + d
            if total != 0 and not math.isnan(n) and not math.isnan(d):
                result.append(n / total)
            else:
                result.append(float("nan"))
        return result

    def get_metric_series(self, indicator_key: str, days: int = 400) -> list[float]:
        """Get the final value series for an indicator (applying transform/derivation as needed).

        This is the main entry point for the scoring engine.
        """
        ind_def = config.INDICATORS.get(indicator_key)
        if not ind_def:
            self._errors.append(f"Unknown indicator: {indicator_key}")
            return []

        # External/derived metrics not from crypto-market-data
        if ind_def["source"] in ("external", "derived", "technical"):
            return []  # handled by signal_score.py

        filename = ind_def["file"]
        transform = ind_def.get("transform")

        if filename is None:
            return []

        if transform:
            return self.get_transformed(filename, transform, days)
        return self.get_values_array(filename, days)

    def get_metric_current(self, indicator_key: str) -> Optional[float]:
        """Get the latest single value for an indicator."""
        series = self.get_metric_series(indicator_key)
        if not series:
            return None
        # Return the last non-NaN value
        for v in reversed(series):
            if not math.isnan(v):
                return v
        return None

    def get_available_indicators(self) -> list[str]:
        """Return list of indicator keys that have data available."""
        available = []
        for key, ind_def in config.INDICATORS.items():
            if ind_def["source"] in ("external", "derived", "technical"):
                continue
            if ind_def["file"] and ind_def["file"] in self._raw:
                available.append(key)
        return available

    def get_data_info(self) -> dict[str, Any]:
        """Get summary of all fetched data for debugging."""
        info: dict[str, Any] = {
            "fetched_at": self._ts(),
            "files": {},
            "indicators_available": self.get_available_indicators(),
            "errors": self._errors,
        }
        for filename, parsed in self._raw.items():
            data = parsed.get("data", [])
            last_ts = data[-1]["timestamp"] if data else None
            info["files"][filename] = {
                "points": len(data),
                "last_date": self._ts_ms(last_ts) if last_ts else None,
                "last_value": data[-1]["value"] if data else None,
            }
        return info

    # ── Internal ─────────────────────────────────────────────────────

    def _fetch_file(self, filename: str) -> None:
        """Fetch a single file (cache or remote)."""
        cache_path = self.cache_dir / filename

        # Try cache first
        if self._cache_valid(cache_path):
            self._load_cache(cache_path, filename)
            return

        # Fetch from remote with retries
        url = f"{self.base_url}/{filename}"
        data = self._fetch_remote(url, filename)
        if data:
            self._raw[filename] = data
            self._save_cache(cache_path, data)
            points = len(data.get("data", []))
            self._fetch_log.append(f"  [OK] {filename}: {points} points (fetched)")

    def _cache_valid(self, path: Path) -> bool:
        """Check if cache file exists and is fresh."""
        if not path.exists():
            return False
        age = time.time() - path.stat().st_mtime
        return age < CACHE_TTL_SECONDS

    def _load_cache(self, path: Path, filename: str) -> None:
        """Load and parse cached file."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
            self._raw[filename] = data
            points = len(data.get("data", []))
            self._fetch_log.append(f"  [CACHE] {filename}: {points} points")
        except Exception as e:
            self._errors.append(f"Cache load error {filename}: {e}")
            self._fetch_log.append(f"  [CACHE-ERR] {filename}: {e}")

    def _save_cache(self, path: Path, data: dict) -> None:
        """Save parsed data to cache."""
        try:
            with open(path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            self._errors.append(f"Cache save error: {e}")

    def _fetch_remote(self, url: str, filename: str) -> Optional[dict]:
        """Fetch JSON from remote URL with retries."""
        import urllib.request
        import urllib.error

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "btc-signal-analyzer/1.0"},
                )
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                    raw = resp.read()
                    data = json.loads(raw)

                    # Validate structure
                    if "data" not in data or not isinstance(data["data"], list):
                        raise ValueError("Invalid data structure: missing 'data' array")

                    # Normalize: ensure each point has timestamp and value
                    normalized_points = []
                    for point in data["data"]:
                        ts = point.get("timestamp", 0)
                        val = point.get("value")
                        if val is None:
                            continue
                        normalized_points.append({
                            "timestamp": int(ts),
                            "value": float(val),
                        })

                    data["data"] = normalized_points
                    return data

            except urllib.error.HTTPError as e:
                self._errors.append(f"HTTP {e.code} for {filename} (attempt {attempt})")
            except (json.JSONDecodeError, ValueError) as e:
                self._errors.append(f"Parse error {filename}: {e}")
                return None  # Don't retry parse errors
            except Exception as e:
                self._errors.append(f"Fetch error {filename} (attempt {attempt}): {e}")

            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BACKOFF * attempt)

        self._fetch_log.append(f"  [FAIL] {filename}: all {RETRY_ATTEMPTS} attempts failed")
        return None

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    @staticmethod
    def _ts_ms(ms: int) -> str:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def ts_to_date(ts_ms: int) -> str:
        """Convert millisecond timestamp to date string."""
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
