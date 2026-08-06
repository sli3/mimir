"""
tests/dashboard/test_radar_reason_endpoint.py — Flask endpoint tests for
POST /api/radar/reason (Phase 53)

Validation failures are the ONLY 400 path; LLM failures must surface as
a structured 200 with status="unavailable" — never a 500.

Run with:
    uv run pytest tests/dashboard/test_radar_reason_endpoint.py -v
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

import dashboard.server as server
from dashboard.server import app
from llm.path_reasoner import PathReasoner, ReasoningResult


def _valid_payload(**overrides) -> dict:
    payload = {
        "icao": "ABC123",
        "callsign": "QFA1",
        "squawk": "1200",
        "altitude_ft": 35000.0,
        "track": 270.0,
        "groundspeed": 450.0,
        "vertical_rate": 0.0,
        "bearing_deg": 45.0,
        "range_nm": 10.0,
        "theta_deg_per_sec": 0.5,
        "delta_r_nm_per_sec": -0.1,
        "projected_bearing_deg": 67.5,
        "projected_range_nm": 5.5,
        "trail_length": 3,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client():
    """Flask test client for the dashboard server."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def mock_reasoner():
    """Replace the shared PathReasoner with a mock for the test duration."""
    original = server._path_reasoner
    substitute = MagicMock()
    server._path_reasoner = substitute
    try:
        yield substitute
    finally:
        server._path_reasoner = original


@pytest.fixture
def real_reasoner():
    """Replace the shared PathReasoner with a real instance pointed at a
    test URL, so llm.path_reasoner.requests.post can be patched to drive
    genuine failure paths through the endpoint."""
    original = server._path_reasoner
    server._path_reasoner = PathReasoner(
        base_url="http://localhost:8080/v1", model="test-model"
    )
    try:
        yield server._path_reasoner
    finally:
        server._path_reasoner = original


class TestValidPayloads:
    def test_valid_payload_returns_200_with_reasoning_fields(
        self, client, mock_reasoner
    ):
        mock_reasoner.reason.return_value = ReasoningResult(
            status="ok",
            verdict="Steady cruise on a stable heading",
            confidence="high",
            notes="Projection consistent with current vector.",
            raw_response="{}",
            cause=None,
        )

        response = client.post("/api/radar/reason", json=_valid_payload())

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["verdict"] == "Steady cruise on a stable heading"
        assert data["confidence"] == "high"
        assert data["notes"] == "Projection consistent with current vector."
        assert data["cause"] is None

    def test_valid_payload_with_nullable_fields_null(self, client, mock_reasoner):
        """Null callsign/squawk/per-frame fields are a valid real state —
        ADS-B typecodes carry disjoint field sets and squawk is never
        decoded today (TD-53-A)."""
        mock_reasoner.reason.return_value = ReasoningResult(
            status="ok", verdict="v", confidence="low", notes="n",
            raw_response="", cause=None,
        )

        response = client.post(
            "/api/radar/reason",
            json=_valid_payload(
                callsign=None, squawk=None, altitude_ft=None,
                track=None, groundspeed=None, vertical_rate=None,
            ),
        )

        assert response.status_code == 200
        cleaned = mock_reasoner.reason.call_args[0][0]
        assert cleaned["callsign"] is None
        assert cleaned["squawk"] is None
        assert cleaned["altitude_ft"] is None


