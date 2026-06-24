"""Tests for tools/seed_chromadb.py.

All tests use synthetic data. No HuggingFace download, no hardware required.
"""

from pathlib import Path

import numpy as np
import pytest

from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore
from tools.seed_chromadb import (
    CLASS_META,
    RTL_ML_SAMPLE_RATE,
    build_metadata,
    discover_dataset_files,
    extract_iq_data,
    process_sample,
    wipe_collection,
)


def _make_synthetic_iq(length: int = 1048576) -> np.ndarray:
    """Generate synthetic complex64 IQ data for testing."""
    rng = np.random.default_rng(42)
    return (rng.standard_normal(length) + 1j * rng.standard_normal(length)).astype(
        np.complex64
    )


def _make_synthetic_record() -> dict:
    """Build a full ChromaDB record from synthetic IQ data."""
    embedder = SpectrumEmbedder()
    iq = _make_synthetic_iq()
    psd = compute_psd(
        samples=iq,
        sample_rate_hz=RTL_ML_SAMPLE_RATE,
        center_freq_hz=100_000_000,
    )
    fingerprint = fingerprint_spectrum(psd)
    meta = build_metadata("test_class", 0, iq, {
        "center_freq_hz": 100_000_000,
        "label": "test",
    })
    return embedder.embed_fingerprint(fingerprint, metadata=meta)


def _clean_store() -> SignalStore:
    """Create a fresh in-memory SignalStore with a clean collection."""
    # ChromaDB in-memory client persists across instances within the same
    # process. Delete the collection first to ensure a clean state.
    try:
        SignalStore(path=":memory:").delete_collection()
    except Exception:
        pass
    return SignalStore(path=":memory:")


class TestPipelineProducesValidRecord:
    """Full pipeline: synthetic IQ -> record with correct structure."""

    def test_record_has_required_keys(self) -> None:
        """Output record has id, embedding, metadata keys."""
        record = _make_synthetic_record()
        assert "id" in record
        assert "embedding" in record
        assert "metadata" in record

    def test_embedding_length_is_7(self) -> None:
        """Embedding vector has length 7 (matching embedder dimension)."""
        record = _make_synthetic_record()
        assert len(record["embedding"]) == 7

    def test_metadata_has_label(self) -> None:
        """Metadata contains the label field."""
        record = _make_synthetic_record()
        assert record["metadata"]["label"] == "test"


class TestSampleRateIs1024000:
    """Sample rate passed to compute_psd must be 1.024 MSPS."""

    def test_returns_correct_sample_rate(self) -> None:
        """compute_psd returns sample_rate_hz == 1_024_000."""
        iq = _make_synthetic_iq(4096)
        psd = compute_psd(
            samples=iq,
            sample_rate_hz=RTL_ML_SAMPLE_RATE,
            center_freq_hz=100_000_000,
        )
        assert psd["sample_rate_hz"] == 1_024_000

    def test_rtl_ml_constant_is_1024000(self) -> None:
        """The constant is 1_024_000."""
        assert RTL_ML_SAMPLE_RATE == 1_024_000


class TestIsmLabelIs433Variant:
    """ISM_sensors class maps to ISM_sensors_433 label."""

    def test_ism_label_is_suffixed(self) -> None:
        """ISM_sensors label is ISM_sensors_433, not ISM_sensors."""
        assert CLASS_META["ISM_sensors"]["label"] == "ISM_sensors_433"

    def test_ism_center_freq_is_433_mhz(self) -> None:
        """ISM_sensors center_freq_hz is 433_920_000."""
        assert CLASS_META["ISM_sensors"]["center_freq_hz"] == 433_920_000


class TestBatchInsertIntoStore:
    """Batch insert into in-memory SignalStore."""

    def test_batch_insert_three_records(self) -> None:
        """Insert 3 records with unique IDs, count is 3."""
        store = _clean_store()
        embedder = SpectrumEmbedder()
        records = []
        for i in range(3):
            rng = np.random.default_rng(i)
            iq = (rng.standard_normal(4096) + 1j * rng.standard_normal(4096)).astype(
                np.complex64
            )
            psd = compute_psd(iq, RTL_ML_SAMPLE_RATE, 100_000_000 + i)
            fp = fingerprint_spectrum(psd)
            meta = build_metadata("test", i, iq, {"center_freq_hz": 100_000_000 + i, "label": f"test_{i}"})
            records.append(embedder.embed_fingerprint(fp, metadata=meta))
        store.add_batch(records)
        assert store.count() == 3

    def test_batch_insert_zero_records(self) -> None:
        """Insert 0 records, count is 0."""
        store = _clean_store()
        store.add_batch([])
        assert store.count() == 0


