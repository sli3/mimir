"""Test spawned receive-only helpers with injected fakes and no radio hardware."""

from __future__ import annotations

import ast
import builtins
import logging
import multiprocessing
import os
import signal
import sys
import threading
import time
from functools import partial
from multiprocessing import resource_tracker, spawn
from pathlib import Path
from typing import Callable, Iterable, Iterator
from unittest.mock import Mock, patch

import numpy as np
import pytest

from core.device.receiver_process import (
    ReceiverProcess,
    _main_module_not_reimported,
)
from core.legal.compliance_guard import HardwareTransmitError
from tests.core.receiver_process_fakes import (
    FakeReceiver,
    make_receiver,
    partial_reply_helper,
)


def _root_log_settings() -> dict[str, str | None]:
    """Inspect the first root formatter, keeping private format access here."""
    formatter = logging.getLogger().handlers[0].formatter
    assert formatter is not None
    return {"log_format": formatter._fmt, "log_datefmt": formatter.datefmt}


class _LogReportingReceiver(FakeReceiver):
    """Report the spawned helper's logging settings through fake device info."""

    def device_info(self) -> dict:
        """Include root formatter settings alongside the fake receiver identity."""
        return {**super().device_info(), **_root_log_settings()}


def _make_log_reporting_receiver() -> _LogReportingReceiver:
    """Build a spawn-picklable fake that reports child logging configuration."""
    return _LogReportingReceiver()


@pytest.fixture
def restored_signal_mask() -> Iterator[None]:
    """Restore the test thread's original signal mask even after a failure."""
    if not hasattr(signal, "pthread_sigmask"):
        pytest.skip("POSIX signal masks are unavailable")
    original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)


@pytest.fixture
def receiver_builder() -> Iterator[Callable[..., ReceiverProcess]]:
    """Inject picklable fakes with optional call logs and reap every helper."""
    receivers = []

    def build(
        mode: str = "healthy",
        *,
        flag_path: Path | None = None,
        entered_path: Path | None = None,
        calls_path: Path | None = None,
        **kwargs: float,
    ) -> ReceiverProcess:
        """Create a fake proxy with short timeouts and optional call logs."""
        options = dict(
            open_timeout=5.0,
            read_timeout=0.3,
            tune_timeout=0.3,
            reconnect_interval=0.0,
            close_join_timeout=0.1,
        )
        options.update(kwargs)
        receiver = ReceiverProcess(
            "hackrf",
            receiver_factory=partial(
                make_receiver, mode, flag_path=flag_path, entered_path=entered_path,
                calls_path=calls_path,
            ),
            **options,
        )
        receivers.append(receiver)
        return receiver

    try:
        yield build
    finally:
        for receiver in receivers:
            receiver.close()


def _wait_for_read(path: Path) -> None:
    """Wait for a helper to enter a read before making concurrency assertions."""
    deadline = time.monotonic() + 3.0
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), "helper never entered read"


def _read_in_thread(receiver: ReceiverProcess, errors: list) -> None:
    """Collect the expected loss error rather than leaking a thread exception."""
    try:
        receiver.read_samples(16)
    except RuntimeError as exc:
        errors.append(exc)


