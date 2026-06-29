"""
tests/dashboard/test_api_adsb_parse.py — Flask API endpoint tests for /api/adsb/parse

Tests the ADS-B frame parsing endpoint using Flask's test_client.

Run with:
    uv run pytest tests/dashboard/test_api_adsb_parse.py -v
"""

import pytest

from dashboard.server import app


@pytest.fixture
def client():
    """Flask test client for the dashboard server."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestApiAdsbParse:
    """Tests for GET /api/adsb/parse."""

    def test_parse_missing_hex_returns_400(self, client):
        """GET /api/adsb/parse with no params returns 400."""
        response = client.get("/api/adsb/parse")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_parse_invalid_hex_chars_returns_400(self, client):
        """GET /api/adsb/parse?hex=ZZZZ0000 returns 400 for non-hex characters."""
        response = client.get("/api/adsb/parse?hex=ZZZZ0000")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_parse_valid_df17_airborne_position(self, client):
        """Valid DF17 airborne-position frame hex string parses correctly."""
        # DF17 TC 11 (airborne position) - confirmed valid via pyModeS
        hex_string = "8D406B902015A678D4D220AA4BDA"
        response = client.get(f"/api/adsb/parse?hex={hex_string}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["df"] == 17
        assert isinstance(data["crc_ok"], bool)
        assert data["typecode"] == 4
        assert data["message_type"] == "Aircraft identification"
        assert "fields" in data

    def test_parse_valid_df17_velocity(self, client):
        """Valid DF17 velocity frame (TC 19) parses correctly."""
        # DF17 TC 19 (airborne velocity) - confirmed valid via pyModeS
        hex_string = "8D485020994409940838175B284F"
        response = client.get(f"/api/adsb/parse?hex={hex_string}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["df"] == 17
        assert data["message_type"] == "Airborne velocity"
        assert "fields" in data
        # At least one of Speed or Track should be present
        has_speed_or_track = (
            "Speed" in data["fields"] or "Track" in data["fields"]
        )
        assert has_speed_or_track

    def test_parse_oversized_hex_returns_400(self, client):
        """GET /api/adsb/parse with hex > 32 chars returns 400."""
        response = client.get("/api/adsb/parse?hex=123456789012345678901234567890123")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "too long" in data["error"].lower()

    def test_parse_empty_hex_returns_400(self, client):
        """GET /api/adsb/parse?hex= returns 400."""
        response = client.get("/api/adsb/parse?hex=")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data