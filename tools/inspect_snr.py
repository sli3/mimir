#!/usr/bin/env python3
"""Keep the old read-only SNR inspector name as a compatibility wrapper.

Use ``./mimir tool vectors snr`` for inspection and optional guarded deletion.
This wrapper keeps the original preview flags and cannot execute deletes.
"""

from __future__ import annotations

import argparse
import sys

from tools.vectors import snr


def main() -> None:
    """Parse the legacy read-only flags and report through vectors snr."""
    print(
        "Use ./mimir tool vectors snr instead of inspect_snr.",
        file=sys.stderr,
    )
    parser = argparse.ArgumentParser(
        description="Read-only SNR inspection by label (no deletion)."
    )
    parser.add_argument("--path", default="data/vectorstore")
    parser.add_argument("--label", default=snr.DEFAULT_LABEL)
    parser.add_argument(
        "--max-snr", type=float,
        help="Preview snr_db STRICTLY BELOW this value; never deletes.",
    )
    args = parser.parse_args()
    code = snr.run(args.path, args.label, args.max_snr, execute=False)
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
