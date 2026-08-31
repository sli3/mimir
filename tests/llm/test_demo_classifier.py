"""
tests/llm/test_demo_classifier.py
Mimir RF Scanner — Phase 76 Demo Signal Classifier Tests

PURPOSE
-------
Tests for the cache-backed ``DemoSignalClassifier`` used in ``--demo``
mode. Proves it loads caches safely, returns cached
``ClassificationResult`` objects, falls back gracefully, and never
touches the network.

Run with:
    uv run pytest tests/llm/test_demo_classifier.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm.classifier import ClassificationResult
from llm.demo_classifier import DemoSignalClassifier


# ── Shared helpers ─────────────────────────────────────────────────────────

def _make_classification_result() -> ClassificationResult:
    """Return a realistic cached ClassificationResult."""
    return ClassificationResult(
        signal_type="fm_broadcast",
        confidence="high",
        confidence_score=0.94,
        novel=False,
        reasoning="Strong match to FM broadcast at 98 MHz.",
        au_legal_status="legal_rx",
        frequency_band="fm_broadcast_band",
        raw_response='{"signal_type": "fm_broadcast"}',
    )


def _make_cache_dict(file_id: str = "abc", chunk_idx: str = "5") -> dict:
    """Build a minimal valid cache dict around one chunk entry."""
    result = _make_classification_result()
    return {
        "version": 1,
        "device_driver": "hackrf",
        "files": {
            file_id: {
                "path": "/tmp/demo.sigmf-meta",
                "device_profile": "hackrf",
                "chunks": {
                    chunk_idx: {
                        "signal_type": result.signal_type,
                        "confidence": result.confidence,
                        "confidence_score": result.confidence_score,
                        "novel": result.novel,
                        "reasoning": result.reasoning,
                        "au_legal_status": result.au_legal_status,
                        "frequency_band": result.frequency_band,
                        "raw_response": result.raw_response,
                    }
                },
            }
        },
    }


def _write_cache(path: Path, data: dict) -> None:
    """Write a cache dict to disk as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def fingerprint() -> dict:
    """A fingerprint carrying a valid demo key."""
    return {
        "center_freq_hz": 98_000_000,
        "peak_freq_hz": 98_000_000,
        "peak_power_db": -23.4,
        "noise_floor_db": -80.0,
        "snr_db": 42.0,
        "bandwidth_hz": 200_000,
        "occupied_bins": 200,
        "spectral_flatness": 0.021,
        "mimir:demo_key": "abc:5",
    }


# ── Constructor tests ────────────────────────────────────────────────────────

