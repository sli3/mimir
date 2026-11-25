"""
tests/core/test_capture_pipeline.py — Tests for the IQ capture pipeline

Tests cover:
- capture_iq raises RuntimeError (not HardwareTransmitError) without hardware
- save_capture creates output_dir if missing
- save_capture filename matches expected SigMF pattern and writes the .sigmf-data sibling
- saved SigMF recording reloads as complex64 with matching data and metadata
- SigMF metadata round-trips device identity and legal provenance
- capture_iq and capture_iq_pluto never call transmit-family methods
- save_capture records the fingerprint as a nested mimir:fingerprint field
  (and omits it entirely when fingerprint is None)
- bandwidth_hz is recorded as SigMF core:bandwidth metadata (never as DSP)
- no TX patterns exist in capture.py
"""

import json
import sys
import os
import re
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest
import sigmf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.legal.compliance_guard import HardwareTransmitError
from core.pipeline.capture import (
    _FINGERPRINT_METADATA_KEYS,
    capture_iq,
    capture_iq_pluto,
    save_capture,
    save_recording,
)

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

    def test_no_transmit_method_called_on_hackrf_receiver(self) -> None:
        """capture_iq reads samples without calling transmit-family methods."""
        with patch("core.pipeline.capture.HackRFReceiver") as mock_receiver_cls:
            mock_sdr = MagicMock()
            mock_receiver_cls.return_value = mock_sdr

            capture_iq(
                freq_hz=98_000_000,
                num_samples=1024,
                sample_rate_hz=2_000_000,
                lna_gain_db=16,
                vga_gain_db=20,
            )

            mock_sdr.read_samples.assert_called_once_with(1024)
            for method_name in TX_METHOD_NAMES:
                getattr(mock_sdr, method_name).assert_not_called()

            # The constructor must never receive a transmit-direction argument.
            ctor_kwargs = mock_receiver_cls.call_args.kwargs
            for kwarg_name, kwarg_value in ctor_kwargs.items():
                assert kwarg_name not in TX_METHOD_NAMES
                assert kwarg_value not in TX_METHOD_NAMES


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


