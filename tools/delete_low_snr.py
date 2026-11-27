#!/usr/bin/env python3
"""Keep the old guarded SNR deletion name as a compatibility wrapper.

Use ``./mimir tool vectors snr``. The legacy cut remains required; deletion
still requires --execute, a backup and confirmation of the selected count.
"""

from __future__ import annotations

import argparse
import sys

from tools.vectors import snr


def main() -> None:
    """Parse the legacy required cut and forward to guarded vectors snr."""
    print(
        "Use ./mimir tool vectors snr instead of delete_low_snr.",
        file=sys.stderr,
    )
    parser = argparse.ArgumentParser(
        description="Delete low-SNR vectors by label (dry-run by default)."
    )
    parser.add_argument("--path", default="data/vectorstore")
    parser.add_argument("--label", default=snr.DEFAULT_LABEL)
    parser.add_argument("--max-snr", type=float, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    code = snr.run(args.path, args.label, args.max_snr, args.execute)
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
