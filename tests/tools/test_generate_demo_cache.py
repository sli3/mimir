"""
tests/tools/test_generate_demo_cache.py — Tests for generate_demo_cache.py

The generate_demo_cache tool reads SigMF files, fingerprints each chunk,
queries ChromaDB, and calls the LLM classifier to build a JSON cache. These
tests verify the CLI shape, dry-run behaviour, cache output format, and
error handling using real SigMF files built in tmp_path. The LLM is mocked
so no network calls are made.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from core.config.loader import ConfigError
from core.pipeline.capture import save_capture, save_recording
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from core.pipeline.replay import MAX_SEQUENCE_ENTRIES
from dashboard.shared_state import BAND_PROFILES
from llm.classifier import ClassificationResult
from tools.generate_demo_cache import _parse_args, main


_FREQ_HZ = 98_000_000
_SAMPLE_RATE_HZ = 2_000_000


@pytest.fixture(autouse=True)
def mock_config(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Keep every CLI test independent of the real configuration file."""
    loader = MagicMock(return_value=SimpleNamespace(
        llm_url="configured-endpoint",
        llm_cooldown_sec=17.0,
        llm_connect_timeout_sec=3.0,
    ))
    monkeypatch.setattr("tools.generate_demo_cache.load_config", loader)
    monkeypatch.delenv("MIMIR_LLM_URL", raising=False)
    return loader


@pytest.mark.parametrize("override", [None, "environment-endpoint"])
def test_classifier_uses_configured_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_config: MagicMock,
    override: str | None,
) -> None:
    """Use config timeouts and the configured URL or environment override."""
    meta_path = tmp_path / "input.sigmf-meta"
    meta_path.touch()
    classifier = MagicMock()
    monkeypatch.setattr("tools.generate_demo_cache.SignalClassifier", classifier)
    monkeypatch.setattr("tools.generate_demo_cache.SpectrumEmbedder", MagicMock())
    monkeypatch.setattr("tools.generate_demo_cache.AcmaReference", MagicMock())
    monkeypatch.setattr(
        "tools.generate_demo_cache._build_cache", MagicMock(return_value=0)
    )
    monkeypatch.delenv("MIMIR_LLM_URL", raising=False)
    if override is not None:
        monkeypatch.setenv("MIMIR_LLM_URL", override)

    exit_code = _run_main(monkeypatch, [
        "--files", str(meta_path), "--cache", str(tmp_path / "cache.json"),
    ])

    assert exit_code == 0
    mock_config.assert_called_once_with()
    config = mock_config.return_value
    classifier.assert_called_once_with(
        base_url=config.llm_url if override is None else override,
        cooldown_sec=config.llm_cooldown_sec,
        connect_timeout_sec=config.llm_connect_timeout_sec,
    )


def test_config_error_exits_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mock_config: MagicMock,
) -> None:
    """Configuration errors print a clear message and exit without traceback."""
    meta_path = tmp_path / "input.sigmf-meta"
    meta_path.touch()
    mock_config.side_effect = ConfigError("invalid scanner settings")
    classifier = MagicMock()
    monkeypatch.setattr("tools.generate_demo_cache.SignalClassifier", classifier)

    exit_code = _run_main(monkeypatch, [
        "--files", str(meta_path), "--cache", str(tmp_path / "cache.json"),
    ])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "ERROR: invalid scanner settings" in captured.out
    assert "Traceback" not in captured.out + captured.err
    classifier.assert_not_called()


def _make_samples(num_samples: int = 16_384, seed: int = 42) -> np.ndarray:
    """Reproducible synthetic noise IQ."""
    rng = np.random.default_rng(seed)
    return (
        rng.standard_normal(num_samples) + 1j * rng.standard_normal(num_samples)
    ).astype(np.complex64)


def _expected_fingerprint(samples, freq_hz, sample_rate_hz, band_key):
    """Fingerprint computed with the same band profile parameterisation."""
    profile = BAND_PROFILES[band_key]
    psd_result = compute_psd(samples, sample_rate_hz, freq_hz)
    return fingerprint_spectrum(
        psd_result,
        signal_threshold_db=profile.get("signal_threshold_db"),
        crop_half_width_hz=profile.get("crop_half_width_hz"),
        burst_use_wide_window=profile.get("burst_use_wide_window", False),
        trace_key=profile.get("fingerprint_trace_key", "psd_db"),
    )


