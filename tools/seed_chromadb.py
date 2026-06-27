"""
seed_chromadb.py — Seed ChromaDB with RTL-ML reference signal dataset

Downloads RTL-ML dataset from HuggingFace, processes each sample through
Mimir's pipeline (FFT -> fingerprint -> embed), and stores vectors in
ChromaDB as labelled reference signals.

WARNING: Re-running this script will destroy all existing ChromaDB data
(including any manually added reference vectors) and re-seed from scratch.
The collection is unconditionally wiped before each seed run.

This is a one-off seeding script. Do not import or use in production code.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging
import sys
from pathlib import Path

import numpy as np
from huggingface_hub import snapshot_download

from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore

logger = logging.getLogger(__name__)

RTL_ML_SAMPLE_RATE = 1_024_000  # Original capture sample rate — kept for metadata only

# Mimir's production sample rate. FFT must be run at this rate so seeded
# vectors match live captures. hz_per_bin = sample_rate / nfft:
#   RTL_ML_SAMPLE_RATE -> 500 Hz/bin  (wrong — half of live)
#   MIMIR_SAMPLE_RATE  -> 976.5625 Hz/bin  (correct — matches scanner.py)
# bandwidth_hz and occupied_bins dimensions are derived from hz_per_bin,
# so using the wrong rate corrupts 2 of 7 embedding dimensions for every
# seeded vector.
MIMIR_SAMPLE_RATE = 2_000_000

# RTL-ML dataset class metadata.
# center_freq_hz: authoritative AU frequency used for embedding and LLM context.
# label: stored in ChromaDB metadata — must match signal_type values in classifier.py.
# signal_threshold_db: per-class detection threshold passed to fingerprint_spectrum().
#   Using the global 24 dB fallback for all classes produces bandwidth_hz=0 for
#   weaker signals (APRS, ISM) where live SNR is well below 24 dB. Per-class values
#   match BAND_PROFILES in dashboard/shared_state.py so seeded and live vectors use
#   the same threshold.
#
# NOTE: ISM_sensors in RTL-ML was captured at 433.92 MHz (EU band). Mimir targets
# 915 MHz (AU/NZ ISM band). center_freq_hz is overridden here to 915 MHz so the
# peak_freq_hz embedding dimension is correct for AU queries. The underlying RF
# characteristics (bandwidth, spectral flatness) of LoRa/ISM signals are similar
# across bands — the waveform shape is what matters for similarity search.
#
# NOTE: pager (931.9 MHz) removed — not a Mimir target band and pollutes ISM
# queries (pager at 931.9 MHz is closer to live ISM at 915 MHz than ISM_sensors
# at 433.9 MHz, causing pager to be returned as top neighbour for every ISM scan).
CLASS_META: dict[str, dict] = {
    "ADS_B":        {"center_freq_hz": 1_090_000_000, "label": "ADS_B",        "signal_threshold_db": 3.0},
    "APRS":         {"center_freq_hz":   145_175_000, "label": "APRS",         "signal_threshold_db": 10.0},
    "FM_broadcast": {"center_freq_hz":    98_000_000, "label": "FM_broadcast",  "signal_threshold_db": 21.0},
    "ISM_sensors":  {"center_freq_hz":   915_000_000, "label": "ISM_915",       "signal_threshold_db": 3.0},
    "NOAA_APT":     {"center_freq_hz":   137_500_000, "label": "NOAA_APT",      "signal_threshold_db": 6.0},
    "noise":        {"center_freq_hz":   100_000_000, "label": "noise",         "signal_threshold_db": 24.0},
}

CAPTURE_ORIGIN = "Temecula, CA, USA"

# Classes excluded from seeding — not relevant to AU/SA operations.
# FRS_GMRS: US citizens band, no AU equivalent.
# NOAA_weather: US weather radio service, not broadcast in AU.
# pager: 931.9 MHz pager service — not a Mimir target band. Removing from
#   CLASS_META alone is insufficient; the dataset files still exist and the
#   CLASS_META fallback in main() would seed them with default metadata.
#   Must be listed here so discover_dataset_files() skips them entirely.
EXCLUDED_CLASSES: set[str] = {"FRS_GMRS", "NOAA_weather", "pager"}


def extract_iq_data(filepath: Path) -> np.ndarray | None:
    """Load IQ data from a .npy file, handling both dict and raw array formats."""
    try:
        data = np.load(filepath, allow_pickle=True)
    except Exception as exc:
        logger.error("Failed to load %s: %s", filepath, exc)
        return None

    if isinstance(data, np.ndarray) and data.dtype == np.complex64:
        # Raw complex64 array (v1 format)
        return data

    if isinstance(data, np.ndarray) and data.dtype == np.object_:
        data = data.item()

    if isinstance(data, dict):
        samples = data.get("samples")
        if samples is not None and isinstance(samples, np.ndarray) and np.iscomplexobj(samples):
            return samples.astype(np.complex64)
        logger.error("%s: dict found but no complex64 'samples' key", filepath)
        return None

    dtype_str = str(data.dtype) if hasattr(data, "dtype") else "N/A"
    logger.error("%s: unexpected format (dtype=%s, type=%s)", filepath, dtype_str, type(data))
    return None


def build_metadata(
    class_name: str,
    sample_index: int,
    iq_data: np.ndarray,
    meta: dict,
) -> dict:
    """Build metadata dict for a processed sample."""
    return {
        "label": meta["label"],
        "source": "rtl-ml-dataset",
        "class": class_name,
        "sample_index": sample_index,
        "center_freq_hz": meta["center_freq_hz"],
        "sample_rate_hz": MIMIR_SAMPLE_RATE,
        "capture_origin": CAPTURE_ORIGIN,
        "n_samples": len(iq_data),
    }


def process_sample(
    filepath: Path,
    class_name: str,
    meta: dict,
    sample_index: int,
    embedder: SpectrumEmbedder,
) -> dict | None:
    """Load one .npy file, run pipeline, return ChromaDB record or None on error."""
    iq_data = extract_iq_data(filepath)
    if iq_data is None:
        return None

    try:
        psd = compute_psd(
            samples=iq_data,
            sample_rate_hz=MIMIR_SAMPLE_RATE,
            center_freq_hz=meta["center_freq_hz"],
        )
        threshold = meta.get("signal_threshold_db")
        fingerprint = fingerprint_spectrum(psd, signal_threshold_db=threshold)
        metadata = build_metadata(class_name, sample_index, iq_data, meta)
        record = embedder.embed_fingerprint(fingerprint, metadata=metadata)
        return record
    except Exception as exc:
        logger.error("Failed to process %s: %s", filepath, exc)
        return None


def discover_dataset_files(dataset_path: Path) -> dict[str, list[tuple[Path, int]]]:
    """Walk dataset directory and group .npy files by class name.

    Supports both flat (v1) and subdirectory (v2) structures.

    Returns:
        Dict mapping class_name -> list of (filepath, sample_index) tuples.
    """
    validated_dir = dataset_path / "datasets_validated"
    if not validated_dir.is_dir():
        logger.error("datasets_validated/ not found in %s", dataset_path)
        return {}

    classes: dict[str, list[tuple[Path, int]]] = {}

    subdirs = sorted([
        p for p in validated_dir.iterdir()
        if p.is_dir()
    ])

    if subdirs:
        # v2 structure: subdirectories per class
        for subdir in subdirs:
            class_name = subdir.name
            npy_files = sorted(subdir.glob("*.npy"))
            if not npy_files:
                continue
            classes[class_name] = []
            for fpath in npy_files:
                # Extract sample index from filename (e.g. "FM_broadcast_5.npy" -> 5)
                stem = fpath.stem
                parts = stem.split("_")
                try:
                    idx = int(parts[-1])
                except (ValueError, IndexError):
                    idx = 0
                classes[class_name].append((fpath, idx))
    else:
        # v1 structure: flat files in datasets_validated/
        for fpath in sorted(validated_dir.glob("*.npy")):
            stem = fpath.stem
            # Match class name prefix
            matched = False
            for class_name in CLASS_META:
                if stem.startswith(class_name + "_") or stem == class_name:
                    parts = stem.split("_")
                    try:
                        idx = int(parts[-1])
                    except (ValueError, IndexError):
                        idx = 0
                    classes.setdefault(class_name, []).append((fpath, idx))
                    matched = True
                    break
            if not matched:
                logger.warning("Unrecognised file (skipping): %s", fpath.name)

    return classes


def wipe_collection(store: SignalStore) -> None:
    """Delete the existing collection to prepare for fresh seeding.

    Replaces the old interactive check_duplicates() function. Unconditionally
    wipes the collection so re-seeding never produces duplicate records
    (the 800->1600 problem observed during earlier builds).

    After calling this function, the caller must create a new SignalStore
    instance because the old instance's internal collection handle becomes
    stale after deletion.

    Catches Exception broadly because ChromaDB raises different exception
    types depending on backend version (ValueError, NotFoundError, or
    others). First-run case (collection does not exist) is also caught here.
    """
    print("Wiping existing collection before seeding...")
    try:
        store.delete_collection()
    except Exception:
        # First run: collection does not exist yet. Also catches
        # ValueError/NotFoundError depending on ChromaDB backend version.
        pass


def main() -> None:
    """Run the seeding process: wipe, download, process, insert.

    The collection is wiped before each run to guarantee a clean seed.
    A fresh SignalStore instance is created after the wipe because the
    old instance's internal collection handle is stale post-deletion.

    Classes listed in EXCLUDED_CLASSES are skipped regardless of whether
    their files exist in the cached dataset directory. This prevents
    non-AU-relevant signal types (e.g. FRS_GMRS, NOAA_weather) from
    being inserted even when present in the HuggingFace dataset cache.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    store = SignalStore(path="data/vectorstore")
    wipe_collection(store)
    store = SignalStore(path="data/vectorstore")

    embedder = SpectrumEmbedder()

    print("Downloading RTL-ML dataset from HuggingFace...")
    sys.stdout.flush()
    dataset_path = Path(
        snapshot_download(
            repo_id="TrevTron/rtl-ml-dataset",
            repo_type="dataset",
        )
    )
    print(f"Dataset cached at: {dataset_path}")

    classes = discover_dataset_files(dataset_path)
    if not classes:
        logger.error("No dataset files found. Check dataset structure.")
        sys.exit(1)

    total_processed = 0
    class_counts: dict[str, int] = {}

    for class_name in sorted(classes):
        if class_name in EXCLUDED_CLASSES:
            print(f"  {class_name}: skipped (excluded — not AU-relevant)")
            continue

        file_list = classes[class_name]
        meta = CLASS_META.get(class_name, {
            "center_freq_hz": 100_000_000,
            "label": class_name,
        })

        class_records: list[dict] = []
        for fpath, sample_index in file_list:
            record = process_sample(fpath, class_name, meta, sample_index, embedder)
            if record is not None:
                class_records.append(record)
                total_processed += 1

        if class_records:
            store.add_batch(class_records)
            class_counts[class_name] = len(class_records)

        print(f"  {class_name}: {len(class_records)}/{len(file_list)} samples inserted")

    print(f"\nSeeding complete.")
    print(f"  Total records inserted: {total_processed}")
    for class_name, count in sorted(class_counts.items()):
        print(f"    {class_name}: {count}")
    print(f"  Store count after seeding: {store.count()}")


if __name__ == "__main__":
    main()