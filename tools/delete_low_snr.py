#!/usr/bin/env python3
"""
delete_low_snr.py — Delete low-SNR vectors for one label, with safety gates.

Purpose
-------
Companion to tools/inspect_snr.py. Removes records for a chosen ``--label`` whose
stored ``snr_db`` is STRICTLY BELOW a ``--max-snr`` cut line you supply (a record
at exactly the cut value is KEPT). This exists because capture_to_vectorstore.py
has no sub-threshold gate, so noise-only frames were stored under real band labels
and now cause false high-confidence matches on live noise.

There is no clean, principled SNR/threshold/timestamp split in the ADS_B data
(inspect_snr.py confirmed a continuous smear, not a bimodal one), so this tool
does NOT recommend a cut — YOU choose ``--max-snr`` after eyeballing the
histogram. Preview the exact set first with:
    PYTHONPATH=. python tools/inspect_snr.py --label ADS_B --max-snr 8.0
then delete the identical set here by passing the same value.

Shared flag contract with inspect_snr.py: ``--path``, ``--label``, ``--max-snr``
mean exactly the same thing in both tools. ``--max-snr`` is REQUIRED here (no
default) so a deletion cannot run without a deliberate cut value.

Safety gates (all of them apply):
  1. Dry-run by DEFAULT. Without ``--execute`` nothing is deleted — it only
     prints the records that WOULD go.
  2. ``--execute`` auto-creates a full backup of the store directory
     (``<path>.backup-<timestamp>``) BEFORE any delete. If the backup fails,
     the run aborts and nothing is deleted.
  3. Interactive confirmation: you must type the exact record count to proceed.
     Typing anything else aborts.
  4. Refuses to operate on an in-memory (":memory:") store — there is nothing
     to back up and nothing to persist.

Run (from repo root, per project convention):
    # 1. Preview (read-only):
    PYTHONPATH=. python tools/inspect_snr.py --label ADS_B --max-snr 8.0
    # 2. Dry-run the delete (still no changes):
    PYTHONPATH=. python tools/delete_low_snr.py --label ADS_B --max-snr 8.0
    # 3. Actually delete (backup + confirm):
    PYTHONPATH=. python tools/delete_low_snr.py --label ADS_B --max-snr 8.0 --execute

Legal: Receive-only. Radiocommunications Act 1992 (Cth). AU/SA. ACMA.
       This tool only reads and deletes rows in a local database. It performs
       no RF operation of any kind — no receive, no transmit, no network.

Destructive-DB policy: this is a standalone manual maintenance script by design,
NOT a reusable SignalStore method and NOT a /build target. It reaches into the
store's collection to delete by id (the same get-then-delete-by-ids pattern as
SignalStore.delete_by_label), which is intentional for a one-off manual tool.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from embeddings.store import SignalStore

DEFAULT_LABEL = "ADS_B"

# ChromaDB handles small delete batches trivially; chunk anyway so the tool
# stays sane if pointed at a pathologically large selection in future.
DELETE_CHUNK = 500


def _select_rows(store: SignalStore, label: str, max_snr: float) -> list[dict]:
    """Return the records for ``label`` with snr_db strictly below ``max_snr``.

    Mirrors inspect_snr.py's selection exactly so the same --max-snr value
    yields the same set in both tools. Records with a missing snr_db are
    skipped (they cannot be judged and are never selected for deletion).
    """
    dump = store.get_all_embeddings()
    rows: list[dict] = []
    for rec_id, meta in zip(dump["ids"], dump["metadatas"]):
        if not meta or str(meta.get("label")) != label:
            continue
        snr = meta.get("snr_db")
        if snr is None:
            continue
        if float(snr) < max_snr:
            rows.append(
                {
                    "id": rec_id,
                    "snr_db": float(snr),
                    "threshold_db": meta.get("signal_threshold_db"),
                    "peak_power_db": meta.get("peak_power_db"),
                    "timestamp": meta.get("timestamp"),
                }
            )
    rows.sort(key=lambda r: r["snr_db"])
    return rows


def _print_selection(rows: list[dict], label: str, max_snr: float) -> None:
    """Print the records that match the cut, in inspect_snr.py's column style."""
    print(f"\n=== Selection: label '{label}', snr_db < {max_snr:.2f} dB "
          f"(strictly below) ===")
    print(f"Matched {len(rows)} record(s).")
    if not rows:
        return
    print(f"  {'snr_db':>8}  {'thresh':>7}  {'peak_db':>8}  id")
    for r in rows:
        thr = (f"{float(r['threshold_db']):.1f}"
               if r["threshold_db"] is not None else "  ?  ")
        peak = (f"{float(r['peak_power_db']):.1f}"
                if r["peak_power_db"] is not None else "   ?   ")
        print(f"  {r['snr_db']:>8.2f}  {thr:>7}  {peak:>8}  {r['id']}")


