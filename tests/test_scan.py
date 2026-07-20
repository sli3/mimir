"""Tests for scan.py startup error handling and --device selection.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""
import sys
from unittest.mock import MagicMock, patch

import pytest

import scan
import dashboard.shared_state as shared_state


class TestScanStartupErrors:
    """Verify scan.py exits cleanly when the SDR is unavailable."""

    @pytest.fixture(autouse=True)
    def _patch_dependencies(self):
        """Patch heavy dependencies so importing scan.py does not touch hardware."""
        with (
            patch("scan.load_config") as mock_load_config,
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
            patch.object(sys, "argv", ["scan.py"]),
        ):
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

            self.mock_load_config = mock_load_config
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

    def test_fatal_error_exits_with_code_1(self):
        """A generic Exception from scanner.run() must cause exit code 1."""
        device = MagicMock()
        self.mock_build_device.return_value = device

        scanner = MagicMock()
        scanner.run.side_effect = Exception("Unexpected hardware fault")

        with patch("scan.ScanRunner", return_value=scanner):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 1

    def test_successful_startup_exits_zero_on_keyboard_interrupt(self):
        """When device.open() succeeds, main() should enter the scan loop."""
        device = MagicMock()
        self.mock_build_device.return_value = device

        scanner = MagicMock()
        scanner.run.side_effect = KeyboardInterrupt

        with patch("scan.ScanRunner", return_value=scanner):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        # KeyboardInterrupt inside scanner.run() triggers the except block,
        # which prints a message and falls through to the finally block,
        # which calls sys.exit(0).
        assert exc_info.value.code == 0
        device.open.assert_called_once()


class TestDeviceSelection:
    """Verify scan.py --device wiring (Phase 37)."""

    @pytest.fixture(autouse=True)
    def _patch_dependencies(self):
        """Patch heavy dependencies so main() never touches hardware."""
        with (
            patch("scan.load_config") as mock_load_config,
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

            self.mock_build_device = mock_build_device
            self.mock_scan_runner = mock_scan_runner_cls.return_value
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

    def test_default_device_is_hackrf(self):
        """Without --device, build_device is called with the hackrf driver."""
        self._run_main(["scan.py"])
        self.mock_build_device.assert_called_once_with(
            "hackrf",
            lna_gain_db=24.0,
            vga_gain_db=26.0,
            amp_enable=False,
        )

    def test_explicit_plutosdr_device(self):
        """--device plutosdr routes to build_device with the plutosdr driver."""
        self.config.frequencies_hz = [915_000_000]
        self._run_main(["scan.py", "--device", "plutosdr"])
        self.mock_build_device.assert_called_once_with(
            "plutosdr",
            lna_gain_db=24.0,
            vga_gain_db=26.0,
            amp_enable=False,
        )

    def test_plutosdr_with_supported_freq_focuses_on_first_supported(self):
        """Pluto startup focuses on the first configured frequency it can
        receive (915 MHz ISM here) and sets current_band to match."""
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
        self.config.frequencies_hz = [98_000_000, 1_090_000_000, 915_000_000]

        with patch.object(sys, "argv", ["scan.py", "--device", "plutosdr"]):
            with pytest.raises(SystemExit) as exc_info:
                scan.main()

        assert exc_info.value.code == 0
        self.mock_scan_runner.set_focus_frequency.assert_called_once_with(
            1_090_000_000.0
        )