def test_default_construction_never_builds_or_imports_soapy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A default factory is safe to construct and is deliberately never opened."""
    monkeypatch.delitem(sys.modules, "SoapySDR", raising=False)
    original_import = builtins.__import__

    def checked_import(name: str, *args: object, **kwargs: object) -> object:
        """Reject even an attempted SoapySDR import during proxy construction."""
        assert name != "SoapySDR"
        return original_import(name, *args, **kwargs)

    with patch("core.device.factory.build_device") as build_device, patch(
        "core.device.receiver_process.multiprocessing.get_context"
    ) as get_context, patch("builtins.__import__", side_effect=checked_import):
        receiver = ReceiverProcess("hackrf")
        try:
            assert not receiver.is_open
            assert receiver._process is None
            build_device.assert_not_called()
            get_context.assert_not_called()
        finally:
            receiver.close()


def test_open_and_read_round_trip(receiver_builder: Callable) -> None:
    """A real spawned fake sends cached identity and complex64 samples over IPC."""
    receiver = receiver_builder()
    receiver.open()
    assert receiver.is_open
    assert receiver._process.daemon
    assert receiver._process._start_method == "spawn"
    assert receiver.device_info()["driver"] == "fake"
    assert not receiver.device_info()["soapy_loaded"]
    samples = receiver.read_samples(131072)
    assert samples.shape == (131072,)
    assert samples.dtype == np.complex64
    assert np.all(samples == 98)


def test_helper_logging_matches_console_format() -> None:
    """Compare child log formats with scan.py and the expected literals.

    Inspect logging in the child so the parent's logging and signal state
    remain under pytest's control.
    """
    scan_path = Path(__file__).resolve().parents[2] / "scan.py"
    scan_tree = ast.parse(scan_path.read_text(encoding="utf-8"))
    console_formats = {}
    for node in ast.walk(scan_tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "basicConfig"
        ):
            console_formats = {
                keyword.arg: ast.literal_eval(keyword.value)
                for keyword in node.keywords
                if keyword.arg in {"format", "datefmt"}
            }
            break
    assert "format" in console_formats
    assert "datefmt" in console_formats
    receiver = ReceiverProcess(
        "hackrf", receiver_factory=_make_log_reporting_receiver, open_timeout=5.0,
    )
    try:
        receiver.open()
        info = receiver.device_info()
        assert info["log_format"] == console_formats["format"]
        assert info["log_datefmt"] == console_formats["datefmt"]
        assert info["log_format"] == (
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        assert info["log_datefmt"] == "%H:%M:%S"
    finally:
        receiver.close()


def test_helper_start_preparation_skips_main_script(
    receiver_builder: Callable,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Real CPython preparation data names __main__ instead of its script path.

    Stub start and its matching join so fixture cleanup can close the proxy
    without trying to join a child that was never launched.
    """
    main_module = sys.modules["__main__"]
    monkeypatch.setattr(main_module, "__spec__", None)
    monkeypatch.setattr(
        main_module, "__file__", str(tmp_path / "main.py"), raising=False,
    )
    receiver = receiver_builder()
    preparation_data: dict = {}

    def inspect_start(process: multiprocessing.Process) -> None:
        """Stub the unstarted process's join and inspect real spawn preparation."""
        process.join = Mock(return_value=None)
        preparation_data.update(spawn.get_preparation_data(process.name))

    def reply(timeout: float) -> dict:
        """Supply readiness without starting a child or accessing hardware."""
        return {"driver": "fake"}

    monkeypatch.setattr(
        multiprocessing.context.SpawnProcess, "start", inspect_start,
    )
    monkeypatch.setattr(receiver, "_reply", reply)
    receiver.open()
    assert preparation_data["init_main_from_name"] == "__main__"
    assert "init_main_from_path" not in preparation_data
    assert main_module.__spec__ is None


