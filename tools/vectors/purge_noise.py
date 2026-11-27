"""Preview or purge noise-shaped fingerprints from a local vector store.

Decode normalised embedding features using the embedder's ranges and the
classifier's deterministic noise gate. Preserve reference labels, skip missing
or short embeddings and round decoded fields to limit float32 boundary drift.
Execution requires a persistent store, a backup and typed count confirmation.
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Sequence

from embeddings.embedder import EMBEDDING_FEATURES, NORMALISATION_RANGES
from embeddings.store import SignalStore
from llm.classifier import SignalClassifier
from tools.vectors import _store_ops

EXCLUDED_REFERENCE_LABELS = frozenset({"noise", "noise_floor"})


def _decode_noise_features(embedding: Sequence[float] | None) -> dict | None:
    """Decode stored noise fields; skip incomplete or non-finite vectors."""
    if embedding is None or len(embedding) < len(EMBEDDING_FEATURES):
        return None
    decoded: dict = {}
    for name in ("occupied_bins", "spectral_flatness"):
        lo, hi = NORMALISATION_RANGES[name]
        normalised = float(embedding[EMBEDDING_FEATURES.index(name)])
        value = lo + normalised * (hi - lo)
        if not math.isfinite(value):
            return None
        decoded[name] = (
            round(value) if name == "occupied_bins" else round(value, 6)
        )
    return decoded


def _select_rows(
    store: SignalStore, label: str | None = None,
) -> tuple[list[dict], int]:
    """Select decoded noise rows while always protecting reference labels."""
    dump = store.get_all_embeddings()
    embeddings = dump.get("embeddings")
    # Avoid truth-value checks: ChromaDB may return numpy arrays or lists.
    if embeddings is None:
        embeddings = []
    metadatas = dump.get("metadatas")
    if metadatas is None:
        metadatas = []
    classifier = SignalClassifier()
    rows: list[dict] = []
    excluded = 0
    for idx, rec_id in enumerate(dump["ids"]):
        meta = metadatas[idx] if idx < len(metadatas) else None
        record_label = str((meta or {}).get("label", ""))
        if label is not None and record_label != label:
            continue
        if record_label.casefold() in EXCLUDED_REFERENCE_LABELS:
            excluded += 1
            continue
        embedding = embeddings[idx] if idx < len(embeddings) else None
        decoded = _decode_noise_features(embedding)
        if decoded is not None and classifier.is_noise_shaped(decoded):
            rows.append({
                "id": rec_id,
                "label": record_label,
                **decoded,
                "snr_db": (meta or {}).get("snr_db"),
            })
    return rows, excluded


def _print_selection(
    rows: list[dict], label: str | None, excluded: int,
) -> None:
    """Report selected ids, decoded fields and protected reference counts."""
    scope = f"label '{label}'" if label is not None else "all labels"
    print(f"\n=== Noise-shaped selection: {scope} ===")
    print(f"Matched {len(rows)} record(s).")
    print(f"Excluded {excluded} record(s) as reference labels.")
    if not rows:
        return
    print(f"  {'label':<18}  {'bins':>6}  {'flatness':>9}  {'snr_db':>8}  id")
    for row in rows:
        snr = (
            f"{float(row['snr_db']):.2f}" if row["snr_db"] is not None else "?"
        )
        print(
            f"  {row['label']:<18}  {row['occupied_bins']:>6}  "
            f"{row['spectral_flatness']:>9.6f}  {snr:>8}  {row['id']}"
        )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add optional store and label flags plus explicit deletion opt-in."""
    parser.add_argument(
        "--path", default="data/vectorstore",
        help="Path to the ChromaDB store (default: data/vectorstore).",
    )
    parser.add_argument(
        "--label",
        help="Restrict selection to this label (default: all labels).",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Back up the store and require confirmation before deleting.",
    )


def run(path: str, label: str | None, execute: bool) -> int:
    """Preview noise rows or back up, confirm and delete the selected ids."""
    if execute and path == _store_ops.MEMORY_STORE:
        print(_store_ops.MEMORY_STORE_REFUSAL)
        return 1

    store = SignalStore(path=path)
    total_before = store.count()
    print(f"\nStore: {path}")
    print(f"Total records in collection: {total_before}")
    print(f"Labels present: {', '.join(store.list_labels()) or '(none)'}")
    rows, excluded = _select_rows(store, label)
    _print_selection(rows, label, excluded)
    if not rows:
        print("\nNothing matches the cut. No changes made.")
        return 0
    ids = [row["id"] for row in rows]
    if not execute:
        print(f"\nDRY RUN: nothing was deleted. {len(ids)} record(s) matched.")
        print("Re-run with --execute to back up the store and delete these.")
        return 0

    # Filesystem backup errors abort before confirmation or deletion.
    print("\nCreating backup before deletion...")
    try:
        backup_path = _store_ops.make_backup(path)
    except OSError as exc:
        print(f"BACKUP FAILED: {exc}")
        print("Aborting. No records were deleted.")
        return 1
    print(f"  Backup created: {backup_path}")
    print(f"\nAbout to permanently delete {len(ids)} noise-shaped record(s).")
    if not _store_ops.confirm_count(len(ids)):
        print("Confirmation did not match. Aborting. No records were deleted.")
        print(f"Backup retained at: {backup_path}")
        return 1

    deleted = _store_ops.delete_ids(store, ids)
    print(f"\nDeleted {deleted} record(s).")
    print(
        f"Collection now holds {store.count()} record(s) (was {total_before})."
    )
    print(f"Backup retained at: {backup_path}")
    return 0
