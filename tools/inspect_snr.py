#!/usr/bin/env python3
"""
inspect_snr.py — READ-ONLY SNR inspection of stored vectors, by label.

Purpose
-------
The production vector store (data/vectorstore) can contain noise-only captures
that were stored under a real band label, because capture_to_vectorstore.py has
no sub-threshold gate — every captured frame is stored regardless of whether a
real signal was present. Live noise then matches those stored noise vectors
closely, producing false high-confidence classifications when nothing is on air.

This script does NOT delete anything. It reads every record, isolates the ones
for a chosen ``--label``, and prints their SNR distribution so you can SEE any
noise/real split and choose a cut line before any deletion. It also
cross-references each record's own stored per-band threshold
(``signal_threshold_db``) — a record whose ``snr_db`` is below its own capture
threshold was almost certainly noise.

This tool is label-agnostic: inspect any band by passing ``--label``. The stored
label strings use underscores, matching capture_to_vectorstore.py CAPTURE_TARGETS
(e.g. ``ADS_B``, ``AIS``, ``APRS``, ``FM``). Passing a label that matches zero
records is reported clearly rather than looking like success.

Pairs with tools/delete_low_snr.py: pass the SAME ``--max-snr`` value to that
tool to delete exactly the record set previewed here (both use strictly-less-than
semantics — a record at exactly the cut value is KEPT).

Run (from repo root, per project convention):
    PYTHONPATH=. python tools/inspect_snr.py
    PYTHONPATH=. python tools/inspect_snr.py --label AIS
    PYTHONPATH=. python tools/inspect_snr.py --label ADS_B --max-snr 8.0

Legal: Receive-only. Radiocommunications Act 1992 (Cth). AU/SA. ACMA.
       This tool only reads a local database. No RF, no TX, no network.
"""

from __future__ import annotations

import argparse
from collections import Counter

from embeddings.store import SignalStore

# Default label if none supplied. The stored label string for ADS-B is "ADS_B"
# (underscore) — see capture_to_vectorstore.py CAPTURE_TARGETS. Matching the exact
# stored string matters: "adsb" or "ADS-B" would match zero records.
DEFAULT_LABEL = "ADS_B"


