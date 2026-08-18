"""
tests/core/test_capture_pipeline.py — Tests for the IQ capture pipeline

Tests cover:
- capture_iq raises RuntimeError (not HardwareTransmitError) without hardware
- save_capture creates output_dir if missing
- save_capture filename matches expected SigMF pattern and writes the .sigmf-data sibling
- saved SigMF recording reloads as complex64 with matching data and metadata
- SigMF metadata round-trips device identity and legal provenance
- capture_and_save dispatches to the correct device capture function
- capture_and_save validates the device string before any hardware call
- capture_and_save validates the band string before any hardware call
- capture_and_save measures a spectral fingerprint from the captured samples
  and passes it through to save_capture
- save_capture records the fingerprint as a nested mimir:fingerprint field
  (and omits it entirely when fingerprint is None)
- bandwidth_hz is recorded as SigMF core:bandwidth metadata (never as DSP)
- no TX patterns exist in capture.py
"""

import sys
import os
import re
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest
import sigmf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.legal.compliance_guard import HardwareTransmitError
from core.pipeline.capture import (
    _FINGERPRINT_METADATA_KEYS,
    capture_and_save,
    capture_iq,
    capture_iq_pluto,
    save_capture,
    save_recording,
)
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from dashboard.shared_state import BAND_PROFILES

TX_METHOD_NAMES = [
    "transmit",
    "write_samples",
    "writeStream",
    "set_tx_gain",
    "set_tx_frequency",
    "setupTxStream",
    "activateTxStream",
]


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
    """Tests for the save_capture function (SigMF format)."""

    def test_creates_output_dir_if_missing(self, tmp_path):
        """save_capture creates the output directory if it does not exist."""
        output_dir = tmp_path / "nested" / "dir" / "captures"
        assert not output_dir.exists()

        samples = np.zeros(1024, dtype=np.complex64)
        save_capture(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            output_dir=output_dir,
        )

        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_filename_matches_pattern(self, tmp_path):
        """save_capture returns capture_{freq}hz_YYYYMMDD_HHMMSS.sigmf-meta."""
        samples = np.zeros(1024, dtype=np.complex64)
        result_path = save_capture(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            output_dir=tmp_path,
        )

        pattern = r"capture_98000000hz_\d{8}_\d{6}\.sigmf-meta"
        assert re.match(pattern, result_path.name), (
            f"Filename '{result_path.name}' does not match expected pattern."
        )

        # The sibling .sigmf-data file must exist with the same base name.
        data_path = Path(str(result_path)[: -len(".sigmf-meta")] + ".sigmf-data")
        assert data_path.exists(), (
            f"Expected sibling .sigmf-data file at {data_path}, not found."
        )

    def test_saved_file_reloads_as_complex64(self, tmp_path):
        """SigMF recording reloads with dtype complex64, matching data and metadata."""
        original = np.random.randn(512).astype(np.float32) + \
                   1j * np.random.randn(512).astype(np.float32)
        original = original.astype(np.complex64)

        freq_hz = 145_175_000
        sample_rate_hz = 2_000_000
        result_path = save_capture(
            original,
            freq_hz=freq_hz,
            sample_rate_hz=sample_rate_hz,
            output_dir=tmp_path,
        )

        read_back = sigmf.fromfile(str(result_path))

        assert read_back.sample_rate == sample_rate_hz
        assert read_back.get_captures()[0][sigmf.FREQUENCY_KEY] == freq_hz
        assert len(read_back.get_captures()) == 1, (
            "Expected exactly one capture record (fromarray pre-creates one, "
            "our add_capture merges into it rather than appending)."
        )

        read_data = read_back[: len(original)]
        assert read_data.dtype == np.complex64, (
            f"Expected dtype complex64, got {read_data.dtype}."
        )
        np.testing.assert_array_equal(original, read_data)

    def test_metadata_round_trips_device_and_legal_provenance(self, tmp_path):
        """SigMF metadata carries device identity and the passive-RX legal note."""
        samples = np.zeros(256, dtype=np.complex64)
        result_path = save_capture(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            output_dir=tmp_path,
        )

        meta = sigmf.fromfile(str(result_path))

        assert meta.hw == "HackRF One"
        assert meta.get_global_field("mimir:device_profile") == "hackrf"
        assert "Radiocommunications Act" in meta.description
        assert "ACMA" in meta.description

    def test_save_capture_with_fingerprint_none_omits_mimir_fingerprint_field(
        self, tmp_path
    ):
        """fingerprint=None omits mimir:fingerprint from the SigMF metadata."""
        samples = np.zeros(256, dtype=np.complex64)
        result = save_capture(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            output_dir=tmp_path,
            fingerprint=None,
        )

        meta = sigmf.fromfile(str(result))
        assert meta.get_global_field("mimir:fingerprint") is None, (
            "fingerprint=None must omit mimir:fingerprint entirely, not "
            "write an empty or null field."
        )

    def test_save_capture_with_fingerprint_writes_nested_mimir_fingerprint(
        self, tmp_path
    ):
        """A fingerprint dict lands as one nested mimir:fingerprint field."""
        fingerprint = {
            "peak_freq_hz": 98_000_500.0,
            "peak_power_db": -25.0,
            "noise_floor_db": -90.0,
            "snr_db": 65.0,
            "bandwidth_hz": 200_000.0,
            "occupied_bins": 100,
            "spectral_flatness": 0.1,
        }
        samples = np.zeros(256, dtype=np.complex64)
        result = save_capture(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            output_dir=tmp_path,
            fingerprint=fingerprint,
        )

        meta = sigmf.fromfile(str(result))
        stored = meta.get_global_field("mimir:fingerprint")
        assert stored == fingerprint, (
            "mimir:fingerprint must round-trip exactly the seven "
            "measurement keys with their values."
        )
        # The measurement keys must stay nested, never flattened to the
        # top level of the global fields.
        assert meta.get_global_field("peak_freq_hz") is None
        assert stored["peak_freq_hz"] == 98_000_500.0


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


