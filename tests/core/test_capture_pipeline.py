"""
tests/core/test_capture_pipeline.py — Tests for the IQ capture pipeline

Tests cover:
- capture_iq raises RuntimeError (not HardwareTransmitError) without hardware
- save_capture creates output_dir if missing
- save_capture filename matches expected pattern
- saved file reloads as complex64
- no TX patterns exist in capture.py
"""

import sys
import os
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.legal.compliance_guard import HardwareTransmitError
from core.pipeline.capture import capture_iq, save_capture


class TestCaptureIq:
    """Tests for the capture_iq function."""

    def test_raises_runtime_error_without_hardware(self):
        """capture_iq raises RuntimeError when no hardware is connected."""
        with patch("core.pipeline.capture.HackRFReceiver") as mock_receiver_cls:
            mock_sdr = MagicMock()
            mock_sdr.__enter__ = MagicMock(
                side_effect=RuntimeError("No HackRF device found.")
            )
            mock_sdr.__exit__ = MagicMock(return_value=False)
            mock_receiver_cls.return_value = mock_sdr

            with pytest.raises(RuntimeError) as exc_info:
                capture_iq(
                    freq_hz=98_000_000,
                    num_samples=1024,
                    sample_rate_hz=2_000_000,
                    lna_gain_db=16,
                    vga_gain_db=20,
                )

            assert not isinstance(exc_info.value, HardwareTransmitError), (
                "capture_iq must raise RuntimeError, not HardwareTransmitError, "
                "when hardware is unavailable."
            )


class TestSaveCapture:
    """Tests for the save_capture function."""

    def test_creates_output_dir_if_missing(self, tmp_path):
        """save_capture creates the output directory if it does not exist."""
        output_dir = tmp_path / "nested" / "dir" / "captures"
        assert not output_dir.exists()

        samples = np.zeros(1024, dtype=np.complex64)
        save_capture(samples, freq_hz=98_000_000, output_dir=output_dir)

        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_filename_matches_pattern(self, tmp_path):
        """save_capture filename matches capture_{freq}hz_YYYYMMDD_HHMMSS.npy."""
        samples = np.zeros(1024, dtype=np.complex64)
        result_path = save_capture(samples, freq_hz=98_000_000, output_dir=tmp_path)

        pattern = r"capture_98000000hz_\d{8}_\d{6}\.npy"
        assert re.match(pattern, result_path.name), (
            f"Filename '{result_path.name}' does not match expected pattern."
        )

    def test_saved_file_reloads_as_complex64(self, tmp_path):
        """Saved .npy file reloads with dtype complex64 and matching data."""
        original = np.random.randn(512).astype(np.float32) + \
                   1j * np.random.randn(512).astype(np.float32)
        original = original.astype(np.complex64)

        result_path = save_capture(original, freq_hz=145_175_000, output_dir=tmp_path)
        reloaded = np.load(result_path)

        assert reloaded.dtype == np.complex64, (
            f"Expected dtype complex64, got {reloaded.dtype}."
        )
        np.testing.assert_array_equal(original, reloaded)


class TestNoTxPatterns:
    """Verify that capture.py contains no transmit-related code."""

    def test_no_tx_patterns_in_capture_py(self):
        """capture.py must not contain any TX function names or patterns."""
        capture_path = Path(__file__).resolve().parent.parent.parent / "core" / "pipeline" / "capture.py"
        source = capture_path.read_text()

        tx_patterns = [
            "writeStream",
            "transmit_guard",
            "HardwareTransmitError",
            ".transmit(",
            ".write_samples(",
            "setupTxStream",
            "activateTxStream",
            "set_tx_gain",
            "set_tx_frequency",
        ]

        for pattern in tx_patterns:
            assert pattern not in source, (
                f"TX pattern '{pattern}' found in capture.py — "
                "this file must be receive-only."
            )