class TestDemoClassifierConstructor:
    """Tests for DemoSignalClassifier cache loading."""

    def test_valid_cache_populates_cache(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path, _make_cache_dict())

        classifier = DemoSignalClassifier(cache_path=cache_path)

        assert "abc" in classifier._cache["files"]
        assert "5" in classifier._cache["files"]["abc"]["chunks"]

    def test_missing_file_results_in_empty_cache(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "does_not_exist.json"
        classifier = DemoSignalClassifier(cache_path=cache_path)

        assert classifier._cache == {}

    def test_malformed_json_results_in_empty_cache(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "bad_cache.json"
        cache_path.write_text("this is not json", encoding="utf-8")

        classifier = DemoSignalClassifier(cache_path=cache_path)

        assert classifier._cache == {}

    def test_oversized_cache_results_in_empty_cache_with_warning(
        self, tmp_path: Path, caplog
    ) -> None:
        cache_path = tmp_path / "huge_cache.json"
        # Pad the cache to just over the 50 MB cap.
        _write_cache(cache_path, _make_cache_dict())
        existing = cache_path.read_bytes()
        cache_path.write_bytes(existing + b" " * (50_000_001 - len(existing)))

        with caplog.at_level("WARNING", logger="llm.demo_classifier"):
            classifier = DemoSignalClassifier(cache_path=cache_path)

        assert classifier._cache == {}
        assert "exceeding" in caplog.text


# ── check_connection tests ───────────────────────────────────────────────────

class TestDemoClassifierCheckConnection:
    """Tests for DemoSignalClassifier.check_connection()."""

    def test_check_connection_returns_true(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path, _make_cache_dict())
        classifier = DemoSignalClassifier(cache_path=cache_path)

        assert classifier.check_connection() is True

    @patch("llm.classifier.requests.get")
    def test_check_connection_makes_no_network_call(
        self, mock_get, tmp_path: Path
    ) -> None:
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path, _make_cache_dict())
        classifier = DemoSignalClassifier(cache_path=cache_path)

        classifier.check_connection()

        mock_get.assert_not_called()


# ── classify tests ───────────────────────────────────────────────────────────

class TestDemoClassifierClassify:
    """Tests for DemoSignalClassifier.classify()."""

    def test_cache_hit_returns_classification_result(
        self, tmp_path: Path, fingerprint: dict
    ) -> None:
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path, _make_cache_dict())
        classifier = DemoSignalClassifier(cache_path=cache_path)

        result = classifier.classify(fingerprint, [])

        assert isinstance(result, ClassificationResult)
        assert result.signal_type == "fm_broadcast"
        assert result.confidence == "high"
        assert result.confidence_score == 0.94
        assert result.reasoning == "Strong match to FM broadcast at 98 MHz."

    def test_cache_miss_returns_fallback_with_specific_reason(
        self, tmp_path: Path, fingerprint: dict
    ) -> None:
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path, _make_cache_dict())
        classifier = DemoSignalClassifier(cache_path=cache_path)
        fingerprint["mimir:demo_key"] = "abc:99"

        result = classifier.classify(fingerprint, [])

        assert result.signal_type == "unavailable"
        assert result.confidence == "low"
        assert result.confidence_score == 0.0
        assert "Demo cache miss for key abc:99" in result.reasoning
        assert "chunk not covered" in result.reasoning

    def test_missing_demo_key_returns_fallback_with_specific_reason(
        self, tmp_path: Path, fingerprint: dict
    ) -> None:
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path, _make_cache_dict())
        classifier = DemoSignalClassifier(cache_path=cache_path)
        fingerprint.pop("mimir:demo_key")

        result = classifier.classify(fingerprint, [])

        assert result.signal_type == "unavailable"
        assert result.confidence == "low"
        assert result.confidence_score == 0.0
        assert "Demo cache key missing" in result.reasoning
        assert "mimir:demo_key" in result.reasoning

    def test_malformed_cache_entry_returns_fallback(
        self, tmp_path: Path, fingerprint: dict
    ) -> None:
        cache_path = tmp_path / "demo_cache.json"
        cache = _make_cache_dict()
        # Remove a required ClassificationResult field to make the entry
        # malformed.
        del cache["files"]["abc"]["chunks"]["5"]["confidence_score"]
        _write_cache(cache_path, cache)
        classifier = DemoSignalClassifier(cache_path=cache_path)

        result = classifier.classify(fingerprint, [])

        assert result.signal_type == "unavailable"
        assert result.confidence == "low"
        assert result.confidence_score == 0.0
        assert "malformed" in result.reasoning.lower()

    def test_fallback_never_fabricates_verdict(
        self, tmp_path: Path, fingerprint: dict
    ) -> None:
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path, _make_cache_dict())
        classifier = DemoSignalClassifier(cache_path=cache_path)
        fingerprint["mimir:demo_key"] = "missing:0"

        result = classifier.classify(fingerprint, [])

        assert result.signal_type == "unavailable"
        assert result.confidence == "low"
        assert result.confidence_score == 0.0


# ── Wire-level no-HTTP test ──────────────────────────────────────────────────

class TestDemoClassifierNoNetwork:
    """Wire-level proof that DemoSignalClassifier never calls requests."""

    @patch("llm.classifier.requests.post")
    @patch("llm.classifier.requests.get")
    def test_classify_never_calls_requests(
        self, mock_get, mock_post, tmp_path: Path, fingerprint: dict
    ) -> None:
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path, _make_cache_dict())
        classifier = DemoSignalClassifier(cache_path=cache_path)

        # Hit path.
        classifier.classify(fingerprint, [])
        # Miss path.
        fingerprint["mimir:demo_key"] = "abc:99"
        classifier.classify(fingerprint, [])
        # Missing key path.
        fingerprint.pop("mimir:demo_key")
        classifier.classify(fingerprint, [])

        mock_post.assert_not_called()
        mock_get.assert_not_called()
