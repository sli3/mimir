"""Terminal-aware boxes, block progress and console logging for tools."""

import itertools
import logging
import os
import re
import shutil
import sys
import textwrap
import threading
import time
from collections.abc import Callable, Iterable
from types import TracebackType
from typing import TextIO


OK = "✓"
WARNING = "⚠"
FAILURE = "✗"
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_RESET = "\033[0m"
_current_spinner: "Spinner | None" = None
_current_spinner_lock = threading.Lock()


def colour_enabled(stream: TextIO | None = None) -> bool:
    """Check the current stream's TTY status and non-empty NO_COLOR setting."""
    stream = sys.stdout if stream is None else stream
    return (
        bool(getattr(stream, "isatty", lambda: False)())
        and not os.environ.get("NO_COLOR")
    )


def _colour(text: str, code: str) -> str:
    """Wrap text in a terminal style only when stdout currently allows it."""
    return f"\033[{code}m{text}{_RESET}" if colour_enabled() else text


def ok(text: str) -> str:
    """Colour successful status text green on a terminal."""
    return _colour(text, "92")


def warn(text: str) -> str:
    """Colour warning text yellow on a terminal."""
    return _colour(text, "93")


def fail(text: str) -> str:
    """Colour failure text red on a terminal."""
    return _colour(text, "91")


def step(text: str) -> str:
    """Colour progress text cyan on a terminal."""
    return _colour(text, "96")


def dim(text: str) -> str:
    """Dim secondary text on a terminal."""
    return _colour(text, "2")


def visible_len(text: str) -> int:
    """Return the character count after stripping ANSI escape sequences."""
    return len(_ANSI.sub("", text))


def _wrap(text: str, width: int) -> list[str]:
    """Wrap visible text with textwrap while preserving its ANSI styles."""
    plain = _ANSI.sub("", text)
    chunks = textwrap.wrap(
        plain, width=width, expand_tabs=False, replace_whitespace=False
    )
    if not chunks:
        return [""]
    # Record original character positions and the style active before each one.
    positions: list[int] = []
    styles: list[str] = []
    active = ""
    index = 0
    while index < len(text):
        escape = _ANSI.match(text, index)
        if escape:
            code = escape.group()
            active = "" if code in ("\033[0m", "\033[m") else active + code
            index = escape.end()
        else:
            positions.append(index)
            styles.append(active)
            index += 1
    wrapped = []
    offset = 0
    for chunk in chunks:
        start = plain.index(chunk, offset)
        end = start + len(chunk)
        rendered = (
            styles[start] + text[positions[start]:positions[end - 1] + 1]
        )
        if styles[end - 1]:
            rendered += _RESET
        wrapped.append(rendered)
        offset = end
    return wrapped


def box(
    title: str,
    lines: Iterable[str],
    style: Callable[[str], str] | None = None,
    width: int | None = None,
) -> None:
    """Print a rounded, fixed-width box, defaulting to 72 total columns.

    ``width`` is the total column limit, including borders and two spaces of
    padding on each side. Cap it to the terminal width; ANSI styles do not
    contribute to the limit. Seven columns is the minimum supported width.
    """
    body = [part for line in lines for part in line.split("\n")]
    columns = max(7, min(
        width if width is not None else 72,
        shutil.get_terminal_size(fallback=(80, 24)).columns,
    ))
    title = textwrap.shorten(
        _ANSI.sub("", title), width=columns - 6, placeholder="…"
    )
    content_width = columns - 6
    border_style = style if style is not None else str
    top = f"╭─ {title} " + "─" * (columns - len(title) - 5) + "╮"
    print(border_style(top))
    for line in body:
        for part in _wrap(line, content_width):
            padding = " " * (content_width - visible_len(part))
            print(f"{border_style('│')}  {part}{padding}  {border_style('│')}")
    print(border_style("╰" + "─" * (columns - 2) + "╯"))


