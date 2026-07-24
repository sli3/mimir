"""tests/llm/test_classifier_noise_gate.py
Mimir RF Scanner — Phase 41 tests for the deterministic pre-LLM noise gate.

PURPOSE
───────
Phase 41 adds a deterministic short-circuit ahead of the ChromaDB query and
LLM call in the scanner's AI loop. When a fingerprint unambiguously describes
noise (no real occupied bandwidth AND a near-white spectrum), the scanner
emits a deterministic ``noise`` ClassificationResult via
``classify_noise_deterministic()`` and skips the LLM entirely. Without this
gate, every noise-floor scan round-trips to the LLM and returns a
confident-looking band label (e.g. "adsb 40%"), flooding SIGNAL HISTORY and
wasting one LLM call per noise scan.

These tests lock in:

- ``is_noise_shaped()`` — the conjunction rule (occupied bins AND spectral
  flatness), the boundary behaviour, the narrow-tonal carve-out, and the
  fail-open behaviour when fields are missing.
- ``classify_noise_deterministic()`` — the deterministic verdict's fields,
  including the deliberate 0.9 confidence_score (a confident, uninteresting
  verdict — distinct from the 0.4 uncertainty CAP applied by
  ``_apply_confidence_caps()``).

No LLM server is required — both methods are deterministic and call no
network code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the repository root is on the path when this file is run in isolation.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm.classifier import (
    ClassificationResult,
    SignalClassifier,
    _CAPPED_CONFIDENCE_SCORE,
    _NEAR_ZERO_BINS,
    _NOISE_FLATNESS,
)


class TestIsNoiseShaped:
    """Tests for ``SignalClassifier.is_noise_shaped``.

    A fingerprint is noise-shaped only when BOTH conditions hold at once:
    occupied_bins <= _NEAR_ZERO_BINS AND spectral_flatness >= _NOISE_FLATNESS.
    The conjunction protects genuine narrow tonal signals (low flatness) and
    real wideband signals (many occupied bins) from being gated as noise.
    """

    @pytest.fixture
    def classifier(self) -> SignalClassifier:
        """Minimal classifier for testing the noise gate methods."""
        return SignalClassifier(
            base_url="http://localhost:8080/v1",
            model="test-model",
            temperature=0.1,
        )

    def test_returns_true_on_canonical_noise(
        self, classifier: SignalClassifier
    ) -> None:
        """Zero occupied bins with near-white flatness is noise-shaped."""
        fingerprint = {"occupied_bins": 0, "spectral_flatness": 0.99}
        assert classifier.is_noise_shaped(fingerprint) is True

    def test_returns_true_on_boundary(self, classifier: SignalClassifier) -> None:
        """The boundary values on both axes still count as noise-shaped."""
        fingerprint = {
            "occupied_bins": 1,
            "spectral_flatness": 0.9,
        }
        assert fingerprint["occupied_bins"] == _NEAR_ZERO_BINS
        assert fingerprint["spectral_flatness"] == _NOISE_FLATNESS
        assert classifier.is_noise_shaped(fingerprint) is True

    def test_returns_false_on_real_signal(
        self, classifier: SignalClassifier
    ) -> None:
        """A wideband real signal fails the occupied-bins axis."""
        fingerprint = {"occupied_bins": 180, "spectral_flatness": 0.03}
        assert classifier.is_noise_shaped(fingerprint) is False

    def test_returns_false_on_narrow_tone(
        self, classifier: SignalClassifier
    ) -> None:
        """A genuine narrowband tonal signal fails the flatness axis.

        This is the critical carve-out: a single CW carrier occupies at most
        one bin but concentrates its energy, so its spectral flatness is LOW.
        It must fall through to the LLM, never be gated as noise.
        """
        fingerprint = {"occupied_bins": 1, "spectral_flatness": 0.2}
        assert classifier.is_noise_shaped(fingerprint) is False

    def test_fails_open_when_occupied_bins_missing(
        self, classifier: SignalClassifier
    ) -> None:
        """Missing occupied_bins fails open — the LLM path is the fallback."""
        fingerprint = {"spectral_flatness": 0.95}
        assert classifier.is_noise_shaped(fingerprint) is False

    def test_fails_open_when_spectral_flatness_missing(
        self, classifier: SignalClassifier
    ) -> None:
        """Missing spectral_flatness fails open — the LLM path is the fallback."""
        fingerprint = {"occupied_bins": 0}
        assert classifier.is_noise_shaped(fingerprint) is False

    def test_fails_open_when_both_missing(
        self, classifier: SignalClassifier
    ) -> None:
        """An empty fingerprint must never fabricate a noise verdict."""
        assert classifier.is_noise_shaped({}) is False


class TestClassifyNoiseDeterministic:
    """Tests for ``SignalClassifier.classify_noise_deterministic``.

    The deterministic verdict is emitted when the gate fires, with no LLM
    call and no ChromaDB query having taken place. Its fields must be honest
    about that: empty raw_response, unknown band, not novel, legal_rx status.
    """

    @pytest.fixture
    def classifier(self) -> SignalClassifier:
        """Minimal classifier for testing the noise gate methods."""
        return SignalClassifier(
            base_url="http://localhost:8080/v1",
            model="test-model",
            temperature=0.1,
        )

    @staticmethod
    def _noise_fingerprint() -> dict:
        """Canonical noise-shaped fingerprint (passes is_noise_shaped)."""
        return {
            "center_freq_hz": 1_090_000_000,
            "occupied_bins": 0,
            "spectral_flatness": 0.99,
        }

    def test_returns_noise_signal_type(self, classifier: SignalClassifier) -> None:
        result = classifier.classify_noise_deterministic(self._noise_fingerprint())
        assert isinstance(result, ClassificationResult)
        assert result.signal_type == "noise"

    def test_returns_low_confidence(self, classifier: SignalClassifier) -> None:
        result = classifier.classify_noise_deterministic(self._noise_fingerprint())
        assert result.confidence == "low"

    def test_returns_high_confidence_score(
        self, classifier: SignalClassifier
    ) -> None:
        """0.9 means "confident verdict, just an uninteresting one".

        This is deliberately distinct from _CAPPED_CONFIDENCE_SCORE (0.4),
        which means "uncertain verdict" when _apply_confidence_caps() clamps
        an LLM result.
        """
        result = classifier.classify_noise_deterministic(self._noise_fingerprint())
        assert result.confidence_score == 0.9
        assert result.confidence_score != _CAPPED_CONFIDENCE_SCORE

    def test_returns_not_novel(self, classifier: SignalClassifier) -> None:
        result = classifier.classify_noise_deterministic(self._noise_fingerprint())
        assert result.novel is False

    def test_returns_legal_rx_status(self, classifier: SignalClassifier) -> None:
        """Passive reception is unconditional under the Act — always legal_rx."""
        result = classifier.classify_noise_deterministic(self._noise_fingerprint())
        assert result.au_legal_status == "legal_rx"

    def test_returns_unknown_band(self, classifier: SignalClassifier) -> None:
        result = classifier.classify_noise_deterministic(self._noise_fingerprint())
        assert result.frequency_band == "unknown"

    def test_returns_empty_raw_response(self, classifier: SignalClassifier) -> None:
        """No LLM was called, so there is no raw response to keep."""
        result = classifier.classify_noise_deterministic(self._noise_fingerprint())
        assert result.raw_response == ""

    def test_reasoning_contains_actual_values(
        self, classifier: SignalClassifier
    ) -> None:
        """The reasoning string carries the actual measured values."""
        fingerprint = {"occupied_bins": 1, "spectral_flatness": 0.95}
        result = classifier.classify_noise_deterministic(fingerprint)
        assert "occupied_bins=1" in result.reasoning
        assert "spectral_flatness=0.950" in result.reasoning

    def test_reasoning_mentions_threshold_constants(
        self, classifier: SignalClassifier
    ) -> None:
        """The reasoning names the thresholds so the operator reading SIGNAL
        HISTORY can see exactly what tripped the gate."""
        result = classifier.classify_noise_deterministic(self._noise_fingerprint())
        assert f"<= {_NEAR_ZERO_BINS}" in result.reasoning
        assert f">= {_NOISE_FLATNESS}" in result.reasoning
