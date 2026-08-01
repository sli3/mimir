"""
tests/dashboard/test_radar_page.py — /radar page route tests

Tests that the /radar Flask route serves the React app's index.html,
mirroring the existing /vectordb route behaviour. The React entry point
inspects window.location.pathname and mounts RadarPage instead of the
main dashboard App.

Run with:
    uv run pytest tests/dashboard/test_radar_page.py -v
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dashboard.server import app


@pytest.fixture
def client():
    """Flask test client for the dashboard server."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestRadarPage:
    """Tests for GET /radar."""

    def test_radar_route_returns_200_and_serves_html(self, client):
        """GET /radar returns 200 with the React app's index.html."""
        response = client.get("/radar")
        assert response.status_code == 200
        assert "html" in response.mimetype
        assert b'<div id="root">' in response.data