@pytest.mark.parametrize("with_sigmask", [False, True])
@pytest.mark.parametrize("spec_state", ["object", "none", "missing"])
@pytest.mark.parametrize("outcome", ["success", "error", "interrupt"])
def test_helper_start_restores_main_spec(
    receiver_builder: Callable,
    monkeypatch: pytest.MonkeyPatch,
    with_sigmask: bool,
    spec_state: str,
    outcome: str,
) -> None:
    """Both start branches restore the exact spec before masks and readiness.

    Simulate signal masks and start outcomes without launching a child. Check
    restoration for an object, None and an absent attribute, including failure
    and KeyboardInterrupt, keeping the original spec during tracker setup.
    Stub each simulated process's join so successful opens also clean up safely.
    """
    main_module = sys.modules["__main__"]
    original_spec = object() if spec_state == "object" else None
    if spec_state == "missing":
        monkeypatch.delattr(main_module, "__spec__", raising=False)
    else:
        monkeypatch.setattr(main_module, "__spec__", original_spec)
    events: list[str] = []
    failure = (
        ValueError("start failed") if outcome == "error"
        else KeyboardInterrupt() if outcome == "interrupt" else None
    )

    def assert_original_spec() -> None:
        """Check attribute absence or exact identity, including an original None."""
        if spec_state == "missing":
            assert not hasattr(main_module, "__spec__")
        else:
            assert main_module.__spec__ is original_spec

    def ensure_running() -> None:
        """Require the original spec during tracker initialisation."""
        assert_original_spec()
        events.append("tracker")

    def record_sigmask(how: int, mask: Iterable[int]) -> set[signal.Signals]:
        """Require spec restoration before the caller's mask is restored."""
        assert_original_spec()
        if how == signal.SIG_SETMASK:
            events.append("restore_mask")
        return set()

    def start(process: multiprocessing.Process) -> None:
        """Stub join, check the temporary main name and simulate the outcome."""
        process.join = Mock(return_value=None)
        events.append("start")
        assert main_module.__spec__.name == "__main__"
        if failure is not None:
            raise failure

    def reply(timeout: float) -> dict:
        """Require the original spec when readiness is requested after start."""
        assert_original_spec()
        events.append("reply")
        return {"driver": "fake"}

    if with_sigmask:
        monkeypatch.setattr(
            signal, "pthread_sigmask", record_sigmask, raising=False,
        )
    else:
        monkeypatch.delattr(signal, "pthread_sigmask", raising=False)
    monkeypatch.setattr(resource_tracker, "ensure_running", ensure_running)
    monkeypatch.setattr(multiprocessing.context.SpawnProcess, "start", start)
    receiver = receiver_builder()
    monkeypatch.setattr(receiver, "_reply", reply)
    if outcome == "success":
        receiver.open()
        assert receiver.is_open
    elif outcome == "error":
        with pytest.raises(RuntimeError, match="start failed") as error:
            receiver.open()
        assert error.value.__cause__ is failure
    else:
        with pytest.raises(KeyboardInterrupt) as interrupt:
            receiver.open()
        assert interrupt.value is failure
    assert_original_spec()
    expected = ["tracker", "start", "restore_mask"] if with_sigmask else ["start"]
    if outcome == "success":
        expected.append("reply")
    assert events == expected