def _build_one_shot(tmp_path: Path) -> Path:
    """Write a real one-shot SigMF capture."""
    samples = _make_samples(16_384)
    fingerprint = _expected_fingerprint(
        samples, _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
    )
    return save_capture(
        samples,
        freq_hz=_FREQ_HZ,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        output_dir=tmp_path,
        fingerprint=fingerprint,
    )


def _build_recording(tmp_path: Path, chunks: int = 2) -> Path:
    """Write a real Record-mode SigMF capture with ``chunks`` cycles."""
    samples = _make_samples(chunks * 8192)
    sequence = []
    start = 0
    for _ in range(chunks):
        chunk_samples = samples[start : start + 8192]
        fingerprint = _expected_fingerprint(
            chunk_samples, _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        sequence.append({
            **fingerprint,
            "sample_start": start,
            "sample_count": 8192,
            "timestamp_sec": start / _SAMPLE_RATE_HZ,
        })
        start += 8192
    return save_recording(
        samples,
        freq_hz=_FREQ_HZ,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        device="hackrf",
        fingerprint_sequence=sequence,
        output_dir=tmp_path,
    )


def _patch_classifier(monkeypatch, result: ClassificationResult):
    """Replace SignalClassifier in the tool with one returning a fixed result."""
    calls = []

    class FakeClassifier:
        def __init__(self, *args, **kwargs):
            pass

        def check_connection(self):
            return True

        def classify(self, fingerprint, neighbours, acma_allocations=None):
            calls.append({
                "fingerprint": fingerprint,
                "neighbours": neighbours,
                "acma_allocations": acma_allocations,
            })
            return result

    monkeypatch.setattr("tools.generate_demo_cache.SignalClassifier", FakeClassifier)
    return calls


def _run_main(monkeypatch, argv, fake_result=None):
    """Invoke the tool's main() with a patched sys.argv and mocked deps."""
    if fake_result is not None:
        _patch_classifier(monkeypatch, fake_result)
    monkeypatch.setattr(sys, "argv", ["generate_demo_cache.py", *argv])
    monkeypatch.setattr("tools.generate_demo_cache.SignalStore", lambda path: MagicMock(
        query=lambda vector, n_results=5: {
            "metadatas": [[]],
            "distances": [[]],
        },
    ))
    try:
        main()
    except SystemExit as exc:
        return exc.code


class TestParseArgs:
    """Argparse structure and validation."""

    def test_files_required(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["generate_demo_cache.py"])
        with pytest.raises(SystemExit):
            _parse_args()

    def test_cache_required_without_dry_run(self, monkeypatch):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "generate_demo_cache.py",
                "--files",
                "some.sigmf-meta",
            ],
        )
        args = _parse_args()
        assert args.dry_run is False
        assert args.cache is None


class TestDryRun:
    """Dry-run validates files and reports counts without classification."""

    def test_dry_run_one_shot(self, tmp_path, monkeypatch, capsys):
        meta_path = _build_one_shot(tmp_path)
        fake_calls = _patch_classifier(
            monkeypatch,
            ClassificationResult(
                signal_type="fm_broadcast",
                confidence="high",
                confidence_score=0.9,
                novel=False,
                reasoning="test",
                au_legal_status="legal_rx",
                frequency_band="fm_broadcast_band",
                raw_response="",
            ),
        )
        exit_code = _run_main(monkeypatch, [
            "--files",
            str(meta_path),
            "--dry-run",
        ])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "1 chunk(s) (one-shot)" in out
        assert "Total expected chunks: 1" in out
        assert fake_calls == []

    def test_dry_run_record_mode(self, tmp_path, monkeypatch, capsys):
        meta_path = _build_recording(tmp_path, chunks=3)
        exit_code = _run_main(monkeypatch, [
            "--files",
            str(meta_path),
            "--dry-run",
        ])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "3 chunk(s) (record-mode)" in out
        assert "Total expected chunks: 3" in out


