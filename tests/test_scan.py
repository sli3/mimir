"""Tests for scan.py startup errors, live shutdown and --device selection.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""
import logging
import sys
from collections.abc import Iterator
from unittest.mock import MagicMock, call, patch

import pytest

import scan
import dashboard.shared_state as shared_state
from core.device.detect import DetectedDevice
from core.device.hackrf_rx import HackRFReceiver
from core.device.pluto_rx import PlutoReceiver


def _hackrf_detected() -> DetectedDevice:
    """A DetectedDevice as detect_device would return for a HackRF One."""
    return DetectedDevice(
        driver="hackrf",
        display_name="HackRF One",
        min_freq_hz=1_000_000,
        max_freq_hz=6_000_000_000,
        gain_model="split",
        max_gain_db=62.0,
        wrapper_class=HackRFReceiver,
    )


def _pluto_detected() -> DetectedDevice:
    """A DetectedDevice as detect_device would return for an ADALM-PLUTO."""
    return DetectedDevice(
        driver="plutosdr",
        display_name="ADALM-PLUTO",
        min_freq_hz=325_000_000,
        max_freq_hz=3_800_000_000,
        gain_model="combined",
        max_gain_db=74.5,
        wrapper_class=PlutoReceiver,
    )


class TestScanStartupErrors:
    """Verify startup failures and ordered live scanner shutdown."""

    @pytest.fixture(autouse=True)
    def _patch_dependencies(self) -> Iterator[None]:
        """Mock live components with a successful wait and shared shutdown log."""
        with (
            patch("scan.load_config") as mock_load_config,
            patch("scan.detect_device") as mock_detect_device,
            patch("scan.build_device") as mock_build_device,
            patch("scan.SpectrumEmbedder"),
            patch("scan.SignalStore"),
            patch("scan.SignalClassifier"),
            patch("scan.ScanRunner") as mock_scan_runner_cls,
            patch("scan.AcarsSubscriber") as mock_acars_cls,
            patch("scan.AisSubscriber") as mock_ais_cls,
            patch("scan.AdsbSubscriber") as mock_adsb_cls,
            patch("scan.time.sleep"),
            patch("scan.start_server") as mock_start_server,
            patch.object(sys, "argv", ["scan.py"]),
        ):
            # Default: a HackRF is the detected device. Individual tests
            # override this when they exercise the Pluto path.
            mock_detect_device.return_value = _hackrf_detected()
            config = MagicMock()
            config.lna_gain_db = 24.0
            config.vga_gain_db = 26.0
            config.amp_enable = False
            config.dashboard_host = "127.0.0.1"
            config.dashboard_port = 5000
            config.frequencies_hz = [98_000_000]
            config.dwell_time_sec = 2.0
            config.num_samples = 2_000_000
            config.queue_maxsize = 20
            config.llm_url = "http://localhost:8080/v1"
            mock_load_config.return_value = config
            self.config = config

            mock_broadcast = MagicMock()
            mock_start_server.return_value = mock_broadcast
            mock_start_server._broadcast_spectrum_fn = MagicMock()

            scanner = mock_scan_runner_cls.return_value
            scanner.wait_stopped.return_value = True
            self.shutdown_calls = MagicMock()
            self.shutdown_calls.attach_mock(scanner.stop, "stop")
            self.shutdown_calls.attach_mock(scanner.wait_stopped, "wait_stopped")
            self.shutdown_calls.attach_mock(
                mock_acars_cls.return_value.stop, "stop_acars"
            )
            self.shutdown_calls.attach_mock(
                mock_ais_cls.return_value.stop, "stop_ais"
            )
            self.shutdown_calls.attach_mock(
                mock_adsb_cls.return_value.stop, "stop_adsb"
            )
            self.shutdown_calls.attach_mock(
                mock_build_device.return_value.close, "close"
            )

            self.mock_load_config = mock_load_config
            self.mock_detect_device = mock_detect_device
            self.mock_build_device = mock_build_device
            self.mock_scan_runner_cls = mock_scan_runner_cls
            yield

    def test_runtime_error_on_open_logs_and_exits(self, caplog):
        """A RuntimeError from device.open() must log at ERROR and exit code 1."""
        device = MagicMock()
        device.open.side_effect = RuntimeError("No HackRF device found")
        self.mock_build_device.return_value = device

        with pytest.raises(SystemExit) as exc_info:
            scan.main()

        assert exc_info.value.code == 1
        assert "Startup failed" in caplog.text
        assert "No HackRF device found" in caplog.text
        assert "Is the HackRF One connected?" in caplog.text

    def test_os_error_on_open_logs_and_exits(self, caplog):
        """An OSError from device.open() must log at ERROR and exit code 1."""
        device = MagicMock()
        device.open.side_effect = OSError("USB device not found")
        self.mock_build_device.return_value = device

        with pytest.raises(SystemExit) as exc_info:
            scan.main()

        assert exc_info.value.code == 1
        assert "Startup failed" in caplog.text
        assert "USB device not found" in caplog.text
        assert "Is the HackRF One connected?" in caplog.text

    def test_keyboard_interrupt_on_open_logs_and_exits(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Ctrl+C during open logs cancellation and exits before components start."""
        device = self.mock_build_device.return_value
        device.open.side_effect = KeyboardInterrupt

        with (
            patch("scan.start_server") as mock_start_server,
            caplog.at_level(logging.INFO, logger="scan"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 130
        assert (
            "scan",
            logging.INFO,
            "Start-up cancelled by user before the HackRF One was opened.",
        ) in caplog.record_tuples
        self.mock_scan_runner_cls.assert_not_called()
        mock_start_server.assert_not_called()
        device.close.assert_not_called()

    def test_keyboard_interrupt_on_build_logs_and_exits(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Ctrl+C during device construction logs cancellation and exits 130."""
        self.mock_build_device.side_effect = KeyboardInterrupt

        with caplog.at_level(logging.INFO, logger="scan"):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 130
        assert (
            "scan",
            logging.INFO,
            "Start-up cancelled by user before the HackRF One was opened.",
        ) in caplog.record_tuples

    def test_fatal_error_exits_with_code_1(self) -> None:
        """A fatal scan error exits with code 1 after a successful stop wait."""
        device = MagicMock()
        self.mock_build_device.return_value = device

        scanner = MagicMock()
        scanner.run.side_effect = Exception("Unexpected hardware fault")
        scanner.wait_stopped.return_value = True

        with patch("scan.ScanRunner", return_value=scanner):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 1

    def test_successful_startup_exits_zero_on_keyboard_interrupt(self) -> None:
        """Ctrl+C stops and waits before subscribers stop and the device closes."""
        device = self.mock_build_device.return_value
        scanner = self.mock_scan_runner_cls.return_value
        scanner.run.side_effect = KeyboardInterrupt

        with pytest.raises(SystemExit) as exc_info:
            scan.main()

        # Successful shutdown preserves the intentional Ctrl+C exit status.
        assert exc_info.value.code == 0
        device.open.assert_called_once()
        assert self.shutdown_calls.mock_calls == [
            call.stop(),
            call.wait_stopped(timeout=5.0),
            call.stop_acars(),
            call.stop_ais(),
            call.stop_adsb(),
            call.close(),
        ]

    def test_shutdown_wait_timeout_warns_and_closes_device(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A timed-out scan wait warns and still closes the live receiver."""
        scanner = self.mock_scan_runner_cls.return_value
        scanner.run.side_effect = KeyboardInterrupt
        scanner.wait_stopped.return_value = False

        with caplog.at_level(logging.WARNING, logger="scan"):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 0
        assert self.shutdown_calls.mock_calls == [
            call.stop(),
            call.wait_stopped(timeout=5.0),
            call.stop_acars(),
            call.stop_ais(),
            call.stop_adsb(),
            call.close(),
        ]
        assert (
            "scan",
            logging.WARNING,
            "Scan thread is still inside a device call; "
            "the receiver will be closed anyway.",
        ) in caplog.record_tuples


class TestDeviceSelection:
    """Verify scan.py --device wiring (Phase 37)."""

    @pytest.fixture(autouse=True)
    def _patch_dependencies(self) -> Iterator[None]:
        """Mock device selection and a successful shutdown wait without hardware."""
        with (
            patch("scan.load_config") as mock_load_config,
            patch("scan.detect_device") as mock_detect_device,
            patch("scan.build_device") as mock_build_device,
            patch("scan.SpectrumEmbedder"),
            patch("scan.SignalStore"),
            patch("scan.SignalClassifier"),
            patch("scan.ScanRunner") as mock_scan_runner_cls,
            patch("scan.AcarsSubscriber"),
            patch("scan.AisSubscriber"),
            patch("scan.AdsbSubscriber"),
            patch("scan.time.sleep"),
            patch("scan.start_server") as mock_start_server,
        ):
            # Default: a HackRF is the detected device. Tests exercising
            # the Pluto path call _set_detected_driver("plutosdr").
            mock_detect_device.return_value = _hackrf_detected()
            config = MagicMock()
            config.lna_gain_db = 24.0
            config.vga_gain_db = 26.0
            config.amp_enable = False
            config.dashboard_host = "127.0.0.1"
            config.dashboard_port = 5000
            config.frequencies_hz = [98_000_000]
            config.dwell_time_sec = 2.0
            config.num_samples = 2_000_000
            config.queue_maxsize = 20
            config.llm_url = "http://localhost:8080/v1"
            mock_load_config.return_value = config
            self.config = config

            mock_broadcast = MagicMock()
            mock_start_server.return_value = mock_broadcast
            mock_start_server._broadcast_spectrum_fn = MagicMock()

            self.mock_detect_device = mock_detect_device
            self.mock_build_device = mock_build_device
            self.mock_scan_runner = mock_scan_runner_cls.return_value
            self.mock_scan_runner.wait_stopped.return_value = True
            yield

    @pytest.fixture(autouse=True)
    def _restore_current_band(self):
        """The plutosdr startup path rewrites shared_state.current_band;
        restore it after each test so other suites see canonical state."""
        with shared_state.current_band_lock:
            original = dict(shared_state.current_band)
        yield
        with shared_state.current_band_lock:
            shared_state.current_band = original

    def _run_main(self, argv):
        with patch.object(sys, "argv", argv):
            with pytest.raises(SystemExit):
                scan.main()

    def _set_detected_driver(self, driver: str):
        """Point the mocked detect_device at the named driver.

        The default fixture state is a detected HackRF; tests that exercise
        the Pluto startup path call this first so main() resolves the
        plutosdr driver exactly as it would with real hardware present.
        """
        if driver == "plutosdr":
            self.mock_detect_device.return_value = _pluto_detected()
        else:
            self.mock_detect_device.return_value = _hackrf_detected()

    def test_default_device_prefers_pluto_when_both_present(self) -> None:
        """With no --device and both devices present (mocked detection
        resolving to Pluto), build_device is called with the plutosdr
        driver and helper_process=True. Pluto is the default per the 2026-07-15
        multi-device decision."""
        self._set_detected_driver("plutosdr")
        self.config.frequencies_hz = [915_000_000]
        self._run_main(["scan.py"])
        self.mock_build_device.assert_called_once_with(
            "plutosdr",
            lna_gain_db=24.0,
            vga_gain_db=26.0,
            amp_enable=False,
            helper_process=True,
        )

    def test_default_device_selects_hackrf_when_only_hackrf_present(self) -> None:
        """With no --device and only a HackRF present (mocked detection
        resolving to HackRF), build_device is called with the hackrf
        driver and helper_process=True."""
        self._run_main(["scan.py"])
        self.mock_build_device.assert_called_once_with(
            "hackrf",
            lna_gain_db=24.0,
            vga_gain_db=26.0,
            amp_enable=False,
            helper_process=True,
        )

    def test_explicit_hackrf_forces_hackrf_even_when_pluto_present(self) -> None:
        """--device hackrf is the manual override for the six sub-325 MHz
        bands: detect_device is consulted with preferred='hackrf' and the
        resolved driver passed to build_device is hackrf with
        helper_process=True, even when a Pluto is also present."""
        self._run_main(["scan.py", "--device", "hackrf"])
        self.mock_detect_device.assert_called_once_with(preferred="hackrf")
        self.mock_build_device.assert_called_once_with(
            "hackrf",
            lna_gain_db=24.0,
            vga_gain_db=26.0,
            amp_enable=False,
            helper_process=True,
        )

    def test_detect_device_runtime_error_exits_1(self, caplog):
        """A RuntimeError from detect_device (no supported SDR present)
        logs an error and exits 1 BEFORE build_device is ever called."""
        self.mock_detect_device.side_effect = RuntimeError(
            "No supported SDR device found"
        )

        with patch.object(sys, "argv", ["scan.py"]):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 1
        self.mock_build_device.assert_not_called()
        assert "SDR detection failed" in caplog.text
        assert "No supported SDR device found" in caplog.text

    def test_explicit_plutosdr_device(self) -> None:
        """--device plutosdr requests a Pluto helper-process receiver."""
        self._set_detected_driver("plutosdr")
        self.config.frequencies_hz = [915_000_000]
        self._run_main(["scan.py", "--device", "plutosdr"])
        self.mock_build_device.assert_called_once_with(
            "plutosdr",
            lna_gain_db=24.0,
            vga_gain_db=26.0,
            amp_enable=False,
            helper_process=True,
        )

    def test_plutosdr_with_supported_freq_focuses_on_first_supported(self):
        """Pluto startup focuses on the first configured frequency it can
        receive (915 MHz ISM here) and sets current_band to match."""
        self._set_detected_driver("plutosdr")
        self.config.frequencies_hz = [98_000_000, 915_000_000, 1_090_000_000]
        self._run_main(["scan.py", "--device", "plutosdr"])

        self.mock_scan_runner.set_focus_frequency.assert_called_once_with(
            915_000_000.0
        )
        with shared_state.current_band_lock:
            band = dict(shared_state.current_band)
        assert band["center_freq_hz"] == 915_000_000

    def test_plutosdr_with_no_supported_freq_exits_1(self, caplog):
        """Pluto with no receivable configured frequency exits 1 BEFORE the
        device is ever built or opened."""
        self._set_detected_driver("plutosdr")
        self.config.frequencies_hz = [98_000_000, 127_000_000]

        with patch.object(sys, "argv", ["scan.py", "--device", "plutosdr"]):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 1
        self.mock_build_device.assert_not_called()
        assert "No configured frequency is receivable" in caplog.text

    def test_plutosdr_with_only_adsb_focuses_on_1090(self):
        """Pluto with only ADS-B configured focuses on 1090 MHz and does
        not exit 1."""
        self._set_detected_driver("plutosdr")
        self.config.frequencies_hz = [1_090_000_000]

        with patch.object(sys, "argv", ["scan.py", "--device", "plutosdr"]):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 0
        self.mock_scan_runner.set_focus_frequency.assert_called_once_with(
            1_090_000_000.0
        )

    def test_plutosdr_with_out_of_range_freq_exits_1(self, caplog):
        """4 GHz is above Pluto's 3.8 GHz ceiling. The nearest-band lookup
        resolves it to "adsb" (a supported band), so a band-only check
        would slip through — HIGH-01: the range check must reject it and
        exit 1 BEFORE the device is ever built."""
        self._set_detected_driver("plutosdr")
        self.config.frequencies_hz = [4_000_000_000]

        with patch.object(sys, "argv", ["scan.py", "--device", "plutosdr"]):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 1
        self.mock_build_device.assert_not_called()
        assert "No configured frequency is receivable" in caplog.text
        assert "ADALM-PLUTO" in caplog.text

    def test_plutosdr_with_mixed_in_range_and_out_of_range_focuses_on_first_in_range(self):
        """The 4 GHz entry is out of range and skipped; the first in-range
        Pluto-supported frequency (1090 MHz ADS-B) wins."""
        self._set_detected_driver("plutosdr")
        self.config.frequencies_hz = [4_000_000_000, 1_090_000_000, 915_000_000]

        with patch.object(sys, "argv", ["scan.py", "--device", "plutosdr"]):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 0
        self.mock_scan_runner.set_focus_frequency.assert_called_once_with(
            1_090_000_000.0
        )

    def test_plutosdr_with_mixed_in_range_unsupported_skips_unsupported_focuses_on_first_supported(self):
        """98 MHz FM is IN Pluto's raw tuning range but the band is NOT
        supported for Pluto; the first in-range AND supported frequency
        (1090 MHz ADS-B) wins."""
        self._set_detected_driver("plutosdr")
        self.config.frequencies_hz = [98_000_000, 1_090_000_000, 915_000_000]

        with patch.object(sys, "argv", ["scan.py", "--device", "plutosdr"]):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 0
        self.mock_scan_runner.set_focus_frequency.assert_called_once_with(
            1_090_000_000.0
        )
