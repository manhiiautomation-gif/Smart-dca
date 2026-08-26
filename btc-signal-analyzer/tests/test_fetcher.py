"""Tests for onchain_fetcher — no network calls, only parsing and transforms."""

import json
import math
import os
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.onchain_fetcher import (
    OnchainFetcher,
    _simple_rolling_mean,
    _rolling_sum,
    _rolling_pct_change,
)

# Alias for test compatibility
_rolling_mean = _simple_rolling_mean


# ── Mock data generator ──────────────────────────────────────────────

def _make_mock_json(filename: str, n_points: int = 100) -> dict:
    """Create a mock crypto-market-data JSON file."""
    import time
    now_ms = int(time.time() * 1000)
    day_ms = 86400000
    data = []
    base_val = 100.0
    for i in range(n_points):
        ts = now_ms - (n_points - 1 - i) * day_ms
        # Slight upward trend with noise
        val = base_val + i * 0.5 + (i % 7 - 3) * 2
        data.append({"timestamp": ts, "value": val})
    return {
        "name": f"Test {filename}",
        "data": data,
        "last_data_date": data[-1]["timestamp"] if data else 0,
    }


def _write_mock_files(tmpdir: str, filenames: list[str], n_points: int = 400):
    """Write mock JSON files to tmpdir."""
    paths = {}
    for fn in filenames:
        data = _make_mock_json(fn, n_points)
        path = os.path.join(tmpdir, fn)
        with open(path, "w") as f:
            json.dump(data, f)
        paths[fn] = path
    return paths


# ── Tests ────────────────────────────────────────────────────────────

class TestRollingTransforms:
    def test_simple_rolling_mean(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        result = _simple_rolling_mean(values, 3)
        # Index 1 (half of 3-1=2) should have mean of [1,2,3] = 2
        assert not math.isnan(result[1])
        assert result[1] == 2.0
        assert result[2] == 3.0
        assert result[3] == 4.0

    def test_rolling_sum(self):
        values = list(range(1, 8))  # 1..7
        result = _rolling_sum(values, 3)
        # First 2 should be NaN
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        # Index 2: 1+2+3 = 6
        assert result[2] == 6.0
        # Index 3: 2+3+4 = 9
        assert result[3] == 9.0

    def test_rolling_pct_change(self):
        values = [100, 110, 105, 115, 120]
        result = _rolling_pct_change(values, 2)
        assert math.isnan(result[0])
        # Index 2: (105 - 100) / 100 * 100 = 5.0
        assert abs(result[2] - 5.0) < 0.01
        # Index 3: (115 - 110) / 110 * 100 ≈ 4.545
        assert abs(result[3] - 4.545) < 0.1

    def test_empty_input(self):
        assert _simple_rolling_mean([], 7) == []
        assert _rolling_sum([], 7) == []
        assert _rolling_pct_change([], 7) == []

    def test_nan_handling(self):
        values = [1.0, float("nan"), 3.0, 4.0, 5.0]
        result = _simple_rolling_mean(values, 3)
        # Should skip NaN in window
        # No assertion on exact value, just should not crash
        assert len(result) == len(values)


class TestOnchainFetcher:
    def test_load_from_cache(self):
        """Test loading pre-written JSON files from cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filenames = ["btc_exchange_netflow.json", "btc_funding_rates.json"]
            _write_mock_files(tmpdir, filenames, n_points=400)

            fetcher = OnchainFetcher(cache_dir=tmpdir)
            # Directly load cache by triggering fetch (cache is fresh)
            fetcher.fetch_all(filenames)

            assert len(fetcher.errors) == 0
            assert fetcher.get_current("btc_exchange_netflow.json") is not None

    def test_get_values_array(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filenames = ["btc_exchange_netflow.json"]
            _write_mock_files(tmpdir, filenames, n_points=400)

            fetcher = OnchainFetcher(cache_dir=tmpdir)
            fetcher.fetch_all(filenames)

            values = fetcher.get_values_array("btc_exchange_netflow.json", days=30)
            assert len(values) == 30
            assert all(isinstance(v, float) for v in values)

    def test_get_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filenames = ["btc_exchange_netflow.json"]
            _write_mock_files(tmpdir, filenames, n_points=400)

            fetcher = OnchainFetcher(cache_dir=tmpdir)
            fetcher.fetch_all(filenames)

            history = fetcher.get_history("btc_exchange_netflow.json", days=10)
            assert len(history) == 10
            assert "timestamp" in history[0]
            assert "value" in history[0]

    def test_derived_ratio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filenames = ["btc_long_liquidations.json", "btc_short_liquidations.json"]
            _write_mock_files(tmpdir, filenames, n_points=100)

            fetcher = OnchainFetcher(cache_dir=tmpdir)
            fetcher.fetch_all(filenames)

            ratio = fetcher.get_derived_ratio(
                "btc_long_liquidations.json",
                "btc_short_liquidations.json",
                days=50,
            )
            assert len(ratio) == 50
            # All ratios should be between 0 and 1
            for r in ratio:
                assert 0 <= r <= 1.0 or math.isnan(r)

    def test_transformed_7d_ma(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filenames = ["btc_exchange_reserve.json"]
            _write_mock_files(tmpdir, filenames, n_points=400)

            fetcher = OnchainFetcher(cache_dir=tmpdir)
            fetcher.fetch_all(filenames)

            transformed = fetcher.get_transformed("btc_exchange_reserve.json", "7d_ma", days=400)
            assert len(transformed) == 400
            # First few should be NaN (edge padding)
            assert math.isnan(transformed[0])
            # Last values should be valid (within edge padding)
            # With 400 points and window=7, last 3 should be valid
            assert not math.isnan(transformed[-4])

    def test_data_info(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filenames = ["btc_exchange_netflow.json"]
            _write_mock_files(tmpdir, filenames, n_points=100)

            fetcher = OnchainFetcher(cache_dir=tmpdir)
            fetcher.fetch_all(filenames)

            info = fetcher.get_data_info()
            assert "btc_exchange_netflow.json" in info["files"]
            assert info["files"]["btc_exchange_netflow.json"]["points"] == 100


if __name__ == "__main__":
    import unittest
    unittest.main()
