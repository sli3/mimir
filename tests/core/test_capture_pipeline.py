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
from core.pipeline.capture import capture_iq, capture_iq_pluto, save_capture


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


class TestCaptureIqPluto:
    """Tests for the capture_iq_pluto function (Pluto RX path)."""

    def test_constructs_pluto_receiver_with_exact_args(self):
        """PlutoReceiver is constructed with the exact kwargs passed in."""
        with patch("core.pipeline.capture.PlutoReceiver") as mock_receiver_cls:
            mock_sdr = MagicMock()
            mock_receiver_cls.return_value = mock_sdr

            capture_iq_pluto(
                freq_hz=915e6,
                num_samples=1024,
                sample_rate_hz=2e6,
                gain_db=30.0,
                bandwidth_hz=1.8e6,
            )

            mock_receiver_cls.assert_called_once_with(
                center_freq_hz=915e6,
                sample_rate_hz=2e6,
                gain_db=30.0,
                bandwidth_hz=1.8e6,
            )

    def test_uses_context_manager_and_read_samples(self):
        """The receiver is used as a context manager and read_samples drives the capture."""
        with patch("core.pipeline.capture.PlutoReceiver") as mock_receiver_cls:
            mock_sdr = MagicMock()
            mock_receiver_cls.return_value = mock_sdr

            result = capture_iq_pluto(
                freq_hz=915e6,
                num_samples=2048,
                sample_rate_hz=2e6,
                gain_db=30.0,
            )

            mock_sdr.__enter__.assert_called_once()
            mock_sdr.read_samples.assert_called_once_with(2048)
            assert result is mock_sdr.read_samples.return_value
            mock_sdr.__exit__.assert_called_once()

    def test_propagates_runtime_error_from_read_samples(self):
        """A RuntimeError from the device layer is re-raised, not swallowed."""
        with patch("core.pipeline.capture.PlutoReceiver") as mock_receiver_cls:
            mock_sdr = MagicMock()
            mock_sdr.read_samples.side_effect = RuntimeError("boom")
            mock_receiver_cls.return_value = mock_sdr

            with pytest.raises(RuntimeError, match="boom"):
                capture_iq_pluto(
                    freq_hz=915e6,
                    num_samples=1024,
                    sample_rate_hz=2e6,
                    gain_db=30.0,
                )

    def test_propagates_value_error_for_out_of_range_gain(self):
        """An out-of-range gain raises ValueError, never RuntimeError."""
        with patch("core.pipeline.capture.PlutoReceiver") as mock_receiver_cls:
            mock_receiver_cls.side_effect = ValueError(
                "Gain 80.0 dB out of range. Valid range: 0.0–74.5 dB."
            )

            with pytest.raises(ValueError) as exc_info:
                capture_iq_pluto(
                    freq_hz=915e6,
                    num_samples=1024,
                    sample_rate_hz=2e6,
                    gain_db=80.0,
                )

            assert not isinstance(exc_info.value, RuntimeError), (
                "ValueError for out-of-range gain must propagate unchanged, "
                "not be converted into a RuntimeError."
            )

    def test_no_transmit_method_called_on_pluto_receiver(self):
        """TX-safety: no transmit-family method is ever invoked on the receiver."""
        with patch("core.pipeline.capture.PlutoReceiver") as mock_receiver_cls:
            mock_sdr = MagicMock()
            mock_receiver_cls.return_value = mock_sdr

            capture_iq_pluto(
                freq_hz=915e6,
                num_samples=1024,
                sample_rate_hz=2e6,
                gain_db=30.0,
            )

            tx_methods = [
                "transmit",
                "write_samples",
                "writeStream",
                "set_tx_gain",
                "set_tx_frequency",
                "setupTxStream",
                "activateTxStream",
            ]
            for method_name in tx_methods:
                getattr(mock_sdr, method_name).assert_not_called()

            # The constructor must never receive a transmit-direction argument.
            ctor_kwargs = mock_receiver_cls.call_args.kwargs
            for kwarg_name, kwarg_value in ctor_kwargs.items():
                assert kwarg_name not in tx_methods
                assert kwarg_value not in tx_methods


class TestCaptureIqUnchanged:
    """Confirm Block 1 did not break the existing HackRF capture path."""

    def test_capture_iq_hackrf_still_works_with_own_mock(self):
        """capture_iq still drives HackRFReceiver with the same args as before."""
        with patch("core.pipeline.capture.HackRFReceiver") as mock_receiver_cls:
            mock_sdr = MagicMock()
            mock_receiver_cls.return_value = mock_sdr

            result = capture_iq(
                freq_hz=98e6,
                num_samples=1024,
                sample_rate_hz=2e6,
                lna_gain_db=16,
                vga_gain_db=20,
            )

            mock_receiver_cls.assert_called_once_with(
                center_freq_hz=98e6,
                sample_rate_hz=2e6,
                lna_gain_db=16,
                vga_gain_db=20,
            )
            mock_sdr.__enter__.assert_called_once()
            mock_sdr.read_samples.assert_called_once_with(1024)
            assert result is mock_sdr.read_samples.return_value


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
