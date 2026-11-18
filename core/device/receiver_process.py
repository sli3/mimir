"""Mimir receive-only receiver proxy with a replaceable helper process.

LEGAL NOTICE
Jurisdiction: Australia, South Australia (Adelaide). Authority: ACMA.
Law: Radiocommunications Act 1992 (Cth). Licence held: NONE.
Only receive operations reach the helper. The underlying SoapySDR library is
TX-capable; its use is restricted to the existing RX-only device wrappers.

Unplugging can leave dead native handles, and SoapySDR caches devices within
each process. Replacing a spawned helper gives a fresh cache and isolates
native crashes. Spawn re-imports the parent's __main__, so scanner start-up
can be slow. Ctrl+C before the helper installs SIG_IGN can kill that helper;
the parent treats this as a lost session. A real readStream timeout now costs
a helper restart rather than an in-process retry. Pluto measurements remain
untrustworthy for several minutes after replugging, even when samples resume.
Reply deadlines cover the complete payload. A watchdog stops a helper that
stalls mid-message, unblocking receipt while the caller retains the pipe lock.
"""

from __future__ import annotations

import logging
import multiprocessing
import signal
import threading
import time
from multiprocessing.connection import Connection
from typing import Callable

import numpy as np

from core.device.device_base import DeviceBase
from core.legal.compliance_guard import transmit_guard

logger = logging.getLogger(__name__)


