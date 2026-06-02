"""Tests for tools/diagnose_live.py."""

from unittest.mock import MagicMock, patch

import pytest

from tools.diagnose_live import DiagnosticSession, _render_ascii_bar


# =============================================================================
# _render_ascii_bar
# =============================================================================


class TestRenderAsciiBar:
    """Tests for the _render_ascii_bar function."""

    def test_bar_is_20_chars_default(self) -> None:
        """Default bar output is exactly 20 characters wide."""
        psd = [-80.0] * 2048
        bar = _render_ascii_bar(psd)
        assert len(bar) == 20

    def test_all_weak_signal(self) -> None:
        """All values below -60 dBFS produce all weak chars."""
        psd = [-80.0] * 2048
        bar = _render_ascii_bar(psd)
        assert bar == "░" * 20

    def test_all_strong_signal(self) -> None:
        """All values above -60 dBFS produce all strong chars."""
        psd = [-50.0] * 2048
        bar = _render_ascii_bar(psd)
        assert bar == "█" * 20

    def test_mixed_signal_halves(self) -> None:
        """First half weak, second half strong produces correct split."""
        psd = [-80.0] * 1024 + [-50.0] * 1024
        bar = _render_ascii_bar(psd)
        assert bar == "░" * 10 + "█" * 10

    def test_empty_psd(self) -> None:
        """Empty PSD list produces all weak chars."""
        bar = _render_ascii_bar([])
        assert bar == "░" * 20

    def test_custom_width(self) -> None:
        """Custom width argument changes bar length."""
        psd = [-80.0] * 2048
        bar = _render_ascii_bar(psd, width=10)
        assert len(bar) == 10

    def test_single_bin(self) -> None:
        """Single value PSD produces correct bar."""
        bar = _render_ascii_bar([-50.0], width=5)
        assert bar == "█" * 5

    def test_boundary_at_threshold(self) -> None:
        """Value exactly at -60 dBFS is treated as weak (not greater than)."""
        psd = [-60.0] * 2048
        bar = _render_ascii_bar(psd)
        assert bar == "░" * 20

    def test_value_just_above_threshold(self) -> None:
        """Value just above -60 dBFS is treated as strong."""
        psd = [-59.9] * 2048
        bar = _render_ascii_bar(psd)
        assert bar == "█" * 20


# =============================================================================
# spectrum_update event handler
# =============================================================================


@pytest.fixture
def mock_session() -> DiagnosticSession:
    """Create a DiagnosticSession with a mocked socketio.Client."""
    with patch("tools.diagnose_live.socketio.Client") as mock_cls:
        mock_cls.return_value = MagicMock()
        session = DiagnosticSession("http://localhost:5000", 10)
        yield session


class TestSpectrumUpdateHandler:
    """Tests for the spectrum_update event handler."""

    def test_updates_count(self, mock_session: DiagnosticSession) -> None:
        """Handler increments the spectrum_update_count."""
        data = {
            "center_freq_hz": 98_900_000,
            "psd_db": [-80.0] * 2048,
        }
        mock_session._on_spectrum_update(data)
        assert mock_session.spectrum_update_count == 1

    def test_updates_count_multiple(self, mock_session: DiagnosticSession) -> None:
        """Multiple events increment count correctly."""
        data = {
            "center_freq_hz": 98_900_000,
            "psd_db": [-80.0] * 2048,
        }
        for _ in range(5):
            mock_session._on_spectrum_update(data)
        assert mock_session.spectrum_update_count == 5

    def test_records_timestamp(self, mock_session: DiagnosticSession) -> None:
        """Handler records a timestamp for each event."""
        data = {
            "center_freq_hz": 98_900_000,
            "psd_db": [-80.0] * 2048,
        }
        mock_session._on_spectrum_update(data)
        assert len(mock_session.spectrum_timestamps) == 1

    def test_correct_output_format(
        self, mock_session: DiagnosticSession, capsys: pytest.CaptureFixture
    ) -> None:
        """Handler prints correct output format to stdout."""
        data = {
            "center_freq_hz": 98_900_000,
            "psd_db": [-80.0, -70.0, -60.0, -50.0],
        }
        mock_session._on_spectrum_update(data)
        output = capsys.readouterr().out
        assert "[spectrum_update]" in output
        assert "bins=4" in output
        assert "dBFS" in output

    def test_empty_psd_no_crash(self, mock_session: DiagnosticSession) -> None:
        """Handler handles empty psd_db without crashing."""
        data = {"center_freq_hz": 98_900_000, "psd_db": []}
        mock_session._on_spectrum_update(data)
        assert mock_session.spectrum_update_count == 1

    def test_missing_psd_key(self, mock_session: DiagnosticSession) -> None:
        """Handler handles missing psd_db key gracefully."""
        data = {"center_freq_hz": 98_900_000}
        mock_session._on_spectrum_update(data)
        assert mock_session.spectrum_update_count == 1


