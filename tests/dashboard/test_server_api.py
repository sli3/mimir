"""
tests/dashboard/test_server_api.py — Flask API endpoint tests

Tests the /api/frequencies endpoint and any other dashboard/server.py
REST routes in isolation using Flask's test_client.

Run with:
    uv run pytest tests/dashboard/test_server_api.py -v
"""

import json
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dashboard.server import app


# Load the reference file independently so test counts stay correct
# even when the data file is updated.
_REF_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "frequency_reference.json"
)
with open(_REF_PATH, "r", encoding="utf-8") as _f:
    _REF_DATA = json.load(_f)

_TOTAL_ENTRIES = len(_REF_DATA)
_TAGGED_ENTRIES = len([e for e in _REF_DATA if e.get("mimir_band") is not None])


@pytest.fixture
def client():
    """Flask test client for the dashboard server."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestApiFrequencies:
    """Tests for GET /api/frequencies."""

    def test_unfiltered_returns_all_entries(self, client):
        """Unfiltered request returns 200 and all entries from the reference file."""
        response = client.get("/api/frequencies")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == _TOTAL_ENTRIES, (
            f"Expected {_TOTAL_ENTRIES} entries, got {len(data)}. "
            f"If the data file changed, this assertion is expected to update."
        )

    def test_tagged_only_returns_non_null_bands(self, client):
        """tagged_only=1 returns only entries with a mimir_band set."""
        response = client.get("/api/frequencies?tagged_only=1")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == _TAGGED_ENTRIES, (
            f"Expected {_TAGGED_ENTRIES} tagged entries, got {len(data)}. "
            f"If the data file changed, this assertion is expected to update."
        )
        for entry in data:
            assert entry["mimir_band"] is not None

    def test_min_mhz_filter(self, client):
        """min_mhz filters out entries ending below the threshold."""
        response = client.get("/api/frequencies?min_mhz=100")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) > 0
        for entry in data:
            assert entry["freq_end_mhz"] >= 100

    def test_max_mhz_filter(self, client):
        """max_mhz filters out entries starting above the threshold."""
        response = client.get("/api/frequencies?max_mhz=100")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) > 0
        for entry in data:
            assert entry["freq_start_mhz"] <= 100

    def test_min_and_max_mhz_combined(self, client):
        """Both min_mhz and max_mhz can be used together."""
        response = client.get("/api/frequencies?min_mhz=87&max_mhz=108")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) > 0
        for entry in data:
            assert entry["freq_end_mhz"] >= 87
            assert entry["freq_start_mhz"] <= 108

    def test_empty_range_returns_empty_array(self, client):
        """A range with no matching entries returns 200 and []."""
        response = client.get("/api/frequencies?min_mhz=999999&max_mhz=999999")
        assert response.status_code == 200
        data = response.get_json()
        assert data == []

    def test_tagged_only_with_min_max(self, client):
        """tagged_only combined with min_mhz/max_mhz works."""
        response = client.get("/api/frequencies?min_mhz=87&max_mhz=108&tagged_only=1")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) > 0
        for entry in data:
            assert entry["mimir_band"] is not None
            assert entry["freq_end_mhz"] >= 87
            assert entry["freq_start_mhz"] <= 108

    def test_entries_match_source_schema(self, client):
        """Each returned entry has the same keys as the source file."""
        response = client.get("/api/frequencies")
        data = response.get_json()
        assert len(data) > 0
        entry = data[0]
        assert "freq_start_mhz" in entry
        assert "freq_end_mhz" in entry
        assert "services" in entry
        assert "footnotes" in entry
        assert "mimir_band" in entry
        assert "notes" in entry


class TestApiFrequenciesErrorHandling:
    """Tests for error paths in /api/frequencies."""

    def test_corrupt_file_returns_500(self, client):
        """If the reference file is unreadable, return 500 with error JSON."""
        from unittest.mock import patch, mock_open
        from dashboard import server as server_module

        with patch.object(server_module, "open", mock_open(read_data="not json")):
            response = client.get("/api/frequencies")
            assert response.status_code == 500
            data = response.get_json()
            assert "error" in data

    def test_missing_file_returns_500(self, client):
        """If the reference file does not exist, return 500 with error JSON."""
        from unittest.mock import patch
        from dashboard import server as server_module

        def raise_fnf(*args, **kwargs):
            raise FileNotFoundError("No such file")

        with patch.object(server_module, "open", raise_fnf):
            response = client.get("/api/frequencies")
            assert response.status_code == 500
            data = response.get_json()
            assert "error" in data