def _receiver_helper(
    connection: Connection,
    driver: str,
    gain_kwargs: dict,
    receiver_factory: Callable[[], DeviceBase] | None,
    frequency: float,
    sample_rate: float | None,
    gain: float | None,
) -> None:
    """Own all native receiver handles and serve a fixed receive-only protocol."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    logging.basicConfig(level=logging.INFO)
    device = None
    try:
        # Library exceptions cross this boundary as text, never native objects.
        try:
            if receiver_factory is None:
                from core.device.factory import build_device

                device = build_device(driver, **gain_kwargs)
            else:
                device = receiver_factory()
            device.set_center_frequency(frequency)
            if sample_rate is not None:
                device.set_sample_rate(sample_rate)
            if gain is not None:
                device.set_gain(gain)
            device.open()
            connection.send((True, device.device_info()))
        except Exception as exc:
            connection.send((False, str(exc)))
            return

        while True:
            command, value = connection.recv()
            try:
                if command == "read":
                    result = device.read_samples(value)
                elif command == "tune":
                    device.set_center_frequency(value)
                    result = None
                elif command == "close":
                    device.close()
                    device = None
                    connection.send((True, None))
                    return
                else:
                    raise ValueError(f"Unknown receiver command: {command!r}")
            except Exception as exc:
                connection.send((False, str(exc)))
                return
            connection.send((True, result))
    except (EOFError, OSError):
        # Parent shutdown also releases the receiver when no close arrived.
        pass
    finally:
        if device is not None:
            try:
                device.close()
            except Exception:
                logger.exception("Receiver helper cleanup failed")
        connection.close()


class ReceiverProcess(DeviceBase):
    """Serialise receiver calls and replace a lost helper on a later read."""

    def __init__(
        self,
        driver: str,
        *,
        lna_gain_db: float = 24.0,
        vga_gain_db: float = 26.0,
        amp_enable: bool = False,
        receiver_factory: Callable[[], DeviceBase] | None = None,
        open_timeout: float = 60.0,
        read_timeout: float = 20.0,
        tune_timeout: float = 10.0,
        reconnect_interval: float = 2.0,
        close_join_timeout: float = 2.0,
    ) -> None:
        """Store configuration without importing SoapySDR or starting a helper.

        Sample rate and combined gain may be set only while closed and are
        applied before each helper opens. All timeouts are seconds. Factories
        supplied by tests must be module-level, spawn-picklable callables.
        """
        self._driver = driver
        self._gain_kwargs = dict(
            lna_gain_db=lna_gain_db,
            vga_gain_db=vga_gain_db,
            amp_enable=amp_enable,
        )
        self._receiver_factory = receiver_factory
        self._open_timeout = open_timeout
        self._read_timeout = read_timeout
        self._tune_timeout = tune_timeout
        self._reconnect_interval = reconnect_interval
        self._close_join_timeout = close_join_timeout
        self._center_freq_hz = (
            1_090_000_000.0 if driver == "plutosdr" else 98_000_000.0
        )
        self._sample_rate_hz = 2_000_000.0
        self._configured_sample_rate: float | None = None
        self._gain_db: float | None = None
        self._lock = threading.Lock()
        self._process = None
        self._connection: Connection | None = None
        self._info: dict = {}
        self._is_open = False
        self._closing = False
        self._next_reconnect = 0.0

    def __getattr__(self, name: str) -> None:
        """Fail closed for unsupported public operations; keep private lookup normal."""
        if name.startswith("_"):
            raise AttributeError(name)
        transmit_guard(name)

    def _stop_helper(self, process: multiprocessing.Process | None) -> None:
        """Reap a helper without touching its pipe, including during a locked read."""
        if process is not None and process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(self._close_join_timeout)
            if process.is_alive():
                process.kill()
                process.join(self._close_join_timeout)

    def _dispose_helper(self) -> None:
        """Reap and discard the current session while the caller owns the pipe lock."""
        process = self._process
        connection = self._connection
        self._process = None
        self._connection = None
        self._stop_helper(process)
        if connection is not None:
            connection.close()

    def _lose_session(self) -> None:
        """Discard dead handles and rate-limit the next fresh process attempt."""
        self._next_reconnect = time.monotonic() + self._reconnect_interval
        self._dispose_helper()

    def _reply(self, timeout: float) -> object:
        """Bound polling and full receipt with one deadline, including partial frames.

        Poll only detects initial bytes. A watchdog stops the captured helper
        at the deadline so a blocked recv observes EOF. It never uses the
        connection, which remains protected by the caller's lock. Join the
        watchdog before returning so it cannot affect a later session.
        """
        connection = self._connection
        process = self._process
        if connection is None or process is None:
            raise RuntimeError("Receiver helper exited")
        deadline = time.monotonic() + timeout
        expired = threading.Event()

        def expire_reply() -> None:
            """Interrupt a partial receive by stopping only this reply's helper."""
            expired.set()
            self._stop_helper(process)

        watchdog = threading.Timer(
            max(0.0, deadline - time.monotonic()), expire_reply,
        )
        watchdog.daemon = True
        watchdog.start()
        try:
            if not connection.poll(max(0.0, deadline - time.monotonic())):
                if not process.is_alive() and not expired.is_set():
                    raise RuntimeError("Receiver helper exited")
                raise RuntimeError("Receiver helper reply timed out")
            try:
                ok, result = connection.recv()
            except (EOFError, OSError) as exc:
                if expired.is_set():
                    raise RuntimeError("Receiver helper reply timed out") from exc
                raise
        finally:
            watchdog.cancel()
            watchdog.join()
        if expired.is_set() or time.monotonic() >= deadline:
            raise RuntimeError("Receiver helper reply timed out")
        if not ok:
            raise RuntimeError(f"Receiver helper failed: {result}")
        return result

    def _start_helper(self) -> None:
        """Spawn under the pipe lock; reap on failure or shutdown during readiness."""
        if self._closing:
            raise RuntimeError("Receiver is closing")
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        self._connection = parent
        process = context.Process(
            target=_receiver_helper,
            args=(child, self._driver, self._gain_kwargs, self._receiver_factory,
                  self._center_freq_hz, self._configured_sample_rate, self._gain_db),
            daemon=True,
        )
        self._process = process
        try:
            process.start()
            child.close()
            if self._closing:
                raise RuntimeError("Receiver is closing")
            self._info = self._reply(self._open_timeout)
            if self._closing:
                raise RuntimeError("Receiver is closing")
        except (Exception, KeyboardInterrupt) as exc:
            self._lose_session()
            if isinstance(exc, KeyboardInterrupt):
                raise
            raise RuntimeError(
                f"Could not open {self._driver} receiver: {exc}"
            ) from exc
        finally:
            child.close()

    def open(self) -> None:
        """Open a fresh helper, leaving no running helper if readiness fails."""
        with self._lock:
            if self._is_open:
                return
            self._closing = False
            self._start_helper()
            self._is_open = True

    def _request(self, command: str, value: object, timeout: float) -> object:
        """Exchange one command under the caller's lock; discard every lost session."""
        try:
            if self._closing or self._connection is None:
                raise RuntimeError("Receiver helper is unavailable")
            if self._process is None or not self._process.is_alive():
                raise RuntimeError("Receiver helper exited")
            self._connection.send((command, value))
            result = self._reply(timeout)
            if self._closing:
                raise RuntimeError("Receiver is closing")
            return result
        except (EOFError, OSError, RuntimeError, ValueError) as exc:
            self._lose_session()
            raise RuntimeError(f"{self._driver} receiver session lost: {exc}") from exc

    def read_samples(self, num_samples: int) -> np.ndarray:
        """Read IQ samples, attempting a rate-limited fresh helper after loss."""
        with self._lock:
            if not self._is_open or self._closing:
                raise RuntimeError("Receiver is not open")
            if self._process is None:
                if time.monotonic() < self._next_reconnect:
                    raise RuntimeError("Receiver is waiting to reconnect")
                self._start_helper()
                logger.info("SDR reconnected (%s)", self._driver)
            return self._request("read", num_samples, self._read_timeout)

    def set_center_frequency(self, freq_hz: float) -> None:
        """Record tuning and forward best effort; a failed tune never escapes."""
        self._center_freq_hz = freq_hz
        with self._lock:
            if self._process is not None and not self._closing:
                try:
                    self._request("tune", freq_hz, self._tune_timeout)
                except RuntimeError:
                    logger.debug("Receiver tuning lost its helper", exc_info=True)

    def set_sample_rate(self, rate_hz: float) -> None:
        """Store the sample rate for future helpers; reject changes while open."""
        with self._lock:
            if self._is_open:
                raise RuntimeError("Set sample rate only while the receiver is closed")
            self._sample_rate_hz = rate_hz
            self._configured_sample_rate = rate_hz

    def set_gain(self, gain_db: float) -> None:
        """Store combined gain for future helpers; reject changes while open."""
        with self._lock:
            if self._is_open:
                raise RuntimeError("Set gain only while the receiver is closed")
            self._gain_db = gain_db

    def device_info(self) -> dict:
        """Return cached helper information, or a closed-receiver status."""
        return dict(self._info) if self._is_open else {
            "driver": self._driver, "status": "not open",
        }

    @property
    def is_open(self) -> bool:
        """Report logical open state without waiting on reads, even during loss."""
        return self._is_open

    @property
    def center_freq_hz(self) -> float:
        """Return the last requested frequency without taking the pipe lock."""
        return self._center_freq_hz

    @property
    def sample_rate_hz(self) -> float:
        """Return the configured sample rate without taking the pipe lock."""
        return self._sample_rate_hz

    def close(self) -> None:
        """Stop reconnection, then close or kill without racing locked pipe access.

        If a read owns the lock, kill its helper without touching the pipe.
        That read observes EOF and disposes of the session under the lock.
        """
        self._closing = True
        self._is_open = False
        acquired = self._lock.acquire(timeout=self._close_join_timeout)
        try:
            if not acquired:
                self._stop_helper(self._process)
                return
            if self._process is not None:
                try:
                    if self._process.is_alive() and self._connection is not None:
                        self._connection.send(("close", None))
                        self._reply(self._close_join_timeout)
                    self._process.join(self._close_join_timeout)
                except (EOFError, OSError, RuntimeError, ValueError):
                    pass
            self._dispose_helper()
        finally:
            self._is_open = False
            if acquired:
                self._lock.release()