def _mock_sdr_with_samples(num_samples: int = 1024) -> MagicMock:
    """A mock SDR whose read_samples returns a real complex64 array.

    save_capture() feeds the samples to sigmf.fromarray(), which needs a
    genuine numpy array - a bare MagicMock return value would fail there.
    """
    mock_sdr = MagicMock()
    mock_sdr.read_samples.return_value = np.zeros(num_samples, dtype=np.complex64)
    return mock_sdr


class TestCaptureAndSave:
    """Tests for the capture_and_save orchestration function (Phase 61)."""

    def test_dispatches_to_capture_iq_for_hackrf(self, tmp_path):
        """device="hackrf" constructs HackRFReceiver with wrapper default gains."""
        with patch("core.pipeline.capture.HackRFReceiver") as mock_hackrf_cls, \
             patch("core.pipeline.capture.PlutoReceiver") as mock_pluto_cls:
            mock_sdr = _mock_sdr_with_samples(1024)
            mock_hackrf_cls.return_value = mock_sdr

            result = capture_and_save(
                freq_hz=98_000_000,
                num_samples=1024,
                sample_rate_hz=2_000_000,
                band="fm_broadcast",
                output_dir=tmp_path,
                device="hackrf",
            )

            mock_hackrf_cls.assert_called_once_with(
                center_freq_hz=98_000_000,
                sample_rate_hz=2_000_000,
                lna_gain_db=mock_hackrf_cls.DEFAULT_LNA_GAIN_DB,
                vga_gain_db=mock_hackrf_cls.DEFAULT_VGA_GAIN_DB,
            )
            mock_pluto_cls.assert_not_called()
            mock_sdr.read_samples.assert_called_once_with(1024)
            assert result.name.endswith(".sigmf-meta")
            assert result.exists()

    def test_dispatches_to_capture_iq_pluto_for_plutosdr(self, tmp_path):
        """device="plutosdr" constructs PlutoReceiver with default gain + bandwidth."""
        with patch("core.pipeline.capture.HackRFReceiver") as mock_hackrf_cls, \
             patch("core.pipeline.capture.PlutoReceiver") as mock_pluto_cls:
            mock_sdr = _mock_sdr_with_samples(1024)
            mock_pluto_cls.return_value = mock_sdr

            capture_and_save(
                freq_hz=1_090_000_000,
                num_samples=1024,
                sample_rate_hz=2_000_000,
                band="adsb",
                output_dir=tmp_path,
                device="plutosdr",
                bandwidth_hz=1_800_000,
            )

            mock_pluto_cls.assert_called_once_with(
                center_freq_hz=1_090_000_000,
                sample_rate_hz=2_000_000,
                gain_db=mock_pluto_cls.DEFAULT_GAIN_DB,
                bandwidth_hz=1_800_000,
            )
            mock_hackrf_cls.assert_not_called()
            mock_sdr.read_samples.assert_called_once_with(1024)

    def test_unknown_device_raises_value_error_before_hardware_call(self, tmp_path):
        """An unknown device key raises ValueError and never touches hardware."""
        with patch("core.pipeline.capture.HackRFReceiver") as mock_hackrf_cls, \
             patch("core.pipeline.capture.PlutoReceiver") as mock_pluto_cls:
            with pytest.raises(ValueError, match="Unknown device 'bogus'"):
                capture_and_save(
                    freq_hz=98_000_000,
                    num_samples=1024,
                    sample_rate_hz=2_000_000,
                    band="fm_broadcast",
                    output_dir=tmp_path,
                    device="bogus",
                )

            mock_hackrf_cls.assert_not_called()
            mock_pluto_cls.assert_not_called()

    def test_sigmf_meta_hw_field_is_adalm_pluto_for_plutosdr(self, tmp_path):
        """End-to-end: a Pluto capture records hw as ADALM-PLUTO in SigMF."""
        with patch("core.pipeline.capture.PlutoReceiver") as mock_pluto_cls:
            mock_pluto_cls.return_value = _mock_sdr_with_samples(512)

            result = capture_and_save(
                freq_hz=1_090_000_000,
                num_samples=512,
                sample_rate_hz=2_000_000,
                band="adsb",
                output_dir=tmp_path,
                device="plutosdr",
            )

            meta = sigmf.fromfile(str(result))
            assert meta.hw == "ADALM-PLUTO", (
                "core:hw must come from DEVICE_PROFILES['plutosdr'] - "
                "a wrong driver key would write the wrong hardware name."
            )
            assert meta.get_global_field("mimir:device_profile") == "plutosdr"

    def test_sigmf_meta_hw_field_uses_device_profiles_display_name_directly(
        self, tmp_path
    ):
        """save_capture resolves core:hw via DEVICE_PROFILES, not a local dict."""
        samples = np.zeros(256, dtype=np.complex64)
        result = save_capture(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            device="hackrf",
            output_dir=tmp_path,
        )

        meta = sigmf.fromfile(str(result))
        assert meta.hw == "HackRF One"

    def test_bandwidth_hz_recorded_as_core_bandwidth_in_capture_record(
        self, tmp_path
    ):
        """bandwidth_hz lands in the capture record as core:bandwidth."""
        samples = np.zeros(256, dtype=np.complex64)
        result = save_capture(
            samples,
            freq_hz=1_090_000_000,
            sample_rate_hz=2_000_000,
            device="plutosdr",
            output_dir=tmp_path,
            bandwidth_hz=1_800_000,
        )

        meta = sigmf.fromfile(str(result))
        captures = meta.get_captures()
        assert len(captures) == 1
        assert captures[0][sigmf.FREQUENCY_KEY] == 1_090_000_000
        assert captures[0]["core:bandwidth"] == 1_800_000

    def test_bandwidth_hz_none_omits_core_bandwidth_field(self, tmp_path):
        """bandwidth_hz=None omits core:bandwidth entirely from the record."""
        samples = np.zeros(256, dtype=np.complex64)
        result = save_capture(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            output_dir=tmp_path,
        )

        meta = sigmf.fromfile(str(result))
        captures = meta.get_captures()
        assert len(captures) == 1
        assert captures[0][sigmf.FREQUENCY_KEY] == 98_000_000
        assert "core:bandwidth" not in captures[0]

    def test_hackrf_bandwidth_hz_logs_warning_and_still_records_metadata(
        self, tmp_path, caplog
    ):
        """HackRF + bandwidth_hz: warning logged, value still in SigMF metadata."""
        with patch("core.pipeline.capture.HackRFReceiver") as mock_hackrf_cls:
            mock_hackrf_cls.return_value = _mock_sdr_with_samples(256)

            with caplog.at_level(logging.WARNING, logger="core.pipeline.capture"):
                result = capture_and_save(
                    freq_hz=98_000_000,
                    num_samples=256,
                    sample_rate_hz=2_000_000,
                    band="fm_broadcast",
                    output_dir=tmp_path,
                    device="hackrf",
                    bandwidth_hz=1_800_000,
                )

            warnings = [
                r for r in caplog.records
                if r.levelno == logging.WARNING and "bandwidth_hz" in r.getMessage()
            ]
            assert warnings, "Expected a warning that bandwidth_hz is ignored on HackRF"
            assert "bandwidth_hz ignored" in warnings[0].getMessage()

            meta = sigmf.fromfile(str(result))
            assert meta.get_captures()[0]["core:bandwidth"] == 1_800_000

    def test_pluto_bandwidth_hz_passed_through_to_capture_iq_pluto(self, tmp_path):
        """Pluto + bandwidth_hz: the value reaches the PlutoReceiver constructor."""
        with patch("core.pipeline.capture.PlutoReceiver") as mock_pluto_cls:
            mock_pluto_cls.return_value = _mock_sdr_with_samples(256)

            capture_and_save(
                freq_hz=915_000_000,
                num_samples=256,
                sample_rate_hz=2_000_000,
                band="adsb",
                output_dir=tmp_path,
                device="plutosdr",
                bandwidth_hz=1_500_000,
            )

            assert mock_pluto_cls.call_args.kwargs["bandwidth_hz"] == 1_500_000

    def test_no_transmit_methods_called_on_pluto_via_capture_and_save(self, tmp_path):
        """TX-safety: no transmit-family method is invoked on the Pluto path."""
        with patch("core.pipeline.capture.PlutoReceiver") as mock_pluto_cls:
            mock_sdr = _mock_sdr_with_samples(256)
            mock_pluto_cls.return_value = mock_sdr

            capture_and_save(
                freq_hz=915_000_000,
                num_samples=256,
                sample_rate_hz=2_000_000,
                band="adsb",
                output_dir=tmp_path,
                device="plutosdr",
            )

            for method_name in TX_METHOD_NAMES:
                getattr(mock_sdr, method_name).assert_not_called()

            ctor_kwargs = mock_pluto_cls.call_args.kwargs
            for kwarg_name, kwarg_value in ctor_kwargs.items():
                assert kwarg_name not in TX_METHOD_NAMES
                assert kwarg_value not in TX_METHOD_NAMES

    def test_no_transmit_methods_called_on_hackrf_via_capture_and_save(self, tmp_path):
        """TX-safety: no transmit-family method is invoked on the HackRF path."""
        with patch("core.pipeline.capture.HackRFReceiver") as mock_hackrf_cls:
            mock_sdr = _mock_sdr_with_samples(256)
            mock_hackrf_cls.return_value = mock_sdr

            capture_and_save(
                freq_hz=98_000_000,
                num_samples=256,
                sample_rate_hz=2_000_000,
                band="fm_broadcast",
                output_dir=tmp_path,
                device="hackrf",
            )

            for method_name in TX_METHOD_NAMES:
                getattr(mock_sdr, method_name).assert_not_called()

            ctor_kwargs = mock_hackrf_cls.call_args.kwargs
            for kwarg_name, kwarg_value in ctor_kwargs.items():
                assert kwarg_name not in TX_METHOD_NAMES
                assert kwarg_value not in TX_METHOD_NAMES

    def test_capture_and_save_does_not_call_save_capture_with_unknown_device(
        self, tmp_path
    ):
        """The unknown-device ValueError fires before save_capture is reached."""
        with patch("core.pipeline.capture.save_capture") as mock_save, \
             patch("core.pipeline.capture.HackRFReceiver") as mock_hackrf_cls, \
             patch("core.pipeline.capture.PlutoReceiver") as mock_pluto_cls:
            with pytest.raises(ValueError, match="Unknown device 'bogus'"):
                capture_and_save(
                    freq_hz=98_000_000,
                    num_samples=1024,
                    sample_rate_hz=2_000_000,
                    band="fm_broadcast",
                    output_dir=tmp_path,
                    device="bogus",
                )

            mock_save.assert_not_called()
            mock_hackrf_cls.assert_not_called()
            mock_pluto_cls.assert_not_called()

    def test_unknown_band_raises_value_error_before_hardware_call(self, tmp_path):
        """An unrecognised band raises ValueError and never touches hardware."""
        with patch("core.pipeline.capture.HackRFReceiver") as mock_hackrf_cls, \
             patch("core.pipeline.capture.PlutoReceiver") as mock_pluto_cls, \
             patch("core.pipeline.capture.save_capture") as mock_save, \
             patch("core.pipeline.capture.compute_psd") as mock_psd, \
             patch("core.pipeline.capture.fingerprint_spectrum") as mock_fp:
            with pytest.raises(ValueError, match="Unknown band 'bogus_band'"):
                capture_and_save(
                    freq_hz=98_000_000,
                    num_samples=1024,
                    sample_rate_hz=2_000_000,
                    band="bogus_band",
                    output_dir=tmp_path,
                    device="hackrf",
                )

            mock_hackrf_cls.assert_not_called()
            mock_pluto_cls.assert_not_called()
            mock_psd.assert_not_called()
            mock_fp.assert_not_called()
            mock_save.assert_not_called()

    def test_valid_band_produces_fingerprint_and_passes_to_save_capture(
        self, tmp_path
    ):
        """A valid band yields a measured fingerprint passed to save_capture.

        compute_psd and fingerprint_spectrum run for real (via wraps spies)
        on a genuine numpy capture; only save_capture is mocked, to capture
        the fingerprint kwarg it receives.
        """
        with patch("core.pipeline.capture.HackRFReceiver") as mock_hackrf_cls, \
             patch("core.pipeline.capture.compute_psd", wraps=compute_psd) as spy_psd, \
             patch(
                 "core.pipeline.capture.fingerprint_spectrum",
                 wraps=fingerprint_spectrum,
             ) as spy_fp, \
             patch("core.pipeline.capture.save_capture") as mock_save:
            mock_hackrf_cls.return_value = _mock_sdr_with_samples(2048)

            capture_and_save(
                freq_hz=98_000_000,
                num_samples=2048,
                sample_rate_hz=2_000_000,
                band="fm_broadcast",
                output_dir=tmp_path,
                device="hackrf",
            )

            spy_psd.assert_called_once()
            spy_fp.assert_called_once()

            # The band profile supplies the per-band measurement parameters.
            profile = BAND_PROFILES["fm_broadcast"]
            fp_kwargs = spy_fp.call_args.kwargs
            assert fp_kwargs["signal_threshold_db"] == profile["signal_threshold_db"]
            assert fp_kwargs["crop_half_width_hz"] == profile["crop_half_width_hz"]
            assert fp_kwargs["burst_use_wide_window"] == profile.get(
                "burst_use_wide_window", False
            )

            mock_save.assert_called_once()
            fingerprint = mock_save.call_args.kwargs["fingerprint"]
            expected_keys = {
                "peak_freq_hz",
                "peak_power_db",
                "noise_floor_db",
                "snr_db",
                "bandwidth_hz",
                "occupied_bins",
                "spectral_flatness",
            }
            for key in expected_keys:
                assert key in fingerprint, (
                    f"Fingerprint passed to save_capture is missing {key!r}."
                )