class TestSaveNameCollisions:
    """Both save paths preserve existing files and serialise name selection."""

    _BASE_NAME = "capture_98000000hz_20261124_152422"

    @pytest.fixture(autouse=True)
    def frozen_capture_time(self) -> Iterator[None]:
        """Freeze only the capture module's clock before any workers start."""
        with patch("core.pipeline.capture.datetime") as clock:
            clock.now.return_value = datetime(2026, 11, 24, 15, 24, 22)
            yield

    @pytest.fixture(params=["capture", "recording"])
    def saver(
        self, request: pytest.FixtureRequest, tmp_path: Path
    ) -> Callable[[np.ndarray], Path]:
        """Exercise each public save function with the same frequency and path."""
        kwargs = {
            "freq_hz": 98_000_000,
            "sample_rate_hz": 2_000_000,
            "device": "hackrf",
            "output_dir": tmp_path,
        }
        if request.param == "recording":
            return partial(save_recording, fingerprint_sequence=[], **kwargs)
        return partial(save_capture, **kwargs)

    def test_repeated_saves_preserve_first_pair(
        self, saver: Callable[[np.ndarray], Path]
    ) -> None:
        """Same-second saves use the exact plain, _2 and _3 names without loss."""
        first = saver(np.zeros(32, dtype=np.complex64))
        assert first.name == f"{self._BASE_NAME}.sigmf-meta"
        first_meta = first.read_bytes()
        first_data = first.with_suffix(".sigmf-data").read_bytes()

        second = saver(np.ones(32, dtype=np.complex64))
        third = saver(np.full(32, 2, dtype=np.complex64))
        assert second.name == f"{self._BASE_NAME}_2.sigmf-meta"
        assert third.name == f"{self._BASE_NAME}_3.sigmf-meta"
        for path in (first, second, third):
            assert path.exists()
            assert path.with_suffix(".sigmf-data").exists()
        assert first.read_bytes() == first_meta
        assert first.with_suffix(".sigmf-data").read_bytes() == first_data

    @pytest.mark.parametrize("extension", [".sigmf-meta", ".sigmf-data"])
    def test_orphaned_file_reserves_plain_name(
        self, saver: Callable[[np.ndarray], Path], tmp_path: Path, extension: str
    ) -> None:
        """Either half of an existing pair forces _2 and stays unchanged."""
        orphan = tmp_path / f"{self._BASE_NAME}{extension}"
        orphan.write_bytes(b"existing capture")
        result = saver(np.zeros(32, dtype=np.complex64))
        assert result.name == f"{self._BASE_NAME}_2.sigmf-meta"
        assert result.with_suffix(".sigmf-data").exists()
        assert orphan.read_bytes() == b"existing capture"

    def test_name_selection_and_write_hold_shared_lock(
        self, saver: Callable[[np.ndarray], Path]
    ) -> None:
        """Both save functions hold the shared lock during naming and writing."""
        from core.pipeline import capture

        samples = np.zeros(32, dtype=np.complex64)
        meta = sigmf.fromarray(samples)
        choose_base = capture._unique_base_path
        write_meta = meta.tofile
        lock_states = []

        def checked_base_path(output_dir: Path, freq_hz: float) -> Path:
            """Record the shared lock state when the real name chooser runs."""
            lock_states.append(("name", capture._SAVE_NAME_LOCK.locked()))
            return choose_base(output_dir, freq_hz)

        def checked_tofile(base_path: Path) -> None:
            """Record the shared lock state when the real SigMF write runs."""
            lock_states.append(("write", capture._SAVE_NAME_LOCK.locked()))
            write_meta(base_path)

        with (
            patch("core.pipeline.capture.sigmf.fromarray", return_value=meta),
            patch(
                "core.pipeline.capture._unique_base_path",
                side_effect=checked_base_path,
            ),
            patch.object(meta, "tofile", side_effect=checked_tofile),
        ):
            result = saver(samples)

        assert lock_states == [("name", True), ("write", True)]
        assert result.exists()
        assert result.with_suffix(".sigmf-data").exists()

    def test_concurrent_saves_choose_distinct_names(
        self, saver: Callable[[np.ndarray], Path]
    ) -> None:
        """Two threads at one frozen instant save distinct, complete pairs."""
        barrier = threading.Barrier(2)

        def save_at_barrier() -> Path:
            """Wait for the other request before saving at the frozen instant."""
            barrier.wait(timeout=5)
            return saver(np.zeros(32, dtype=np.complex64))

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(save_at_barrier) for _ in range(2)]
            paths = [future.result(timeout=10) for future in futures]
        assert {path.name for path in paths} == {
            f"{self._BASE_NAME}.sigmf-meta",
            f"{self._BASE_NAME}_2.sigmf-meta",
        }
        for path in paths:
            assert path.exists()
            assert path.with_suffix(".sigmf-data").exists()

    def test_exhausted_names_raise_file_exists_error(
        self, saver: Callable[[np.ndarray], Path], tmp_path: Path
    ) -> None:
        """The plain name and suffixes _2 through _999 exhaust the namespace."""
        (tmp_path / f"{self._BASE_NAME}.sigmf-meta").touch()
        for number in range(2, 1000):
            (tmp_path / f"{self._BASE_NAME}_{number}.sigmf-meta").touch()
        with pytest.raises(FileExistsError, match="_999"):
            saver(np.zeros(32, dtype=np.complex64))


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


