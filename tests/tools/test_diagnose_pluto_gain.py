"""
tests/tools/test_diagnose_pluto_gain.py
Mimir RF Scanner — Pluto Gain Diagnostic Tool Tests

All tests mock capture_iq_pluto and compute_psd so no hardware is required.
"""

import sys
import os
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools import diagnose_pluto_gain
from tools.diagnose_pluto_gain import (
    BAND_KEYS,
    BAND_SWEEP,
    GAIN_CANDIDATES,
    SPUR_MARGIN_DB,
    main,
    sweep_band,
)


def _fake_samples(num_samples: int = 256_000) -> np.ndarray:
    """Return a benign complex64 sample array of the requested length."""
    return np.zeros(num_samples, dtype=np.complex64)


def _flat_psd_with_excursions(
    num_bins: int = 2048,
    floor_db: float = -80.0,
    excursion_db: float = -50.0,
    num_excursions: int = 5,
) -> np.ndarray:
    """A flat noise floor with exactly num_excursions bins above the margin."""
    psd = np.full(num_bins, floor_db, dtype=np.float64)
    psd[:num_excursions] = excursion_db
    return psd


class TestSweepBand:
    """Tests for sweep_band measurement logic."""

    def test_noise_floor_and_excursions_calculated_correctly(self):
        """Median floor and excursion count are computed per gain step."""
        psd = _flat_psd_with_excursions()

        with patch.object(
            diagnose_pluto_gain, "capture_iq_pluto", return_value=_fake_samples()
        ), patch.object(
            diagnose_pluto_gain, "compute_psd", return_value={"psd_db": psd}
        ):
            result = sweep_band(BAND_KEYS["ism"])

        rows = result["rows"]
        assert len(rows) == len(GAIN_CANDIDATES)
        gains_seen = [row[0] for row in rows]
        assert gains_seen == list(GAIN_CANDIDATES)

        for gain, noise_floor_db, excursions, max_db in rows:
            assert noise_floor_db == pytest.approx(-80.0, abs=0.01)
            assert excursions == 5
            assert max_db == pytest.approx(-50.0, abs=0.01)

    def test_every_gain_within_pluto_range_and_in_candidates(self):
        """No fabricated gain value: every swept gain is a valid candidate."""
        with patch.object(
            diagnose_pluto_gain, "capture_iq_pluto", return_value=_fake_samples()
        ) as mock_capture, patch.object(
            diagnose_pluto_gain,
            "compute_psd",
            return_value={"psd_db": _flat_psd_with_excursions()},
        ):
            for band in BAND_SWEEP:
                sweep_band(band)

        assert mock_capture.call_count == 2 * len(GAIN_CANDIDATES)
        for call in mock_capture.call_args_list:
            gain_db = call.kwargs["gain_db"]
            assert 0.0 <= gain_db <= 74.5
            assert gain_db in GAIN_CANDIDATES

    def test_capture_iq_pluto_used_and_capture_iq_never_called(self):
        """The Pluto capture path is used; the HackRF path is never touched."""
        with patch.object(
            diagnose_pluto_gain, "capture_iq_pluto", return_value=_fake_samples()
        ) as mock_pluto, patch.object(
            diagnose_pluto_gain,
            "compute_psd",
            return_value={"psd_db": _flat_psd_with_excursions()},
        ), patch(
            "tools.diagnose_pluto_gain.capture_iq", create=True
        ) as mock_hackrf:
            for band in BAND_SWEEP:
                sweep_band(band)

        assert mock_pluto.call_count > 0
        assert mock_hackrf.call_count == 0

    def test_empty_psd_step_skips_without_aborting_sweep(self):
        """An empty PSD skips one gain step; the rest of the sweep completes."""
        good_psd = {"psd_db": _flat_psd_with_excursions()}
        empty_psd = {"psd_db": np.array([])}
        # First gain step yields an empty PSD; all subsequent steps are valid.
        psd_responses = [empty_psd] + [good_psd] * (len(GAIN_CANDIDATES) - 1)

        with patch.object(
            diagnose_pluto_gain, "capture_iq_pluto", return_value=_fake_samples()
        ), patch.object(
            diagnose_pluto_gain, "compute_psd", side_effect=psd_responses
        ):
            result = sweep_band(BAND_KEYS["ism"])

        assert len(result["rows"]) == len(GAIN_CANDIDATES) - 1

    def test_per_step_exception_is_skipped_not_aborted(self):
        """A RuntimeError from capture skips one gain step; the sweep continues."""
        # First gain step raises (e.g. a USB hiccup exhausting the read
        # retry); all subsequent steps capture valid samples.
        capture_responses = [RuntimeError("USB hiccup")] + [
            _fake_samples()
        ] * (len(GAIN_CANDIDATES) - 1)

        with patch.object(
            diagnose_pluto_gain, "capture_iq_pluto", side_effect=capture_responses
        ) as mock_capture, patch.object(
            diagnose_pluto_gain,
            "compute_psd",
            return_value={"psd_db": _flat_psd_with_excursions()},
        ):
            result = sweep_band(BAND_KEYS["ism"])

        assert len(result["rows"]) == len(GAIN_CANDIDATES) - 1
        assert mock_capture.call_count == len(GAIN_CANDIDATES)


class TestMainBandSelection:
    """Tests for main() --band flag behaviour."""

    def _run_main(self, argv: list[str]) -> MagicMock:
        """Run main() with mocked capture/PSD and the given argv."""
        with patch.object(sys, "argv", argv), patch.object(
            diagnose_pluto_gain, "capture_iq_pluto", return_value=_fake_samples()
        ) as mock_capture, patch.object(
            diagnose_pluto_gain,
            "compute_psd",
            return_value={"psd_db": _flat_psd_with_excursions()},
        ):
            main()
        return mock_capture

    @staticmethod
    def _freqs_called(mock_capture: MagicMock) -> list[float]:
        return [call.kwargs["freq_hz"] for call in mock_capture.call_args_list]

    def test_band_flag_ism_sweeps_only_915(self):
        """--band ism sweeps 915 MHz only, never 1090 MHz."""
        mock_capture = self._run_main(["prog", "--band", "ism"])
        freqs = self._freqs_called(mock_capture)

        assert mock_capture.call_count == len(GAIN_CANDIDATES)
        assert 915e6 in freqs
        assert 1090e6 not in freqs

    def test_band_flag_adsb_sweeps_only_1090(self):
        """--band adsb sweeps 1090 MHz only, never 915 MHz."""
        mock_capture = self._run_main(["prog", "--band", "adsb"])
        freqs = self._freqs_called(mock_capture)

        assert mock_capture.call_count == len(GAIN_CANDIDATES)
        assert 1090e6 in freqs
        assert 915e6 not in freqs

    def test_no_band_flag_sweeps_both(self):
        """No --band flag sweeps both bands."""
        mock_capture = self._run_main(["prog"])
        freqs = self._freqs_called(mock_capture)

        assert mock_capture.call_count == 2 * len(GAIN_CANDIDATES)
        assert 915e6 in freqs
        assert 1090e6 in freqs
