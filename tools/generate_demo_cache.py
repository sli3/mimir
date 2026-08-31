"""
generate_demo_cache.py — Generate a JSON cache of LLM classifications for SigMF files

Offline tool. Reads one or more saved SigMF captures (one-shot
``mimir:fingerprint`` or Record-mode ``mimir:fingerprint_sequence``),
recomputes the spectral fingerprint of each chunk under the capture's
band profile, queries ChromaDB, looks up ACMA allocations, and calls
the LLM classifier to build a JSON cache. In ``--dry-run`` mode the tool
only validates the files and reports chunk counts without contacting
the LLM or writing a cache.

Usage:
    python -m tools.generate_demo_cache \
        --files data/captures/*.sigmf-meta \
        --cache data/demo_cache/demo_cache.json

    python -m tools.generate_demo_cache \
        --files data/captures/file.sigmf-meta \
        --dry-run

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

from core.pipeline.fingerprint import fingerprint_samples
from core.pipeline.replay import (
    MAX_ONE_SHOT_SAMPLES,
    MAX_SEQUENCE_ENTRIES,
    ReplayFileError,
    SAVED_MEASUREMENT_KEYS,
    _load_sigmf,
    _resolve_band,
    _validate_measurement_keys,
    _validate_sequence,
)
from dashboard.shared_state import resolve_band_profile
from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore
from llm.acma_reference import AcmaReference
from llm.classifier import SignalClassifier

logger = logging.getLogger(__name__)

ANSI_RED = "\033[91m"
ANSI_RESET = "\033[0m"

# Report progress every PROGRESS_INTERVAL chunks.
_PROGRESS_INTERVAL = 50


def _colour(text: str, code: str) -> str:
    """Wrap text in an ANSI colour code."""
    return f"{code}{text}{ANSI_RESET}"


def _count_chunks(meta) -> tuple[int, str]:
    """Validate a SigMF file and return the number of chunks it contains.

    Mirrors the validation logic in ``_replay_capture_impl`` without
    reading any samples. One-shot files count as one chunk.
    """
    captures = meta.get_captures()
    core_freq = captures[0].get("core:frequency") if captures else None
    if core_freq is None:
        raise ReplayFileError(
            "SigMF metadata has no core:frequency capture field — "
            "cannot resolve a band profile"
        )
    core_freq = float(core_freq)

    band_key, _band_match = _resolve_band(core_freq)
    if band_key is None:
        raise ReplayFileError(
            f"could not resolve a BAND_PROFILES band for {core_freq:.0f} Hz"
        )

    total_samples = int(meta.sample_count or 0)

    saved_single = meta.get_global_field("mimir:fingerprint")
    saved_sequence = meta.get_global_field("mimir:fingerprint_sequence")
    if saved_sequence is not None:
        sequence = _validate_sequence(saved_sequence, total_samples)
        return len(sequence), "record-mode"
    if saved_single is not None:
        _validate_measurement_keys(saved_single, "mimir:fingerprint")
        if total_samples > MAX_ONE_SHOT_SAMPLES:
            raise ReplayFileError(
                f"one-shot replay refused: file implies {total_samples} samples, "
                f"exceeding the {MAX_ONE_SHOT_SAMPLES}-sample cap"
            )
        return 1, "one-shot"
    raise ReplayFileError(
        "SigMF file carries neither mimir:fingerprint nor "
        "mimir:fingerprint_sequence — nothing to classify"
    )


def _neighbours_from_query_result(query_result: dict) -> list[dict]:
    """Convert a ChromaDB query result into the label/distance list used by
    the LLM pipeline."""
    metadatas = query_result.get("metadatas") or [[]]
    distances = query_result.get("distances") or [[]]
    if not metadatas or not distances:
        return []
    return [
        {"label": m.get("label", "unknown") if m else "unknown", "distance": d}
        for m, d in zip(metadatas[0], distances[0])
    ]


def _classify_chunk(
    fingerprint: dict,
    embedder: SpectrumEmbedder,
    store: SignalStore,
    classifier: SignalClassifier,
    acma: AcmaReference,
) -> dict:
    """Embed a fingerprint, query the vector store, and classify."""
    vector = embedder.embed(fingerprint)
    query_result = store.query(vector, n_results=5)
    neighbours = _neighbours_from_query_result(query_result)
    acma_allocations = acma.lookup(fingerprint.get("center_freq_hz", 0))
    result = classifier.classify(fingerprint, neighbours, acma_allocations=acma_allocations)
    return dict(dataclasses.asdict(result))


def _process_file(
    file_path: Path,
    cache: dict,
    embedder: SpectrumEmbedder,
    store: SignalStore,
    classifier: SignalClassifier,
    acma: AcmaReference,
) -> int:
    """Classify every chunk of one SigMF file and write entries into cache.

    Returns the number of chunks classified. Raises ReplayFileError for
    file-level problems so the caller can continue with the next file.
    """
    meta = _load_sigmf(file_path)
    captures = meta.get_captures()
    core_freq = captures[0].get("core:frequency") if captures else None
    if core_freq is None:
        raise ReplayFileError(
            "SigMF metadata has no core:frequency capture field — "
            "cannot resolve a band profile"
        )
    core_freq = float(core_freq)
    sample_rate = float(meta.sample_rate)

    band_key, _band_match = _resolve_band(core_freq)
    if band_key is None:
        raise ReplayFileError(
            f"could not resolve a BAND_PROFILES band for {core_freq:.0f} Hz"
        )

    device = meta.get_global_field("mimir:device_profile") or "hackrf"
    # Ensure the band profile resolves for the device before reading samples.
    resolve_band_profile(band_key, device)

    total_samples = int(meta.sample_count or 0)
    saved_single = meta.get_global_field("mimir:fingerprint")
    saved_sequence = meta.get_global_field("mimir:fingerprint_sequence")

    chunks: dict[str, dict] = {}

    if saved_sequence is not None:
        sequence = _validate_sequence(saved_sequence, total_samples)
        for idx, entry in enumerate(sequence):
            samples = meta.read_samples(
                start_index=entry["sample_start"],
                count=entry["sample_count"],
            )
            fingerprint = fingerprint_samples(
                samples, sample_rate, core_freq, band_key, device
            )
            chunks[str(idx)] = _classify_chunk(
                fingerprint, embedder, store, classifier, acma
            )
            if (idx + 1) % _PROGRESS_INTERVAL == 0:
                print(
                    f"  ... chunk {idx + 1}/{len(sequence)} done",
                    flush=True,
                )
    elif saved_single is not None:
        _validate_measurement_keys(saved_single, "mimir:fingerprint")
        if total_samples > MAX_ONE_SHOT_SAMPLES:
            raise ReplayFileError(
                f"one-shot replay refused: file implies {total_samples} samples, "
                f"exceeding the {MAX_ONE_SHOT_SAMPLES}-sample cap"
            )
        samples = meta.read_samples(count=-1)
        fingerprint = fingerprint_samples(
            samples, sample_rate, core_freq, band_key, device
        )
        chunks["0"] = _classify_chunk(
            fingerprint, embedder, store, classifier, acma
        )
    else:
        raise ReplayFileError(
            "SigMF file carries neither mimir:fingerprint nor "
            "mimir:fingerprint_sequence — nothing to classify"
        )

    abs_path = str(file_path.resolve())
    file_id = hashlib.sha256(abs_path.encode()).hexdigest()
    cache["files"][file_id] = {
        "path": abs_path,
        "device_profile": str(device),
        "chunks": chunks,
    }
    return len(chunks)


def _run_dry_run(file_paths: list[Path]) -> int:
    """Validate files and print chunk counts without classification."""
    total_chunks = 0
    failed: list[str] = []
    for file_path in file_paths:
        try:
            meta = _load_sigmf(file_path)
            count, mode = _count_chunks(meta)
            print(f"{file_path.name}: {count} chunk(s) ({mode})")
            total_chunks += count
        except ReplayFileError as exc:
            failed.append(f"{file_path.name}: {exc}")
            print(_colour(f"ERROR: {file_path.name}: {exc}", ANSI_RED))
    if failed:
        print()
        print(_colour(f"Dry run failed for {len(failed)} file(s).", ANSI_RED))
        return 1
    print()
    print(f"Total expected chunks: {total_chunks}")
    return 0


def _build_cache(
    file_paths: list[Path],
    cache_path: Path,
    embedder: SpectrumEmbedder,
    store: SignalStore,
    classifier: SignalClassifier,
    acma: AcmaReference,
) -> int:
    """Classify every chunk and write the cache to disk.

    Returns the exit code (0 on success, 1 if any file failed).
    """
    cache: dict[str, Any] = {
        "version": 1,
        "device_driver": None,
        "files": {},
    }
    failed: list[str] = []
    total_chunks = 0

    for file_path in file_paths:
        print(f"Processing {file_path.name}...")
        try:
            chunk_count = _process_file(
                file_path, cache, embedder, store, classifier, acma
            )
            total_chunks += chunk_count
        except ReplayFileError as exc:
            failed.append(f"{file_path.name}: {exc}")
            print(_colour(f"ERROR: {file_path.name}: {exc}", ANSI_RED))
        except Exception as exc:
            failed.append(f"{file_path.name}: {exc}")
            logger.exception("Failed to process %s", file_path)
            print(_colour(f"ERROR: {file_path.name}: {exc}", ANSI_RED))

    if cache["files"]:
        first_file = next(iter(cache["files"].values()))
        cache["device_driver"] = first_file["device_profile"]

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2))
    except OSError as exc:
        print(
            _colour(
                f"ERROR: could not write cache to {cache_path}: {exc}",
                ANSI_RED,
            )
        )
        return 1

    successful_files = len(cache["files"])
    print(
        f"Cached {total_chunks} chunk(s) across {successful_files} file(s) "
        f"to {cache_path}"
    )
    if failed:
        print(_colour(f"Failed files: {len(failed)}", ANSI_RED))
        for failure in failed:
            print(_colour(f"  - {failure}", ANSI_RED))
        return 1
    return 0


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a JSON cache of LLM classifications for one or more "
            "SigMF capture files. Offline file IO + LLM only — no hardware "
            "is touched."
        ),
    )
    parser.add_argument(
        "--files",
        nargs="+",
        type=Path,
        required=True,
        help="One or more .sigmf-meta files to classify.",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=None,
        help="Output JSON cache path (required unless --dry-run is set).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate files and report chunk counts without contacting the "
            "LLM or writing a cache."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point for generate_demo_cache."""
    args = _parse_args()

    if not args.dry_run and args.cache is None:
        print(
            _colour(
                "ERROR: --cache is required unless --dry-run is set.",
                ANSI_RED,
            )
        )
        sys.exit(1)

    # Filter out non-existent paths early with a clear message.
    missing = [p for p in args.files if not p.exists()]
    if missing:
        for p in missing:
            print(_colour(f"ERROR: file not found: {p}", ANSI_RED))
        sys.exit(1)

    if args.dry_run:
        sys.exit(_run_dry_run(args.files))

    # Real run: initialise the LLM pipeline dependencies.
    embedder = SpectrumEmbedder()
    store = SignalStore(path="data/vectorstore")
    classifier = SignalClassifier()
    acma = AcmaReference()

    sys.exit(
        _build_cache(
            args.files,
            args.cache,
            embedder,
            store,
            classifier,
            acma,
        )
    )


if __name__ == "__main__":
    main()
