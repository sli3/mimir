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
from unittest.mock import patch

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


class _FakeSignalStore:
    """In-memory stand-in for SignalStore used by /api/vectorstore/points tests."""

    def __init__(self, records):
        self._records = records
        self.get_all_embeddings_call_count = 0

    def count(self):
        return len(self._records)

    def get_all_embeddings(self):
        self.get_all_embeddings_call_count += 1
        return {
            "ids": [r["id"] for r in self._records],
            "embeddings": [r["embedding"] for r in self._records],
            "metadatas": [r["metadata"] for r in self._records],
        }


class TestApiVectorstorePoints:
    """Tests for GET /api/vectorstore/points."""

    def test_empty_store_returns_empty_response(self, client):
        """An empty ChromaDB collection returns status 'empty' and no points."""
        fake_store = _FakeSignalStore([])
        with patch("dashboard.server._get_signal_store", return_value=fake_store), \
             patch.dict("dashboard.server._VECTORSTORE_CACHE",
                        {"count": -1, "points": None, "method": None}, clear=True):
            response = client.get("/api/vectorstore/points")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "empty"
            assert data["count"] == 0
            assert data["points"] == []
            assert data["method"] is None

    def test_small_store_uses_pca(self, client):
        """Fewer than 5 records uses PCA and reports method 'pca'."""
        records = [
            {"id": "r1", "embedding": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
             "metadata": {"label": "FM_broadcast"}},
            {"id": "r2", "embedding": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
             "metadata": {"label": "Aviation_VHF"}},
            {"id": "r3", "embedding": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
             "metadata": {"label": "ACARS"}},
        ]
        with patch("dashboard.server._get_signal_store", return_value=_FakeSignalStore(records)), \
             patch.dict("dashboard.server._VECTORSTORE_CACHE",
                        {"count": -1, "points": None, "method": None}, clear=True):
            response = client.get("/api/vectorstore/points")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"
            assert data["method"] == "pca"
            assert data["count"] == 3
            assert len(data["points"]) == 3
            for point in data["points"]:
                assert "x" in point and "y" in point and "z" in point

    def test_two_record_store_pads_to_three_dimensions(self, client):
        """A 2-record store must not crash; PCA is padded to 3D coordinates."""
        records = [
            {"id": "r1", "embedding": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
             "metadata": {"label": "FM_broadcast"}},
            {"id": "r2", "embedding": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1],
             "metadata": {"label": "Aviation_VHF"}},
        ]
        with patch("dashboard.server._get_signal_store", return_value=_FakeSignalStore(records)), \
             patch.dict("dashboard.server._VECTORSTORE_CACHE",
                        {"count": -1, "points": None, "method": None}, clear=True):
            response = client.get("/api/vectorstore/points")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"
            assert data["method"] == "pca"
            assert data["count"] == 2
            assert len(data["points"]) == 2
            for point in data["points"]:
                assert "x" in point and "y" in point and "z" in point

    def test_four_record_store_uses_pca(self, client):
        """A 4-record store uses PCA with 3 components."""
        records = [
            {"id": f"r{i}", "embedding": [i / 10.0 + j / 100.0 for j in range(7)],
             "metadata": {"label": f"label_{i}"}}
            for i in range(4)
        ]
        with patch("dashboard.server._get_signal_store", return_value=_FakeSignalStore(records)), \
             patch.dict("dashboard.server._VECTORSTORE_CACHE",
                        {"count": -1, "points": None, "method": None}, clear=True):
            response = client.get("/api/vectorstore/points")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"
            assert data["method"] == "pca"
            assert data["count"] == 4
            assert len(data["points"]) == 4

    def test_large_store_uses_tsne_with_perplexity_guard(self, client):
        """5+ records uses t-SNE and caps perplexity at n - 1."""
        records = [
            {"id": f"r{i}", "embedding": [i / 10.0] * 7,
             "metadata": {"label": f"label_{i}"}}
            for i in range(5)
        ]
        with patch("dashboard.server._get_signal_store", return_value=_FakeSignalStore(records)), \
             patch.dict("dashboard.server._VECTORSTORE_CACHE",
                        {"count": -1, "points": None, "method": None}, clear=True):
            response = client.get("/api/vectorstore/points")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"
            assert data["method"] == "tsne"
            assert data["count"] == 5
            assert len(data["points"]) == 5

    def test_metadata_passthrough(self, client):
        """Metadata fields are surfaced safely on each point."""
        records = [
            {"id": "r1", "embedding": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
             "metadata": {
                 "label": "AIS",
                 "freq_hz": 162_000_000,
                 "snr_db": 12.5,
                 "peak_power_db": -45.0,
                 "timestamp": "2026-07-04T10:00:00",
             }},
        ]
        with patch("dashboard.server._get_signal_store", return_value=_FakeSignalStore(records)), \
             patch.dict("dashboard.server._VECTORSTORE_CACHE",
                        {"count": -1, "points": None, "method": None}, clear=True):
            response = client.get("/api/vectorstore/points")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"
            assert data["method"] == "pca"
            point = data["points"][0]
            assert point["label"] == "AIS"
            assert point["frequency_hz"] == 162_000_000
            assert point["snr_db"] == 12.5
            assert point["peak_power_db"] == -45.0
            assert point["timestamp"] == "2026-07-04T10:00:00"

    def test_center_freq_hz_metadata_key_populates_frequency_hz(self, client):
        """Seed records use 'center_freq_hz' — endpoint must resolve it."""
        records = [
            {"id": "r1", "embedding": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
             "metadata": {
                 "label": "APRS",
                 "center_freq_hz": 145_175_000,
                 "freq_hz": 999_999_999,
                 "source": "rtl-ml-dataset",
             }},
        ]
        with patch("dashboard.server._get_signal_store", return_value=_FakeSignalStore(records)), \
             patch.dict("dashboard.server._VECTORSTORE_CACHE",
                        {"count": -1, "points": None, "method": None}, clear=True):
            response = client.get("/api/vectorstore/points")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"
            point = data["points"][0]
            assert point["label"] == "APRS"
            # center_freq_hz takes precedence over the live-capture freq_hz key.
            assert point["frequency_hz"] == 145_175_000
            # Seed records do not have snr/peak/timestamp keys — these must stay null.
            assert point["snr_db"] is None
            assert point["peak_power_db"] is None
            assert point["timestamp"] is None

    def test_missing_metadata_fields_use_defaults(self, client):
        """Records without metadata keys do not raise KeyError."""
        records = [
            {"id": "r1", "embedding": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
             "metadata": {}},
        ]
        with patch("dashboard.server._get_signal_store", return_value=_FakeSignalStore(records)), \
             patch.dict("dashboard.server._VECTORSTORE_CACHE",
                        {"count": -1, "points": None, "method": None}, clear=True):
            response = client.get("/api/vectorstore/points")
            assert response.status_code == 200
            data = response.get_json()
            point = data["points"][0]
            assert point["label"] == "unknown"
            assert point["frequency_hz"] is None
            assert point["snr_db"] is None
            assert point["peak_power_db"] is None
            assert point["timestamp"] is None

    def test_store_failure_returns_500(self, client):
        """An exception during SignalStore access returns a JSON 500 error."""
        def raise_error():
            raise RuntimeError("store unavailable")

        with patch("dashboard.server._get_signal_store", side_effect=raise_error), \
             patch.dict("dashboard.server._VECTORSTORE_CACHE",
                        {"count": -1, "points": None, "method": None}, clear=True):
            response = client.get("/api/vectorstore/points")
            assert response.status_code == 500
            data = response.get_json()
            assert "error" in data

    def test_cache_returns_same_points_without_recompute(self, client):
        """A second request with the same record count returns cached points."""
        records = [
            {"id": "r1", "embedding": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
             "metadata": {"label": "FM_broadcast"}},
            {"id": "r2", "embedding": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
             "metadata": {"label": "Aviation_VHF"}},
            {"id": "r3", "embedding": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
             "metadata": {"label": "ACARS"}},
        ]
        fake_store = _FakeSignalStore(records)
        with patch("dashboard.server._get_signal_store", return_value=fake_store), \
             patch.dict("dashboard.server._VECTORSTORE_CACHE",
                        {"count": -1, "points": None, "method": None}, clear=True):
            response1 = client.get("/api/vectorstore/points")
            data1 = response1.get_json()
            response2 = client.get("/api/vectorstore/points")
            data2 = response2.get_json()
            assert data1 == data2
            assert response1.status_code == response2.status_code == 200
            assert fake_store.get_all_embeddings_call_count == 1

