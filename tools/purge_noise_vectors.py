"""Preview or purge noise-shaped fingerprints from a local vector store.

Run from the repository root:
    ./mimir tool purge_noise_vectors
    ./mimir tool purge_noise_vectors --label ADS_B
    ./mimir tool purge_noise_vectors --path /path/to/store --execute

Dry run is the default. Execution first makes a timestamped directory backup
and aborts on any backup failure, then requires the exact selected record count
as confirmation. In-memory stores are refused. Only the store at --path is
covered: data/vectorstore by default, not data/calibration_vectorstore.

Selection decodes normalised embedding features using the embedder's ranges
and the classifier's deterministic noise gate. Decoding is approximate at the
exact boundary; bins are rounded to integers and flatness to six decimals to
limit float32 drift. Missing or short embeddings are skipped. Intentional
noise reference labels are always excluded, even with --label.

Legal: Receive-only. Radiocommunications Act 1992 (Cth), AU/SA, ACMA.
This local database maintenance tool performs no RF operation and no network
operation.
"""

from __future__ import annotations

import argparse
import math
import shutil
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from embeddings.embedder import EMBEDDING_FEATURES, NORMALISATION_RANGES
from embeddings.store import SignalStore
from llm.classifier import SignalClassifier

EXCLUDED_REFERENCE_LABELS = frozenset({"noise", "noise_floor"})
DELETE_CHUNK = 500


def _decode_noise_features(embedding: Sequence[float] | None) -> dict | None:
    """Decode the noise-gate fields, skipping absent or incomplete vectors."""
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
    """Return noise-shaped rows and the reference-label count in the filter."""
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
    """Print selected ids, decoded fields and excluded reference count."""
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


def _make_backup(path: str) -> Path:
    """Copy the store to a timestamped sibling, raising on any failure."""
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"Store path does not exist: {src}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = src.with_name(f"{src.name}.backup-{stamp}")
    if dst.exists():
        raise FileExistsError(f"Backup target already exists: {dst}")
    shutil.copytree(src, dst)
    return dst


def main() -> None:
    """Preview noise rows or back up, confirm and delete the selected ids."""
    parser = argparse.ArgumentParser(
        description="Purge noise-shaped vectors (dry-run by default).",
    )
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
    args = parser.parse_args()
    if args.path == ":memory:":
        print(
            "Refusing to run against an in-memory store: "
            "nothing to back up or persist."
        )
        raise SystemExit(1)

    store = SignalStore(path=args.path)
    total_before = store.count()
    print(f"\nStore: {args.path}")
    print(f"Total records in collection: {total_before}")
    print(f"Labels present: {', '.join(store.list_labels()) or '(none)'}")
    rows, excluded = _select_rows(store, args.label)
    _print_selection(rows, args.label, excluded)
    if not rows:
        print("\nNothing matches the cut. No changes made.")
        return
    ids = [row["id"] for row in rows]
    if not args.execute:
        print(f"\nDRY RUN: nothing was deleted. {len(ids)} record(s) matched.")
        print("Re-run with --execute to back up the store and delete these.")
        return

    # Any backup error must abort before confirmation or deletion.
    print("\nCreating backup before deletion...")
    try:
        backup_path = _make_backup(args.path)
    except Exception as exc:  # noqa: BLE001 - abort on any backup failure
        print(f"BACKUP FAILED: {exc}")
        print("Aborting. No records were deleted.")
        raise SystemExit(1) from exc
    print(f"  Backup created: {backup_path}")
    print(f"\nAbout to permanently delete {len(ids)} noise-shaped record(s).")
    answer = input(
        f"Type the number {len(ids)} to confirm (anything else aborts): "
    )
    if answer.strip() != str(len(ids)):
        print("Confirmation did not match. Aborting. No records were deleted.")
        print(f"Backup retained at: {backup_path}")
        raise SystemExit(1)

    # Standalone maintenance deletes by id, following delete_low_snr.
    collection = store._collection  # noqa: SLF001 - intentional maintenance
    for start in range(0, len(ids), DELETE_CHUNK):
        collection.delete(ids=ids[start:start + DELETE_CHUNK])
    print(f"\nDeleted {len(ids)} record(s).")
    print(
        f"Collection now holds {store.count()} record(s) (was {total_before})."
    )
    print(f"Backup retained at: {backup_path}")


if __name__ == "__main__":
    main()