class TestRealRun:
    """Real runs produce a cache JSON file."""

    def test_one_shot_cache_shape(self, tmp_path, monkeypatch, capsys):
        meta_path = _build_one_shot(tmp_path)
        cache_path = tmp_path / "cache.json"
        fake_result = ClassificationResult(
            signal_type="fm_broadcast",
            confidence="high",
            confidence_score=0.95,
            novel=False,
            reasoning="Strong FM match.",
            au_legal_status="legal_rx",
            frequency_band="fm_broadcast_band",
            raw_response="{}",
        )
        _patch_classifier(monkeypatch, fake_result)
        monkeypatch.setattr(sys, "argv", [
            "generate_demo_cache.py",
            "--files",
            str(meta_path),
            "--cache",
            str(cache_path),
        ])
        monkeypatch.setattr("tools.generate_demo_cache.SignalStore", lambda path: MagicMock(
            query=lambda vector, n_results=5: {
                "metadatas": [[{"label": "fm_broadcast"}]],
                "distances": [[0.031]],
            },
        ))

        try:
            main()
        except SystemExit as exc:
            exit_code = exc.code

        assert exit_code == 0
        assert cache_path.exists()
        raw = cache_path.read_text()
        cache = json.loads(raw)
        assert cache["version"] == 1
        assert cache["device_driver"] == "hackrf"
        assert len(cache["files"]) == 1
        file_entry = next(iter(cache["files"].values()))
        assert file_entry["path"] == str(meta_path.resolve())
        assert file_entry["device_profile"] == "hackrf"
        assert "chunks" in file_entry
        assert "0" in file_entry["chunks"]
        chunk = file_entry["chunks"]["0"]
        assert chunk["signal_type"] == "fm_broadcast"
        assert chunk["confidence"] == "high"
        assert chunk["confidence_score"] == pytest.approx(0.95)
        assert chunk["novel"] is False
        assert chunk["au_legal_status"] == "legal_rx"
        assert chunk["frequency_band"] == "fm_broadcast_band"
        assert chunk["raw_response"] == "{}"
        # Pretty-printed JSON uses indent=2.
        assert "  \"version\":" in raw

    def test_cache_pretty_printed_indent_2(self, tmp_path, monkeypatch):
        meta_path = _build_one_shot(tmp_path)
        cache_path = tmp_path / "cache.json"
        fake_result = ClassificationResult(
            signal_type="noise",
            confidence="low",
            confidence_score=0.9,
            novel=False,
            reasoning="noise",
            au_legal_status="legal_rx",
            frequency_band="unknown",
            raw_response="",
        )
        _patch_classifier(monkeypatch, fake_result)
        monkeypatch.setattr(sys, "argv", [
            "generate_demo_cache.py",
            "--files",
            str(meta_path),
            "--cache",
            str(cache_path),
        ])
        monkeypatch.setattr("tools.generate_demo_cache.SignalStore", lambda path: MagicMock())

        try:
            main()
        except SystemExit as exc:
            pass

        raw = cache_path.read_text()
        # Indent of 2 spaces means the opening brace is followed by a
        # two-space indented key on the next line.
        assert "\n  \"version\":" in raw

    def test_record_mode_multiple_chunks(self, tmp_path, monkeypatch):
        meta_path = _build_recording(tmp_path, chunks=3)
        cache_path = tmp_path / "cache.json"
        call_count = {"n": 0}

        class CountingClassifier:
            def __init__(self, *args, **kwargs):
                pass

            def classify(self, fingerprint, neighbours, acma_allocations=None):
                call_count["n"] += 1
                return ClassificationResult(
                    signal_type="fm_broadcast",
                    confidence="high",
                    confidence_score=0.9,
                    novel=False,
                    reasoning="test",
                    au_legal_status="legal_rx",
                    frequency_band="fm_broadcast_band",
                    raw_response="",
                )

        monkeypatch.setattr(
            "tools.generate_demo_cache.SignalClassifier", CountingClassifier
        )
        monkeypatch.setattr(sys, "argv", [
            "generate_demo_cache.py",
            "--files",
            str(meta_path),
            "--cache",
            str(cache_path),
        ])
        monkeypatch.setattr("tools.generate_demo_cache.SignalStore", lambda path: MagicMock(
            query=lambda vector, n_results=5: {
                "metadatas": [[{"label": "fm_broadcast"}]],
                "distances": [[0.01]],
            },
        ))

        try:
            main()
        except SystemExit as exc:
            exit_code = exc.code

        assert exit_code == 0
        cache = json.loads(cache_path.read_text())
        file_entry = next(iter(cache["files"].values()))
        assert set(file_entry["chunks"].keys()) == {"0", "1", "2"}
        assert call_count["n"] == 3


