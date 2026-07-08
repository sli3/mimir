"""
tools/check_thresholds_cli.py
Mimir RF Scanner — threshold-guard CLI harness.

Exercises the PURE derive_thresholds() guard logic from
tools/calibrate_thresholds.py without touching hardware, ChromaDB, or the
capture pipeline. Two modes:

  SUITE  (no args)  — runs a fixed set of cases with expected outcomes,
                      asserts each, prints a table, exits 0 if all pass else 1.
                      Use this as a pre-commit smoke test.

  EVAL   (--eval S C) — evaluate one (same_type_spread, cross_type_min) pair,
                        print the verdict and derived thresholds, exit 0.
                        Use this in the field: read the two numbers off a real
                        calibrate_thresholds.py run and check them instantly.

Legal / safety: pure arithmetic only. No RF capture, no transmission, no
hardware access. Receive-only project; this file touches no radio at all.
Jurisdiction AU/SA, ACMA, Radiocommunications Act 1992 (Cth).

Usage:
    PYTHONPATH=. python tools/check_thresholds_cli.py
    PYTHONPATH=. python tools/check_thresholds_cli.py --eval 0.0006 0.0124
"""

import argparse
import sys

# Import the REAL logic under test, not a copy. If this import fails, it is
# almost always because PYTHONPATH is not the repo root — say so plainly.
try:
    from tools.calibrate_thresholds import (
        CROSS_TYPE_MIN_FLOOR,
        SEPARABILITY_FACTOR,
        STRONG_MATCH_FLOOR,
        derive_thresholds,
    )
except ImportError as exc:  # pragma: no cover - environment guard
    print(
        "ERROR: could not import tools.calibrate_thresholds.\n"
        "Run from the repo root with:  PYTHONPATH=. python "
        "tools/check_thresholds_cli.py\n"
        f"Underlying import error: {exc}",
        file=sys.stderr,
    )
    raise SystemExit(2)

# ANSI colours — plain fallback if output is not a TTY (e.g. piped to a file).
if sys.stdout.isatty():
    _GREEN, _RED, _YELLOW, _DIM, _RESET = (
        "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m",
    )
else:
    _GREEN = _RED = _YELLOW = _DIM = _RESET = ""


def _verdict(ok: bool) -> str:
    return f"{_GREEN}PASS{_RESET}" if ok else f"{_RED}FAIL{_RESET}"


# Fixed self-check cases. Each row: (label, same_type_spread, cross_type_min,
# expected_ok). Values are grounded in real Mimir runs where noted.
SUITE_CASES = [
    # label,                                       same,    cross,   expect_ok
    ("degenerate live run (ACARS/Aviation, noise)", 0.0001, 0.0005, False),
    ("clean run (handoff real numbers)",            0.0006, 0.0124, True),
    ("inverted ADS-B run (2026-07-08, overlap)",    0.0179, 0.0143, False),
    ("tight-but-real edge",                         0.0015, 0.0060, True),
    ("cross exactly at floor",                      0.0010, 0.0050, True),
    ("below floor but ratio would pass",            0.0001, 0.0040, False),
    ("wide same-type overlap",                      0.0060, 0.0100, False),
]


def run_suite() -> int:
    """Run every SUITE_CASE, assert expected ok, print a table. Return exit code."""
    print(f"\nThreshold-guard self-check")
    print(f"{_DIM}SEPARABILITY_FACTOR={SEPARABILITY_FACTOR}  "
          f"STRONG_MATCH_FLOOR={STRONG_MATCH_FLOOR}  "
          f"CROSS_TYPE_MIN_FLOOR={CROSS_TYPE_MIN_FLOOR}{_RESET}\n")
    header = f"{'case':<42} {'same':>8} {'cross':>8}  {'result':>8}  {'exp':>4}  detail"
    print(header)
    print("-" * len(header) + ("-" * 24))

    failures = 0
    for label, same, cross, expect_ok in SUITE_CASES:
        result = derive_thresholds(same, cross)
        ok = result["ok"]
        matched = ok == expect_ok
        if not matched:
            failures += 1
        mark = f"{_GREEN}✓{_RESET}" if matched else f"{_RED}✗ MISMATCH{_RESET}"
        exp = "ok" if expect_ok else "no"
        detail = (
            f"strong={result['strong_match']} poss={result['possible_match']} "
            f"diff={result['different_type']}"
            if ok else (result["reason"].split(":")[0] if result["reason"] else "")
        )
        print(f"{label:<42} {same:>8.4f} {cross:>8.4f}  "
              f"{_verdict(ok):>17}  {exp:>4}  {mark} {_DIM}{detail}{_RESET}")

    print()
    if failures:
        print(f"{_RED}SELF-CHECK FAILED: {failures} case(s) did not match "
              f"expected outcome.{_RESET}")
        print("The guard logic has regressed — do NOT commit.\n")
        return 1
    print(f"{_GREEN}SELF-CHECK PASSED: all {len(SUITE_CASES)} cases behaved as "
          f"expected.{_RESET}\n")
    return 0


def run_eval(same: float, cross: float) -> int:
    """Evaluate a single pair and print the full verdict. Always returns 0."""
    result = derive_thresholds(same, cross)
    ok = result["ok"]
    print(f"\nsame_type_spread (p90):   {same:.4f}")
    print(f"cross_type_min:           {cross:.4f}")
    print(f"{_DIM}floor gate:  cross >= {CROSS_TYPE_MIN_FLOOR}  -> "
          f"{cross >= CROSS_TYPE_MIN_FLOOR}{_RESET}")
    print(f"{_DIM}ratio gate:  cross >  {SEPARABILITY_FACTOR} x same "
          f"({SEPARABILITY_FACTOR * same:.4f})  -> "
          f"{cross > SEPARABILITY_FACTOR * same}{_RESET}")
    print()
    print(f"VERDICT: {_verdict(ok)}")
    if ok:
        print(f"  STRONG_MATCH   = {result['strong_match']}")
        print(f"  POSSIBLE_MATCH = {result['possible_match']}")
        print(f"  DIFFERENT_TYPE = {result['different_type']}")
        print(f"  NOVEL_SIGNAL   = {result['novel_signal']}")
        print(f"\n  {_GREEN}These numbers are internally consistent. Still confirm "
              f"the capture had live signal before pasting.{_RESET}")
    else:
        print(f"  {_RED}{result['reason']}{_RESET}")
        print(f"\n  {_RED}Do NOT paste thresholds from this run.{_RESET}")
    print()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check Mimir threshold-guard logic (suite or single eval).",
    )
    parser.add_argument(
        "--eval",
        nargs=2,
        type=float,
        metavar=("SAME_TYPE_SPREAD", "CROSS_TYPE_MIN"),
        help="Evaluate one pair instead of running the self-check suite.",
    )
    args = parser.parse_args()

    if args.eval is not None:
        same, cross = args.eval
        if same < 0 or cross < 0:
            print("ERROR: distances cannot be negative.", file=sys.stderr)
            raise SystemExit(2)
        raise SystemExit(run_eval(same, cross))

    raise SystemExit(run_suite())


if __name__ == "__main__":
    main()
