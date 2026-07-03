"""
tests/llm/test_classifier_offline.py
Mimir RF Scanner — Phase 22 LLM Offline Handling Tests

PURPOSE
───────
Tests for the LLM offline cooldown logic introduced in Phase 22.
Covers startup connectivity probes and classify() fast-fail/cooldown
behaviour without requiring a live LLM server.

Run with:
    python -m pytest tests/llm/test_classifier_offline.py -v
"""

import sys
import os
import json
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from llm.classifier import ClassificationResult, SignalClassifier


def _make_fingerprint(
    center_freq_hz: float = 98_000_000,
    peak_power_db: float = -23.4,
    snr_db: float = 42.1,
    spectral_flatness: float = 0.021,
    timestamp: str = "2026-05-22T14:33:11",
) -> dict:
    """Build a minimal fingerprint dict for testing."""
    return {
        "center_freq_hz": center_freq_hz,
        "peak_power_db": peak_power_db,
        "snr_db": snr_db,
        "spectral_flatness": spectral_flatness,
        "timestamp": timestamp,
    }


def _make_neighbours() -> list:
    """Build a minimal neighbours list for testing."""
    return [
        {"label": "fm_broadcast", "distance": 0.031},
        {"label": "fm_broadcast", "distance": 0.089},
        {"label": "noise", "distance": 0.741},
    ]


def _make_llm_response(payload: dict) -> MagicMock:
    """Build a mock requests.Response that returns the given dict as JSON."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(payload)
                }
            }
        ]
    }
    return mock_response


@pytest.fixture
def classifier() -> SignalClassifier:
    """A SignalClassifier instance pointed at a local test server."""
    return SignalClassifier(
        base_url="http://localhost:8080/v1",
        model="test-model",
        temperature=0.1,
    )


@pytest.fixture
def fingerprint() -> dict:
    return _make_fingerprint()


@pytest.fixture
def neighbours() -> list:
    return _make_neighbours()


class TestCheckConnection:
    """Tests for SignalClassifier.check_connection()."""

    @patch("llm.classifier.requests.get")
    def test_check_connection_success(self, mock_get, classifier):
        """A reachable /models endpoint returns True and clears cooldown."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = classifier.check_connection()

        assert result is True
        assert classifier._offline_until == 0.0

    @patch("llm.classifier.requests.get")
    def test_check_connection_connection_error(self, mock_get, classifier):
        """ConnectionError makes check_connection() return False and sets cooldown."""
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")

        result = classifier.check_connection()

        assert result is False
        assert classifier._offline_until > time.time()

    @patch("llm.classifier.requests.get")
    def test_check_connection_timeout(self, mock_get, classifier):
        """Timeout makes check_connection() return False and sets cooldown."""
        mock_get.side_effect = requests.exceptions.Timeout("timed out")

        result = classifier.check_connection()

        assert result is False
        assert classifier._offline_until > time.time()

    @patch("llm.classifier.requests.get")
    def test_check_connection_http_error(self, mock_get, classifier):
        """HTTPError from /models is treated as reachable — endpoint may not exist."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=404)
        )
        mock_get.return_value = mock_response

        result = classifier.check_connection()

        assert result is True
        assert classifier._offline_until == 0.0


class TestClassifyOfflineHandling:
    """Tests for classify() cooldown and offline-result behaviour."""

    def test_classify_fast_fail_during_cooldown(self, classifier, fingerprint, neighbours):
        """classify() must skip the network call and return llm_offline during cooldown."""
        classifier._offline_until = time.time() + 9999

        with patch("llm.classifier.requests.post") as mock_post:
            result = classifier.classify(fingerprint, neighbours)

        assert result.signal_type == "llm_offline"
        assert mock_post.called is False

    @patch("llm.classifier.requests.post")
    def test_classify_sets_cooldown_on_connection_error(
        self, mock_post, classifier, fingerprint, neighbours
    ):
        """ConnectionError during classify() sets cooldown and returns llm_offline."""
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")

        result = classifier.classify(fingerprint, neighbours)

        assert result.signal_type == "llm_offline"
        assert classifier._offline_until > time.time()

    @patch("llm.classifier.requests.post")
    def test_classify_resets_cooldown_on_success(
        self, mock_post, classifier, fingerprint, neighbours
    ):
        """A successful response clears any prior cooldown."""
        classifier._offline_until = time.time() - 1
        mock_post.return_value = _make_llm_response({
            "signal_type": "fm_broadcast",
            "confidence": "high",
            "confidence_score": 0.94,
            "novel": False,
            "reasoning": "Test.",
            "au_legal_status": "legal_rx",
            "frequency_band": "fm_broadcast_band",
        })

        result = classifier.classify(fingerprint, neighbours)

        assert result.signal_type != "llm_offline"
        assert classifier._offline_until == 0.0

    def test_offline_result_distinct_from_fallback_result(self, classifier):
        """Offline and fallback results use different signal_type values."""
        offline = classifier._offline_result()
        fallback = classifier._fallback_result("test")

        assert offline.signal_type == "llm_offline"
        assert fallback.signal_type == "unavailable"
        assert "llm_offline" != "unavailable"

    def test_classify_no_args_still_works(self):
        """SignalClassifier() with no arguments uses documented defaults."""
        cls = SignalClassifier()

        assert cls._cooldown_sec == 60.0
        assert cls._connect_timeout_sec == 5.0