def _make_sequence_entry(sample_start, sample_count, **overrides):
    """A per-cycle fingerprint_sequence entry as the scan loop builds it:
    the seven _FINGERPRINT_METADATA_KEYS measurement fields plus the
    three replay-slicing fields (sample_start / sample_count /
    timestamp_sec)."""
    entry = {
        "peak_freq_hz": 98_000_500.0,
        "peak_power_db": -25.0,
        "noise_floor_db": -90.0,
        "snr_db": 65.0,
        "bandwidth_hz": 200_000.0,
        "occupied_bins": 100,
        "spectral_flatness": 0.1,
        "sample_start": sample_start,
        "sample_count": sample_count,
        "timestamp_sec": sample_start / 2_000_000,
    }
    entry.update(overrides)
    return entry


class TestSaveRecording:
    """Tests for the save_recording function (Phase 68 SigMF format).

    save_recording() sits alongside save_capture(): same filename
    convention, same legal provenance, same mimir: namespace, but it
    writes a per-cycle "mimir:fingerprint_sequence" JSON list instead of
    the singular "mimir:fingerprint" field. The two fields are mutually
    exclusive by construction.
    """

    def test_filename_matches_save_capture_pattern(self, tmp_path):
        """save_recording returns capture_{freq}hz_YYYYMMDD_HHMMSS.sigmf-meta
        plus a sibling .sigmf-data file, exactly as save_capture does."""
        samples = np.zeros(2048, dtype=np.complex64)
        result_path = save_recording(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            device="hackrf",
            fingerprint_sequence=[],
            output_dir=tmp_path,
        )

        pattern = r"capture_98000000hz_\d{8}_\d{6}\.sigmf-meta"
        assert re.match(pattern, result_path.name), (
            f"Filename '{result_path.name}' does not match expected pattern."
        )
        data_path = Path(str(result_path)[: -len(".sigmf-meta")] + ".sigmf-data")
        assert data_path.exists(), (
            f"Expected sibling .sigmf-data file at {data_path}, not found."
        )

    def test_metadata_round_trips_device_and_legal_provenance(self, tmp_path):
        """SigMF metadata carries device identity and the passive-RX note."""
        samples = np.zeros(256, dtype=np.complex64)
        result_path = save_recording(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            device="hackrf",
            fingerprint_sequence=[],
            output_dir=tmp_path,
        )

        meta = sigmf.fromfile(str(result_path))

        assert meta.hw == "HackRF One"
        assert meta.get_global_field("mimir:device_profile") == "hackrf"
        assert "Radiocommunications Act" in meta.description
        assert "ACMA" in meta.description

    def test_legal_description_byte_identical_to_save_capture(self, tmp_path):
        """The passive-RX legal provenance text must be byte-identical
        between save_capture() and save_recording(). A future edit to one
        that diverges from the other would silently split the legal
        contract across the two recording paths — this test fails first."""
        samples = np.zeros(256, dtype=np.complex64)
        capture_path = save_capture(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            output_dir=tmp_path,
        )
        recording_path = save_recording(
            samples,
            freq_hz=145_175_000,
            sample_rate_hz=2_000_000,
            device="hackrf",
            fingerprint_sequence=[],
            output_dir=tmp_path,
        )

        capture_meta = sigmf.fromfile(str(capture_path))
        recording_meta = sigmf.fromfile(str(recording_path))
        assert recording_meta.description == capture_meta.description

    def test_fingerprint_sequence_round_trips_as_json_list(self, tmp_path):
        """A 2-entry fingerprint_sequence lands under
        mimir:fingerprint_sequence as a list of dicts, each carrying
        exactly the seven measurement keys plus the three slicing fields."""
        sequence = [
            _make_sequence_entry(0, 2048),
            _make_sequence_entry(2048, 1024),
        ]
        samples = np.zeros(3072, dtype=np.complex64)
        result_path = save_recording(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            device="hackrf",
            fingerprint_sequence=sequence,
            output_dir=tmp_path,
        )

        meta = sigmf.fromfile(str(result_path))
        stored = meta.get_global_field("mimir:fingerprint_sequence")
        assert isinstance(stored, list)
        assert len(stored) == 2
        expected_keys = set(_FINGERPRINT_METADATA_KEYS) | {
            "sample_start",
            "sample_count",
            "timestamp_sec",
        }
        for entry in stored:
            assert set(entry.keys()) == expected_keys
        assert stored[0]["sample_start"] == 0
        assert stored[0]["sample_count"] == 2048
        assert stored[0]["timestamp_sec"] == 0.0
        assert stored[1]["sample_start"] == 2048
        assert stored[1]["sample_count"] == 1024
        assert stored[1]["timestamp_sec"] == 2048 / 2_000_000

    def test_singular_mimir_fingerprint_field_is_absent(self, tmp_path):
        """The recording path must NEVER write the singular
        mimir:fingerprint field — the two fields are mutually exclusive
        by construction, so no downstream reader faces an either/or."""
        samples = np.zeros(256, dtype=np.complex64)
        result_path = save_recording(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            device="hackrf",
            fingerprint_sequence=[_make_sequence_entry(0, 256)],
            output_dir=tmp_path,
        )

        meta = sigmf.fromfile(str(result_path))
        assert meta.get_global_field("mimir:fingerprint") is None, (
            "save_recording must omit mimir:fingerprint entirely, not "
            "write an empty or null field."
        )

    def test_internal_keys_filtered_per_entry(self, tmp_path):
        """Internal-only detection-pipeline keys (signal_threshold_db,
        snr_margin_db, is_burst, etc.) are stripped from every per-cycle
        entry even when the caller passes them — save_recording has the
        same defensive filtering property as save_capture regardless of
        what the caller hands over."""
        dirty = _make_sequence_entry(
            0,
            256,
            signal_threshold_db=21.0,
            snr_margin_db=44.0,
            is_burst=True,
        )
        samples = np.zeros(256, dtype=np.complex64)
        result_path = save_recording(
            samples,
            freq_hz=98_000_000,
            sample_rate_hz=2_000_000,
            device="hackrf",
            fingerprint_sequence=[dirty],
            output_dir=tmp_path,
        )

        meta = sigmf.fromfile(str(result_path))
        stored = meta.get_global_field("mimir:fingerprint_sequence")
        assert len(stored) == 1
        expected_keys = set(_FINGERPRINT_METADATA_KEYS) | {
            "sample_start",
            "sample_count",
            "timestamp_sec",
        }
        assert set(stored[0].keys()) == expected_keys
        assert "signal_threshold_db" not in stored[0]
        assert "snr_margin_db" not in stored[0]
        assert "is_burst" not in stored[0]
