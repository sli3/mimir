"""Freeze the dashboard's public names and payload shapes before its split.

Inspect runtime objects, never server source text. Payload values remain free
to change apart from the approved decode/fingerprint source discriminators.
"""

from collections.abc import Iterator
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

import dashboard.server as server
from core.pipeline.scan_result import ScanResult
from llm.classifier import ClassificationResult
from modules.acars.message import AcarsMessage
from modules.adsb.message import AdsbMessage
from modules.ais.message import AisMessage


SCAN_RESULT_KEYS = {
    "timestamp", "center_freq_hz", "signal_type", "confidence",
    "confidence_score", "novel", "au_legal_status", "reasoning",
    "peak_power_db", "peak_bin_power_db", "burst_ratio_db",
    "expected_noise_ratio_db", "burst_excess_db", "is_burst", "snr_db",
    "signal_threshold_db", "snr_margin_db", "bandwidth_hz",
    "spectral_flatness", "chroma_distance", "source",
}


class _StopLoop(Exception):
    """Stop the synchronous stats loop after its first emission."""


@pytest.fixture(autouse=True)
def isolated_server_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Restore shared server state and broadcast attributes after each test."""
    monkeypatch.setattr(server, "_focused_freq_hz", None)
    monkeypatch.setattr(server, "_scanner_ref", None)
    monkeypatch.setattr(server, "_device_ref", None)
    monkeypatch.setattr(server, "_last_hw_error_time", 0.0)
    attributes = ("_broadcast_fn", "_broadcast_spectrum_fn")
    previous = {
        name: getattr(server.start_server, name)
        for name in attributes if hasattr(server.start_server, name)
    }
    try:
        yield
    finally:
        for name in attributes:
            if name in previous:
                setattr(server.start_server, name, previous[name])
            elif hasattr(server.start_server, name):
                delattr(server.start_server, name)


@pytest.fixture
def adsb_message() -> AdsbMessage:
    """Provide a minimal real ADS-B message for payload shape checks."""
    return AdsbMessage(
        icao="7C4B4C", callsign=None, altitude_ft=None, latitude=None,
        longitude=None, groundspeed=None, track=None, vertical_rate=None,
        raw_hex="", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _assert_emission(emit: Mock, event: str, keys: set[str]) -> None:
    """Check one emitted event and its exact payload key set."""
    emit.assert_called_once()
    assert emit.call_args.args[0] == event
    assert set(emit.call_args.args[1]) == keys


def test_route_contract() -> None:
    """Freeze non-static routes, including the read-only recording status."""
    routes = {
        (rule.rule, frozenset(rule.methods - {"HEAD", "OPTIONS"}))
        for rule in server.app.url_map.iter_rules()
        if rule.endpoint != "static"
    }
    assert routes == {
        ("/", frozenset({"GET"})),
        ("/api/frequencies", frozenset({"GET"})),
        ("/api/adsb/parse", frozenset({"GET"})),
        ("/api/radar/reason", frozenset({"POST"})),
        ("/api/capture", frozenset({"POST"})),
        ("/api/record/start", frozenset({"POST"})),
        ("/api/record/stop", frozenset({"POST"})),
        ("/api/record/status", frozenset({"GET"})),
        ("/api/replay", frozenset({"POST"})),
        ("/api/captures", frozenset({"GET"})),
        ("/vectordb", frozenset({"GET"})),
        ("/radar", frozenset({"GET"})),
        ("/replay", frozenset({"GET"})),
        ("/api/vectorstore/points", frozenset({"GET"})),
    }
    assert len(routes) == 14


def test_socket_handler_contract() -> None:
    """Freeze the registered root-namespace SocketIO handler names."""
    assert server.socketio.server is not None
    assert set(server.socketio.server.handlers["/"]) == {
        "set_focus_frequency", "set_capture_trigger",
    }


def test_importable_names_contract() -> None:
    """Keep the public server facade available through future re-exports."""
    callable_names = {
        "start_server", "record_hw_error", "emit_acars_message",
        "emit_ais_message", "emit_adsb_aircraft", "emit_adsb_scan_result",
        "AdsbFieldTracker", "_compute_hackrf_status", "handle_set_focus",
        "handle_set_capture_trigger", "_get_signal_store",
    }
    attribute_names = {
        "app", "socketio", "_VECTORSTORE_CACHE", "_REPLAY_CAPTURES_DIR",
        "_focused_freq_hz", "_device_ref", "_last_hw_error_time",
        "_scanner_ref", "_path_reasoner", "_field_tracker", "time",
    }
    for name in callable_names | attribute_names:
        assert hasattr(server, name), name
    for name in callable_names | {"app"}:
        assert callable(getattr(server, name)), name


def test_acars_payload_contract() -> None:
    """Freeze the ACARS event name and payload keys."""
    message = AcarsMessage(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        freq_hz=130_025_000.0, mode="2", registration="VH-ABC",
        label="H1", block_id="A", text="", crc_ok=True,
    )
    with patch("dashboard.server.socketio.emit") as emit:
        server.emit_acars_message(message)
        _assert_emission(emit, "acars_message", {
            "timestamp", "freq_hz", "registration", "label", "block_id",
            "text", "crc_ok", "raw",
        })


def test_ais_payload_contract() -> None:
    """Freeze the AIS event name and payload keys."""
    message = AisMessage(
        mmsi="503000000", lat=None, lon=None, speed=None, course=None,
        vessel_name=None, msg_type=1, channel="A",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), raw_nmea="",
    )
    with patch("dashboard.server.socketio.emit") as emit:
        server.emit_ais_message(message)
        _assert_emission(emit, "ais_message", {
            "timestamp", "mmsi", "vessel_name", "lat", "lon", "speed",
            "course", "channel", "raw",
        })


def test_adsb_aircraft_payload_contract(adsb_message: AdsbMessage) -> None:
    """Freeze ADS-B keys, including the bearing rate in degrees per second."""
    with patch("dashboard.server.socketio.emit") as emit:
        server.emit_adsb_aircraft(adsb_message)
        # delta_r_deg_per_sec is bearing rate; deltaRNmPerSec is range rate.
        _assert_emission(emit, "adsb_aircraft", {
            "icao", "callsign", "altitude_ft", "latitude", "longitude",
            "groundspeed", "track", "vertical_rate", "squawk",
            "bearing_deg", "delta_r_deg_per_sec", "range_nm", "timestamp",
            "raw_hex",
        })


def test_decode_scan_result_contract(
    adsb_message: AdsbMessage, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Freeze the decoded scan-result shape while preserving tracker state."""
    monkeypatch.setattr(server._field_tracker, "_state", {})
    with patch("dashboard.server.socketio.emit") as emit:
        server.emit_adsb_scan_result(adsb_message)
        _assert_emission(emit, "scan_result", SCAN_RESULT_KEYS)
        assert emit.call_args.args[1]["source"] == "decode"


