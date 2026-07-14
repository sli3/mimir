"""tests/llm/test_classifier_confidence_caps.py
Mimir RF Scanner — Phase 34 regression tests for classifier confidence caps
and prompt reordering (Phase 33).

PURPOSE
───────
These tests lock in the deterministic backstop introduced in Phase 33 that
prevents a frequency or ACMA allocation match from inflating confidence when
the measured signal is weak or noise-like. They also guard the prompt wording
that demotes ACMA/frequency to a secondary plausibility check and keeps the
reverted burst-structure labels out of the user prompt.

No LLM server is required — the tests call ``_apply_confidence_caps`` and the
prompt builders directly.

TEST DATA NOTES
───────────────
The noise-blip cap threshold uses 1090 MHz ADS-B fingerprints with SNR margins
of +1.7 dB and +2.9 dB against a 104.7 MHz FM reference at approximately
+23.1 dB margin above the noise floor. These values come from live field
captures and anchor the ``_MARGIN_FLOOR_DB`` constant in
``llm/classifier.py``.
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
    _MARGIN_FLOOR_DB,
    _NEAR_ZERO_BINS,
    _NOISE_FLATNESS,
)


class TestConfidenceCaps:
    """Regression tests for ``SignalClassifier._apply_confidence_caps``.

    The LLM sets ``confidence_score`` itself, so a frequency or ACMA match can
    talk the model into "high" even when the signal is barely above the noise
    floor or is a single-bin noise spike. These caps are a deterministic backstop.

    Covers rules A1 through A5 from Phase 33:

    - **A1** Low SNR margin (below ``_MARGIN_FLOOR_DB``) caps confidence to "low".
      Uses 1090 MHz ADS-B fingerprints with margins of +1.7 dB and +2.9 dB.
    - **A2** Single-bin, noise-flat signals are capped regardless of SNR.
    - **A3** Strong, wide signals pass through unchanged (104.7 MHz FM at ~+23.1 dB).
    - **A4** Narrow tonal signals with low spectral flatness are exempt from the
      single-bin cap.
    - **A5** Missing optional fingerprint fields degrade gracefully without
      triggering false caps.
    """

    @pytest.fixture
    def classifier(self) -> SignalClassifier:
        """Minimal classifier for testing the cap methods."""
        return SignalClassifier(
            base_url="http://localhost:8080/v1",
            model="test-model",
            temperature=0.1,
        )

    @staticmethod
    def _make_result(
        score: float = 0.9,
        confidence: str = "high",
    ) -> ClassificationResult:
        """Build a ClassificationResult with controlled confidence fields."""
        return ClassificationResult(
            signal_type="adsb",
            confidence=confidence,
            confidence_score=score,
            novel=False,
            reasoning="LLM-produced reasoning.",
            au_legal_status="legal_rx",
            frequency_band="adsb_band",
            raw_response="{}",
        )

    @staticmethod
    def _make_fingerprint(
        snr_margin_db: float | None = None,
        occupied_bins: int | None = None,
        spectral_flatness: float | None = None,
    ) -> dict:
        """Build a minimal fingerprint dict with optional cap-relevant fields."""
        fingerprint = {
            "center_freq_hz": 1_090_000_000,
            "peak_power_db": -50.0,
            "snr_db": 20.0,
            "timestamp": "2026-07-14T00:00:00",
        }
        if snr_margin_db is not None:
            fingerprint["snr_margin_db"] = snr_margin_db
        if occupied_bins is not None:
            fingerprint["occupied_bins"] = occupied_bins
        if spectral_flatness is not None:
            fingerprint["spectral_flatness"] = spectral_flatness
        return fingerprint

    def test_cap_fires_on_low_snr_margin(self, classifier: SignalClassifier) -> None:
        """Margin below the floor caps confidence to low, with a note."""
        for margin in (1.7, 2.9):
            result = self._make_result(score=0.9, confidence="high")
            fingerprint = self._make_fingerprint(
                snr_margin_db=margin,
                occupied_bins=12,
                spectral_flatness=0.4,
            )
            capped = classifier._apply_confidence_caps(result, fingerprint)

            assert capped.confidence_score == _CAPPED_CONFIDENCE_SCORE, (
                f"SNR margin {margin} dB is below the {_MARGIN_FLOOR_DB} dB "
                "floor — confidence must be capped."
            )
            assert capped.confidence == "low"
            assert "capped" in capped.reasoning.lower()

    def test_cap_fires_on_single_bin_noise(self, classifier: SignalClassifier) -> None:
        """A single-bin, noise-flat signal is capped regardless of SNR."""
        result = self._make_result(score=0.9, confidence="high")
        fingerprint = self._make_fingerprint(
            snr_margin_db=20.0,
            occupied_bins=_NEAR_ZERO_BINS,
            spectral_flatness=_NOISE_FLATNESS + 0.05,
        )
        capped = classifier._apply_confidence_caps(result, fingerprint)

        assert capped.confidence_score == _CAPPED_CONFIDENCE_SCORE
        assert capped.confidence == "low"
        assert "capped" in capped.reasoning.lower()

    def test_cap_does_not_fire_on_strong_real_signal(
        self, classifier: SignalClassifier
    ) -> None:
        """A clean, wide, strong signal passes through unchanged."""
        result = self._make_result(score=0.94, confidence="high")
        fingerprint = self._make_fingerprint(
            snr_margin_db=23.1,
            occupied_bins=50,
            spectral_flatness=0.005,
        )
        fingerprint["bandwidth_hz"] = 164_000

        capped = classifier._apply_confidence_caps(result, fingerprint)

        assert capped.confidence_score == 0.94
        assert capped.confidence == "high"
        assert "capped" not in capped.reasoning.lower()

    def test_cap_does_not_fire_on_narrow_tonal_signal(
        self, classifier: SignalClassifier
    ) -> None:
        """The single-bin carve-out protects genuine narrow tonal signals."""
        result = self._make_result(score=0.85, confidence="high")
        fingerprint = self._make_fingerprint(
            snr_margin_db=20.0,
            occupied_bins=_NEAR_ZERO_BINS,
            spectral_flatness=0.05,  # well below the noise-flatness threshold
        )
        capped = classifier._apply_confidence_caps(result, fingerprint)

        assert capped.confidence_score == 0.85
        assert capped.confidence == "high"
        assert "capped" not in capped.reasoning.lower()

    def test_missing_fields_degrade_gracefully(
        self, classifier: SignalClassifier
    ) -> None:
        """Missing optional fields are ignored; the matching branch still caps."""
        # All three absent: no condition can trigger, so the result is untouched.
        result = self._make_result(score=0.9, confidence="high")
        fingerprint = self._make_fingerprint()
        capped = classifier._apply_confidence_caps(result, fingerprint)
        assert capped.confidence_score == 0.9
        assert capped.confidence == "high"
        assert "capped" not in capped.reasoning.lower()

        # snr_margin_db missing, but the single-bin noise branch can still fire.
        result = self._make_result(score=0.9, confidence="high")
        fingerprint = self._make_fingerprint(
            occupied_bins=1,
            spectral_flatness=0.95,
        )
        capped = classifier._apply_confidence_caps(result, fingerprint)
        assert capped.confidence_score == _CAPPED_CONFIDENCE_SCORE
        assert capped.confidence == "low"

        # occupied_bins missing, but the marginal-SNR branch can still fire.
        result = self._make_result(score=0.9, confidence="high")
        fingerprint = self._make_fingerprint(snr_margin_db=1.0)
        capped = classifier._apply_confidence_caps(result, fingerprint)
        assert capped.confidence_score == _CAPPED_CONFIDENCE_SCORE
        assert capped.confidence == "low"

        # spectral_flatness missing, but the marginal-SNR branch can still fire.
        result = self._make_result(score=0.9, confidence="high")
        fingerprint = self._make_fingerprint(
            snr_margin_db=2.0,
            occupied_bins=1,
        )
        capped = classifier._apply_confidence_caps(result, fingerprint)
        assert capped.confidence_score == _CAPPED_CONFIDENCE_SCORE
        assert capped.confidence == "low"


class TestPromptReordering:
    """Regression tests for Phase 33's prompt-content changes.

    Verifies that the user prompt surfaces bandwidth, occupied bins, and SNR
    margin in plain English (B1), that the system prompt demotes ACMA/frequency
    to a secondary plausibility check rather than primary evidence (B2), and
    that reverted internal labels (e.g. ``peak_bin_power_db``, "burst structure")
    do not leak into the user-facing prompt (B3).
    """

    @pytest.fixture
    def classifier(self) -> SignalClassifier:
        """Minimal classifier for testing prompt construction."""
        return SignalClassifier(
            base_url="http://localhost:8080/v1",
            model="test-model",
            temperature=0.1,
        )

    @staticmethod
    def _rich_fingerprint() -> dict:
        """Fingerprint with all Phase 33 evidence fields present."""
        return {
            "center_freq_hz": 1_090_000_000,
            "peak_power_db": -50.0,
            "snr_db": 20.0,
            "spectral_flatness": 0.05,
            "bandwidth_hz": 164_000,
            "occupied_bins": 50,
            "snr_margin_db": 10.0,
            "timestamp": "2026-07-14T00:00:00",
        }

    def test_user_prompt_includes_bandwidth_occupied_bins_and_margin(
        self, classifier: SignalClassifier
    ) -> None:
        """The user prompt surfaces the Phase 33 quality fields in plain English."""
        prompt = classifier._build_user_prompt(self._rich_fingerprint(), [])
        lowered = prompt.lower()
        assert "bandwidth" in lowered
        assert "occupied" in lowered
        assert "margin" in lowered

    def test_system_prompt_demotes_acma_frequency_to_plausibility(
        self, classifier: SignalClassifier
    ) -> None:
        """ACMA/frequency is a secondary plausibility check, not primary evidence."""
        system_prompt = classifier._build_system_prompt()
        lowered = system_prompt.lower()

        assert "plausibility" in lowered
        assert "noise sitting at an allocated frequency still matches" in lowered
        assert "vector-store nearest neighbours" in system_prompt

    def test_user_prompt_does_not_include_reverted_burst_labels(
        self, classifier: SignalClassifier
    ) -> None:
        """The reverted burst-structure labels stay out of the user prompt."""
        # Include the field in the fingerprint so the test proves it is NOT surfaced.
        fingerprint = self._rich_fingerprint()
        fingerprint["peak_bin_power_db"] = -45.0

        prompt = classifier._build_user_prompt(fingerprint, [])
        assert "peak_bin_power_db" not in prompt
        assert "burst structure" not in prompt
        assert "consistent with ADS-B" not in prompt