# =============================================================================
# scan_result event handler
# =============================================================================


class TestScanResultHandler:
    """Tests for the scan_result event handler."""

    def test_updates_count(self, mock_session: DiagnosticSession) -> None:
        """Handler increments the scan_result_count."""
        data = {
            "center_freq_hz": 98_900_000,
            "signal_type": "fm_broadcast",
            "confidence": "high",
            "novel": False,
        }
        mock_session._on_scan_result(data)
        assert mock_session.scan_result_count == 1

    def test_correct_output_format(
        self, mock_session: DiagnosticSession, capsys: pytest.CaptureFixture
    ) -> None:
        """Handler prints correct fields in output."""
        data = {
            "center_freq_hz": 98_900_000,
            "signal_type": "fm_broadcast",
            "confidence": "high",
            "novel": False,
        }
        mock_session._on_scan_result(data)
        output = capsys.readouterr().out
        assert "[scan_result]" in output
        assert "98.900" in output
        assert "fm_broadcast" in output
        assert "high" in output
        assert "False" in output

    def test_novel_flag_true(
        self, mock_session: DiagnosticSession, capsys: pytest.CaptureFixture
    ) -> None:
        """Handler prints novel=True when novel flag is set."""
        data = {
            "center_freq_hz": 1_090_000_000,
            "signal_type": "unknown",
            "confidence": "low",
            "novel": True,
        }
        mock_session._on_scan_result(data)
        output = capsys.readouterr().out
        assert "novel=True" in output

    def test_handles_missing_fields(self, mock_session: DiagnosticSession) -> None:
        """Handler handles missing fields without crashing."""
        mock_session._on_scan_result({})
        assert mock_session.scan_result_count == 1


# =============================================================================
# PASS/FAIL logic
# =============================================================================


class TestPassFailLogic:
    """Tests for the PASS/FAIL exit logic."""

    def test_pass_both_events_received(self, mock_session: DiagnosticSession) -> None:
        """Exit code 0 when both event types received."""
        mock_session._on_spectrum_update(
            {"psd_db": [-80.0] * 2048, "center_freq_hz": 98_900_000}
        )
        mock_session._on_scan_result(
            {
                "center_freq_hz": 98_900_000,
                "signal_type": "fm",
                "confidence": "high",
                "novel": False,
            }
        )
        assert mock_session._determine_exit_code() == 0

    def test_fail_no_spectrum_update(self, mock_session: DiagnosticSession) -> None:
        """Exit code 1 when no spectrum_update received."""
        mock_session._on_scan_result(
            {
                "center_freq_hz": 98_900_000,
                "signal_type": "fm",
                "confidence": "high",
                "novel": False,
            }
        )
        assert mock_session._determine_exit_code() == 1

    def test_fail_no_scan_result(self, mock_session: DiagnosticSession) -> None:
        """Exit code 1 when no scan_result received."""
        mock_session._on_spectrum_update(
            {"psd_db": [-80.0] * 2048, "center_freq_hz": 98_900_000}
        )
        assert mock_session._determine_exit_code() == 1

    def test_fail_connection_error(self, mock_session: DiagnosticSession) -> None:
        """Exit code 1 when connection error occurred."""
        mock_session.connection_error = True
        mock_session._on_spectrum_update(
            {"psd_db": [-80.0] * 2048, "center_freq_hz": 98_900_000}
        )
        mock_session._on_scan_result(
            {
                "center_freq_hz": 98_900_000,
                "signal_type": "fm",
                "confidence": "high",
                "novel": False,
            }
        )
        assert mock_session._determine_exit_code() == 1

    def test_pass_determine_exit_code(self, mock_session: DiagnosticSession) -> None:
        """run() returns 0 when both events received and no error."""
        mock_session._on_spectrum_update(
            {"psd_db": [-80.0] * 2048, "center_freq_hz": 98_900_000}
        )
        mock_session._on_scan_result(
            {
                "center_freq_hz": 98_900_000,
                "signal_type": "fm",
                "confidence": "high",
                "novel": False,
            }
        )
        assert mock_session._determine_exit_code() == 0


