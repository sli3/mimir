"""
core/device/device_base.py
Mimir RF Scanner — Abstract Device Interface

This defines the contract that every SDR device wrapper must follow.
The HackRF wrapper (hackrf_rx.py) implements this interface.

Why an abstract base class?
───────────────────────────
Right now we only support the HackRF One. In the future we might add
support for an RTL-SDR dongle, a BladeRF, or other hardware. By
defining a common interface here, the rest of the pipeline code can
work with any SDR device without knowing which specific hardware is
attached.

Think of it like a power socket: the interface (the socket shape) is
standardised, so any device with the right plug can connect. The base
class is the socket shape.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class DeviceBase(ABC):
    """
    Abstract base class for all SDR device wrappers in Mimir.

    Every method that has anything to do with transmitting is declared
    here as a blocked operation. Subclasses MUST call transmit_guard()
    at the top of any TX-adjacent method implementation.

    Only receive-side methods are declared as abstract (i.e. required
    to be implemented). TX methods are declared here so that if a
    subclass accidentally inherits a TX method, it is already blocked.
    """

    # ── Identity ──────────────────────────────────────────────────────

    @abstractmethod
    def device_info(self) -> dict:
        """
        Return a dictionary of device information.

        Should include at minimum: driver, serial, hardware revision,
        firmware version.
        """
        ...

    # ── Receive — subclasses must implement these ──────────────────────

    @abstractmethod
    def set_center_frequency(self, freq_hz: float) -> None:
        """
        Tune the receiver to a centre frequency in Hz.

        Example: set_center_frequency(98_000_000) tunes to 98 MHz (FM).
        """
        ...

    @abstractmethod
    def set_sample_rate(self, rate_hz: float) -> None:
        """
        Set how many samples per second the device captures.

        Higher rates = wider slice of spectrum visible at once,
        but more data to process. Typical values: 2_000_000 (2 MHz),
        10_000_000 (10 MHz), 20_000_000 (20 MHz).
        """
        ...

    @abstractmethod
    def set_gain(self, gain_db: float) -> None:
        """
        Set receiver gain in decibels.

        Higher gain = more sensitive, but can overload on strong signals.
        Start low (around 20 dB) and increase if signals are too weak.
        """
        ...

    @abstractmethod
    def read_samples(self, num_samples: int):
        """
        Capture and return IQ samples from the receiver.

        Returns a numpy array of complex64 values. Each sample is one
        complex number: a real part (I = In-phase) and an imaginary part
        (Q = Quadrature). Together they represent the amplitude and phase
        of the received radio signal at that instant.

        Args:
            num_samples: How many IQ samples to capture.

        Returns:
            numpy.ndarray of dtype complex64, shape (num_samples,)
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """
        Release the device and free all resources.

        Always call this when finished, or use the device as a
        context manager (with statement) which calls it automatically.
        """
        ...

    # ── Transmit — permanently blocked ────────────────────────────────
    # These methods exist so that any accidental TX call is intercepted
    # at this level, even if a subclass forgets to block them.

    def transmit(self, *args, **kwargs) -> None:
        """Blocked — transmission is illegal without an ACMA licence."""
        from core.legal.compliance_guard import transmit_guard
        transmit_guard("transmit")

    def write_samples(self, *args, **kwargs) -> None:
        """Blocked — transmission is illegal without an ACMA licence."""
        from core.legal.compliance_guard import transmit_guard
        transmit_guard("write_samples")

    def set_tx_gain(self, *args, **kwargs) -> None:
        """Blocked — transmission is illegal without an ACMA licence."""
        from core.legal.compliance_guard import transmit_guard
        transmit_guard("set_tx_gain")

    def set_tx_frequency(self, *args, **kwargs) -> None:
        """Blocked — transmission is illegal without an ACMA licence."""
        from core.legal.compliance_guard import transmit_guard
        transmit_guard("set_tx_frequency")

    # ── Context manager support ────────────────────────────────────────

    def __enter__(self) -> DeviceBase:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
