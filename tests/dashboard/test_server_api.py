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


class TestApiCaptures:
    """Tests for GET /api/captures (Phase 71).

    Each test builds a real SigMF capture in tmp_path via save_capture()
    or save_recording() and monkeypatches dashboard.server._REPLAY_CAPTURES_DIR
    to point at it, so the route's directory listing resolves inside the temp
    directory. The paired .sigmf-data files are never read.
    """

    _FREQ_HZ = 98_000_000
    _SAMPLE_RATE_HZ = 2_000_000

    def _build_capture(self, tmp_path, snr_bump_db=0.0):
        """Write a real one-shot capture; optionally skew saved snr_db."""
        import numpy as np
        from core.pipeline.capture import save_capture
        from core.pipeline.fft import compute_psd
        from core.pipeline.features import fingerprint_spectrum
        from dashboard.shared_state import BAND_PROFILES

        rng = np.random.default_rng(42)
        samples = (
            rng.standard_normal(16_384) + 1j * rng.standard_normal(16_384)
        ).astype(np.complex64)
        profile = BAND_PROFILES["fm_broadcast"]
        psd_result = compute_psd(samples, self._SAMPLE_RATE_HZ, self._FREQ_HZ)
        fingerprint = fingerprint_spectrum(
            psd_result,
            signal_threshold_db=profile.get("signal_threshold_db"),
            crop_half_width_hz=profile.get("crop_half_width_hz"),
            burst_use_wide_window=profile.get("burst_use_wide_window", False),
            trace_key=profile.get("fingerprint_trace_key", "psd_db"),
        )
        if snr_bump_db:
            fingerprint["snr_db"] = float(fingerprint["snr_db"]) + snr_bump_db
        return save_capture(
            samples,
            freq_hz=self._FREQ_HZ,
            sample_rate_hz=self._SAMPLE_RATE_HZ,
            output_dir=tmp_path,
            fingerprint=fingerprint,
        )

    def _build_recording(self, tmp_path, entries=2):
        """Write a real Record-mode capture with N per-cycle entries."""
        import numpy as np
        from core.pipeline.capture import save_recording
        from core.pipeline.fft import compute_psd
        from core.pipeline.features import fingerprint_spectrum
        from dashboard.shared_state import BAND_PROFILES

        samples_per_cycle = 16_384
        rng = np.random.default_rng(43)
        samples = (
            rng.standard_normal(samples_per_cycle * entries)
            + 1j * rng.standard_normal(samples_per_cycle * entries)
        ).astype(np.complex64)
        profile = BAND_PROFILES["fm_broadcast"]
        sequence = []
        for idx in range(entries):
            cycle = samples[
                idx * samples_per_cycle : (idx + 1) * samples_per_cycle
            ]
            psd_result = compute_psd(cycle, self._SAMPLE_RATE_HZ, self._FREQ_HZ)
            fingerprint = fingerprint_spectrum(
                psd_result,
                signal_threshold_db=profile.get("signal_threshold_db"),
                crop_half_width_hz=profile.get("crop_half_width_hz"),
                burst_use_wide_window=profile.get("burst_use_wide_window", False),
                trace_key=profile.get("fingerprint_trace_key", "psd_db"),
            )
            sequence.append({
                **{k: fingerprint[k] for k in fingerprint if k in (
                    "peak_freq_hz", "peak_power_db", "noise_floor_db",
                    "snr_db", "bandwidth_hz", "occupied_bins",
                    "spectral_flatness"
                )},
                "sample_start": idx * samples_per_cycle,
                "sample_count": samples_per_cycle,
                "timestamp_sec": float(idx),
            })
        return save_recording(
            samples,
            freq_hz=self._FREQ_HZ,
            sample_rate_hz=self._SAMPLE_RATE_HZ,
            device="hackrf",
            fingerprint_sequence=sequence,
            output_dir=tmp_path,
        )

    @pytest.fixture
    def captures_dir(self, tmp_path, monkeypatch):
        """Point the route's captures-dir anchor at tmp_path."""
        monkeypatch.setattr(
            "dashboard.server._REPLAY_CAPTURES_DIR", tmp_path.resolve()
        )
        return tmp_path

    def test_empty_dir_returns_200_with_empty_list(self, client, captures_dir):
        """An empty captures directory returns 200 with captures=[]."""
        response = client.get("/api/captures")
        assert response.status_code == 200
        data = response.get_json()
        assert data == {"captures": []}

    def test_missing_dir_returns_200_with_empty_list(self, client, captures_dir):
        """A missing captures directory returns 200 with captures=[]."""
        captures_dir.rmdir()
        response = client.get("/api/captures")
        assert response.status_code == 200
        data = response.get_json()
        assert data == {"captures": []}

    def test_oneshot_capture_lists_with_mode_oneshot(self, client, captures_dir):
        """A one-shot capture is listed with mode 'oneshot' and chunk_count 1."""
        meta_path = self._build_capture(captures_dir)
        response = client.get("/api/captures")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["captures"]) == 1
        entry = data["captures"][0]
        assert entry["filename"] == meta_path.name
        assert entry["mode"] == "oneshot"
        assert entry["chunk_count"] == 1
        assert entry["core_frequency_hz"] == self._FREQ_HZ
        assert entry["device"] == "hackrf"
        assert entry["timestamp"] is not None
        assert "error" not in entry

    def test_record_capture_lists_with_mode_record(self, client, captures_dir):
        """A Record-mode capture is listed with mode 'record' and the right chunk count."""
        meta_path = self._build_recording(captures_dir, entries=2)
        response = client.get("/api/captures")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["captures"]) == 1
        entry = data["captures"][0]
        assert entry["filename"] == meta_path.name
        assert entry["mode"] == "record"
        assert entry["chunk_count"] == 2
        assert entry["core_frequency_hz"] == self._FREQ_HZ
        assert entry["device"] == "hackrf"

    def test_malformed_file_appears_as_unknown_not_500(self, client, captures_dir):
        """A corrupt .sigmf-meta is listed as mode 'unknown' and does not abort the listing."""
        self._build_capture(captures_dir)
        bad = captures_dir / "capture_98000000hz_20260819_000000.sigmf-meta"
        bad.write_text("not sigmf {{")
        response = client.get("/api/captures")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["captures"]) == 2
        bad_entry = next(e for e in data["captures"] if e["filename"] == bad.name)
        assert bad_entry["mode"] == "unknown"
        assert bad_entry["chunk_count"] == 0
        assert "error" in bad_entry
        good_entry = next(e for e in data["captures"] if e["filename"] != bad.name)
        assert good_entry["mode"] == "oneshot"

    def test_non_sigmf_files_excluded(self, client, captures_dir):
        """Plain text and .npy files in the captures dir are ignored."""
        self._build_capture(captures_dir)
        (captures_dir / "notes.txt").write_text("hello")
        (captures_dir / "backup.npy").write_text("not really numpy")
        response = client.get("/api/captures")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["captures"]) == 1
        assert data["captures"][0]["mode"] == "oneshot"

    def test_sort_order_descending_by_timestamp(self, client, captures_dir):
        """Captures are returned newest-first by parsed filename timestamp."""
        names = [
            "capture_98000000hz_20260819_120000.sigmf-meta",
            "capture_98000000hz_20260819_130000.sigmf-meta",
            "capture_98000000hz_20260819_110000.sigmf-meta",
        ]
        for name in names:
            (captures_dir / name).write_text(json.dumps({
                "global": {"mimir:device_profile": "hackrf"},
                "captures": [{"core:frequency": self._FREQ_HZ}],
            }))
        response = client.get("/api/captures")
        assert response.status_code == 200
        data = response.get_json()
        assert [e["filename"] for e in data["captures"]] == [
            "capture_98000000hz_20260819_130000.sigmf-meta",
            "capture_98000000hz_20260819_120000.sigmf-meta",
            "capture_98000000hz_20260819_110000.sigmf-meta",
        ]

    def test_subdirectory_files_excluded(self, client, captures_dir):
        """Files inside subdirectories are not listed; search is non-recursive."""
        self._build_capture(captures_dir)
        sub = captures_dir / "subdir"
        sub.mkdir()
        (sub / "capture_98000000hz_20260819_140000.sigmf-meta").write_text(
            json.dumps({
                "global": {"mimir:device_profile": "hackrf"},
                "captures": [{"core:frequency": self._FREQ_HZ}],
            })
        )
        response = client.get("/api/captures")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["captures"]) == 1


