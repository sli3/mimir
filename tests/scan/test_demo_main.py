"""
tests/scan/test_demo_main.py
Mimir RF Scanner — Phase 76 scan.py demo-mode dispatch tests

PURPOSE
-------
Tests for ``scan.py`` argument parsing and the demo-mode branch in
``main()``. Proves that ``--demo`` skips hardware detection, skips device
construction, skips decoder subscribers, and enters the demo path, while
the non-demo path remains unchanged.

Run with:
    uv run pytest tests/scan/test_demo_main.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.pipeline.capture import save_capture
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from dashboard.shared_state import BAND_PROFILES
from scan import main


_FREQ_HZ = 98_000_000
_SAMPLE_RATE_HZ = 2_000_000


def _make_samples(num_samples: int = 16_384, seed: int = 42) -> np.ndarray:
    """Reproducible synthetic noise IQ."""
    rng = np.random.default_rng(seed)
    return (
        rng.standard_normal(num_samples) + 1j * rng.standard_normal(num_samples)
    ).astype(np.complex64)


def _expected_fingerprint(samples, freq_hz, sample_rate_hz, band_key):
    """Fingerprint computed with the band profile parameterisation."""
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
    """Write a real one-shot SigMF capture at 98 MHz."""
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


def _write_cache(path: Path) -> None:
    """Write a minimal valid demo cache JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cache = {
        "version": 1,
        "device_driver": "hackrf",
        "files": {
            "abc": {
                "path": "/tmp/demo.sigmf-meta",
                "device_profile": "hackrf",
                "chunks": {
                    "0": {
                        "signal_type": "fm_broadcast",
                        "confidence": "high",
                        "confidence_score": 0.94,
                        "novel": False,
                        "reasoning": "Demo cache hit.",
                        "au_legal_status": "legal_rx",
                        "frequency_band": "fm_broadcast_band",
                        "raw_response": "{}",
                    }
                },
            }
        },
    }
    path.write_text(json.dumps(cache), encoding="utf-8")


def _patch_dependencies():
    """Return a context manager stack of patches for the demo branch."""
    # Each patch is applied via a context manager; the caller uses them
    # in a ``with`` chain.
    p_start_server = patch("scan.start_server")
    p_scanner = patch("scan.ScanRunner")
    p_demo_classifier = patch("scan.DemoSignalClassifier")
    p_demo_producer = patch("scan.DemoProducer")
    p_detect_device = patch("scan.detect_device")
    p_build_device = patch("scan.build_device")
    p_acars = patch("scan.AcarsSubscriber")
    p_ais = patch("scan.AisSubscriber")
    p_adsb = patch("scan.AdsbSubscriber")
    p_load_config = patch("scan.load_config")
    p_signal_store = patch("scan.SignalStore")
    p_embedder = patch("scan.SpectrumEmbedder")
    p_adsb_demo = patch("scan.AdsbDemoProducer")
    return (
        p_start_server,
        p_scanner,
        p_demo_classifier,
        p_demo_producer,
        p_detect_device,
        p_build_device,
        p_acars,
        p_ais,
        p_adsb,
        p_load_config,
        p_signal_store,
        p_embedder,
        p_adsb_demo,
    )


def _apply_patches(patches):
    """Enter all patches and return their mock objects plus a cleanup list."""
    mocks = []
    stack = []
    for p in patches:
        cm = p
        m = cm.start()
        mocks.append(m)
        stack.append(cm)

    # Configure the most common mocks so callers don't have to.
    mocks[0].return_value._broadcast_spectrum_fn = MagicMock()
    mocks[0]._broadcast_spectrum_fn = MagicMock()
    mocks[10].return_value = MagicMock()
    # AdsbDemoProducer mock needs the same shape as the real instance for
    # scan.py's finally block.
    mocks[12].return_value._thread = MagicMock()
    mocks[12].return_value._stop_event = MagicMock()

    return mocks, stack


def _stop_all(stack):
    """Exit all patches in reverse order."""
    for cm in reversed(stack):
        cm.stop()


# ── Argument-parsing tests ───────────────────────────────────────────────────

