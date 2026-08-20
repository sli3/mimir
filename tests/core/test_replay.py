"""
tests/core/test_replay.py — Tests for the SigMF replay pipeline (Phase 70)

replay_capture() reads a SigMF capture from disk (NEVER hardware),
recomputes its spectral fingerprint under today's BAND_PROFILES, and
compares field-by-field against the fingerprint saved at capture time.

All tests build REAL SigMF files in tmp_path via save_capture() /
save_recording() with reproducible synthetic IQ (seeded
np.random.default_rng) — no hardware, no mocks of the pipeline itself.

Run with:
    uv run pytest tests/core/test_replay.py -v
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from core.pipeline.capture import save_capture, save_recording
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from core.pipeline.replay import (
    MAX_SEQUENCE_ENTRIES,
    ReplayFileError,
    _compare_fingerprints,
    replay_capture,
)
from dashboard.shared_state import (
    BAND_PROFILES,
    PLUTO_BAND_PROFILES,
    resolve_band_profile,
)


_FREQ_HZ = 98_000_000
_SAMPLE_RATE_HZ = 2_000_000


def _make_samples(num_samples: int, seed: int = 42) -> np.ndarray:
    """Reproducible synthetic noise IQ."""
    rng = np.random.default_rng(seed)
    return (
        rng.standard_normal(num_samples) + 1j * rng.standard_normal(num_samples)
    ).astype(np.complex64)


def _expected_fingerprint(
    samples: np.ndarray,
    freq_hz: float,
    sample_rate_hz: float,
    band_key: str,
) -> dict:
    """Fingerprint computed with the same BAND_PROFILES parameterisation
    replay_capture() must apply — all four fingerprint_spectrum()
    arguments from the one profile dict, including fingerprint_trace_key."""
    profile = BAND_PROFILES[band_key]
    psd_result = compute_psd(samples, sample_rate_hz, freq_hz)
    return fingerprint_spectrum(
        psd_result,
        signal_threshold_db=profile.get("signal_threshold_db"),
        crop_half_width_hz=profile.get("crop_half_width_hz"),
        burst_use_wide_window=profile.get("burst_use_wide_window", False),
        trace_key=profile.get("fingerprint_trace_key", "psd_db"),
    )


def _sequence_entry(fingerprint: dict, sample_start: int, sample_count: int,
                    sample_rate_hz: float = _SAMPLE_RATE_HZ) -> dict:
    """A per-cycle fingerprint_sequence entry as save_recording() expects:
    the measurement fields plus the three replay-slicing fields."""
    return {
        **fingerprint,
        "sample_start": sample_start,
        "sample_count": sample_count,
        "timestamp_sec": sample_start / sample_rate_hz,
    }


def _json_safe(obj):
    """Convert numpy scalars to plain Python numbers for json.dumps."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def _write_sigmf_pair(tmp_path, samples, global_fields, captures):
    """Write a .sigmf-meta / .sigmf-data pair by hand, bypassing
    save_capture() / save_recording() so the fixture can carry field
    shapes those writers would refuse (e.g. a non-numeric
    timestamp_sec, which save_recording() float()-coerces at write
    time, or a missing core:sample_rate, which both writers always
    set)."""
    base = tmp_path / "capture_98000000hz_20260819_000000"
    data_path = Path(str(base) + ".sigmf-data")
    meta_path = Path(str(base) + ".sigmf-meta")
    data_path.write_bytes(
        np.ascontiguousarray(samples, dtype="<c8").tobytes()
    )
    meta = {
        "global": _json_safe(
            {"core:datatype": "cf32_le", "core:version": "1.2.0",
             **global_fields}
        ),
        "captures": captures,
        "annotations": [],
    }
    meta_path.write_text(json.dumps(meta))
    return meta_path