class TestApiReplay:
    """Tests for POST /api/replay (Phase 70).

    Each test builds a REAL SigMF capture in tmp_path via save_capture()
    and monkeypatches dashboard.server._REPLAY_CAPTURES_DIR at it, so the
    route's path containment resolves inside the temp directory.
    """

    _FREQ_HZ = 98_000_000
    _SAMPLE_RATE_HZ = 2_000_000

    def _build_capture(self, tmp_path, snr_bump_db=0.0):
        """Write a real one-shot capture; optionally skew saved snr_db."""
        import numpy as np
        from core.pipeline.capture import save_capture
        from core.pipeline.fft import compute_psd
        from core.pipeline.features import fingerprint_spectrum
        from dashboard.shared_state import BAND_PROFILES

        rng = np.random.default_rng(42)
        samples = (
            rng.standard_normal(16_384) + 1j * rng.standard_normal(16_384)
        ).astype(np.complex64)
        profile = BAND_PROFILES["fm_broadcast"]
        psd_result = compute_psd(samples, self._SAMPLE_RATE_HZ, self._FREQ_HZ)
        fingerprint = fingerprint_spectrum(
            psd_result,
            signal_threshold_db=profile.get("signal_threshold_db"),
            crop_half_width_hz=profile.get("crop_half_width_hz"),
            burst_use_wide_window=profile.get("burst_use_wide_window", False),
            trace_key=profile.get("fingerprint_trace_key", "psd_db"),
        )
        if snr_bump_db:
            fingerprint["snr_db"] = float(fingerprint["snr_db"]) + snr_bump_db
        return save_capture(
            samples,
            freq_hz=self._FREQ_HZ,
            sample_rate_hz=self._SAMPLE_RATE_HZ,
            output_dir=tmp_path,
            fingerprint=fingerprint,
        )

    @pytest.fixture
    def captures_dir(self, tmp_path, monkeypatch):
        """Point the route's captures-dir anchor at tmp_path."""
        monkeypatch.setattr(
            "dashboard.server._REPLAY_CAPTURES_DIR", tmp_path.resolve()
        )
        return tmp_path

    def test_success_with_matches(self, client, captures_dir):
        """A capture saved with its true fingerprint replays to a 200
        with the full structured result."""
        meta_path = self._build_capture(captures_dir)
        response = client.post("/api/replay", json={"path": meta_path.name})
        assert response.status_code == 200
        data = response.get_json()
        assert data["summary"] == {
            "total_chunks": 1,
            "matched_chunks": 1,
            "mismatched_chunks": 0,
        }
        assert data["band_resolution"]["band_key"] == "fm_broadcast"
        assert data["band_resolution"]["match"] == "exact"
        assert data["file_metadata"]["fingerprint_field"] == "mimir:fingerprint"
        chunk = data["per_chunk_results"][0]
        assert chunk["comparison"]["all_match"] is True
        assert "replayed_fingerprint" in chunk
        assert "saved_fingerprint" in chunk

    def test_success_with_mismatches_still_200(self, client, captures_dir):
        """A 5 dB-skewed saved fingerprint is a finding, not a failure:
        200 with mismatched_chunks == 1."""
        meta_path = self._build_capture(captures_dir, snr_bump_db=5.0)
        response = client.post("/api/replay", json={"path": meta_path.name})
        assert response.status_code == 200
        data = response.get_json()
        assert data["summary"]["mismatched_chunks"] == 1
        chunk = data["per_chunk_results"][0]
        assert chunk["comparison"]["all_match"] is False
        assert chunk["comparison"]["field_results"]["snr_db"]["match"] is False

    def test_malformed_file_returns_replay_failed(self, client, captures_dir):
        """A corrupt .sigmf-meta returns 400 with error 'replay_failed'."""
        bad = captures_dir / "capture_98000000hz_20260819_000000.sigmf-meta"
        bad.write_text("not sigmf {{")
        response = client.post("/api/replay", json={"path": bad.name})
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"] == "replay_failed"
        assert "detail" in data

    def test_path_traversal_rejected(self, client, captures_dir):
        """../ traversal escapes the captures dir and returns 400."""
        response = client.post(
            "/api/replay", json={"path": "../../etc/passwd"}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"] == "path_outside_captures_dir"

    def test_absolute_path_outside_captures_rejected(self, client, captures_dir):
        """An absolute path outside data/captures/ is rejected the same way."""
        response = client.post("/api/replay", json={"path": "/etc/passwd"})
        assert response.status_code == 400
        assert response.get_json()["error"] == "path_outside_captures_dir"

    def test_non_sigmf_suffix_rejected(self, client, captures_dir):
        """A file inside the captures dir without the .sigmf-meta suffix
        returns 400 with error 'not_a_sigmf_meta_file'."""
        (captures_dir / "notes.txt").write_text("hello")
        response = client.post("/api/replay", json={"path": "notes.txt"})
        assert response.status_code == 400
        assert response.get_json()["error"] == "not_a_sigmf_meta_file"

    def test_missing_path_key_rejected(self, client, captures_dir):
        """A body without 'path' returns 400 with error 'invalid_path'."""
        response = client.post("/api/replay", json={})
        assert response.status_code == 400
        assert response.get_json()["error"] == "invalid_path"

    def test_non_object_body_rejected(self, client, captures_dir):
        """A non-JSON-object body returns 400 with error 'invalid_body'."""
        response = client.post(
            "/api/replay",
            data="not json at all",
            content_type="application/json",
        )
        assert response.status_code == 400
        assert response.get_json()["error"] == "invalid_body"

    def test_missing_file_returns_404(self, client, captures_dir):
        """A well-formed path naming a nonexistent file returns 404."""
        response = client.post(
            "/api/replay", json={"path": "nope.sigmf-meta"}
        )
        assert response.status_code == 404
        assert response.get_json()["error"] == "file_not_found"

    def test_concurrent_replay_returns_503(self, client, captures_dir):
        """While the replay lock is held, a second caller gets a
        structured 503 rather than queuing behind the first replay."""
        from core.pipeline.replay import REPLAY_LOCK

        meta_path = self._build_capture(captures_dir)
        assert REPLAY_LOCK.acquire(blocking=False)
        try:
            response = client.post("/api/replay", json={"path": meta_path.name})
        finally:
            REPLAY_LOCK.release()
        assert response.status_code == 503
        data = response.get_json()
        assert data["error"] == "busy"
        assert "detail" in data

