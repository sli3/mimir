#!/usr/bin/env python3
"""run_guard.py — the PreToolUse hook entry point. Runs agent_guard.py, failing closed.

agent_guard.py already turns its own runtime errors into a block (exit 2). It
cannot do that if the file itself no longer loads: a syntax error or a name
that does not exist at import time makes Python exit 1, and Claude Code treats
any exit other than 2 as a non-blocking error, so the call would go ahead.

This launcher loads the guard itself, so ANY failure (missing file, syntax
error, import error, an unexpected exit code) becomes exit 2: the call is
blocked and the reason is shown. Exit 0, with or without an "ask" decision on
stdout, and exit 2 pass through unchanged.

Keep this file small and dependency-free. Like agent_guard.py it is read-only
on disk (chmod a-w) and only Prin edits it.
"""

import importlib.util
import sys
from pathlib import Path

GUARD = Path(__file__).resolve().with_name("agent_guard.py")


def fail(reason: str) -> None:
    """Block the tool call because the guard could not decide."""
    print(f"agent_guard: {reason}; call blocked (fail closed)", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    """Load agent_guard.py and run its main(), mapping every failure to exit 2."""
    try:
        spec = importlib.util.spec_from_file_location("agent_guard", GUARD)
        if spec is None or spec.loader is None:
            fail(f"cannot load {GUARD.name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.main()
    except SystemExit as stop:
        if stop.code in (None, 0, 2):
            raise
        fail(f"guard exited with {stop.code!r}")
    except BaseException as err:  # noqa: BLE001 - fail closed on anything
        fail(f"guard could not run ({err!r})")


if __name__ == "__main__":
    main()
