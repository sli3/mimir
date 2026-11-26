"""Check console layout, block progress and logging around active spinners."""

import io
import logging
import os
import threading
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from tools import _console


class TTYStream(io.StringIO):
    """Provide an in-memory stdout which reports itself as a terminal."""

    def isatty(self) -> bool:
        """Report a terminal without requiring a real console."""
        return True


@pytest.mark.parametrize("no_colour", [None, "", "1"])
def test_colour_enabled(
    monkeypatch: pytest.MonkeyPatch, no_colour: str | None
) -> None:
    """Resolve stdout and NO_COLOR afresh, including an empty opt-out value."""
    if no_colour is None:
        monkeypatch.delenv("NO_COLOR", raising=False)
    else:
        monkeypatch.setenv("NO_COLOR", no_colour)
    terminal = TTYStream()
    monkeypatch.setattr(_console.sys, "stdout", terminal)
    assert _console.colour_enabled() is (no_colour != "1")
    assert _console.colour_enabled(terminal) is (no_colour != "1")
    assert not _console.colour_enabled(io.StringIO())
    monkeypatch.setattr(_console.sys, "stdout", io.StringIO())
    assert not _console.colour_enabled()


@pytest.mark.parametrize(
    "helper, code", [("ok", "92"), ("warn", "93"), ("fail", "91"),
                     ("step", "96"), ("dim", "2")],
)
def test_colour_helpers(
    monkeypatch: pytest.MonkeyPatch, helper: str, code: str
) -> None:
    """Each helper colours only the current terminal when colour is allowed."""
    colour = getattr(_console, helper)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(_console.sys, "stdout", TTYStream())
    assert colour("text") == f"\033[{code}mtext\033[0m"
    monkeypatch.setenv("NO_COLOR", "yes")
    assert colour("text") == "text"
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setattr(_console.sys, "stdout", io.StringIO())
    assert colour("text") == "text"


def test_visible_len() -> None:
    """Count text and status symbols without counting ANSI style codes."""
    assert _console.visible_len("\033[1;32m✓ good\033[0m") == 6
    assert _console.visible_len("") == 0


