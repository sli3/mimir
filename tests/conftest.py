"""Close test SignalStores and optionally report raw file descriptor growth."""

import logging
from collections.abc import Generator
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from embeddings.store import SignalStore

if TYPE_CHECKING:
    from _pytest.terminal import TerminalReporter


logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def close_signal_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Close each real store created by a test, including failed initialisation."""
    stores: list[SignalStore] = []
    original_init = SignalStore.__init__

    @wraps(original_init)
    def tracked_init(self: SignalStore, *args: Any, **kwargs: Any) -> None:
        """Track the store before initialisation so partial clients are closed."""
        stores.append(self)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(SignalStore, "__init__", tracked_init)
    yield
    for store in reversed(stores):
        try:
            store.close()
        except (AttributeError, RuntimeError, OSError, ValueError):
            logger.exception("Could not close test SignalStore")


@dataclass
class _FdMeasurement:
    """Store the first and last raw descriptor counts for a test or file."""

    before: int
    after: int

    @property
    def growth(self) -> int:
        """Return net descriptor growth without triggering garbage collection."""
        return self.after - self.before


@dataclass
class _FdReport:
    """Keep descriptor measurements in the current pytest configuration."""

    available: bool = True
    session_start: int | None = None
    session_end: int | None = None
    tests: list[tuple[str, _FdMeasurement]] = field(default_factory=list)
    files: dict[str, _FdMeasurement] = field(default_factory=dict)


_FD_REPORT_KEY = pytest.StashKey[_FdReport]()


def _count_fds(report: _FdReport) -> int | None:
    """Count raw procfs entries, disabling the report if procfs is unavailable."""
    if not report.available:
        return None
    try:
        fd_directory = Path("/proc/self/fd")
        if fd_directory.is_dir():
            return sum(1 for _ in fd_directory.iterdir())
    except OSError:
        pass
    report.available = False
    return None


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the optional per-test file descriptor report."""
    parser.addoption(
        "--fd-report",
        action="store_true",
        default=False,
        help="Report raw file descriptor growth per test and file.",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    """Initialise report state and count descriptors before collection."""
    if session.config.getoption("--fd-report"):
        report = _FdReport()
        session.config.stash[_FD_REPORT_KEY] = report
        report.session_start = _count_fds(report)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(
    item: pytest.Item, nextitem: pytest.Item | None,
) -> Generator[None, bool | None, bool | None]:
    """Measure setup, call and teardown, including final fixture clean-up."""
    report = item.config.stash.get(_FD_REPORT_KEY, None)
    before = _count_fds(report) if report is not None else None
    try:
        result = yield
    finally:
        if report is not None and before is not None:
            after = _count_fds(report)
            if after is not None:
                report.tests.append(
                    (item.nodeid, _FdMeasurement(before, after))
                )
                filename = str(item.path)
                if filename not in report.files:
                    report.files[filename] = _FdMeasurement(before, after)
                else:
                    # Span the file's first test start to its last test end.
                    report.files[filename].after = after
    return result


def pytest_sessionfinish(
    session: pytest.Session, exitstatus: int,
) -> None:
    """Count session-end descriptors before the terminal report is rendered."""
    report = session.config.stash.get(_FD_REPORT_KEY, None)
    if report is not None:
        report.session_end = _count_fds(report)


def pytest_terminal_summary(
    terminalreporter: "TerminalReporter",
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Display session counts, top test growth and non-zero per-file growth."""
    if not config.getoption("--fd-report"):
        return
    report = config.stash.get(_FD_REPORT_KEY, None)
    if report is None or not report.available:
        terminalreporter.write_line(
            "FD report unavailable on this platform."
        )
        return

    terminalreporter.write_sep("=", "File descriptor report (raw counts)")
    terminalreporter.write_line(
        "Counts include one fd used for the listing itself. Module- or "
        "session-scoped fixture fds are attributed to the first test "
        "that uses them."
    )
    terminalreporter.write_line(
        f"Session start: {report.session_start}; "
        f"session end: {report.session_end}"
    )
    terminalreporter.write_sep("-", "Top 25 tests by net fd growth")
    terminalreporter.write_line("nodeid | before | after | growth")
    for nodeid, measurement in sorted(
        report.tests, key=lambda entry: entry[1].growth, reverse=True,
    )[:25]:
        terminalreporter.write_line(
            f"{nodeid} | {measurement.before} | {measurement.after} | "
            f"{measurement.growth:+d}"
        )

    terminalreporter.write_sep("-", "Per-file net fd growth (non-zero)")
    terminalreporter.write_line("file | before | after | growth")
    for filename, measurement in sorted(
        report.files.items(),
        key=lambda entry: entry[1].growth,
        reverse=True,
    ):
        if measurement.growth:
            terminalreporter.write_line(
                f"{filename} | {measurement.before} | {measurement.after} | "
                f"{measurement.growth:+d}"
            )
