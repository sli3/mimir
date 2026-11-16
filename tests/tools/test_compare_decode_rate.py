"""Smoke tests for decode-rate counting and CLI flow using mocked hardware."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from tools import compare_decode_rate


def test_run_capture_counts_accepted_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Count accepted frames and aircraft during one mocked capture iteration."""
    device = MagicMock()
    device.read_samples.return_value = np.zeros(8, dtype=np.complex64)
    demodulator = MagicMock()
    demodulator.demodulate.return_value = [
        "8D40621D58C382D690C8AC2863A7",
        "8D4840D6202CC371C32CE0576098",
    ]
    decoder = MagicMock()
    decoder.decode.side_effect = [SimpleNamespace(icao="ABC123"), None]
    clock = MagicMock()
    clock.monotonic.side_effect = [0, 0, 1, 1000, 1000]
    monkeypatch.setattr(
        compare_decode_rate, "AdsbDemodulator", MagicMock(return_value=demodulator)
    )
    monkeypatch.setattr(
        compare_decode_rate, "AdsbDecoder", MagicMock(return_value=decoder)
    )
    monkeypatch.setattr(compare_decode_rate, "time", clock)

    stats = compare_decode_rate._run_capture(device, "Mock receiver", 10)

    assert stats.valid_frames == 1
    assert stats.unique_aircraft == 1
    assert stats.chunks_processed == 1


def test_print_summary_labels_combined_frame_types(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Label the summary with the combined DF4/5/17/18 frame types."""
    hackrf = compare_decode_rate.DecodeStats(device_name="HackRF One")
    pluto = compare_decode_rate.DecodeStats(device_name="ADALM-PLUTO")

    compare_decode_rate._print_summary(hackrf, pluto)

    assert "valid frames (DF4/5/17/18)" in capsys.readouterr().out


def test_main_skip_pluto_uses_only_mocked_hackrf_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return success without a Pluto capture when --skip-pluto is supplied."""
    stats = compare_decode_rate.DecodeStats(device_name="HackRF One")
    capture_hackrf = MagicMock(return_value=stats)
    capture_pluto = MagicMock()
    monkeypatch.setattr("builtins.input", MagicMock(return_value=""))
    monkeypatch.setattr(compare_decode_rate, "_capture_hackrf", capture_hackrf)
    monkeypatch.setattr(compare_decode_rate, "_capture_pluto", capture_pluto)
    monkeypatch.setattr(compare_decode_rate.logging, "basicConfig", MagicMock())

    assert compare_decode_rate.main(["--skip-pluto", "--duration", "1"]) == 0

    capture_hackrf.assert_called_once_with(
        1.0,
        compare_decode_rate.HACKRF_ADSB_LNA_DB,
        compare_decode_rate.HACKRF_ADSB_VGA_DB,
    )
    capture_pluto.assert_not_called()