class TestValidationFailures:
    def test_empty_body_returns_400(self, client):
        response = client.post("/api/radar/reason")
        assert response.status_code == 400

    def test_non_object_body_returns_400(self, client):
        response = client.post(
            "/api/radar/reason",
            data="[1, 2, 3]",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_missing_icao_returns_400(self, client):
        payload = _valid_payload()
        del payload["icao"]
        response = client.post("/api/radar/reason", json=payload)
        assert response.status_code == 400

    def test_invalid_icao_charset_returns_400(self, client):
        response = client.post(
            "/api/radar/reason", json=_valid_payload(icao="ZZZZZZ")
        )
        assert response.status_code == 400

    def test_callsign_with_newline_returns_400(self, client):
        response = client.post(
            "/api/radar/reason", json=_valid_payload(callsign="QFA1\nINJECT")
        )
        assert response.status_code == 400

    def test_invalid_squawk_returns_400(self, client):
        response = client.post(
            "/api/radar/reason", json=_valid_payload(squawk="ABCD")
        )
        assert response.status_code == 400

    def test_non_octal_squawk_digit_returns_400(self, client):
        response = client.post(
            "/api/radar/reason", json=_valid_payload(squawk="1280")
        )
        assert response.status_code == 400

    def test_non_numeric_bearing_returns_400(self, client):
        response = client.post(
            "/api/radar/reason", json=_valid_payload(bearing_deg="north")
        )
        assert response.status_code == 400

    def test_nan_in_numeric_field_returns_400(self, client):
        # Python's json module serialises NaN by default, and Flask's
        # parser accepts it back — the endpoint must reject it itself.
        response = client.post(
            "/api/radar/reason", json=_valid_payload(bearing_deg=float("nan"))
        )
        assert response.status_code == 400

    def test_infinity_in_numeric_field_returns_400(self, client):
        response = client.post(
            "/api/radar/reason",
            json=_valid_payload(range_nm=float("inf")),
        )
        assert response.status_code == 400

    def test_bearing_above_360_returns_400(self, client):
        response = client.post(
            "/api/radar/reason", json=_valid_payload(bearing_deg=360.1)
        )
        assert response.status_code == 400

    def test_bearing_below_0_returns_400(self, client):
        response = client.post(
            "/api/radar/reason", json=_valid_payload(bearing_deg=-0.1)
        )
        assert response.status_code == 400

    def test_out_of_range_nullable_field_returns_400(self, client):
        response = client.post(
            "/api/radar/reason", json=_valid_payload(groundspeed=701.0)
        )
        assert response.status_code == 400

    def test_out_of_range_trail_length_returns_400(self, client):
        response = client.post(
            "/api/radar/reason", json=_valid_payload(trail_length=1001)
        )
        assert response.status_code == 400


class TestThetaBoundWidened:
    """Phase 55: theta_deg_per_sec bound widened from ±30 to ±90.

    The bound's job is prompt-injection defence, not physical
    plausibility filtering — a legitimate close overhead pass can exceed
    30°/s, so values up to ±90 must validate.
    """

    def _post_with_theta(self, client, mock_reasoner, theta):
        mock_reasoner.reason.return_value = ReasoningResult(
            status="ok", verdict="v", confidence="low", notes="n",
            raw_response="", cause=None,
        )
        return client.post(
            "/api/radar/reason",
            json=_valid_payload(theta_deg_per_sec=theta),
        )

    def test_theta_60_accepted(self, client, mock_reasoner):
        """60°/s was rejected under the old ±30 bound; now accepted."""
        response = self._post_with_theta(client, mock_reasoner, 60.0)
        assert response.status_code == 200

    def test_theta_45_accepted(self, client, mock_reasoner):
        response = self._post_with_theta(client, mock_reasoner, 45.0)
        assert response.status_code == 200

    def test_theta_89_99_accepted(self, client, mock_reasoner):
        response = self._post_with_theta(client, mock_reasoner, 89.99)
        assert response.status_code == 200

    def test_theta_90_boundary_accepted(self, client, mock_reasoner):
        """The boundary value itself is inclusive."""
        response = self._post_with_theta(client, mock_reasoner, 90.0)
        assert response.status_code == 200

    def test_theta_90_1_rejected(self, client):
        response = client.post(
            "/api/radar/reason",
            json=_valid_payload(theta_deg_per_sec=90.1),
        )
        assert response.status_code == 400

    def test_theta_minus_90_1_rejected(self, client):
        response = client.post(
            "/api/radar/reason",
            json=_valid_payload(theta_deg_per_sec=-90.1),
        )
        assert response.status_code == 400

    def test_theta_nan_rejected(self, client):
        response = client.post(
            "/api/radar/reason",
            json=_valid_payload(theta_deg_per_sec=float("nan")),
        )
        assert response.status_code == 400

    def test_theta_missing_key_rejected(self, client):
        payload = _valid_payload()
        del payload["theta_deg_per_sec"]
        response = client.post("/api/radar/reason", json=payload)
        assert response.status_code == 400


class TestLlmFailureNever500:
    """Every LLM failure path must surface as 200 + status unavailable."""

    @patch("llm.path_reasoner.requests.post")
    def test_connection_error_returns_200_unavailable(
        self, mock_post, client, real_reasoner
    ):
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")

        response = client.post("/api/radar/reason", json=_valid_payload())

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "unavailable"
        assert data["cause"] == "network"
        assert data["confidence"] == "low"

    @patch("llm.path_reasoner.requests.post")
    def test_timeout_returns_200_unavailable(
        self, mock_post, client, real_reasoner
    ):
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        response = client.post("/api/radar/reason", json=_valid_payload())

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "unavailable"
        assert data["cause"] == "timeout"

    @patch("llm.path_reasoner.requests.post")
    def test_malformed_llm_json_returns_200_unavailable(
        self, mock_post, client, real_reasoner
    ):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not json{"}}]
        }
        mock_post.return_value = mock_response

        response = client.post("/api/radar/reason", json=_valid_payload())

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "unavailable"
        assert data["cause"] == "parse"

    @patch("llm.path_reasoner.requests.post")
    def test_successful_llm_round_trip_through_endpoint(
        self, mock_post, client, real_reasoner
    ):
        """Full integration: real PathReasoner parsing a fenced response."""
        content = "```json\n" + json.dumps({
            "verdict": "Climbing departure, stable vector",
            "confidence": "medium",
            "notes": "Few trail fixes; treat projection cautiously.",
        }) + "\n```"
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }
        mock_post.return_value = mock_response

        response = client.post("/api/radar/reason", json=_valid_payload())

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["verdict"] == "Climbing departure, stable vector"
        assert data["confidence"] == "medium"