def test_box_padding(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use a fixed 72-column rounded box with two spaces of body padding."""
    monkeypatch.setattr(
        _console.shutil, "get_terminal_size",
        lambda **_: os.terminal_size((80, 24)),
    )
    _console.box("T", ["abc", "x"])
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "╭─ T " + "─" * 66 + "╮",
        "│  abc" + " " * 65 + "│",
        "│  x" + " " * 67 + "│",
        "╰" + "─" * 70 + "╯",
    ]
    assert all(len(line) == 72 for line in lines)


@pytest.mark.parametrize("width", [None, 24, 90])
def test_box_wrapping(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    width: int | None,
) -> None:
    """Wrap within a fixed width, capped at the reported terminal columns."""
    monkeypatch.setattr(
        _console.shutil, "get_terminal_size",
        lambda **_: os.terminal_size((60, 24)),
    )
    text = "calibration status " * 10 + "x" * 90
    _console.box("Results", [text, "", "last\nline"], width=width)
    lines = capsys.readouterr().out.splitlines()
    limit = min(width or 72, 60)
    assert len(lines[0]) == limit
    assert all(len(line) == limit for line in lines)
    body = "".join(line[3:-3].replace(" ", "") for line in lines[1:-1])
    assert body == (text + "lastline").replace(" ", "")


def test_box_coloured_wrapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preserve styles across wrapping within fixed rounded box borders."""
    stream = TTYStream()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(_console.sys, "stdout", stream)
    monkeypatch.setattr(
        _console.shutil, "get_terminal_size",
        lambda **_: os.terminal_size((80, 24)),
    )
    _console.box(
        "Status", [_console.ok("good " * 20)], style=_console.warn, width=25
    )
    lines = stream.getvalue().splitlines()
    assert all(_console.visible_len(line) == 25 for line in lines)
    assert "\033[93m" in lines[0]
    assert all("\033[92m" in line for line in lines[1:-1])


def test_next_step(capsys: pytest.CaptureFixture[str]) -> None:
    """Print the arrow and Next prefix without ANSI on non-terminal stdout."""
    _console.next_step("copy the values.")
    assert capsys.readouterr().out == "→ Next: copy the values.\n"


def test_table_alignment() -> None:
    """Align headers and rows by visible widths even with coloured cells."""
    rows = [["\033[92mADS_B\033[0m", "5"], ["ISM_LoRa", "2"]]
    lines = _console.table(rows, headers=["Band", "Captures"])
    assert [_console._ANSI.sub("", line) for line in lines] == [
        "Band       Captures", "ADS_B      5", "ISM_LoRa   2",
    ]
    assert "\033[92m" in lines[1]
    assert _console.table([]) == []
    assert _console.table([["one"], ["two", "three"]]) == [
        "one", "two   three",
    ]


class ProgressTTY(TTYStream):
    """Notify the test when the spinner first writes a braille frame."""

    def __init__(self) -> None:
        """Create a stream and a synchronisation event without sleeping."""
        super().__init__()
        self.rendered = threading.Event()

    def write(self, text: str) -> int:
        """Record output and signal when an animation frame has been drawn."""
        result = super().write(text)
        if any(frame in text for frame in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            self.rendered.set()
        return result


@pytest.mark.parametrize("error", [None, RuntimeError, KeyboardInterrupt])
def test_spinner_tty_cleanup(
    monkeypatch: pytest.MonkeyPatch, error: type[BaseException] | None,
) -> None:
    """Register progress, render blocks and clean up on every exit path."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        _console.shutil, "get_terminal_size",
        lambda **_: os.terminal_size((80, 24)),
    )
    stream = ProgressTTY()
    spinner = _console.Spinner("capturing 1/2", total=2, stream=stream)
    expectation = pytest.raises(error) if error else nullcontext()
    with expectation:
        with spinner:
            assert _console._current_spinner is spinner
            assert stream.rendered.wait(timeout=2)
            assert spinner._thread is not None
            assert spinner._thread.is_alive()
            assert spinner._thread.daemon
            assert "capturing 1/2" in stream.getvalue()
            spinner.pause()
            before = stream.getvalue()
            spinner.write_above("✗ capture failed")
            assert stream.getvalue() == before + "\r\033[2K✗ capture failed\n"
            spinner.update("waiting 5s", 1, 2)
            stream.rendered.clear()
            spinner.resume()
            assert stream.rendered.wait(timeout=2)
            assert "waiting 5s" in stream.getvalue()
            assert "█" * 15 + "░" * 15 + "   50%" in stream.getvalue()
            if error:
                raise error("capture interrupted")
    assert spinner._thread is not None
    assert not spinner._thread.is_alive()
    assert stream.getvalue().endswith("\r\033[2K")
    assert _console._current_spinner is None


@pytest.mark.parametrize("no_colour_tty", [False, True])
def test_spinner_inert(
    monkeypatch: pytest.MonkeyPatch, no_colour_tty: bool,
) -> None:
    """Register inert progress without a thread or output, then unregister."""
    stream = TTYStream() if no_colour_tty else io.StringIO()
    if no_colour_tty:
        monkeypatch.setenv("NO_COLOR", "1")
    else:
        monkeypatch.delenv("NO_COLOR", raising=False)
    thread = MagicMock()
    monkeypatch.setattr(_console.threading, "Thread", thread)
    with _console.Spinner(stream=stream) as spinner:
        assert _console._current_spinner is spinner
        spinner.update("capturing", 1, 2)
        spinner.pause()
        spinner.resume()
    thread.assert_not_called()
    assert spinner._thread is None
    assert stream.getvalue() == ""
    assert _console._current_spinner is None
    spinner.write_above("plain message")
    assert stream.getvalue() == "plain message\n"


def test_spinner_update_resets_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each update restarts elapsed time for the current capture or wait."""
    monotonic = MagicMock(side_effect=[10.0, 25.0])
    monkeypatch.setattr(_console.time, "monotonic", monotonic)
    spinner = _console.Spinner(stream=io.StringIO())
    assert spinner._started == 10.0
    spinner.update("capturing 2/5", 1, 5)
    assert spinner._started == 25.0
    assert (spinner._label, spinner._done, spinner._total) == (
        "capturing 2/5", 1, 5,
    )


def test_spinner_log_handler_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear active progress before printing a complete formatted log line."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    stream = ProgressTTY()
    handler = _console.SpinnerLogHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    record = logging.LogRecord(
        "core.capture", logging.ERROR, "", 0,
        "failed: %s", ("unplugged",), None,
    )
    with _console.Spinner("capturing", stream=stream) as spinner:
        assert stream.rendered.wait(timeout=2)
        spinner.pause()
        before = stream.getvalue()
        handler.emit(record)
        assert stream.getvalue() == (
            before + "\r\033[2KERROR: failed: unplugged\n"
        )
    assert _console._current_spinner is None


@pytest.mark.parametrize("inert_spinner", [False, True])
def test_spinner_log_handler_stderr(
    capsys: pytest.CaptureFixture[str], inert_spinner: bool,
) -> None:
    """Write plainly to stderr when no active terminal spinner is current."""
    handler = _console.SpinnerLogHandler()
    context = (
        _console.Spinner(stream=io.StringIO()) if inert_spinner else nullcontext()
    )
    with context:
        handler.emit(logging.LogRecord(
            "core.capture", logging.WARNING, "", 0, "device missing", (), None,
        ))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "device missing\n"


@pytest.mark.parametrize("failure", ["format", "write"])
def test_spinner_log_handler_error(
    monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    """Delegate formatting and stream failures to logging's error handler."""
    handler = _console.SpinnerLogHandler()
    handle_error = MagicMock()
    monkeypatch.setattr(handler, "handleError", handle_error)
    if failure == "format":
        monkeypatch.setattr(
            handler, "format", MagicMock(side_effect=ValueError)
        )
    else:
        stream = MagicMock()
        stream.write.side_effect = OSError("stream closed")
        monkeypatch.setattr(_console.sys, "stderr", stream)
    record = logging.LogRecord(
        "core", logging.ERROR, "", 0, "failed", (), None
    )
    handler.emit(record)
    handle_error.assert_called_once_with(record)