def table(
    rows: Iterable[Iterable[str]], headers: Iterable[str] | None = None,
) -> list[str]:
    """Align table lines by visible cell widths, ignoring ANSI styles."""
    cells = [list(row) for row in rows]
    if headers is not None:
        cells.insert(0, list(headers))
    count = max((len(row) for row in cells), default=0)
    widths = [
        max((visible_len(row[index]) for row in cells if index < len(row)),
            default=0)
        for index in range(count)
    ]
    lines = []
    for row in cells:
        padded = []
        for index in range(count):
            cell = row[index] if index < len(row) else ""
            padded.append(cell + " " * (widths[index] - visible_len(cell)))
        lines.append("   ".join(padded).rstrip())
    return lines


class Spinner:
    """Animate a 30-cell block bar and register progress for console logging.

    Animation is limited to colour-enabled TTYs. The current-spinner lock
    protects registration; the separate write lock protects terminal output.
    Nothing holding the write lock may log, including the renderer thread.
    """

    def __init__(
        self, label: str = "", done: int = 0, total: int = 1,
        stream: TextIO | None = None,
    ) -> None:
        """Prepare progress state without starting a background thread."""
        self.stream = sys.stdout if stream is None else stream
        self.active = colour_enabled(self.stream)
        self._label = label
        self._done = done
        self._total = total
        self._started = time.monotonic()
        self._frames = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._paused = False
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "Spinner":
        """Register progress and start a daemon only on an active TTY."""
        global _current_spinner
        with _current_spinner_lock:
            _current_spinner = self
        if self.active:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def _clear(self) -> None:
        """Clear the current terminal line while the caller holds the lock."""
        self.stream.write("\r\033[2K")
        self.stream.flush()

    def _run(self) -> None:
        """Render blocks, percentage and elapsed time on one terminal line."""
        while not self._stop.is_set():
            with self._lock:
                if not self._paused:
                    fraction = min(
                        1.0, max(0.0, self._done / max(1, self._total))
                    )
                    filled = int(30 * fraction)
                    bar = "█" * filled + "░" * (30 - filled)
                    percentage = f"{fraction:.0%}"
                    elapsed = time.monotonic() - self._started
                    line = (
                        f"  {next(self._frames)} {self._label}  "
                        f"{bar}  {percentage:>4}  {elapsed:.1f}s"
                    )
                    # Avoid terminal auto-wrap, including the final column.
                    columns = shutil.get_terminal_size(
                        fallback=(80, 24)
                    ).columns
                    self.stream.write("\r\033[2K" + line[:max(1, columns - 1)])
                    self.stream.flush()
            self._stop.wait(0.1)

    def update(self, label: str, done: int, total: int) -> None:
        """Set the current label and progress, resetting this step's timer."""
        with self._lock:
            self._label, self._done, self._total = label, done, total
            self._started = time.monotonic()

    def write_above(self, text: str) -> None:
        """Print a message without interleaving with the animation."""
        with self._lock:
            if self.active:
                self._clear()
            print(text, file=self.stream, flush=True)

    def pause(self) -> None:
        """Suspend animation and clear its line for prompts or other output."""
        with self._lock:
            self._paused = True
            if self.active:
                self._clear()

    def resume(self) -> None:
        """Allow the renderer to redraw after a pause."""
        with self._lock:
            self._paused = False

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc_value: BaseException | None, traceback: TracebackType | None,
    ) -> bool:
        """Stop, join, clear and unregister progress, preserving exceptions."""
        global _current_spinner
        try:
            self._stop.set()
            if self._thread is not None:
                self._thread.join()
            with self._lock:
                if self.active:
                    self._clear()
        finally:
            with _current_spinner_lock:
                if _current_spinner is self:
                    _current_spinner = None
        return False


class SpinnerLogHandler(logging.Handler):
    """Write console logs above active progress, or plainly to stderr."""

    def emit(self, record: logging.LogRecord) -> None:
        """Format and route a record without holding the registration lock.

        Spinner writes take their own non-reentrant lock. The renderer never
        logs, so the handler cannot be called from inside that write lock.
        Report formatting or stream errors through logging's handleError.
        """
        try:
            message = self.format(record)
            with _current_spinner_lock:
                spinner = _current_spinner
            if spinner is not None and spinner.active:
                spinner.write_above(message)
            else:
                sys.stderr.write(message + "\n")
                sys.stderr.flush()
        except Exception:
            self.handleError(record)


def next_step(text: str) -> None:
    """Print an arrow and the final operator action in the progress colour."""
    print(step(f"→ Next: {text}"))