class TestOneShotReplay:
    """One-shot captures (mimir:fingerprint, Phase 66 flavour)."""

    def test_one_shot_happy_path(self, tmp_path):
        """A file saved with its true fingerprint replays to a full match."""
        samples = _make_samples(16_384)
        fingerprint = _expected_fingerprint(
            samples, _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        meta_path = save_capture(
            samples,
            freq_hz=_FREQ_HZ,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            output_dir=tmp_path,
            fingerprint=fingerprint,
        )

        result = replay_capture(meta_path)

        assert result["summary"]["total_chunks"] == 1
        assert result["summary"]["matched_chunks"] == 1
        assert result["summary"]["mismatched_chunks"] == 0
        chunk = result["per_chunk_results"][0]
        assert chunk["comparison"]["all_match"] is True
        # Every one of the seven saved keys appears in the comparison.
        assert set(chunk["comparison"]["field_results"].keys()) == {
            "peak_freq_hz",
            "peak_power_db",
            "noise_floor_db",
            "snr_db",
            "bandwidth_hz",
            "occupied_bins",
            "spectral_flatness",
        }
        for field_result in chunk["comparison"]["field_results"].values():
            assert field_result["match"] is True
        assert result["file_metadata"]["fingerprint_field"] == "mimir:fingerprint"
        assert result["band_resolution"] == {
            "band_key": "fm_broadcast",
            "match": "exact",
            "band_center_freq_hz": 98_000_000,
            "profile_source": "hackrf_base",
        }

    def test_mismatch_detection(self, tmp_path):
        """A saved snr_db deliberately 5 dB off flags a mismatch with the
        correct delta — and mismatches are findings, not failures."""
        samples = _make_samples(16_384)
        fingerprint = _expected_fingerprint(
            samples, _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        fingerprint["snr_db"] = float(fingerprint["snr_db"]) + 5.0
        meta_path = save_capture(
            samples,
            freq_hz=_FREQ_HZ,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            output_dir=tmp_path,
            fingerprint=fingerprint,
        )

        result = replay_capture(meta_path)

        assert result["summary"]["mismatched_chunks"] == 1
        chunk = result["per_chunk_results"][0]
        assert chunk["comparison"]["all_match"] is False
        snr_result = chunk["comparison"]["field_results"]["snr_db"]
        assert snr_result["match"] is False
        assert snr_result["delta_db"] == pytest.approx(-5.0, abs=1e-6)

    def test_tolerance_override(self, tmp_path):
        """A 5 dB saved/replayed gap flags as a match under a 10 dB
        tolerance override."""
        samples = _make_samples(16_384)
        fingerprint = _expected_fingerprint(
            samples, _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        fingerprint["snr_db"] = float(fingerprint["snr_db"]) + 5.0
        meta_path = save_capture(
            samples,
            freq_hz=_FREQ_HZ,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            output_dir=tmp_path,
            fingerprint=fingerprint,
        )

        result = replay_capture(meta_path, tolerance_db=10.0)

        assert result["summary"]["matched_chunks"] == 1
        chunk = result["per_chunk_results"][0]
        assert chunk["comparison"]["all_match"] is True
        assert chunk["comparison"]["field_results"]["snr_db"]["match"] is True
        assert chunk["comparison"]["tolerance_db"] == 10.0

    def test_band_resolution_nearest(self, tmp_path):
        """A non-canonical frequency (99.5 MHz, between band centres)
        reports band_resolution.match == 'nearest' so the operator knows
        the threshold comparison is against a neighbouring profile."""
        freq_hz = 99_500_000  # nearest BAND_PROFILES centre: fm 98 MHz
        samples = _make_samples(16_384)
        fingerprint = _expected_fingerprint(
            samples, freq_hz, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        meta_path = save_capture(
            samples,
            freq_hz=freq_hz,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            output_dir=tmp_path,
            fingerprint=fingerprint,
        )

        result = replay_capture(meta_path)

        assert result["band_resolution"]["band_key"] == "fm_broadcast"
        assert result["band_resolution"]["match"] == "nearest"
        assert result["band_resolution"]["band_center_freq_hz"] == 98_000_000

    def test_trace_key_applied_for_adsb(self, tmp_path):
        """ADS-B replays against psd_max_hold_db, not the averaged trace.

        BAND_PROFILES['adsb'] carries fingerprint_trace_key='psd_max_hold_db'
        because squitters are short pulses the averaged trace dilutes.
        The saved fingerprint here is computed from the MAX-HOLD trace of
        bursty synthetic samples (a tone present in one chunk only). If
        replay dropped trace_key and fingerprinted the averaged trace,
        peak_power_db would come out lower and the comparison would
        mismatch — a match therefore proves the max-hold trace was used.
        """
        freq_hz = 1_090_000_000
        nfft = 2048
        num_chunks = 8
        samples = _make_samples(nfft * num_chunks, seed=7)
        # Strong tone in chunk 3 only, +200 kHz from centre (inside the
        # 900 kHz crop half-width), so max-hold >> averaged at its bin.
        tone_offset_hz = 200_000
        t = np.arange(nfft) / _SAMPLE_RATE_HZ
        tone = (10.0 * np.exp(2j * np.pi * tone_offset_hz * t)).astype(np.complex64)
        samples[3 * nfft : 4 * nfft] += tone

        fingerprint = _expected_fingerprint(
            samples, freq_hz, _SAMPLE_RATE_HZ, "adsb"
        )
        meta_path = save_capture(
            samples,
            freq_hz=freq_hz,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            output_dir=tmp_path,
            fingerprint=fingerprint,
        )

        result = replay_capture(meta_path)

        assert result["band_resolution"]["band_key"] == "adsb"
        assert result["band_resolution"]["match"] == "exact"
        assert result["summary"]["matched_chunks"] == 1
        assert result["per_chunk_results"][0]["comparison"]["all_match"] is True


class TestDeviceProfileResolution:
    """HIGH-01: replay must parameterise fingerprint_spectrum() with the
    device-resolved band profile (resolve_band_profile), not the raw
    BAND_PROFILES base."""

    def test_pluto_adsb_round_trip_uses_pluto_overlay(self, tmp_path):
        """A Pluto ADS-B capture whose fingerprint was computed at the
        PLUTO_BAND_PROFILES 10.0 dB threshold (calibrated 2026-08-17)
        must replay to a full match.

        Regression test for HIGH-01: before the fix, replay used raw
        BAND_PROFILES["adsb"] (signal_threshold_db 3.0 dB), so
        occupied_bins / bandwidth_hz recomputed at replay time differed
        structurally from the values saved at capture time (10.0 dB) and
        the tool reported a mismatch on a capture that never changed.
        """
        freq_hz = 1_090_000_000
        samples = _make_samples(16_384, seed=11)
        profile = resolve_band_profile("adsb", "plutosdr")
        assert profile["signal_threshold_db"] == (
            PLUTO_BAND_PROFILES["adsb"]["signal_threshold_db"]
        )
        psd_result = compute_psd(samples, _SAMPLE_RATE_HZ, freq_hz)
        fingerprint = fingerprint_spectrum(
            psd_result,
            signal_threshold_db=profile.get("signal_threshold_db"),
            crop_half_width_hz=profile.get("crop_half_width_hz"),
            burst_use_wide_window=profile.get("burst_use_wide_window", False),
            trace_key=profile.get("fingerprint_trace_key", "psd_db"),
        )
        meta_path = save_capture(
            samples,
            freq_hz=freq_hz,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            device="plutosdr",
            output_dir=tmp_path,
            fingerprint=fingerprint,
        )

        result = replay_capture(meta_path)

        assert result["band_resolution"]["profile_source"] == "pluto_overlay"
        assert result["summary"]["matched_chunks"] == 1
        assert result["per_chunk_results"][0]["comparison"]["all_match"] is True


class TestRecordModeReplay:
    """Record-mode captures (mimir:fingerprint_sequence, Phase 68 flavour)."""

    def test_record_mode_happy_path(self, tmp_path):
        """A 3-cycle recording replays every chunk to a full match and
        echoes each entry's slicing fields back."""
        samples = _make_samples(3 * 8192)
        chunks = [samples[0:8192], samples[8192:16384], samples[16384:24576]]
        sequence = []
        start = 0
        for chunk_samples in chunks:
            fingerprint = _expected_fingerprint(
                chunk_samples, _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
            )
            sequence.append(_sequence_entry(fingerprint, start, len(chunk_samples)))
            start += len(chunk_samples)
        meta_path = save_recording(
            samples,
            freq_hz=_FREQ_HZ,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            device="hackrf",
            fingerprint_sequence=sequence,
            output_dir=tmp_path,
        )

        result = replay_capture(meta_path)

        assert result["summary"]["total_chunks"] == 3
        assert result["summary"]["matched_chunks"] == 3
        assert result["file_metadata"]["fingerprint_field"] == (
            "mimir:fingerprint_sequence"
        )
        expected_starts = [0, 8192, 16384]
        for index, chunk in enumerate(result["per_chunk_results"]):
            assert chunk["comparison"]["all_match"] is True
            assert chunk["sample_start"] == expected_starts[index]
            assert chunk["sample_count"] == 8192
            assert chunk["timestamp_sec"] == pytest.approx(
                expected_starts[index] / _SAMPLE_RATE_HZ
            )

    def test_record_mode_entry_count_cap(self, tmp_path):
        """A fingerprint_sequence over the 10,000-entry cap is rejected
        BEFORE any samples are read."""
        fingerprint = {
            "peak_freq_hz": 98_000_500.0,
            "peak_power_db": -25.0,
            "noise_floor_db": -90.0,
            "snr_db": 65.0,
            "bandwidth_hz": 200_000.0,
            "occupied_bins": 100,
            "spectral_flatness": 0.1,
        }
        sequence = [
            _sequence_entry(fingerprint, 0, 0)
            for _ in range(MAX_SEQUENCE_ENTRIES + 1)
        ]
        samples = np.zeros(2048, dtype=np.complex64)
        meta_path = save_recording(
            samples,
            freq_hz=_FREQ_HZ,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            device="hackrf",
            fingerprint_sequence=sequence,
            output_dir=tmp_path,
        )

        with pytest.raises(ReplayFileError, match="cap"):
            replay_capture(meta_path)

    def test_record_mode_slice_beyond_file_total_rejected(self, tmp_path):
        """sample_start + sample_count beyond the file-implied total is a
        typed file error, not a silent short read."""
        fingerprint = _expected_fingerprint(
            _make_samples(4096), _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        samples = _make_samples(4096)
        sequence = [_sequence_entry(fingerprint, 0, 4097)]  # one past the end
        meta_path = save_recording(
            samples,
            freq_hz=_FREQ_HZ,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            device="hackrf",
            fingerprint_sequence=sequence,
            output_dir=tmp_path,
        )

        with pytest.raises(ReplayFileError, match="exceeds the file-implied"):
            replay_capture(meta_path)

    def test_record_mode_negative_sample_start_rejected(self, tmp_path):
        """Negative slicing fields are a typed file error."""
        fingerprint = _expected_fingerprint(
            _make_samples(4096), _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        samples = _make_samples(4096)
        sequence = [_sequence_entry(fingerprint, -1, 2048)]
        meta_path = save_recording(
            samples,
            freq_hz=_FREQ_HZ,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            device="hackrf",
            fingerprint_sequence=sequence,
            output_dir=tmp_path,
        )

        with pytest.raises(ReplayFileError, match="non-negative int"):
            replay_capture(meta_path)

    def test_record_mode_zero_sample_count_rejected(self, tmp_path):
        """MED-02: sample_count=0 must be a typed 400-class file error.

        0 passes a non-negative check, but read_samples(count=0) raises
        IOError — an OSError the /api/replay route would miscategorise
        as a 500 internal_error for what is really a client-named bad
        file."""
        fingerprint = _expected_fingerprint(
            _make_samples(4096), _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        samples = _make_samples(4096)
        sequence = [_sequence_entry(fingerprint, 0, 0)]
        meta_path = save_recording(
            samples,
            freq_hz=_FREQ_HZ,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            device="hackrf",
            fingerprint_sequence=sequence,
            output_dir=tmp_path,
        )

        with pytest.raises(ReplayFileError, match="positive int"):
            replay_capture(meta_path)

    def test_record_mode_non_numeric_timestamp_sec_rejected(self, tmp_path):
        """MED-03: timestamp_sec is one of the three documented
        replay-slicing fields; a non-numeric value must be a typed file
        error at validation time, not flow unvalidated into the result.

        save_recording() coerces timestamp_sec with float() at write
        time, so this fixture is written by hand via _write_sigmf_pair.
        """
        fingerprint = _expected_fingerprint(
            _make_samples(4096), _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        samples = _make_samples(4096)
        entry = {
            **fingerprint,
            "sample_start": 0,
            "sample_count": 4096,
            "timestamp_sec": "not-a-number",
        }
        meta_path = _write_sigmf_pair(
            tmp_path,
            samples,
            global_fields={
                "core:sample_rate": _SAMPLE_RATE_HZ,
                "mimir:device_profile": "hackrf",
                "mimir:fingerprint_sequence": [entry],
            },
            captures=[{"core:sample_start": 0, "core:frequency": _FREQ_HZ}],
        )

        with pytest.raises(ReplayFileError, match="timestamp_sec"):
            replay_capture(meta_path)


class TestFileFailures:
    """File-level failures are hard errors (ReplayFileError)."""

    def test_neither_fingerprint_field_present(self, tmp_path):
        """A SigMF file with no mimir: fingerprint field at all has
        nothing to compare against."""
        samples = _make_samples(4096)
        meta_path = save_capture(
            samples,
            freq_hz=_FREQ_HZ,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            output_dir=tmp_path,
            fingerprint=None,
        )

        with pytest.raises(ReplayFileError, match="neither"):
            replay_capture(meta_path)

    def test_malformed_file(self, tmp_path):
        """A non-SigMF file (corrupt JSON) raises ReplayFileError."""
        bad_path = tmp_path / "capture_98000000hz_20260819_000000.sigmf-meta"
        bad_path.write_text("this is not sigmf metadata {{")

        with pytest.raises(ReplayFileError, match="could not load"):
            replay_capture(bad_path)

    def test_missing_file(self, tmp_path):
        """A path that does not exist raises ReplayFileError."""
        missing = tmp_path / "nope.sigmf-meta"

        with pytest.raises(ReplayFileError):
            replay_capture(missing)

    def test_missing_sample_rate_raises_replay_file_error(self, tmp_path):
        """MED-01: a SigMF file with no core:sample_rate global field
        makes meta.sample_rate raise SigMFAccessError inside the sigmf
        library (it never returns None). Replay must convert that to
        ReplayFileError, never let the raw library exception escape to
        the route (500 HTML) or the CLI (raw traceback)."""
        samples = _make_samples(4096)
        meta_path = _write_sigmf_pair(
            tmp_path,
            samples,
            global_fields={
                "mimir:device_profile": "hackrf",
                "mimir:fingerprint": _expected_fingerprint(
                    samples, _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
                ),
            },
            captures=[{"core:sample_start": 0, "core:frequency": _FREQ_HZ}],
        )

        with pytest.raises(ReplayFileError, match="sigmf library error"):
            replay_capture(meta_path)


class TestComparisonPolicy:
    """Field-comparison semantics, exercised directly on
    _compare_fingerprints (NaN fingerprints are not producible from real
    samples, so the NaN policy is unit-tested here)."""

    def _base_saved(self):
        return {
            "peak_freq_hz": 98_000_500.0,
            "peak_power_db": -25.0,
            "noise_floor_db": -90.0,
            "snr_db": 65.0,
            "bandwidth_hz": 200_000.0,
            "occupied_bins": 205,
            "spectral_flatness": 0.1,
        }

    def test_nan_vs_nan_is_a_match(self):
        """NaN-vs-NaN matches under the module NaN policy: both sides are
        degenerate (noise-only capture), no semantic difference."""
        saved = self._base_saved()
        replayed = dict(saved)
        saved["snr_db"] = float("nan")
        replayed["snr_db"] = float("nan")

        comparison = _compare_fingerprints(saved, replayed, 0.1)

        assert comparison["field_results"]["snr_db"]["match"] is True
        assert comparison["all_match"] is True

    def test_finite_vs_nan_is_a_mismatch(self):
        """One side finite, the other NaN: a genuine difference."""
        saved = self._base_saved()
        replayed = dict(saved)
        replayed["snr_db"] = float("nan")

        comparison = _compare_fingerprints(saved, replayed, 0.1)

        assert comparison["field_results"]["snr_db"]["match"] is False
        assert comparison["all_match"] is False
        assert math.isnan(comparison["field_results"]["snr_db"]["delta_db"])

    def test_bandwidth_hz_float_exact(self):
        """bandwidth_hz compares float-exact (it is occupied_bins *
        hz_per_bin, a float) — a sub-Hz difference flags a mismatch."""
        saved = self._base_saved()
        replayed = dict(saved)
        replayed["bandwidth_hz"] = saved["bandwidth_hz"] + 0.5

        comparison = _compare_fingerprints(saved, replayed, 0.1)

        assert comparison["field_results"]["bandwidth_hz"]["match"] is False
        assert comparison["all_match"] is False

    def test_occupied_bins_integer_exact(self):
        """occupied_bins compares integer-exact — one bin difference flags."""
        saved = self._base_saved()
        replayed = dict(saved)
        replayed["occupied_bins"] = saved["occupied_bins"] + 1

        comparison = _compare_fingerprints(saved, replayed, 0.1)

        assert comparison["field_results"]["occupied_bins"]["match"] is False
        assert comparison["all_match"] is False

    def test_spectral_flatness_small_tolerance(self):
        """spectral_flatness allows a 1e-9 wobble (float log-sum) but
        flags anything meaningful."""
        saved = self._base_saved()
        replayed = dict(saved)
        replayed["spectral_flatness"] = saved["spectral_flatness"] + 5e-10
        comparison = _compare_fingerprints(saved, replayed, 0.1)
        assert comparison["field_results"]["spectral_flatness"]["match"] is True

        replayed["spectral_flatness"] = saved["spectral_flatness"] + 0.01
        comparison = _compare_fingerprints(saved, replayed, 0.1)
        assert comparison["field_results"]["spectral_flatness"]["match"] is False
        assert comparison["all_match"] is False


def test_saved_measurement_keys_is_identity_import_of_fingerprint_metadata_keys():
    """LOW-02: SAVED_MEASUREMENT_KEYS must be a real import alias, not a
    second independent tuple that happens to match. Identity (IS, not
    ==) is the only check that distinguishes the two cases."""
    from core.pipeline.capture import _FINGERPRINT_METADATA_KEYS
    from core.pipeline.replay import SAVED_MEASUREMENT_KEYS

    assert SAVED_MEASUREMENT_KEYS is _FINGERPRINT_METADATA_KEYS