def test_broadcast_payload_contract() -> None:
    """Freeze attached broadcast names and fingerprint/spectrum payloads."""
    result = ScanResult(
        timestamp="2026-01-01T00:00:00+00:00", center_freq_hz=1.0e8,
        fingerprint={}, classification=ClassificationResult(
            signal_type="unknown", confidence="low", confidence_score=0.0,
            novel=False, reasoning="", au_legal_status="legal_rx",
            frequency_band="fm_broadcast_band", raw_response="",
        ),
    )
    with (
        patch("dashboard.server.socketio.emit") as emit,
        patch("dashboard.server.socketio.run"),
        patch("dashboard.server.threading.Thread"),
    ):
        server.start_server("127.0.0.1", 0)
        assert hasattr(server.start_server, "_broadcast_fn")
        assert hasattr(server.start_server, "_broadcast_spectrum_fn")
        server.start_server._broadcast_fn(result)
        _assert_emission(emit, "scan_result", SCAN_RESULT_KEYS)
        assert emit.call_args.args[1]["source"] == "fingerprint"
        emit.reset_mock()
        server.start_server._broadcast_spectrum_fn(
            [0.0, 1.0], 1.0e8, 9.9e7, 1.01e8,
        )
        _assert_emission(emit, "spectrum_update", {
            "psd_db", "center_freq_hz", "freq_min_hz", "freq_max_hz",
        })


def test_system_stats_payload_contract() -> None:
    """Freeze the stats payload using one synchronous scanner-free poll."""
    with (
        patch("dashboard.server.socketio.emit") as emit,
        patch("dashboard.server.socketio.run"),
        patch("dashboard.server.threading.Thread") as thread,
    ):
        server.start_server("127.0.0.1", 0)
        targets = [
            call.kwargs["target"] for call in thread.call_args_list
            if call.kwargs["target"].__name__ == "emit_stats"
        ]
        assert len(targets) == 1
        with patch(
            "dashboard.server.time.sleep", side_effect=[None, _StopLoop()],
        ):
            with pytest.raises(_StopLoop):
                targets[0]()
        _assert_emission(emit, "system_stats", {
            "hackrf_status", "active_frequency_hz", "scan_count",
            "queue_depth", "last_backlog", "llm_call_count",
            "llm_last_inference_ms", "device", "current_device_display",
            "unsupported_bands",
        })
