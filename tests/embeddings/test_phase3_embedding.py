"""
tests/embeddings/test_phase3_embedding.py
Mimir RF Scanner — Phase 3 Embedding + Vector Store Tests

PURPOSE
───────
Tests for SpectrumEmbedder and SignalStore.
Proves fingerprint-to-vector conversion and ChromaDB similarity search work correctly.

Run with:
    python -m pytest tests/embeddings/test_phase3_embedding.py -v

IMPORTANT: These tests use synthetic fingerprints only — no hardware required.
"""

import os
import shutil
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from embeddings.embedder import SpectrumEmbedder, EMBEDDING_FEATURES, VECTOR_DIM
from embeddings.store import SignalStore, COLLECTION_NAME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fingerprint(**overrides) -> dict:
    """Create a valid synthetic fingerprint dict with optional overrides."""
    base = {
        "peak_freq_hz": 98_000_000.0,
        "peak_power_db": -12.0,
        "noise_floor_db": -60.0,
        "snr_db": 48.0,
        "bandwidth_hz": 200_000.0,
        "occupied_bins": 200,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# SpectrumEmbedder tests
# ---------------------------------------------------------------------------

class TestSpectrumEmbedder:
    """Tests for the SpectrumEmbedder class."""

    @pytest.fixture
    def embedder(self):
        return SpectrumEmbedder()

    @pytest.fixture
    def fingerprint(self):
        return _make_fingerprint()

    def test_vector_length(self, embedder, fingerprint):
        """Embedding vector must have exactly VECTOR_DIM elements."""
        vector = embedder.embed(fingerprint)
        assert len(vector) == VECTOR_DIM

    def test_vector_feature_count(self, embedder, fingerprint):
        """VECTOR_DIM must equal the number of EMBEDDING_FEATURES."""
        assert VECTOR_DIM == len(EMBEDDING_FEATURES)

    def test_normalisation_range(self, embedder, fingerprint):
        """All vector values must be in [0, 1]."""
        vector = embedder.embed(fingerprint)
        for v in vector:
            assert 0.0 <= v <= 1.0

    def test_idempotency(self, embedder, fingerprint):
        """Same input must produce the same vector every time."""
        v1 = embedder.embed(fingerprint)
        v2 = embedder.embed(fingerprint)
        assert v1 == v2

    def test_different_fingerprints_produce_different_vectors(self, embedder):
        """Two distinct fingerprints must produce different vectors."""
        fp1 = _make_fingerprint(peak_freq_hz=98_000_000.0)
        fp2 = _make_fingerprint(peak_freq_hz=100_000_000.0)
        assert embedder.embed(fp1) != embedder.embed(fp2)

    def test_clamping_below_range(self, embedder):
        """Values below the normalisation range must be clamped to 0.0."""
        fp = _make_fingerprint(snr_db=-5.0)
        vector = embedder.embed(fp)
        snr_idx = EMBEDDING_FEATURES.index("snr_db")
        assert vector[snr_idx] == 0.0

    def test_clamping_above_range(self, embedder):
        """Values above the normalisation range must be clamped to 1.0."""
        fp = _make_fingerprint(snr_db=200.0)
        vector = embedder.embed(fp)
        snr_idx = EMBEDDING_FEATURES.index("snr_db")
        assert vector[snr_idx] == 1.0

    def test_midpoint_normalisation(self, embedder):
        """A value at the midpoint of its range should normalise to ~0.5."""
        fp = _make_fingerprint(snr_db=50.0)
        vector = embedder.embed(fp)
        snr_idx = EMBEDDING_FEATURES.index("snr_db")
        assert abs(vector[snr_idx] - 0.5) < 0.01

    def test_metadata_passthrough(self, embedder, fingerprint):
        """embed_fingerprint must include metadata in the output record."""
        meta = {"timestamp": "2026-05-22T00:00:00", "source": "hackrf"}
        record = embedder.embed_fingerprint(fingerprint, metadata=meta)
        assert record["metadata"] == meta

    def test_record_has_required_keys(self, embedder, fingerprint):
        """embed_fingerprint output must have id, embedding, metadata."""
        record = embedder.embed_fingerprint(fingerprint)
        assert set(record.keys()) == {"id", "embedding", "metadata"}

    def test_record_id_is_string(self, embedder, fingerprint):
        """Record id must be a non-empty string."""
        record = embedder.embed_fingerprint(fingerprint)
        assert isinstance(record["id"], str)
        assert len(record["id"]) > 0

    def test_record_id_deterministic(self, embedder, fingerprint):
        """Same fingerprint + metadata must produce the same id."""
        meta = {"source": "test"}
        r1 = embedder.embed_fingerprint(fingerprint, metadata=meta)
        r2 = embedder.embed_fingerprint(fingerprint, metadata=meta)
        assert r1["id"] == r2["id"]

    def test_embedding_is_list_of_floats(self, embedder, fingerprint):
        """embedding field must be a list of Python floats."""
        record = embedder.embed_fingerprint(fingerprint)
        assert isinstance(record["embedding"], list)
        for v in record["embedding"]:
            assert isinstance(v, float)

    def test_default_metadata_is_empty_dict(self, embedder, fingerprint):
        """When no metadata is provided, metadata must be {}."""
        record = embedder.embed_fingerprint(fingerprint)
        assert record["metadata"] == {}


# ---------------------------------------------------------------------------
# SignalStore tests
# ---------------------------------------------------------------------------

class TestSignalStore:
    """Tests for the SignalStore class."""

    @pytest.fixture
    def embedder(self):
        return SpectrumEmbedder()

    @pytest.fixture
    def store(self):
        """In-memory store for isolated tests."""
        s = SignalStore(path=":memory:")
        yield s
        try:
            s.delete_collection()
        except Exception:
            pass

    @pytest.fixture
    def fingerprint(self):
        return _make_fingerprint()

    def test_initial_count_is_zero(self, store):
        """A fresh store must have 0 records."""
        assert store.count() == 0

    def test_add_increments_count(self, store, embedder, fingerprint):
        """Adding one record must increase count by 1."""
        record = embedder.embed_fingerprint(fingerprint)
        store.add(record)
        assert store.count() == 1

    def test_add_and_query_round_trip(self, store, embedder, fingerprint):
        """A stored record must be retrievable via similarity query."""
        record = embedder.embed_fingerprint(fingerprint, metadata={"label": "fm_radio"})
        store.add(record)
        results = store.query(record["embedding"], n_results=1)
        assert len(results["ids"][0]) == 1
        assert results["ids"][0][0] == record["id"]

    def test_query_returns_distances(self, store, embedder, fingerprint):
        """Query results must include distance values."""
        record = embedder.embed_fingerprint(fingerprint)
        store.add(record)
        results = store.query(record["embedding"], n_results=1)
        assert "distances" in results
        assert len(results["distances"][0]) == 1

    def test_batch_add(self, store, embedder):
        """add_batch must insert all records at once."""
        fps = [
            _make_fingerprint(peak_freq_hz=98_000_000.0),
            _make_fingerprint(peak_freq_hz=100_000_000.0),
            _make_fingerprint(peak_freq_hz=120_000_000.0),
        ]
        records = [embedder.embed_fingerprint(fp) for fp in fps]
        store.add_batch(records)
        assert store.count() == 3

    def test_batch_add_empty(self, store):
        """add_batch with empty list must not raise."""
        store.add_batch([])
        assert store.count() == 0

    def test_similarity_ordering(self, store, embedder):
        """Query must return results ordered by similarity (closest first)."""
        fp_exact = _make_fingerprint(peak_freq_hz=98_000_000.0)
        fp_close = _make_fingerprint(peak_freq_hz=98_100_000.0)
        fp_far = _make_fingerprint(peak_freq_hz=120_000_000.0)

        for fp in [fp_far, fp_close, fp_exact]:
            store.add(embedder.embed_fingerprint(fp))

        query_vec = embedder.embed(fp_exact)
        results = store.query(query_vec, n_results=3)
        ids = results["ids"][0]
        exact_id = embedder.make_id(fp_exact)
        assert ids[0] == exact_id

    def test_delete_collection(self, store, embedder, fingerprint):
        """After delete_collection, count must raise or store must be empty."""
        record = embedder.embed_fingerprint(fingerprint)
        store.add(record)
        assert store.count() == 1
        store.delete_collection()
        # After deletion, a new collection with the same name should be empty
        new_store = SignalStore(path=":memory:")
        assert new_store.count() == 0
        new_store.delete_collection()

    def test_persistent_store_creates_directory(self, embedder, fingerprint):
        """Persistent store must create the data directory on disk."""
        test_path = "data/test_vectorstore_persistent"
        try:
            store = SignalStore(path=test_path)
            record = embedder.embed_fingerprint(fingerprint)
            store.add(record)
            assert store.count() == 1
            assert os.path.isdir(test_path)
            store.delete_collection()
        finally:
            if os.path.exists(test_path):
                shutil.rmtree(test_path)

    def test_n_results_limit(self, store, embedder):
        """Query must respect n_results limit."""
        fps = [_make_fingerprint(peak_freq_hz=90_000_000.0 + i * 1_000_000) for i in range(10)]
        records = [embedder.embed_fingerprint(fp) for fp in fps]
        store.add_batch(records)

        query_vec = embedder.embed(_make_fingerprint(peak_freq_hz=95_000_000.0))
        results = store.query(query_vec, n_results=3)
        assert len(results["ids"][0]) == 3