def _make_backup(path: str) -> Path:
    """Copy the store directory to a timestamped sibling. Returns the backup path.

    Raises on failure so the caller aborts before deleting anything.
    """
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
    parser = argparse.ArgumentParser(
        description=("Delete low-SNR vectors for one label "
                     "(dry-run by default; --execute backs up and confirms).")
    )
    parser.add_argument(
        "--path",
        default="data/vectorstore",
        help="Path to the ChromaDB store (default: data/vectorstore).",
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help=f"Label to operate on (default: {DEFAULT_LABEL}).",
    )
    parser.add_argument(
        "--max-snr",
        type=float,
        required=True,
        help=("REQUIRED. Delete records with snr_db STRICTLY BELOW this value. "
              "No default — you must choose a cut from the inspect_snr.py "
              "histogram. Pass the same value you previewed there."),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=("Actually delete. Without this flag the tool is a dry-run and "
              "changes nothing. --execute creates a backup and asks for "
              "interactive confirmation before deleting."),
    )
    args = parser.parse_args()

    if args.path == ":memory:":
        print("Refusing to run against an in-memory store — nothing to back up "
              "or persist.")
        sys.exit(1)

    store = SignalStore(path=args.path)
    total_before = store.count()
    print(f"\nStore: {args.path}")
    print(f"Total records in collection: {total_before}")
    print(f"Labels present: {', '.join(store.list_labels()) or '(none)'}")

    rows = _select_rows(store, args.label, args.max_snr)
    _print_selection(rows, args.label, args.max_snr)

    if not rows:
        print("\nNothing matches the cut. No changes made.")
        return

    ids = [r["id"] for r in rows]

    # --- Dry-run gate -------------------------------------------------------
    if not args.execute:
        print(f"\nDRY RUN — nothing was deleted. {len(ids)} record(s) matched.")
        print("Re-run with --execute to back up the store and delete these.")
        return

    # --- Backup BEFORE any delete ------------------------------------------
    print(f"\nCreating backup before deletion...")
    try:
        backup_path = _make_backup(args.path)
    except Exception as exc:  # noqa: BLE001 — abort on ANY backup failure
        print(f"BACKUP FAILED: {exc}")
        print("Aborting. No records were deleted.")
        sys.exit(1)
    print(f"  Backup created: {backup_path}")

    # --- Interactive confirmation ------------------------------------------
    print(f"\nAbout to permanently delete {len(ids)} '{args.label}' record(s) "
          f"with snr_db < {args.max_snr:.2f} dB.")
    answer = input(f"Type the number {len(ids)} to confirm (anything else aborts): ")
    if answer.strip() != str(len(ids)):
        print("Confirmation did not match. Aborting. No records were deleted.")
        print(f"(Your backup at {backup_path} is untouched and can be removed.)")
        sys.exit(1)

    # --- Delete by id, in chunks -------------------------------------------
    # Standalone destructive maintenance: reach into the collection directly,
    # same get-then-delete-by-ids pattern as SignalStore.delete_by_label.
    collection = store._collection  # noqa: SLF001 — intentional for this tool
    deleted = 0
    for i in range(0, len(ids), DELETE_CHUNK):
        chunk = ids[i:i + DELETE_CHUNK]
        collection.delete(ids=chunk)
        deleted += len(chunk)

    total_after = store.count()
    print(f"\nDeleted {deleted} record(s).")
    print(f"Collection now holds {total_after} record(s) "
          f"(was {total_before}).")
    print(f"\nBackup retained at: {backup_path}")
    print("To roll back, remove the current store and restore the backup:")
    print(f"    rm -rf {args.path}")
    print(f"    mv {backup_path} {args.path}")


if __name__ == "__main__":
    main()