# =============================================================================
# Gap detection
# =============================================================================


class TestGapDetection:
    """Tests for gap detection logic."""

    def test_no_gaps_with_uniform_timestamps(
        self, mock_session: DiagnosticSession
    ) -> None:
        """Uniform timestamps produce no gap flags."""
        mock_session.spectrum_timestamps = [100.0 + i * 1.0 for i in range(10)]
        result = mock_session._compute_gaps()
        assert result["gaps_found"] is False
        assert result["num_large_gaps"] == 0

    def test_gaps_detected_with_large_spike(
        self, mock_session: DiagnosticSession
    ) -> None:
        """Timestamps with a large gap are flagged."""
        mock_session.spectrum_timestamps = [
            100.0,
            101.0,
            102.0,
            110.0,
            111.0,
            112.0,
        ]
        result = mock_session._compute_gaps()
        assert result["gaps_found"] is True
        # median = 1.0, 5x = 5.0, gap = 8.0 > 5.0
        assert result["num_large_gaps"] >= 1

    def test_insufficient_data(self, mock_session: DiagnosticSession) -> None:
        """Fewer than 2 timestamps returns no gaps."""
        mock_session.spectrum_timestamps = [100.0]
        result = mock_session._compute_gaps()
        assert result["gaps_found"] is False
        assert result["num_gaps"] == 0

    def test_empty_timestamps(self, mock_session: DiagnosticSession) -> None:
        """No timestamps returns no gaps."""
        mock_session.spectrum_timestamps = []
        result = mock_session._compute_gaps()
        assert result["gaps_found"] is False

    def test_gap_structure(self, mock_session: DiagnosticSession) -> None:
        """Gap result has expected keys."""
        mock_session.spectrum_timestamps = [100.0, 101.0, 102.0]
        result = mock_session._compute_gaps()
        assert "gaps_found" in result
        assert "num_large_gaps" in result
        assert "large_gaps" in result
        assert "median_gap" in result
        assert "num_gaps" in result


# =============================================================================
# Event rate calculation
# =============================================================================


class TestEventRate:
    """Tests for event rate calculation."""

    def test_rate_with_zero_events(self, mock_session: DiagnosticSession) -> None:
        """Rate is 0.0 when no events received."""
        mock_session.spectrum_update_count = 0
        duration = max(mock_session.duration, 0.001)
        rate = mock_session.spectrum_update_count / duration
        assert rate == 0.0

    def test_rate_with_known_count(self, mock_session: DiagnosticSession) -> None:
        """Rate equals count / duration."""
        mock_session.spectrum_update_count = 50
        duration = max(mock_session.duration, 0.001)
        rate = mock_session.spectrum_update_count / duration
        assert rate == 5.0  # 50 / 10

    def test_rate_with_custom_duration(self) -> None:
        """Rate calculation works with different durations."""
        with patch("tools.diagnose_live.socketio.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            session = DiagnosticSession("http://localhost:5000", 30)
            session.spectrum_update_count = 60
            duration = max(session.duration, 0.001)
            rate = session.spectrum_update_count / duration
            assert rate == 2.0  # 60 / 30


# =============================================================================
# DiagnosticSession initialisation
# =============================================================================


class TestSessionInit:
    """Tests for DiagnosticSession initialisation."""

    def test_initial_counts_zero(self) -> None:
        """All counters start at zero."""
        with patch("tools.diagnose_live.socketio.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            session = DiagnosticSession("http://localhost:5000", 10)
            assert session.spectrum_update_count == 0
            assert session.scan_result_count == 0
            assert session.connection_error is False

    def test_handlers_registered(self) -> None:
        """Event handlers are registered on client."""
        mock_client = MagicMock()
        with patch("tools.diagnose_live.socketio.Client", return_value=mock_client):
            session = DiagnosticSession("http://localhost:5000", 10)
            assert session._client.on.call_count >= 2
            # Should have registered spectrum_update and scan_result
            registered_events = [
                call.args[0] for call in session._client.on.call_args_list
            ]
            assert "spectrum_update" in registered_events
            assert "scan_result" in registered_events
