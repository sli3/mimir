"""Keep the old noise-vector maintenance name as a compatibility wrapper.

Use ``./mimir tool vectors purge-noise``. The original path, label and execute
flags keep dry runs as the default, with backup and confirmation gates.
"""

from __future__ import annotations

import argparse
import sys

from tools.vectors import purge_noise


def main() -> None:
    """Parse legacy noise-purge flags and forward to vectors purge-noise."""
    print(
        "Use ./mimir tool vectors purge-noise instead of purge_noise_vectors.",
        file=sys.stderr,
    )
    parser = argparse.ArgumentParser(
        description="Purge noise-shaped vectors (dry-run by default)."
    )
    purge_noise.add_arguments(parser)
    args = parser.parse_args()
    code = purge_noise.run(args.path, args.label, args.execute)
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
