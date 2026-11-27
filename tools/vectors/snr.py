"""Inspect stored SNR and optionally delete a strictly below-cut selection.

Inspection and previews are read-only. Execution requires a persistent store,
a successful directory backup and confirmation of the selected record count.
"""

from __future__ import annotations

import argparse
import shlex
from collections import Counter

from embeddings.store import SignalStore
from tools.vectors import _store_ops

# Labels must match the stored string exactly, including ADS_B's underscore.
DEFAULT_LABEL = "ADS_B"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add SNR inspection flags and the explicit deletion opt-in."""
    parser.add_argument(
        "--path", default="data/vectorstore",
        help="Path to the ChromaDB store (default: data/vectorstore).",
    )
    parser.add_argument(
        "--label", default=DEFAULT_LABEL,
        help=f"Label to inspect (default: {DEFAULT_LABEL}).",
    )
    parser.add_argument(
        "--max-snr", type=float,
        help="Select records with snr_db STRICTLY BELOW this optional cut.",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Back up, confirm and delete; requires --max-snr.",
    )


def _bucket(snr: float) -> str:
    """Return the existing 2 dB-wide histogram bucket label."""
    lo = int(snr // 2) * 2
    return f"[{lo:>3d}, {lo + 2:>3d})"


def _read_rows(store: SignalStore, label: str) -> list[dict]:
    """Read labelled SNR rows, excluding records without a stored SNR."""
    dump = store.get_all_embeddings()
    rows: list[dict] = []
    for rec_id, meta in zip(dump["ids"], dump["metadatas"]):
        if not meta or str(meta.get("label")) != label:
            continue
        snr = meta.get("snr_db")
        if snr is None:
            continue
        rows.append({
            "id": rec_id,
            "snr_db": float(snr),
            "threshold_db": meta.get("signal_threshold_db"),
            "peak_power_db": meta.get("peak_power_db"),
            "timestamp": meta.get("timestamp"),
        })
    rows.sort(key=lambda row: row["snr_db"])
    return rows


def _print_report(rows: list[dict], label: str) -> None:
    """Print the histogram, thresholds, timestamps and lowest-15 views."""
    snrs = [r["snr_db"] for r in rows]
    print(f"=== {label} records: {len(rows)} ===")
    print(
        f"SNR min / median / max: "
        f"{snrs[0]:.2f} / {snrs[len(snrs) // 2]:.2f} / {snrs[-1]:.2f} dB\n"
    )

    # Keep the original ascending 2 dB buckets and their count bars.
    print("SNR histogram (2 dB buckets):")
    hist = Counter(_bucket(s) for s in snrs)
    for bucket in sorted(hist, key=lambda b: int(b.split(",")[0].strip("[ "))):
        bar = "#" * hist[bucket]
        print(f"  {bucket} dB  {hist[bucket]:>4d}  {bar}")
    print()

    # The stored capture threshold is context for inspection, not selection.
    below = [
        r for r in rows
        if r["threshold_db"] is not None
        and r["snr_db"] < float(r["threshold_db"])
    ]
    print(
        f"Records below their own stored signal_threshold_db: "
        f"{len(below)} of {len(rows)}"
    )
    if below:
        print("  (these were sub-threshold at capture time — likely noise)")
        print(
            f"  their SNR range: "
            f"{min(r['snr_db'] for r in below):.2f} .. "
            f"{max(r['snr_db'] for r in below):.2f} dB"
        )
    print()

    # Timestamp spread helps identify records from the same capture run.
    stamps = sorted(str(r["timestamp"]) for r in rows if r["timestamp"])
    if stamps:
        print(f"Timestamp range: {stamps[0]}  ..  {stamps[-1]}")
    print()

    # Retain the original sample columns for checking individual captures.
    print("Lowest 15 by SNR (candidate noise — inspect before trusting):")
    print(f"  {'snr_db':>8}  {'thresh':>7}  {'peak_db':>8}  timestamp")
    for r in rows[:15]:
        thr = (
            f"{float(r['threshold_db']):.1f}"
            if r["threshold_db"] is not None else "  ?  "
        )
        peak = (
            f"{float(r['peak_power_db']):.1f}"
            if r["peak_power_db"] is not None else "   ?   "
        )
        print(f"  {r['snr_db']:>8.2f}  {thr:>7}  {peak:>8}  {r['timestamp']}")
    print()


def _print_selection(
    rows: list[dict], label: str, max_snr: float, total: int,
) -> None:
    """Print the strict-cut preview with the original selection columns."""
    print(f"=== PREVIEW: --max-snr {max_snr:.2f} (strictly below) ===")
    print(
        f"Would select {len(rows)} of {total} '{label}' "
        "record(s) for deletion."
    )
    print(
        f"\n=== Selection: label '{label}', snr_db < {max_snr:.2f} dB "
        f"(strictly below) ==="
    )
    print(f"Matched {len(rows)} record(s).")
    if not rows:
        return
    print(f"  {'snr_db':>8}  {'thresh':>7}  {'peak_db':>8}  id")
    for r in rows:
        thr = (
            f"{float(r['threshold_db']):.1f}"
            if r["threshold_db"] is not None else "  ?  "
        )
        peak = (
            f"{float(r['peak_power_db']):.1f}"
            if r["peak_power_db"] is not None else "   ?   "
        )
        print(f"  {r['snr_db']:>8.2f}  {thr:>7}  {peak:>8}  {r['id']}")


def run(path: str, label: str, max_snr: float | None, execute: bool) -> int:
    """Inspect SNR, then optionally back up, confirm and delete matches."""
    if execute and max_snr is None:
        argparse.ArgumentParser(prog="vectors snr").error(
            "--execute requires --max-snr"
        )
    if execute and path == _store_ops.MEMORY_STORE:
        print(_store_ops.MEMORY_STORE_REFUSAL)
        return 1

    store = SignalStore(path=path)
    total_before = store.count()
    print(f"\nStore: {path}")
    print(f"Total records in collection: {total_before}")
    print(f"Labels present: {', '.join(store.list_labels()) or '(none)'}\n")
    rows = _read_rows(store, label)
    if not rows:
        print(f"No records found with label '{label}'. Nothing to inspect.")
        return 0
    _print_report(rows, label)
    selected = []
    if max_snr is not None:
        selected = [r for r in rows if r["snr_db"] < max_snr]
        _print_selection(selected, label, max_snr, len(rows))
        if not selected:
            print("\nNothing matches the cut. No changes made.")
            return 0

    if not execute:
        print("\nDRY RUN: nothing was deleted. This script made NO changes.")
        if max_snr is not None:
            print("To delete exactly these, run:")
            command = ["./mimir", "tool", "vectors", "snr"]
            # Include custom paths so the suggested command targets this store.
            if path != "data/vectorstore":
                command.extend(["--path", path])
            command.extend([
                "--label", label, "--max-snr", str(max_snr), "--execute",
            ])
            print(f"    {shlex.join(command)}")
        else:
            print(
                "Choose a cut from the histogram and preview it "
                "with --max-snr."
            )
        return 0

    # A successful directory backup must precede confirmation and deletion.
    print("\nCreating backup before deletion...")
    try:
        backup_path = _store_ops.make_backup(path)
    except OSError as exc:
        print(f"BACKUP FAILED: {exc}")
        print("Aborting. No records were deleted.")
        return 1
    print(f"  Backup created: {backup_path}")
    ids = [r["id"] for r in selected]
    print(
        f"\nAbout to permanently delete {len(ids)} '{label}' record(s) "
        f"with snr_db < {max_snr:.2f} dB."
    )
    if not _store_ops.confirm_count(len(ids)):
        print("Confirmation did not match. Aborting. No records were deleted.")
        print(
            f"(Your backup at {backup_path} is untouched and can be removed.)"
        )
        return 1

    deleted = _store_ops.delete_ids(store, ids)
    print(f"\nDeleted {deleted} record(s).")
    print(
        f"Collection now holds {store.count()} record(s) (was {total_before})."
    )
    print(f"\nBackup retained at: {backup_path}")
    print("To roll back, remove the current store and restore the backup:")
    print(f"    rm -rf {shlex.quote(path)}")
    print(f"    mv {shlex.quote(str(backup_path))} {shlex.quote(path)}")
    return 0