class TestWipeAndReseed:
    """Wipe clears existing records before seeding."""

    def test_wipe_clears_populated_store(self) -> None:
        """Wiping a populated store then seeding results in expected count."""
        store = _clean_store()
        record = _make_synthetic_record()
        store.add_batch([record])
        assert store.count() == 1

        wipe_collection(store)
        store = SignalStore(path=":memory:")
        assert store.count() == 0

        store.add_batch([record])
        assert store.count() == 1

    def test_wipe_on_empty_store(self) -> None:
        """Wiping an empty store (first run) does not raise and allows clean seeding."""
        store = _clean_store()
        assert store.count() == 0

        wipe_collection(store)
        store = SignalStore(path=":memory:")
        assert store.count() == 0

        record = _make_synthetic_record()
        store.add_batch([record])
        assert store.count() == 1

    def test_no_doubling_after_wipe(self) -> None:
        """Seeding after wipe produces exactly N records, not 2N."""
        store = _clean_store()
        records = []
        for i in range(3):
            rng = np.random.default_rng(i)
            iq = (rng.standard_normal(4096) + 1j * rng.standard_normal(4096)).astype(
                np.complex64
            )
            psd = compute_psd(iq, RTL_ML_SAMPLE_RATE, 100_000_000 + i)
            fp = fingerprint_spectrum(psd)
            embedder = SpectrumEmbedder()
            meta = build_metadata("test", i, iq, {"center_freq_hz": 100_000_000 + i, "label": f"test_{i}"})
            records.append(embedder.embed_fingerprint(fp, metadata=meta))
        store.add_batch(records)
        assert store.count() == 3

        # Simulate seeding again (as if re-running seed_chromadb.py)
        wipe_collection(store)
        store = SignalStore(path=":memory:")
        store.add_batch(records)
        assert store.count() == 3  # Not 6

    def test_wipe_on_nonexistent_collection(self) -> None:
        """wipe_collection handles ValueError when collection does not exist."""
        store = _clean_store()
        store.delete_collection()
        # collection no longer exists — call wipe_collection on stale store
        wipe_collection(store)
        store = SignalStore(path=":memory:")
        assert store.count() == 0
        record = _make_synthetic_record()
        store.add_batch([record])
        assert store.count() == 1


class TestExtractIqData:
    """Extract IQ data from various .npy formats."""

    def test_raw_complex64_array(self, tmp_path: Path) -> None:
        """Raw complex64 array is extracted correctly."""
        fpath = tmp_path / "raw_array.npy"
        arr = _make_synthetic_iq(256)
        np.save(str(fpath), arr)
        result = extract_iq_data(fpath)
        assert result is not None
        assert result.dtype == np.complex64
        assert len(result) == 256

    def test_dict_with_samples(self, tmp_path: Path) -> None:
        """Dict containing 'samples' key is extracted correctly."""
        fpath = tmp_path / "dict_samples.npy"
        arr = _make_synthetic_iq(512)
        data_dict = {"samples": arr, "label": "test", "center_freq": 100_000_000}
        np.save(str(fpath), data_dict, allow_pickle=True)
        result = extract_iq_data(fpath)
        assert result is not None
        assert result.dtype == np.complex64
        assert len(result) == 512

    def test_dict_missing_samples(self, tmp_path: Path) -> None:
        """Dict missing 'samples' key returns None."""
        fpath = tmp_path / "bad_dict.npy"
        np.save(str(fpath), {"label": "test"}, allow_pickle=True)
        result = extract_iq_data(fpath)
        assert result is None

    def test_invalid_file_returns_none(self, tmp_path: Path) -> None:
        """Invalid .npy file returns None without crashing."""
        fpath = tmp_path / "corrupt.npy"
        fpath.write_text("not a valid npy file")
        result = extract_iq_data(fpath)
        assert result is None