def test_main_spec_context_without_main_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing main module stays absent throughout the spawn context."""
    monkeypatch.delitem(sys.modules, "__main__")
    with _main_module_not_reimported():
        assert "__main__" not in sys.modules
    assert "__main__" not in sys.modules


def test_real_spawn_does_not_run_main_script(
    receiver_builder: Callable,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A real spawned fake reaches readiness without a main-script side effect."""
    marker = tmp_path / "main-imported"
    script = tmp_path / "main.py"
    script.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('main script ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    main_module = sys.modules["__main__"]
    monkeypatch.setattr(main_module, "__spec__", None)
    monkeypatch.setattr(main_module, "__file__", str(script), raising=False)
    receiver = receiver_builder()
    receiver.open()
    assert receiver.device_info()["driver"] == "fake"
    assert main_module.__spec__ is None
    assert not marker.exists()


def test_frequency_forwarded(receiver_builder: Callable) -> None:
    """Live tuning reaches the helper and the requested frequency stays cached."""
    receiver = receiver_builder()
    receiver.open()
    receiver.set_center_frequency(915_000_000.0)
    assert receiver.center_freq_hz == 915_000_000.0
    assert np.all(receiver.read_samples(16) == 915)


def test_read_error_discards_helper(receiver_builder: Callable) -> None:
    """Reported read errors remove the helper while logical open stays true."""
    receiver = receiver_builder("read_error")
    receiver.open()
    process = receiver._process
    with pytest.raises(RuntimeError, match="fake read failed"):
        receiver.read_samples(16)
    assert not process.is_alive()
    assert receiver._process is None
    assert receiver.is_open


@pytest.mark.parametrize("mode,exitcode", [("exit", 17), ("segfault", -signal.SIGSEGV)])
def test_hard_crash_isolated(
    receiver_builder: Callable, mode: str, exitcode: int,
) -> None:
    """Native-style helper death raises in the surviving parent and is reaped."""
    receiver = receiver_builder(mode)
    receiver.open()
    process = receiver._process
    with pytest.raises(RuntimeError):
        receiver.read_samples(16)
    assert not process.is_alive()
    assert process.exitcode == exitcode
    assert receiver._process is None


def test_hung_read_times_out_and_kills_helper(receiver_builder: Callable) -> None:
    """A bounded read timeout reaps even a helper that ignores termination."""
    receiver = receiver_builder("hang_ignore_term")
    receiver.open()
    process = receiver._process
    with pytest.raises(RuntimeError, match="timed out"):
        receiver.read_samples(16)
    assert not process.is_alive()
    assert process.exitcode == -signal.SIGKILL


@pytest.mark.parametrize("mode", ["partial_header", "partial_payload"])
def test_partial_reply_times_out_and_reconnects(
    receiver_builder: Callable, tmp_path: Path, mode: str,
) -> None:
    """A partial Pipe frame must time out, kill its helper and permit reconnection."""
    entered = tmp_path / "partial-reply"
    receiver = receiver_builder(mode, entered_path=entered, read_timeout=0.5)
    errors = []
    reader = threading.Thread(target=_read_in_thread, args=(receiver, errors))
    try:
        with patch(
            "core.device.receiver_process._receiver_helper", partial_reply_helper,
        ):
            receiver.open()
            process = receiver._process
            reader.start()
            _wait_for_read(entered)
            # Without a full-message deadline this read stays blocked until close.
            reader.join(1.5)
            assert not reader.is_alive()
            assert len(errors) == 1
            assert "timed out" in str(errors[0])
            assert not process.is_alive()
            assert process.exitcode == -signal.SIGKILL
            assert receiver._process is None
            assert receiver._connection is None
            assert receiver.is_open

        # Restore the normal helper, still using an injected hardware-free factory.
        receiver._receiver_factory = make_receiver
        assert np.all(receiver.read_samples(16) == 98)
        assert receiver._process.pid != process.pid
    finally:
        receiver.close()
        if reader.ident is not None:
            reader.join(2.0)


def test_replug_restores_last_frequency(
    receiver_builder: Callable, tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    """A new helper sees replug state and applies tuning before opening."""
    flag = tmp_path / "state"
    flag.write_text("healthy", encoding="utf-8")
    receiver = receiver_builder(flag_path=flag)
    receiver.open()
    old_process = receiver._process
    flag.write_text("unplugged", encoding="utf-8")
    with pytest.raises(RuntimeError):
        receiver.read_samples(16)
    receiver.set_center_frequency(1_090_000_000.0)
    # A failed reconnect must also leave no helper behind.
    with pytest.raises(RuntimeError, match="unplugged"):
        receiver.read_samples(16)
    assert receiver._process is None
    flag.write_text("healthy", encoding="utf-8")
    with caplog.at_level("INFO", logger="core.device.receiver_process"):
        assert np.all(receiver.read_samples(16) == 1090)
    assert receiver._process.pid != old_process.pid
    assert receiver.device_info()["frequency"] == 1_090_000_000.0
    assert "SDR reconnected (hackrf)" in caplog.text


def test_same_frequency_reconnect_retunes_and_discards(
    receiver_builder: Callable,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reconnect without changing frequency, then tune live and discard a read."""
    flag = tmp_path / "state"
    calls = tmp_path / "calls"
    flag.write_text("healthy", encoding="utf-8")
    receiver = receiver_builder(flag_path=flag, calls_path=calls)
    receiver.open()
    old_process = receiver._process
    flag.write_text("unplugged", encoding="utf-8")
    with pytest.raises(RuntimeError, match="fake read failed"):
        receiver.read_samples(16)
    assert receiver._process is None
    previous_calls = len(calls.read_text(encoding="utf-8").splitlines())

    flag.write_text("healthy", encoding="utf-8")
    with caplog.at_level("INFO", logger="core.device.receiver_process"):
        samples = receiver.read_samples(16)
    assert samples.shape == (16,)
    assert samples.dtype == np.complex64
    assert np.all(samples == 98)
    assert receiver._process.pid != old_process.pid
    # Store the frequency before opening, then tune live and read twice.
    assert calls.read_text(encoding="utf-8").splitlines()[previous_calls:] == [
        "tune open=False 98000000.0",
        "tune open=True 98000000.0",
        "read open=True",
        "read open=True",
    ]
    assert "SDR reconnected (hackrf)" in caplog.text


def test_reconnect_retune_failure_discards_helper(
    receiver_builder: Callable,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed live retune raises and reaps the helper without a success log."""
    flag = tmp_path / "state"
    flag.write_text("healthy", encoding="utf-8")
    receiver = receiver_builder("tune_error", flag_path=flag)
    receiver.open()
    flag.write_text("unplugged", encoding="utf-8")
    with pytest.raises(RuntimeError, match="fake read failed"):
        receiver.read_samples(16)
    assert receiver._process is None

    flag.write_text("healthy", encoding="utf-8")
    with caplog.at_level("INFO", logger="core.device.receiver_process"):
        with pytest.raises(RuntimeError, match="fake tune failed"):
            receiver.read_samples(16)
    assert receiver._process is None
    assert receiver.is_open
    assert "SDR reconnected" not in caplog.text


def test_reconnect_rate_limit(receiver_builder: Callable) -> None:
    """Reads during the reconnect interval cannot start another helper."""
    receiver = receiver_builder("read_error", reconnect_interval=30.0)
    receiver.open()
    with pytest.raises(RuntimeError):
        receiver.read_samples(16)
    with patch.object(receiver, "_start_helper") as start:
        for _ in range(3):
            with pytest.raises(RuntimeError, match="waiting to reconnect"):
                receiver.read_samples(16)
        start.assert_not_called()


def test_open_failure_reaps_helper(receiver_builder: Callable) -> None:
    """Failed readiness raises RuntimeError and reaps every child it started."""
    existing = {process.pid for process in multiprocessing.active_children()}
    receiver = receiver_builder("open_error")
    with pytest.raises(RuntimeError, match="unplugged"):
        receiver.open()
    assert not receiver.is_open
    assert receiver._process is None
    assert receiver._connection is None
    assert {process.pid for process in multiprocessing.active_children()} <= existing


def test_open_timeout_reaps_helper(receiver_builder: Callable) -> None:
    """A readiness timeout kills the helper and removes it from active children."""
    existing = {process.pid for process in multiprocessing.active_children()}
    receiver = receiver_builder("open_hang", open_timeout=0.5)
    with pytest.raises(RuntimeError, match="timed out"):
        receiver.open()
    assert not receiver.is_open
    assert receiver._process is None
    assert receiver._connection is None
    assert {process.pid for process in multiprocessing.active_children()} <= existing


def test_ready_helper_ignores_sigint(receiver_builder: Callable) -> None:
    """Terminal interrupts cannot kill a helper after it reports readiness."""
    receiver = receiver_builder()
    receiver.open()
    os.kill(receiver._process.pid, signal.SIGINT)
    assert np.all(receiver.read_samples(16) == 98)


@pytest.mark.usefixtures("restored_signal_mask")
def test_starting_helper_ignores_sigint(
    receiver_builder: Callable,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """SIGINT immediately after spawn leaves samples and stderr intact."""
    real_start = multiprocessing.context.SpawnProcess.start

    def start_and_interrupt(process: multiprocessing.Process) -> None:
        """Signal the real child as soon as its start call returns."""
        real_start(process)
        os.kill(process.pid, signal.SIGINT)

    monkeypatch.setattr(
        multiprocessing.context.SpawnProcess, "start", start_and_interrupt,
    )
    receiver = receiver_builder()
    receiver.open()
    assert receiver.is_open
    assert np.all(receiver.read_samples(16) == 98)
    receiver.close()
    assert "KeyboardInterrupt" not in capfd.readouterr().err


@pytest.mark.usefixtures("restored_signal_mask")
@pytest.mark.parametrize("mode", ["healthy", "open_error"])
@pytest.mark.parametrize("initially_blocked", [False, True])
@pytest.mark.parametrize("in_thread", [False, True])
def test_helper_start_restores_caller_mask(
    receiver_builder: Callable,
    mode: str,
    initially_blocked: bool,
    in_thread: bool,
) -> None:
    """Success and failed readiness preserve main and worker thread masks."""
    receiver = receiver_builder(mode)
    errors: list[BaseException] = []

    def open_and_check_mask() -> None:
        """Check either initial SIGINT state and restore this thread on exit."""
        original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
        try:
            how = signal.SIG_BLOCK if initially_blocked else signal.SIG_UNBLOCK
            signal.pthread_sigmask(how, {signal.SIGINT})
            before = signal.pthread_sigmask(signal.SIG_BLOCK, [])
            if mode == "open_error":
                with pytest.raises(RuntimeError, match="unplugged"):
                    receiver.open()
            else:
                receiver.open()
                assert np.all(receiver.read_samples(16) == 98)
            assert signal.pthread_sigmask(signal.SIG_BLOCK, []) == before
        except BaseException as exc:
            # Forward assertion failures and interrupts to the pytest thread.
            errors.append(exc)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)

    if in_thread:
        thread = threading.Thread(target=open_and_check_mask)
        thread.start()
        thread.join(10.0)
        assert not thread.is_alive(), "helper start thread did not finish"
    else:
        open_and_check_mask()
    if errors:
        raise errors[0]


@pytest.mark.usefixtures("restored_signal_mask")
@pytest.mark.parametrize("mode", ["healthy", "open_error"])
def test_helper_start_restores_mask_after_tracker_unblocks_sigint(
    receiver_builder: Callable,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    """Preserve blocked SIGINT across Python 3.11-style tracker initialisation."""
    from multiprocessing import resource_tracker

    real_ensure_running = resource_tracker.ensure_running

    def ensure_running_and_unblock() -> None:
        """Ensure the real tracker, then mimic 3.11's first-start unblock."""
        real_ensure_running()
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGINT})

    monkeypatch.setattr(
        resource_tracker, "ensure_running", ensure_running_and_unblock,
    )
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
    entry_mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    receiver = receiver_builder(mode)
    if mode == "open_error":
        with pytest.raises(RuntimeError, match="unplugged"):
            receiver.open()
    else:
        receiver.open()
    assert signal.pthread_sigmask(signal.SIG_BLOCK, []) == entry_mask


@pytest.mark.usefixtures("restored_signal_mask")
def test_resource_tracker_starts_before_sigint_block(
    receiver_builder: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tracker is ensured before the first SIGINT block, even on first use."""
    from multiprocessing import resource_tracker

    real_ensure_running = resource_tracker.ensure_running
    real_sigmask = signal.pthread_sigmask
    events: list[str] = []
    blocked = False

    def ensure_running() -> None:
        """Record tracker calls only until the first SIGINT block."""
        if not blocked:
            events.append("ensure_running")
        real_ensure_running()

    def record_sigmask(how: int, mask: Iterable[int]) -> set[signal.Signals]:
        """Record the first SIGINT block without changing mask semantics."""
        nonlocal blocked
        if not blocked and how == signal.SIG_BLOCK and signal.SIGINT in mask:
            events.append("block")
            blocked = True
        return real_sigmask(how, mask)

    monkeypatch.setattr(resource_tracker, "ensure_running", ensure_running)
    monkeypatch.setattr(signal, "pthread_sigmask", record_sigmask)
    receiver = receiver_builder()
    receiver.open()
    assert "ensure_running" in events
    assert "block" in events
    assert events.index("ensure_running") < events.index("block")


def test_reported_tune_error_never_raises(receiver_builder: Callable) -> None:
    """A tuning failure discards the helper and is surfaced by the next read."""
    receiver = receiver_builder("tune_error", reconnect_interval=30.0)
    receiver.open()
    process = receiver._process
    receiver.set_center_frequency(915_000_000.0)
    assert not process.is_alive()
    assert receiver._process is None
    assert receiver.center_freq_hz == 915_000_000.0
    with pytest.raises(RuntimeError, match="waiting to reconnect"):
        receiver.read_samples(16)


def test_tune_never_raises_for_dead_helper(receiver_builder: Callable) -> None:
    """A dead helper is discarded by tuning without escaping the scanner path."""
    receiver = receiver_builder(reconnect_interval=30.0)
    receiver.open()
    process = receiver._process
    process.terminate()
    process.join(1.0)
    receiver.set_center_frequency(915_000_000.0)
    assert receiver.center_freq_hz == 915_000_000.0
    assert receiver._process is None
    with pytest.raises(RuntimeError, match="waiting to reconnect"):
        receiver.read_samples(16)


def test_status_does_not_wait_for_read_lock(
    receiver_builder: Callable, tmp_path: Path,
) -> None:
    """Dashboard properties remain available while a read holds the pipe lock."""
    entered = tmp_path / "entered"
    receiver = receiver_builder("hang", entered_path=entered, read_timeout=3.0)
    receiver.open()
    errors = []
    reader = threading.Thread(target=_read_in_thread, args=(receiver, errors))
    observed = []
    completed = threading.Event()

    def inspect_status() -> None:
        """Read every dashboard-facing property while the helper is blocked."""
        observed.extend([
            receiver.is_open, receiver.center_freq_hz, receiver.sample_rate_hz,
        ])
        completed.set()

    status = threading.Thread(target=inspect_status)
    reader.start()
    try:
        _wait_for_read(entered)
        status.start()
        assert completed.wait(0.3)
        assert observed == [True, 98_000_000.0, 2_000_000.0]
    finally:
        receiver.close()
        reader.join(4.0)
        if status.ident is not None:
            status.join(4.0)
    assert not reader.is_alive()


def test_close_kills_stuck_helper_and_prevents_reconnect(
    receiver_builder: Callable, tmp_path: Path,
) -> None:
    """Shutdown is bounded, idempotent and cannot reconnect after a blocked read."""
    entered = tmp_path / "entered"
    receiver = receiver_builder(
        "hang_ignore_term", entered_path=entered, read_timeout=3.0,
    )
    receiver.open()
    process = receiver._process
    errors = []
    reader = threading.Thread(target=_read_in_thread, args=(receiver, errors))
    reader.start()
    try:
        _wait_for_read(entered)
        started = time.monotonic()
        receiver.close()
        receiver.close()
        elapsed = time.monotonic() - started
    finally:
        receiver.close()
        reader.join(4.0)
    assert not reader.is_alive()
    assert elapsed < 1.5
    assert errors
    assert not process.is_alive()
    assert not receiver.is_open
    with patch.object(receiver, "_start_helper") as start:
        with pytest.raises(RuntimeError, match="not open"):
            receiver.read_samples(16)
        start.assert_not_called()


def test_closed_configuration_applied_and_live_changes_rejected(
    receiver_builder: Callable,
) -> None:
    """Closed settings reach the helper; live rate and gain changes fail clearly."""
    receiver = receiver_builder()
    receiver.set_sample_rate(1_000_000.0)
    receiver.set_gain(12.0)
    receiver.open()
    assert receiver.sample_rate_hz == 1_000_000.0
    assert receiver.device_info()["rate"] == 1_000_000.0
    assert receiver.device_info()["gain"] == 12.0
    with pytest.raises(RuntimeError, match="only while"):
        receiver.set_sample_rate(2_000_000.0)
    with pytest.raises(RuntimeError, match="only while"):
        receiver.set_gain(20.0)


def test_guarded_operations(receiver_builder: Callable) -> None:
    """Explicit and inherited output stubs block before starting any helper."""
    receiver = receiver_builder()
    with pytest.raises(HardwareTransmitError):
        receiver.transmit()
    with pytest.raises(HardwareTransmitError):
        receiver.writeStream()
    with pytest.raises(HardwareTransmitError):
        receiver.setupTxStream()
    with pytest.raises(HardwareTransmitError):
        receiver.activateTxStream()
    with pytest.raises(HardwareTransmitError):
        receiver.write_samples()
    with pytest.raises(HardwareTransmitError):
        receiver.set_tx_gain()
    with pytest.raises(HardwareTransmitError):
        receiver.set_tx_frequency()
    assert receiver._process is None


def test_unknown_public_attribute(receiver_builder: Callable) -> None:
    """Unknown public lookups use normal Python fallbacks without a helper."""
    receiver = receiver_builder()
    sentinel = object()

    with pytest.raises(AttributeError):
        receiver.no_such_attr
    assert getattr(receiver, "no_such_attr", sentinel) is sentinel
    assert not hasattr(receiver, "no_such_attr")
    assert receiver._process is None