class TestDemoArgumentValidation:
    """Tests for the new --demo / --demo-files / --demo-cache arguments."""

    @patch.object(sys, "argv", ["scan.py", "--demo", "--device", "hackrf"])
    def test_demo_and_device_are_mutually_exclusive(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code != 0

    @patch.object(sys, "argv", ["scan.py", "--demo"])
    def test_demo_without_demo_files_errors(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code != 0


# ── Branch dispatch tests ─────────────────────────────────────────────────────

class TestDemoBranch:
    """Tests proving the demo branch executes and skips live-only setup."""

    def test_demo_device_attributes(self, tmp_path: Path) -> None:
        """DemoDevice.is_open is False, close() is a no-op, and any other
        attribute access raises NotImplementedError."""
        meta_path = _build_one_shot(tmp_path)
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path)

        patches = _patch_dependencies()
        mocks, stack = _apply_patches(patches)
        (
            _mock_start_server,
            mock_scanner,
            _mock_demo_classifier,
            _mock_demo_producer,
            _mock_detect_device,
            _mock_build_device,
            _mock_acars,
            _mock_ais,
            _mock_adsb,
            _mock_load_config,
            _mock_store,
            _mock_embedder,
            _mock_adsb_demo,
        ) = mocks

        mock_scanner.return_value.start_ai_only.side_effect = KeyboardInterrupt

        with patch.object(sys, "argv", [
            "scan.py",
            "--demo",
            "--demo-files", str(meta_path),
            "--demo-cache", str(cache_path),
        ]):
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 0
            finally:
                _stop_all(stack)

        assert mock_scanner.call_count == 1
        demo_device = mock_scanner.call_args[0][0]
        assert demo_device.is_open is False
        demo_device.close()  # no-op, must not raise
        with pytest.raises(NotImplementedError):
            demo_device.read_samples(1)

    def test_demo_branch_sets_shared_state_current_device(
        self, tmp_path: Path
    ) -> None:
        """Demo mode writes the real device driver key to
        shared_state.current_device before starting the producer."""
        import dashboard.shared_state as shared_state

        meta_path = _build_one_shot(tmp_path)
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path)

        # Save original value for restoration.
        original_device = shared_state.current_device

        patches = _patch_dependencies()
        mocks, stack = _apply_patches(patches)
        (
            _mock_start_server,
            mock_scanner,
            _mock_demo_classifier,
            _mock_demo_producer,
            _mock_detect_device,
            _mock_build_device,
            _mock_acars,
            _mock_ais,
            _mock_adsb,
            _mock_load_config,
            _mock_store,
            _mock_embedder,
            _mock_adsb_demo,
        ) = mocks

        mock_scanner.return_value.start_ai_only.side_effect = KeyboardInterrupt

        with patch.object(sys, "argv", [
            "scan.py",
            "--demo",
            "--demo-files", str(meta_path),
            "--demo-cache", str(cache_path),
        ]):
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 0
            finally:
                _stop_all(stack)
                shared_state.current_device = original_device

        assert shared_state.current_device == "hackrf"

    def test_demo_branch_skips_hardware_and_non_adsb_subscribers(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        meta_path = _build_one_shot(tmp_path)
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path)

        # Make the default ADS-B demo file exist so the conditional ADS-B
        # decode path is exercised deterministically.
        default_adsb_path = (
            tmp_path / "data" / "captures" /
            "capture_1090030000hz_20260820_153307.sigmf-meta"
        )
        default_adsb_path.parent.mkdir(parents=True, exist_ok=True)
        default_adsb_path.touch()
        monkeypatch.chdir(tmp_path)

        patches = _patch_dependencies()
        mocks, stack = _apply_patches(patches)
        (
            mock_start_server,
            mock_scanner,
            mock_demo_classifier,
            mock_demo_producer,
            mock_detect_device,
            mock_build_device,
            mock_acars,
            mock_ais,
            mock_adsb,
            _mock_load_config,
            _mock_store,
            _mock_embedder,
            mock_adsb_demo,
        ) = mocks

        # Simulate the AI loop returning quickly.
        mock_scanner.return_value.start_ai_only.side_effect = KeyboardInterrupt

        with patch.object(sys, "argv", [
            "scan.py",
            "--demo",
            "--demo-files", str(meta_path),
            "--demo-cache", str(cache_path),
        ]):
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 0
            finally:
                _stop_all(stack)

        mock_detect_device.assert_not_called()
        mock_build_device.assert_not_called()
        mock_acars.assert_not_called()
        mock_ais.assert_not_called()
        # ADS-B is started in demo mode via AdsbDemoProducer (TD-76-7).
        mock_adsb.assert_called_once()
        mock_adsb.return_value.start.assert_called_once()
        mock_adsb.return_value.stop.assert_called_once()
        mock_adsb_demo.assert_called_once()
        mock_adsb_demo.return_value.start.assert_called_once()
        mock_adsb_demo.return_value.stop.assert_called_once()
        mock_demo_classifier.assert_called_once()
        mock_demo_producer.assert_called_once()
        mock_scanner.return_value.start_ai_only.assert_called_once()
        mock_start_server.assert_called_once()

    def test_demo_cache_missing_exits_with_error(
        self, tmp_path: Path
    ) -> None:
        meta_path = _build_one_shot(tmp_path)
        missing_cache = tmp_path / "no_cache.json"

        patches = _patch_dependencies()
        mocks, stack = _apply_patches(patches)
        (
            _mock_start_server,
            mock_scanner,
            _mock_demo_classifier,
            _mock_demo_producer,
            mock_detect_device,
            mock_build_device,
            mock_acars,
            mock_ais,
            mock_adsb,
            _mock_load_config,
            _mock_store,
            _mock_embedder,
            _mock_adsb_demo,
        ) = mocks

        with patch.object(sys, "argv", [
            "scan.py",
            "--demo",
            "--demo-files", str(meta_path),
            "--demo-cache", str(missing_cache),
        ]):
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 1
            finally:
                _stop_all(stack)

        mock_detect_device.assert_not_called()
        mock_build_device.assert_not_called()
        mock_acars.assert_not_called()
        mock_ais.assert_not_called()
        mock_adsb.assert_not_called()

    def test_demo_files_missing_exits_with_error(
        self, tmp_path: Path
    ) -> None:
        missing_file = tmp_path / "missing.sigmf-meta"

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", [
                "scan.py",
                "--demo",
                "--demo-files", str(missing_file),
                "--demo-cache", str(tmp_path / "cache.json"),
            ]):
                main()

        assert exc_info.value.code == 1

    def test_explicit_adsb_demo_file_missing_exits_with_error(
        self, tmp_path: Path
    ) -> None:
        """--demo-files-adsb pointing at a non-existent file exits with code 1."""
        meta_path = _build_one_shot(tmp_path)
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path)
        missing_adsb = tmp_path / "missing_adsb.sigmf-meta"

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", [
                "scan.py",
                "--demo",
                "--demo-files", str(meta_path),
                "--demo-cache", str(cache_path),
                "--demo-files-adsb", str(missing_adsb),
            ]):
                main()

        assert exc_info.value.code == 1

    def test_missing_default_adsb_demo_path_graceful_degradation(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        """If the default ADS-B capture is absent, the fingerprint demo still
        runs and AdsbDemoProducer is never constructed.
        """
        meta_path = _build_one_shot(tmp_path)
        cache_path = tmp_path / "demo_cache.json"
        _write_cache(cache_path)

        # Run from a temp directory that does NOT contain the default
        # data/captures/<name>.sigmf-meta file.
        monkeypatch.chdir(tmp_path)

        patches = _patch_dependencies()
        mocks, stack = _apply_patches(patches)
        (
            mock_start_server,
            mock_scanner,
            mock_demo_classifier,
            mock_demo_producer,
            _mock_detect_device,
            _mock_build_device,
            _mock_acars,
            _mock_ais,
            mock_adsb,
            _mock_load_config,
            _mock_store,
            _mock_embedder,
            mock_adsb_demo,
        ) = mocks

        mock_scanner.return_value.start_ai_only.side_effect = KeyboardInterrupt

        with caplog.at_level("WARNING"):
            with patch.object(sys, "argv", [
                "scan.py",
                "--demo",
                "--demo-files", str(meta_path),
                "--demo-cache", str(cache_path),
            ]):
                try:
                    main()
                except SystemExit as exc:
                    assert exc.code == 0
                finally:
                    _stop_all(stack)

        mock_adsb.assert_not_called()
        mock_adsb_demo.assert_not_called()
        mock_demo_classifier.assert_called_once()
        mock_demo_producer.assert_called_once()
        mock_start_server.assert_called_once()
        assert "ADS-B demo file not found" in caplog.text


class TestLiveBranch:
    """Tests proving the non-demo path remains the live hardware path."""

    @patch("llm.classifier.requests.get")
    def test_live_path_calls_detect_and_build_device(self, mock_get) -> None:
        patches = _patch_dependencies()
        mocks, stack = _apply_patches(patches)
        (
            mock_start_server,
            mock_scanner,
            _mock_demo_classifier,
            _mock_demo_producer,
            mock_detect_device,
            mock_build_device,
            mock_acars,
            mock_ais,
            mock_adsb,
            _mock_load_config,
            _mock_store,
            _mock_embedder,
            _mock_adsb_demo,
        ) = mocks

        fake_device = MagicMock()
        fake_device.driver = "hackrf"
        fake_device.is_open = True
        fake_device.close = MagicMock()
        mock_build_device.return_value = fake_device

        fake_detected = MagicMock()
        fake_detected.driver = "hackrf"
        fake_detected.display_name = "HackRF One"
        mock_detect_device.return_value = fake_detected

        mock_scanner.return_value.run.side_effect = KeyboardInterrupt

        # Fake a reachable LLM so check_connection() does not try real HTTP.
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with patch.object(sys, "argv", ["scan.py", "--device", "hackrf"]):
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 0
            finally:
                _stop_all(stack)

        mock_detect_device.assert_called_once()
        mock_build_device.assert_called_once()
        mock_acars.assert_called_once()
        mock_ais.assert_called_once()
        mock_adsb.assert_called_once()
        mock_scanner.return_value.run.assert_called_once()
        fake_device.close.assert_called_once()
