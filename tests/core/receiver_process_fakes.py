"""Spawn-picklable, receive-only doubles; no fake opens a real SDR."""

from __future__ import annotations

import os
import resource
import signal
import struct
import sys
import time
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Callable

import numpy as np

from core.device.device_base import DeviceBase


class FakeReceiver(DeviceBase):
    """Provide deterministic samples, file-controlled outages and native failures."""

    def __init__(
        self,
        mode: str = "healthy",
        flag_path: Path | None = None,
        entered_path: Path | None = None,
    ) -> None:
        """Store paths that remain observable across independent spawned helpers."""
        self.mode = mode
        self.flag_path = flag_path
        self.entered_path = entered_path
        self.frequency = 98_000_000.0
        self.rate = 2_000_000.0
        self.gain = 0.0
        self.opened = False

    def open(self) -> None:
        """Simulate readiness failure or a hang, including a file-controlled outage."""
        if self.mode == "open_hang":
            time.sleep(60.0)
        if self.mode == "open_error" or (
            self.flag_path is not None
            and self.flag_path.read_text(encoding="utf-8") == "unplugged"
        ):
            raise RuntimeError("fake receiver unplugged")
        self.opened = True

    def device_info(self) -> dict:
        """Expose applied configuration and prove no SoapySDR was imported."""
        return {
            "driver": "fake",
            "frequency": self.frequency,
            "rate": self.rate,
            "gain": self.gain,
            "soapy_loaded": "SoapySDR" in sys.modules,
        }

    def set_center_frequency(self, freq_hz: float) -> None:
        """Record the requested frequency or simulate a tuning failure."""
        self.frequency = freq_hz
        if self.mode == "tune_error" and self.opened:
            raise RuntimeError("fake tune failed")

    def set_sample_rate(self, rate_hz: float) -> None:
        """Record the closed-receiver sample rate."""
        self.rate = rate_hz

    def set_gain(self, gain_db: float) -> None:
        """Record the closed-receiver combined gain."""
        self.gain = gain_db

    def read_samples(self, num_samples: int) -> np.ndarray:
        """Return frequency-coded IQ or simulate loss, exit, SIGSEGV or a hang."""
        mode = self.mode
        if self.flag_path is not None:
            mode = self.flag_path.read_text(encoding="utf-8")
        if mode == "hang_ignore_term":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if self.entered_path is not None:
            self.entered_path.touch()
        if mode in ("read_error", "unplugged"):
            raise RuntimeError("fake read failed")
        if mode == "exit":
            os._exit(17)
        if mode == "segfault":
            # Exercise native-crash isolation without writing a core dump.
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            os.kill(os.getpid(), signal.SIGSEGV)
        if mode in ("hang", "hang_ignore_term"):
            time.sleep(60.0)
        return np.full(num_samples, self.frequency / 1e6, dtype=np.complex64)

    def close(self) -> None:
        """Record closure without touching hardware."""
        self.opened = False


def make_receiver(
    mode: str = "healthy",
    flag_path: Path | None = None,
    entered_path: Path | None = None,
) -> FakeReceiver:
    """Build an unopened fake through an importable module-level factory."""
    return FakeReceiver(mode, flag_path, entered_path)


def partial_reply_helper(
    connection: Connection,
    driver: str,
    gain_kwargs: dict,
    receiver_factory: Callable[[], DeviceBase] | None,
    frequency: float,
    sample_rate: float | None,
    gain: float | None,
) -> None:
    """Report readiness, then stall inside a Pipe frame using only an injected fake.

    Partial headers and partial payloads both make poll report readability
    while recv still needs more bytes. Ignore termination to exercise the
    watchdog's kill fallback rather than ending the test double voluntarily.
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    assert receiver_factory is not None
    device = receiver_factory()
    try:
        device.set_center_frequency(frequency)
        device.open()
        connection.send((True, device.device_info()))
        if not connection.poll(5.0):
            raise RuntimeError("Test parent did not request samples")
        command, _ = connection.recv()
        assert command == "read"
        # Match multiprocessing Connection's four-byte network-order length.
        header = struct.pack("!i", 1_048_576)
        frame = (
            header[:2] if device.mode == "partial_header" else header + b"\x80\x04"
        )
        os.write(connection.fileno(), frame)
        if device.entered_path is not None:
            device.entered_path.touch()
        time.sleep(60.0)
    finally:
        device.close()
        connection.close()
