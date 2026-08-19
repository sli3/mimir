"""
tests/tools/test_replay_capture.py — Tests for the replay CLI tool (Phase 70)

Exercises tools/replay_capture.py's argparse structure, exit codes, JSON
output flag, tolerance override, and Ctrl+C handling against REAL SigMF
files built in tmp_path via save_capture() / save_recording() — no
hardware.

Run with:
    uv run pytest tests/tools/test_replay_capture.py -v
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from core.pipeline.capture import save_capture, save_recording
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from dashboard.shared_state import BAND_PROFILES
from tools.replay_capture import _parse_args, main


_FREQ_HZ = 98_000_000
_SAMPLE_RATE_HZ = 2_000_000


def _make_samples(num_samples: int, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (
        rng.standard_normal(num_samples) + 1j * rng.standard_normal(num_samples)
    ).astype(np.complex64)


def _expected_fingerprint(samples, freq_hz, sample_rate_hz, band_key):
    profile = BAND_PROFILES[band_key]
    psd_result = compute_psd(samples, sample_rate_hz, freq_hz)
    return fingerprint_spectrum(
        psd_result,
        signal_threshold_db=profile.get("signal_threshold_db"),
        crop_half_width_hz=profile.get("crop_half_width_hz"),
        burst_use_wide_window=profile.get("burst_use_wide_window", False),
        trace_key=profile.get("fingerprint_trace_key", "psd_db"),
    )


def _build_one_shot(tmp_path: Path, snr_bump_db: float = 0.0) -> Path:
    """Write a real one-shot capture; optionally skew the saved snr_db."""
    samples = _make_samples(16_384)
    fingerprint = _expected_fingerprint(
        samples, _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
    )
    if snr_bump_db:
        fingerprint["snr_db"] = float(fingerprint["snr_db"]) + snr_bump_db
    return save_capture(
        samples,
        freq_hz=_FREQ_HZ,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        output_dir=tmp_path,
        fingerprint=fingerprint,
    )


def _build_recording(tmp_path: Path) -> Path:
    """Write a real 2-cycle Record-mode capture."""
    samples = _make_samples(2 * 8192)
    sequence = []
    start = 0
    for chunk_samples in (samples[0:8192], samples[8192:16384]):
        fingerprint = _expected_fingerprint(
            chunk_samples, _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        sequence.append({
            **fingerprint,
            "sample_start": start,
            "sample_count": len(chunk_samples),
            "timestamp_sec": start / _SAMPLE_RATE_HZ,
        })
        start += len(chunk_samples)
    return save_recording(
        samples,
        freq_hz=_FREQ_HZ,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        device="hackrf",
        fingerprint_sequence=sequence,
        output_dir=tmp_path,
    )


def _run_main(monkeypatch, argv):
    """Invoke the tool's main() with a patched sys.argv."""
    monkeypatch.setattr(sys, "argv", ["replay_capture.py", *argv])
    return main()


class TestParseArgs:
    """Argparse structure and defaults."""

    def test_defaults(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["replay_capture.py", "some.sigmf-meta"])
        args = _parse_args()
        assert args.path == Path("some.sigmf-meta")
        assert args.json is None
        assert args.tolerance_db == 0.1

    def test_json_and_tolerance_flags(self, monkeypatch):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "replay_capture.py",
                "some.sigmf-meta",
                "--json",
                "out.json",
                "--tolerance-db",
                "0.25",
            ],
        )
        args = _parse_args()
        assert args.json == Path("out.json")
        assert args.tolerance_db == 0.25


class TestMainSuccess:
    """Successful replays exit normally (no SystemExit), even with
    mismatches — mismatches are findings, not failures."""

    def test_one_shot_success(self, tmp_path, monkeypatch, capsys):
        meta_path = _build_one_shot(tmp_path)
        _run_main(monkeypatch, [str(meta_path)])
        out = capsys.readouterr().out
        assert "1/1 chunks matched within 0.1 dB tolerance" in out
        assert "fm_broadcast (exact match" in out

    def test_record_mode_success(self, tmp_path, monkeypatch, capsys):
        meta_path = _build_recording(tmp_path)
        _run_main(monkeypatch, [str(meta_path)])
        out = capsys.readouterr().out
        assert "2/2 chunks matched within 0.1 dB tolerance" in out
        # Record-mode chunk lines carry the slicing context.
        assert "sample_start=8192" in out

    def test_mismatch_still_exits_zero(self, tmp_path, monkeypatch, capsys):
        """A 5 dB saved/replayed gap prints MISMATCH but does not fail."""
        meta_path = _build_one_shot(tmp_path, snr_bump_db=5.0)
        _run_main(monkeypatch, [str(meta_path)])
        out = capsys.readouterr().out
        assert "0/1 chunks matched within 0.1 dB tolerance" in out
        assert "MISMATCH" in out

    def test_json_flag_writes_structured_result(
        self, tmp_path, monkeypatch, capsys
    ):
        meta_path = _build_one_shot(tmp_path)
        json_path = tmp_path / "result.json"
        _run_main(monkeypatch, [str(meta_path), "--json", str(json_path)])
        result = json.loads(json_path.read_text())
        assert result["summary"] == {
            "total_chunks": 1,
            "matched_chunks": 1,
            "mismatched_chunks": 0,
        }
        assert result["band_resolution"]["band_key"] == "fm_broadcast"
        assert "per_chunk_results" in result
        assert "written to" in capsys.readouterr().out

    def test_tolerance_override_honoured(self, tmp_path, monkeypatch, capsys):
        """The same 5 dB-skewed file flips to a match at 10 dB tolerance."""
        meta_path = _build_one_shot(tmp_path, snr_bump_db=5.0)
        _run_main(monkeypatch, [str(meta_path), "--tolerance-db", "10.0"])
        out = capsys.readouterr().out
        assert "1/1 chunks matched within 10.0 dB tolerance" in out


class TestMainFailures:
    """File-level failures exit 1; Ctrl+C exits 130."""

    def test_malformed_file_exits_1(self, tmp_path, monkeypatch, capsys):
        bad_path = tmp_path / "capture_98000000hz_20260819_000000.sigmf-meta"
        bad_path.write_text("not sigmf {{")
        with pytest.raises(SystemExit) as excinfo:
            _run_main(monkeypatch, [str(bad_path)])
        assert excinfo.value.code == 1
        assert "ERROR" in capsys.readouterr().out

    def test_missing_file_exits_1(self, tmp_path, monkeypatch, capsys):
        with pytest.raises(SystemExit) as excinfo:
            _run_main(monkeypatch, [str(tmp_path / "nope.sigmf-meta")])
        assert excinfo.value.code == 1

    def test_keyboard_interrupt_exits_130(self, tmp_path, monkeypatch, capsys):
        meta_path = _build_one_shot(tmp_path)

        def _interrupt(*args, **kwargs):
            raise KeyboardInterrupt

        # Patch the name as imported into the tool's own namespace.
        monkeypatch.setattr("tools.replay_capture.replay_capture", _interrupt)
        with pytest.raises(SystemExit) as excinfo:
            _run_main(monkeypatch, [str(meta_path)])
        assert excinfo.value.code == 130
        assert "Interrupted" in capsys.readouterr().out
