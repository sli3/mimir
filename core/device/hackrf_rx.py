"""
core/device/hackrf_rx.py
Mimir RF Scanner — HackRF One Receive-Only Wrapper

LEGAL NOTICE
────────────
Jurisdiction : Australia — South Australia (Adelaide)
Authority    : ACMA (Australian Communications and Media Authority)
Law          : Radiocommunications Act 1992 (Cth)
Licence held : NONE

This file provides RECEIVE-ONLY access to the HackRF One.
Any call to a transmit function raises HardwareTransmitError immediately.
No transmit path exists in this codebase.

WHAT THIS FILE DOES
───────────────────
This is the main way Mimir talks to the HackRF hardware. It wraps
the SoapySDR Python library, which in turn talks to libhackrf.

The chain is:
  Your Python code
      ↓
  HackRFReceiver (this file)
      ↓
  SoapySDR Python bindings  (python3-SoapySDR package)
      ↓
  libhackrf  (hackrf package)
      ↓
  HackRF One hardware via USB

WHY SOAPYSDR?
─────────────
SoapySDR is a "hardware abstraction layer". It means this code doesn't
need to know the exact USB commands the HackRF uses. Instead, it speaks
a generic SDR language and SoapySDR handles the translation.

This also means if you ever use a different SDR (e.g. an RTL-SDR dongle),
only the driver= argument changes — the rest of your pipeline code stays
the same.

RECEIVE DIRECTION — WHY IT IS NOT HARDCODED
───────────────────────────────────────────
SoapySDR represents the receive direction with SOAPY_SDR_RX. Direction
arguments select receive or transmit on this TX-capable library and
hardware, so using the wrong value would violate our receive-only rule.

open() checks the installed SOAPY_SDR_RX against the expected receive
value before enumerating or opening any device. A mismatch raises
RuntimeError. After the check passes, open() captures SOAPY_SDR_RX in
self._rx, which every direction-taking hardware call uses. The expected
value is only a consistency check, never the hardware argument.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from core.device.device_base import DeviceBase
from core.legal.compliance_guard import HardwareTransmitError, transmit_guard

logger = logging.getLogger(__name__)

# SoapySDR/Errors.h: timeout means no data; overflow means samples were dropped.
SOAPY_SDR_TIMEOUT = -1
SOAPY_SDR_OVERFLOW = -4


class HackRFReceiver(DeviceBase):
    """
    Receive-only wrapper for the HackRF One SDR.

    Usage (context manager — recommended):
        with HackRFReceiver() as sdr:
            sdr.set_center_frequency(98_000_000)   # 98 MHz FM
            sdr.set_sample_rate(2_000_000)          # 2 MHz bandwidth
            sdr.set_gain(20)                        # 20 dB gain
            samples = sdr.read_samples(1024 * 256)  # capture IQ data

    Usage (manual):
        sdr = HackRFReceiver()
        sdr.open()
        # ... use it ...
        sdr.close()

    Hardware requirements:
        - HackRF One connected via USB
        - hackrf package installed (dnf install hackrf)
        - python3-SoapySDR installed (dnf install python3-SoapySDR)
        - Antenna attached to the SMA port before powering on
    """

    # Expected receive value, checked against SoapySDR at open().
    # Hardware calls use self._rx, captured from the validated SOAPY_SDR_RX.
    _SOAPY_RX_DIRECTION: int = 1
    _SOAPY_TX_DIRECTION: int = 0  # documented here, never passed to hardware

    # Default safe receive settings
    # Calibrated for telescopic whip SMA antenna (~1 GHz optimised).
    # Poor coupling at FM wavelengths requires gain to compensate.
    # lna=24 / vga=26 confirmed safe on live hardware (no ADC saturation).
    DEFAULT_CENTER_FREQ_HZ: float = 98_000_000    # 98 MHz — FM broadcast
    DEFAULT_SAMPLE_RATE_HZ: float = 2_000_000     # 2 MHz bandwidth
    DEFAULT_LNA_GAIN_DB: float = 24               # RF front-end gain (0–40 dB)
    DEFAULT_VGA_GAIN_DB: float = 26               # Baseband gain (0–62 dB)
    DEFAULT_AMP_ENABLE: bool = False              # RF amp — leave off by default

    def __init__(
        self,
        center_freq_hz: float = DEFAULT_CENTER_FREQ_HZ,
        sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
        lna_gain_db: float = DEFAULT_LNA_GAIN_DB,
        vga_gain_db: float = DEFAULT_VGA_GAIN_DB,
        amp_enable: bool = DEFAULT_AMP_ENABLE,
        serial: Optional[str] = None,
        retune_settle_sec: float = 0.25,
    ) -> None:
        """
        Initialise the HackRF receiver configuration.

        This does NOT open the hardware yet. Call open() or use the
        object as a context manager (with statement). The receive direction
        stays unset until open() validates the installed SoapySDR constant.

        Args:
            center_freq_hz : Frequency to tune to in Hz. Default: 98 MHz.
            sample_rate_hz : Samples per second. Default: 2 MHz.
            lna_gain_db    : LNA (low-noise amplifier) gain 0–40 dB.
                             The LNA is the first amplifier the signal
                             hits — it boosts weak signals before they
                             are processed. Start low, increase if needed.
            vga_gain_db    : VGA (variable gain amplifier) gain 0–62 dB.
                             Applied after the LNA. Controls overall
                             receive level.
            amp_enable     : Whether to enable the built-in RF amplifier.
                             Adds ~11 dB but also adds noise. Keep False
                             unless signals are very weak.
            serial         : Optional HackRF serial number. If None,
                             uses the first detected HackRF.
            retune_settle_sec : Seconds to wait for the PLL (the circuit
                             that locks the tuner onto a frequency) to
                             settle after a retune, while the stream is
                             stopped. Default 0.25 s. The wait must happen
                             with the stream inactive — if the stream is
                             live during the settle, the hardware's ring
                             buffer captures the settling transient and
                             the first read after the retune returns a
                             transient-shaped fingerprint, which shows up
                             as a wrong low-confidence classification and
                             a white stripe on the waterfall.
        """
        self._center_freq_hz = center_freq_hz
        self._sample_rate_hz = sample_rate_hz
        self._lna_gain_db = lna_gain_db
        self._vga_gain_db = vga_gain_db
        self._amp_enable = amp_enable
        self._serial = serial
        self._retune_settle_sec = retune_settle_sec

        self._device = None    # SoapySDR device object — set in open()
        self._stream = None    # RX stream — set in open()
        self._rx: int | None = None
        self._is_open = False

    # ── Lifecycle ──────────────────────────────────────────────────────

    def open(self) -> None:
        """
        Open the HackRF hardware and configure the receiver.

        Validate SOAPY_SDR_RX against the expected receive value before
        device enumeration or construction, then capture it in self._rx
        for every direction-taking hardware call.

        Set self._is_open as soon as the device handle exists. On any
        failure or interrupt after that, the caller's close() releases
        whatever device and stream resources were created.

        Settle-before-activate ordering:
        ────────────────────────────────
        After setFrequency configures the tuner, we wait for the PLL (the
        circuit that locks the tuner onto the frequency) to settle BEFORE
        activating the stream. If the stream were activated first, the
        hardware's ring buffer would capture the settling transient, and
        the first read would return transient-shaped samples — which the
        pipeline would fingerprint as a bogus signal. The same ordering is
        used in set_center_frequency() for mid-run retunes.

        Raises:
            RuntimeError: If SoapySDR is unavailable, its receive constant
                differs from the expected value, no HackRF is found, or
                hardware fails to open.
        """
        try:
            import SoapySDR
            from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
        except ImportError as e:
            raise RuntimeError(
                "SoapySDR Python bindings not found. "
                "Install with: sudo dnf install python3-SoapySDR"
            ) from e

        if SOAPY_SDR_RX != self._SOAPY_RX_DIRECTION:
            raise RuntimeError(
                "The installed SoapySDR receive constant "
                f"({SOAPY_SDR_RX}) does not match the expected receive "
                f"value ({self._SOAPY_RX_DIRECTION}); "
                "the device will not be opened."
            )
        self._rx = SOAPY_SDR_RX

        # Build the device arguments string
        # driver=hackrf tells SoapySDR to use the HackRF plugin
        args = "driver=hackrf"
        if self._serial:
            args += f",serial={self._serial}"

        logger.info("Opening HackRF One (RX only)...")

        # Enumerate available devices before opening
        results = SoapySDR.Device.enumerate(args)
        if not results:
            raise RuntimeError(
                "No HackRF device found. "
                "Check USB connection and run 'hackrf_info' to verify hardware."
            )

        # Open the device
        self._device = SoapySDR.Device(args)
        # Mark open as soon as the handle exists so the caller's close()
        # tears it down if any configuration or stream setup below raises.
        self._is_open = True

        # ── Configure receive channel 0 ────────────────────────────────
        # Channel 0 is the only receive channel on the HackRF One.
        # Use the receive constant captured from SoapySDR after validation.

        self._device.setSampleRate(self._rx, 0, self._sample_rate_hz)
        self._device.setFrequency(self._rx, 0, self._center_freq_hz)
        self._device.setGain(self._rx, 0, "LNA", self._lna_gain_db)
        self._device.setGain(self._rx, 0, "VGA", self._vga_gain_db)
        self._device.setGain(self._rx, 0, "AMP",
                             11.0 if self._amp_enable else 0.0)

        # Set up the receive stream
        # SOAPY_SDR_CF32 = complex float32 = what we want (IQ samples as
        # complex numbers, each component a 32-bit float)
        self._stream = self._device.setupStream(self._rx, SOAPY_SDR_CF32)
        # Settle BEFORE activating the stream, so the PLL settling transient
        # is never captured into the ring buffer (see open() docstring).
        time.sleep(self._retune_settle_sec)
        self._device.activateStream(self._stream)

        logger.info(
            f"HackRF One opened: "
            f"freq={self._center_freq_hz/1e6:.3f} MHz, "
            f"rate={self._sample_rate_hz/1e6:.1f} MHz, "
            f"LNA={self._lna_gain_db} dB, VGA={self._vga_gain_db} dB"
        )

    def close(self) -> None:
        """Release resources safely after a complete or partially failed open.

        Reset _stream, _device, _rx and _is_open even if stream cleanup
        fails. Log closure only when a stream or device handle existed.
        """
        had_resources = self._stream is not None or self._device is not None
        try:
            if self._stream is not None and self._device is not None:
                try:
                    self._device.deactivateStream(self._stream)
                except (RuntimeError, OSError):
                    logger.exception(
                        "Error while deactivating HackRF One stream"
                    )
                # A stream that was set up but never activated can reject
                # deactivation; still attempt to release the stream itself.
                try:
                    self._device.closeStream(self._stream)
                except (RuntimeError, OSError):
                    logger.exception("Error while closing HackRF One stream")
        finally:
            self._stream = None
            self._device = None
            self._rx = None
            self._is_open = False
        if had_resources:
            logger.info("HackRF One closed.")

    def __enter__(self) -> "HackRFReceiver":
        self.open()
        return self

    # ── Receive operations ─────────────────────────────────────────────

    def device_info(self) -> dict:
        """Return device identification information."""
        if not self._is_open:
            return {"status": "not open"}
        info = self._device.getHardwareInfo()
        return dict(info)

    def set_center_frequency(self, freq_hz: float) -> None:
        """
        Tune the receiver to a new centre frequency.

        Use the validated receive direction captured by open().

        Settle-before-activate ordering:
        ────────────────────────────────
        The stream is deactivated BEFORE the retune and reactivated only
        AFTER a settle wait. The tuner contains a PLL (phase-locked loop),
        the circuit that locks onto the new frequency; it takes a short
        time to stabilise. If the stream were live during that window, the
        hardware's ring buffer would capture the settling transient, and
        the first read after the retune would return transient-shaped
        samples — which the pipeline would fingerprint as a bogus signal.
        Settling while the stream is stopped keeps the transient out of
        the buffer entirely.

        Args:
            freq_hz: Frequency in Hz. Examples:
                     98_000_000  = 98 MHz (FM broadcast)
                     145_175_000 = 145.175 MHz (APRS — Australian)
                     1_090_000_000 = 1090 MHz (ADS-B aircraft)
        """
        self._center_freq_hz = freq_hz
        if self._is_open:
            if self._stream is not None:
                self._device.deactivateStream(self._stream)
            self._device.setFrequency(self._rx, 0, freq_hz)
            if self._stream is not None:
                time.sleep(self._retune_settle_sec)
                self._device.activateStream(self._stream)
            logger.debug(f"Centre frequency set to {freq_hz/1e6:.3f} MHz")

    def set_sample_rate(self, rate_hz: float) -> None:
        """
        Set the sample rate (how many IQ samples per second).

        Use the validated receive direction captured by open().

        Args:
            rate_hz: Samples per second. HackRF supports up to 20 MHz.
                     Common values: 2_000_000, 8_000_000, 10_000_000.
        """
        self._sample_rate_hz = rate_hz
        if self._is_open:
            self._device.setSampleRate(self._rx, 0, rate_hz)
            logger.debug(f"Sample rate set to {rate_hz/1e6:.1f} MHz")

    def set_gain(self, gain_db: float) -> None:
        """
        Set combined VGA gain. For fine control use set_lna_gain / set_vga_gain.

        Use the validated receive direction captured by open().

        Args:
            gain_db: Gain in dB, applied to the VGA stage (0–62 dB).
        """
        self._vga_gain_db = gain_db
        if self._is_open:
            self._device.setGain(self._rx, 0, "VGA", gain_db)
            logger.debug(f"VGA gain set to {gain_db} dB")

    def set_lna_gain(self, gain_db: float) -> None:
        """
        Set LNA (Low Noise Amplifier) gain separately.

        Use the validated receive direction captured by open().

        The LNA is the first amplifier in the receive chain. It boosts
        the incoming signal before any other processing, so it has the
        biggest effect on weak-signal reception.

        Args:
            gain_db: LNA gain in dB (0–40 dB in 8 dB steps on HackRF).
        """
        self._lna_gain_db = gain_db
        if self._is_open:
            self._device.setGain(self._rx, 0, "LNA", gain_db)
            logger.debug(f"LNA gain set to {gain_db} dB")

    def read_samples(self, num_samples: int) -> np.ndarray:
        """
        Capture IQ samples from the HackRF receiver.

        What are IQ samples?
        ────────────────────
        IQ stands for In-phase / Quadrature. Each sample is a complex
        number that represents the radio signal at one instant in time:
          - The real part (I) captures one component of the signal
          - The imaginary part (Q) captures a 90-degree-shifted component
        Together they let the software determine both the amplitude (how
        strong the signal is) and the phase (where in its cycle the
        signal is) at each moment.

        The samples come back as a numpy array of complex64 values.
        complex64 means each sample uses 64 bits: 32 bits for I, 32 for Q.

        Args:
            num_samples: Number of IQ samples to capture.
                         1024 samples at 2 MHz sample rate = 0.000512 seconds
                         of radio data.

        Returns:
            numpy.ndarray of shape (num_samples,) and dtype complex64.

        Raises:
            RuntimeError: If the device is not open, an overflow repeats, or
                another negative SoapySDR code (including timeout -1) occurs.

        Overflow retry behaviour:
            SoapySDR overflow (-4) means samples were dropped. Discard any
            partial capture and read once more from zero without resetting
            the stream. Log the overflow and centre frequency. A second
            overflow or any other negative code fails immediately; live
            scanning then replaces the receiver helper with a fresh process.
        """
        if not self._is_open:
            raise RuntimeError("Device is not open. Call open() first.")

        output = np.zeros(num_samples, dtype=np.complex64)
        total = 0
        retry_count = 0
        while total < num_samples:
            remaining = num_samples - total
            chunk = output[total:total + remaining]
            sr = self._device.readStream(
                self._stream, [chunk], remaining, timeoutUs=int(1e7)
            )
            if sr.ret < 0:
                if sr.ret == SOAPY_SDR_OVERFLOW and retry_count < 1:
                    logger.warning(
                        "readStream overflow at %.3f MHz; retrying capture from zero",
                        self._center_freq_hz / 1e6,
                    )
                    retry_count += 1
                    total = 0
                    output = np.zeros(num_samples, dtype=np.complex64)
                    continue
                raise RuntimeError(
                    f"HackRF read failed (SoapySDR error code {sr.ret}). "
                    f"Try reducing sample rate or checking USB connection."
                )
            total += sr.ret
            if sr.ret == 0:
                break

        return output[:total]

    # ── Transmit — all permanently blocked ────────────────────────────
    # These override DeviceBase and add explicit HackRF-specific naming.

    def transmit(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.transmit")

    def write_samples(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.write_samples")

    def writeStream(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.writeStream")

    def set_tx_gain(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.set_tx_gain")

    def set_tx_frequency(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.set_tx_frequency")

    def setupTxStream(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.setupTxStream")

    def activateTxStream(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("HackRFReceiver.activateTxStream")

    # ── Properties (read-only view of current config) ──────────────────

    @property
    def center_freq_hz(self) -> float:
        return self._center_freq_hz

    @property
    def sample_rate_hz(self) -> float:
        return self._sample_rate_hz

    @property
    def is_open(self) -> bool:
        return self._is_open