def _bucket(snr: float) -> str:
    """Return a 2 dB-wide bucket label for an SNR value, for the histogram."""
    lo = int(snr // 2) * 2
    return f"[{lo:>3d}, {lo + 2:>3d})"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only SNR inspection of stored vectors by label (no deletion)."
    )
    parser.add_argument(
        "--path",
        default="data/vectorstore",
        help="Path to the ChromaDB store (default: data/vectorstore).",
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help=f"Label to inspect (default: {DEFAULT_LABEL}).",
    )
    parser.add_argument(
        "--max-snr",
        type=float,
        default=None,
        help=(
            "Optional preview cut. When set, lists exactly which records have "
            "snr_db STRICTLY BELOW this value — i.e. the set that "
            "tools/delete_low_snr.py --max-snr <same value> would remove. "
            "Read-only: this never deletes."
        ),
    )
    args = parser.parse_args()

    store = SignalStore(path=args.path)
    total = store.count()
    print(f"\nStore: {args.path}")
    print(f"Total records in collection: {total}")
    print(f"Labels present: {', '.join(store.list_labels()) or '(none)'}\n")

    # get_all_embeddings() returns ids + metadatas (and embeddings we ignore).
    dump = store.get_all_embeddings()
    ids = dump["ids"]
    metadatas = dump["metadatas"]

    rows = []
    for rec_id, meta in zip(ids, metadatas):
        if not meta or str(meta.get("label")) != args.label:
            continue
        snr = meta.get("snr_db")
        if snr is None:
            continue
        rows.append(
            {
                "id": rec_id,
                "snr_db": float(snr),
                "threshold_db": meta.get("signal_threshold_db"),
                "peak_power_db": meta.get("peak_power_db"),
                "timestamp": meta.get("timestamp"),
            }
        )

    if not rows:
        print(f"No records found with label '{args.label}'. Nothing to inspect.")
        return

    rows.sort(key=lambda r: r["snr_db"])
    snrs = [r["snr_db"] for r in rows]

    print(f"=== {args.label} records: {len(rows)} ===")
    print(f"SNR min / median / max: "
          f"{snrs[0]:.2f} / {snrs[len(snrs) // 2]:.2f} / {snrs[-1]:.2f} dB\n")

    # Histogram (2 dB buckets, ascending)
    print("SNR histogram (2 dB buckets):")
    hist = Counter(_bucket(s) for s in snrs)
    for bucket in sorted(hist, key=lambda b: int(b.split(",")[0].strip("[ "))):
        bar = "#" * hist[bucket]
        print(f"  {bucket} dB  {hist[bucket]:>4d}  {bar}")
    print()

    # Below-own-threshold view: a record whose stored snr_db is below the
    # per-band signal_threshold_db it was captured against is a strong
    # noise candidate. This is a suggestion to eyeball, NOT an auto-selection.
    below = [
        r for r in rows
        if r["threshold_db"] is not None and r["snr_db"] < float(r["threshold_db"])
    ]
    print(f"Records below their own stored signal_threshold_db: "
          f"{len(below)} of {len(rows)}")
    if below:
        print("  (these were sub-threshold at capture time — likely noise)")
        print(f"  their SNR range: "
              f"{min(r['snr_db'] for r in below):.2f} .. "
              f"{max(r['snr_db'] for r in below):.2f} dB")
    print()

    # Timestamp spread — helps confirm whether these all came from one run.
    stamps = sorted(str(r["timestamp"]) for r in rows if r["timestamp"])
    if stamps:
        print(f"Timestamp range: {stamps[0]}  ..  {stamps[-1]}")
    print()

    # Low-SNR sample listing so you can spot-check individual records.
    print("Lowest 15 by SNR (candidate noise — inspect before trusting):")
    print(f"  {'snr_db':>8}  {'thresh':>7}  {'peak_db':>8}  timestamp")
    for r in rows[:15]:
        thr = f"{float(r['threshold_db']):.1f}" if r["threshold_db"] is not None else "  ?  "
        peak = f"{float(r['peak_power_db']):.1f}" if r["peak_power_db"] is not None else "   ?   "
        print(f"  {r['snr_db']:>8.2f}  {thr:>7}  {peak:>8}  {r['timestamp']}")
    print()

    # --max-snr preview — the exact set delete_low_snr.py would remove.
    if args.max_snr is not None:
        selected = [r for r in rows if r["snr_db"] < args.max_snr]
        print(f"=== PREVIEW: --max-snr {args.max_snr:.2f} (strictly below) ===")
        print(f"Would select {len(selected)} of {len(rows)} '{args.label}' "
              f"record(s) for deletion.")
        if selected:
            print(f"  {'snr_db':>8}  {'thresh':>7}  {'peak_db':>8}  id")
            for r in selected:
                thr = (f"{float(r['threshold_db']):.1f}"
                       if r["threshold_db"] is not None else "  ?  ")
                peak = (f"{float(r['peak_power_db']):.1f}"
                        if r["peak_power_db"] is not None else "   ?   ")
                print(f"  {r['snr_db']:>8.2f}  {thr:>7}  {peak:>8}  {r['id']}")
            print(f"\n  To delete exactly these, run:")
            print(f"    PYTHONPATH=. python tools/delete_low_snr.py "
                  f"--label {args.label} --max-snr {args.max_snr} --execute")
        print()

    print("This script made NO changes. To delete, decide a cut line from the "
          "histogram above, preview it here with --max-snr, then use "
          "tools/delete_low_snr.py (backed-up, dry-run-first).")


if __name__ == "__main__":
    main()