class TestFailures:
    """Malformed files and cap breaches are reported clearly."""

    def test_malformed_file_exits_non_zero(self, tmp_path, monkeypatch, capsys):
        bad_path = tmp_path / "capture_98000000hz_20260819_000000.sigmf-meta"
        bad_path.write_text("not sigmf {{")
        cache_path = tmp_path / "cache.json"
        exit_code = _run_main(monkeypatch, [
            "--files",
            str(bad_path),
            "--cache",
            str(cache_path),
        ])
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "ERROR" in out

    def test_missing_file_exits_non_zero(self, tmp_path, monkeypatch, capsys):
        missing = tmp_path / "nope.sigmf-meta"
        cache_path = tmp_path / "cache.json"
        exit_code = _run_main(monkeypatch, [
            "--files",
            str(missing),
            "--cache",
            str(cache_path),
        ])
        assert exit_code == 1
        assert "file not found" in capsys.readouterr().out

    def test_sequence_entry_cap_exits_non_zero(self, tmp_path, monkeypatch, capsys):
        """A fingerprint_sequence over MAX_SEQUENCE_ENTRIES is rejected."""
        samples = np.zeros(MAX_SEQUENCE_ENTRIES + 1, dtype=np.complex64)
        fingerprint = _expected_fingerprint(
            samples[:2048], _FREQ_HZ, _SAMPLE_RATE_HZ, "fm_broadcast"
        )
        sequence = [
            {
                **fingerprint,
                "sample_start": i,
                "sample_count": 1,
                "timestamp_sec": i / _SAMPLE_RATE_HZ,
            }
            for i in range(MAX_SEQUENCE_ENTRIES + 1)
        ]
        meta_path = save_recording(
            samples,
            freq_hz=_FREQ_HZ,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            device="hackrf",
            fingerprint_sequence=sequence,
            output_dir=tmp_path,
        )
        cache_path = tmp_path / "cache.json"
        exit_code = _run_main(monkeypatch, [
            "--files",
            str(meta_path),
            "--cache",
            str(cache_path),
        ])
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "cap" in out.lower()

    def test_failed_file_does_not_abort_good_file(
        self, tmp_path, monkeypatch, capsys
    ):
        """A bad file and a good file together: good file is cached, exit 1."""
        good_path = _build_one_shot(tmp_path)
        bad_path = tmp_path / "bad.sigmf-meta"
        bad_path.write_text("not sigmf")
        cache_path = tmp_path / "cache.json"
        fake_result = ClassificationResult(
            signal_type="fm_broadcast",
            confidence="high",
            confidence_score=0.9,
            novel=False,
            reasoning="test",
            au_legal_status="legal_rx",
            frequency_band="fm_broadcast_band",
            raw_response="",
        )
        _patch_classifier(monkeypatch, fake_result)
        monkeypatch.setattr(sys, "argv", [
            "generate_demo_cache.py",
            "--files",
            str(bad_path),
            str(good_path),
            "--cache",
            str(cache_path),
        ])
        monkeypatch.setattr("tools.generate_demo_cache.SignalStore", lambda path: MagicMock())

        try:
            main()
        except SystemExit as exc:
            exit_code = exc.code

        assert exit_code == 1
        cache = json.loads(cache_path.read_text())
        assert len(cache["files"]) == 1
        file_entry = next(iter(cache["files"].values()))
        assert file_entry["path"] == str(good_path.resolve())
