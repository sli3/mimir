"""
tests/dashboard/test_radar_page.py — /radar page route tests

Tests that the /radar Flask route requests the React app's index.html
from dashboard/static, using a temporary HTML stub so no frontend build
is required.

Run with:
    uv run pytest tests/dashboard/test_radar_page.py -v
"""

import sys
import os
from pathlib import Path

import flask
import pytest
from flask import Response
from flask.testing import FlaskClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dashboard.server import app


@pytest.fixture
def stub_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    """Serve a temporary HTML stub and record the route's requested path."""
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    real_send_from_directory = flask.send_from_directory
    requested: dict[str, str] = {}

    def send_stub(directory: str, filename: str) -> Response:
        """Record the requested path and serve the temporary HTML stub."""
        requested["directory"] = directory
        requested["filename"] = filename
        return real_send_from_directory(tmp_path, filename)

    monkeypatch.setattr(flask, "send_from_directory", send_stub)
    return requested


@pytest.fixture
def client():
    """Flask test client for the dashboard server."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestRadarPage:
    """Tests for GET /radar."""

    def test_radar_route_returns_200_and_serves_html(
        self, client: FlaskClient, stub_index: dict[str, str]
    ) -> None:
        """GET /radar serves the index stub and closes the response deterministically."""
        with client.get("/radar") as response:
            assert response.status_code == 200
            assert "html" in response.mimetype
            assert b'<div id="root">' in response.data
            assert stub_index["filename"] == "index.html"
            assert Path(stub_index["directory"]).parts[-2:] == Path("dashboard/static").parts
