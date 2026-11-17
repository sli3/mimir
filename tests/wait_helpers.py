"""Bounded polling helpers for tests that wait for worker-thread outcomes."""

import threading
import time
from collections.abc import Callable


def wait_until(
    predicate: Callable[[], bool],
    timeout: float = 5.0,
    interval: float = 0.005,
    message: str | None = None,
) -> None:
    """Poll until predicate is true, raising a descriptive assertion on timeout.

    Use an event wait and a performance-counter deadline so patches to the
    shared time module's sleep or monotonic functions cannot affect polling.
    """
    deadline = time.perf_counter() + timeout
    wake = threading.Event()
    while not predicate():
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            detail = f": {message}" if message else ""
            raise AssertionError(
                f"Condition not met within {timeout:g} seconds{detail}"
            )
        wake.wait(min(interval, remaining))