class TestSharedSigmfMetadata:
    """Both paths retain shared metadata, ordering and fail-fast lookup."""

    @pytest.fixture(params=["capture", "recording"])
    def saver(self, request: pytest.FixtureRequest) -> Callable[..., Path]:
        """Supply each save path with its own populated fingerprint field."""
        entry = _make_sequence_entry(0, 256)
        if request.param == "recording":
            return partial(save_recording, fingerprint_sequence=[entry])
        return partial(
            save_capture,
            fingerprint={
                key: entry[key] for key in _FINGERPRINT_METADATA_KEYS
            },
        )

    @pytest.mark.parametrize(
        ("device", "hardware"),
        [("hackrf", "HackRF One"), ("plutosdr", "ADALM-PLUTO")],
    )
    def test_shared_fields_match_between_save_paths(
        self, tmp_path: Path, device: str, hardware: str,
    ) -> None:
        """Equal inputs produce equal shared globals and capture frequency."""
        samples = np.zeros(256, dtype=np.complex64)
        kwargs = {
            "freq_hz": 98_000_000,
            "sample_rate_hz": 2_000_000,
            "device": device,
            "output_dir": tmp_path,
        }
        capture_path = save_capture(samples, **kwargs)
        recording_path = save_recording(
            samples, fingerprint_sequence=[], **kwargs,
        )
        capture_json = json.loads(capture_path.read_text(encoding="utf-8"))
        recording_json = json.loads(recording_path.read_text(encoding="utf-8"))
        expected_globals = {
            "core:hw": hardware,
            "core:description": (
                "Mimir RF Scanner — passive receive only. "
                "Radiocommunications Act 1992 (Cth). ACMA jurisdiction. "
                "No transmission."
            ),
            sigmf.EXTENSIONS_KEY: [
                {"name": "mimir", "version": "1.0.0", "optional": True},
            ],
            "mimir:device_profile": device,
            "core:sample_rate": 2_000_000,
        }
        for key, expected in expected_globals.items():
            assert capture_json["global"][key] == expected
            assert recording_json["global"][key] == expected
        expected_capture = {
            "core:sample_start": 0, sigmf.FREQUENCY_KEY: 98_000_000,
        }
        assert capture_json["captures"] == [expected_capture]
        assert recording_json["captures"] == [expected_capture]

    def test_global_construction_and_written_order(
        self, tmp_path: Path, saver: Callable[..., Path],
    ) -> None:
        """Build shared globals before fingerprints; write sorted SigMF JSON."""
        samples = np.zeros(256, dtype=np.complex64)
        meta = sigmf.fromarray(samples)
        with patch("core.pipeline.capture.sigmf.fromarray", return_value=meta):
            result = saver(
                samples, freq_hz=98_000_000, sample_rate_hz=2_000_000,
                device="hackrf", output_dir=tmp_path,
            )

        fingerprint_key = (
            "mimir:fingerprint"
            if meta.get_global_field("mimir:fingerprint") is not None
            else "mimir:fingerprint_sequence"
        )
        construction_order = [
            "core:hw", "core:description", sigmf.EXTENSIONS_KEY,
            "mimir:device_profile", fingerprint_key,
        ]
        assert [
            key for key in meta.get_global_info() if key in construction_order
        ] == construction_order
        written_json = json.loads(result.read_text(encoding="utf-8"))
        written_globals = written_json["global"]
        # SigMF sorts global keys on serialisation, independently of insertion.
        assert list(written_globals) == sorted(written_globals)
        assert [
            key for key in written_globals if key in construction_order
        ] == [
            "core:description", sigmf.EXTENSIONS_KEY, "core:hw",
            "mimir:device_profile", fingerprint_key,
        ]

    def test_unknown_device_raises_before_writing(
        self, tmp_path: Path, saver: Callable[..., Path],
    ) -> None:
        """Create the directory, then reject unknown devices before writing."""
        output_dir = tmp_path / "new-captures"
        with pytest.raises(KeyError) as exc_info:
            saver(
                np.zeros(256, dtype=np.complex64), freq_hz=98_000_000,
                sample_rate_hz=2_000_000, device="unknown-device",
                output_dir=output_dir,
            )

        assert exc_info.value.args == ("unknown-device",)
        assert output_dir.is_dir()
        assert list(output_dir.iterdir()) == []


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
