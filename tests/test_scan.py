"""Tests for scan.py startup error handling.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""
import sys
from unittest.mock import MagicMock, patch

import pytest

import scan


class TestScanStartupErrors:
    """Verify scan.py exits cleanly when the HackRF is unavailable."""

    @pytest.fixture(autouse=True)
    def _patch_dependencies(self):
        """Patch heavy dependencies so importing scan.py does not touch hardware."""
        with (
            patch("scan.load_config") as mock_load_config,
            patch("scan.HackRFReceiver") as mock_hackrf,
            patch("scan.SpectrumEmbedder"),
            patch("scan.SignalStore"),
            patch("scan.SignalClassifier"),
            patch("scan.ScanRunner"),
            patch("scan.AcarsSubscriber"),
            patch("scan.AisSubscriber"),
            patch("scan.AdsbSubscriber"),
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

            mock_broadcast = MagicMock()
            mock_start_server.return_value = mock_broadcast
            mock_start_server._broadcast_spectrum_fn = MagicMock()

            self.mock_load_config = mock_load_config
            self.mock_hackrf = mock_hackrf
            yield

    def test_runtime_error_on_open_logs_and_exits(self, caplog):
        """A RuntimeError from device.open() must log at ERROR and exit code 1."""
        device = MagicMock()
        device.open.side_effect = RuntimeError("No HackRF device found")
        self.mock_hackrf.return_value = device

        with pytest.raises(SystemExit) as exc_info:
            scan.main()

        assert exc_info.value.code == 1
        assert "Startup failed" in caplog.text
        assert "No HackRF device found" in caplog.text
        assert "Is the HackRF connected?" in caplog.text

    def test_os_error_on_open_logs_and_exits(self, caplog):
        """An OSError from device.open() must log at ERROR and exit code 1."""
        device = MagicMock()
        device.open.side_effect = OSError("USB device not found")
        self.mock_hackrf.return_value = device

        with pytest.raises(SystemExit) as exc_info:
            scan.main()

        assert exc_info.value.code == 1
        assert "Startup failed" in caplog.text
        assert "USB device not found" in caplog.text
        assert "Is the HackRF connected?" in caplog.text

    def test_successful_startup_exits_zero_on_keyboard_interrupt(self):
        """When device.open() succeeds, main() should enter the scan loop."""
        device = MagicMock()
        self.mock_hackrf.return_value = device

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