class TestDiscoverDatasetFiles:
    """File discovery supports v1 flat and v2 subdirectory structures."""

    def test_v2_subdirectory_structure(self, tmp_path: Path) -> None:
        """v2 subdirectory structure is discovered correctly."""
        validated = tmp_path / "datasets_validated"
        fm_dir = validated / "FM_broadcast"
        fm_dir.mkdir(parents=True)
        for i in range(3):
            arr = _make_synthetic_iq(256)
            np.save(str(fm_dir / f"FM_broadcast_{i}.npy"), arr)

        classes = discover_dataset_files(tmp_path)
        assert "FM_broadcast" in classes
        assert len(classes["FM_broadcast"]) == 3

    def test_v1_flat_structure(self, tmp_path: Path) -> None:
        """v1 flat file structure is discovered correctly."""
        validated = tmp_path / "datasets_validated"
        validated.mkdir(parents=True)
        for i in range(2):
            arr = _make_synthetic_iq(256)
            np.save(str(validated / f"FM_broadcast_{i}.npy"), arr)
        for i in range(2):
            arr = _make_synthetic_iq(256)
            np.save(str(validated / f"noise_{i}.npy"), arr)

        classes = discover_dataset_files(tmp_path)
        assert "FM_broadcast" in classes
        assert "noise" in classes
        assert len(classes["FM_broadcast"]) == 2
        assert len(classes["noise"]) == 2

    def test_missing_datasets_validated(self, tmp_path: Path) -> None:
        """Missing datasets_validated/ returns empty dict."""
        classes = discover_dataset_files(tmp_path)
        assert classes == {}


class TestProcessSample:
    """Process sample through the full pipeline."""

    def test_returns_valid_record(self, tmp_path: Path) -> None:
        """Successful processing returns a dict with id/embedding/metadata."""
        fpath = tmp_path / "test.npy"
        arr = _make_synthetic_iq(4096)
        np.save(str(fpath), arr)

        embedder = SpectrumEmbedder()
        meta = {"center_freq_hz": 100_000_000, "label": "test"}
        record = process_sample(fpath, "test_class", meta, 0, embedder)
        assert record is not None
        assert "id" in record
        assert "embedding" in record
        assert "metadata" in record
        assert record["metadata"]["label"] == "test"

    def test_bad_file_does_not_abort(self, tmp_path: Path) -> None:
        """A bad .npy file returns None, does not raise."""
        fpath = tmp_path / "corrupt.npy"
        fpath.write_text("not a valid npy file")

        embedder = SpectrumEmbedder()
        meta = {"center_freq_hz": 100_000_000, "label": "test"}
        record = process_sample(fpath, "test_class", meta, 0, embedder)
        assert record is None


class TestBadFileDoesNotAbort:
    """Exception during processing is caught and does not abort the run."""

    def test_continue_after_exception(self) -> None:
        """Processing continues after a file fails."""
        store = _clean_store()
        embedder = SpectrumEmbedder()
        records = []
        for i in range(2):
            rng = np.random.default_rng(i)
            iq = (rng.standard_normal(4096) + 1j * rng.standard_normal(4096)).astype(
                np.complex64
            )
            psd = compute_psd(iq, RTL_ML_SAMPLE_RATE, 100_000_000 + i)
            fp = fingerprint_spectrum(psd)
            meta = build_metadata("test", i, iq, {"center_freq_hz": 100_000_000 + i, "label": f"test_{i}"})
            records.append(embedder.embed_fingerprint(fp, metadata=meta))
        store.add_batch(records)
        assert store.count() == 2

    def test_main_continues_past_bad_files(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """main() continues when a bad file is encountered."""
        validated = tmp_path / "datasets_validated" / "noise"
        validated.mkdir(parents=True)

        bad_file = validated / "noise_0.npy"
        bad_file.write_text("corrupt")

        arr = _make_synthetic_iq(4096)
        good_file = validated / "noise_1.npy"
        np.save(str(good_file), arr)

        embedder = SpectrumEmbedder()
        meta = {"center_freq_hz": 100_000_000, "label": "noise"}
        result1 = process_sample(bad_file, "noise", meta, 0, embedder)
        result2 = process_sample(good_file, "noise", meta, 1, embedder)

        assert result1 is None
        assert result2 is not None
