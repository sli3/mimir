"""
core/device/pluto_rx.py
Mimir RF Scanner — ADALM-PLUTO Receive-Only Wrapper

LEGAL NOTICE
────────────
Jurisdiction : Australia — South Australia (Adelaide)
Authority    : ACMA (Australian Communications and Media Authority)
Law          : Radiocommunications Act 1992 (Cth)
Licence held : NONE

This file provides RECEIVE-ONLY access to the ADALM-PLUTO.
Any call to a transmit function raises HardwareTransmitError immediately.
No transmit path exists in this codebase.

WHAT THIS FILE DOES
───────────────────
This is an alternative way Mimir can talk to SDR hardware. It wraps
the SoapySDR Python library, which in turn talks to libiio and the
PlutoSDR driver.

The chain is:
  Your Python code
      ↓
  PlutoReceiver (this file)
      ↓
  SoapySDR Python bindings  (python3-SoapySDR package)
      ↓
  libiio / PlutoSDR driver
      ↓
  ADALM-PLUTO hardware via USB

WHY SOAPYSDR?
──────────────
SoapySDR is a "hardware abstraction layer". It means this code doesn't
need to know the exact USB or network commands the Pluto uses. Instead,
it speaks a generic SDR language and SoapySDR handles the translation.

This also means if you ever use a different SDR, only the driver=
argument changes — the rest of your pipeline code stays the same.

RECEIVE DIRECTION — WHY IT IS NOT HARDCODED
───────────────────────────────────────────
SoapySDR represents the receive direction with the constant
SOAPY_SDR_RX. Its numeric value is an implementation detail of the
installed SoapySDR build — this wrapper must never assume it.

The direction opposite to receive is transmit. If a hardcoded receive
value ever diverged from the installed SoapySDR's real constant, every
subsequent call would be routed to the wrong direction. Given this is
TX-capable hardware under a zero-transmit legal constraint, that is not
an acceptable risk to carry.

Therefore open() captures the real SOAPY_SDR_RX from the imported module
into self._rx, and every direction-taking call uses self._rx. There is
exactly one source of truth and it comes from SoapySDR itself.

MEASURED FINDINGS — ADELAIDE, 2026-07-16/17, SPIRAL DISCONE
──────────────────────────────────────────────────────────
These observations were made on real hardware and do not appear in the
datasheet. They are recorded here so future contributors do not have to
rediscover them.

- Stock tuning range is 325 MHz – 3800 MHz. This EXCLUDES six of
  Mimir's eight bands: FM (98 MHz), Aviation VHF (127 MHz), ACARS
  (129.125 MHz), APRS (145.175 MHz), AIS (162 MHz), and the noise_floor
  reference profile (98 MHz). Pluto can only serve ISM (915 MHz) and
  ADS-B (1090 MHz) within the current band plan.

- GAIN TABLE BOUNDARY AT ~35 dB: the noise floor does NOT rise
  monotonically with gain. At 35 dB the floor drops ~3–4 dB below the
  30 dB value, then resumes rising. Reproduced across two independent
  sweep runs on different days. Suspected AD9363 internal gain-table
  boundary, not confirmed. Gain values are therefore not uniformly
  spaced in effect.

- SPURS ABOVE ~30 dB GAIN: above roughly 30 dB combined gain, a picket
  fence of small spurious spikes appears across the span. These are
  Pluto-generated, not environmental — a HackRF capture at the same
  frequency, same antenna, same moment showed a clean trace. Relevant
  to Mimir: spurs land in the PSD, become part of the embedding, and
  could cluster in ChromaDB as if they were signal.

- DC OFFSET is dramatically lower than HackRF: measured abs(mean(samples))
  of ~0.000002–0.0000003 vs HackRF's ~0.005, i.e. ~1,500x to ~36,000x
  lower. Consistent across every run, both days, all gain settings.
  Architectural (AD9363 DC tracking loop), not conditions-dependent.

- Default gain of 30.0 dB is chosen from the spur observation above, NOT
  from a calibration session. It is provisional. Pluto has no
  calibrated band profiles yet — that is Phase 39.

- USB 2.0 caps sustained throughput around 5 MSPS. Mimir uses 2 MHz,
  well inside that.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from core.device.device_base import DeviceBase
from core.legal.compliance_guard import HardwareTransmitError, transmit_guard

logger = logging.getLogger(__name__)


class PlutoReceiver(DeviceBase):
    """
    Receive-only wrapper for the ADALM-PLUTO SDR.

    Usage (context manager — recommended):
        with PlutoReceiver() as sdr:
            sdr.set_center_frequency(1_090_000_000)  # 1090 MHz ADS-B
            sdr.set_sample_rate(2_000_000)           # 2 MHz bandwidth
            sdr.set_gain(30)                         # 30 dB gain
            samples = sdr.read_samples(1024 * 256)   # capture IQ data

    Usage (manual):
        sdr = PlutoReceiver()
        sdr.open()
        # ... use it ...
        sdr.close()

    Hardware requirements:
        - ADALM-PLUTO connected via USB
        - python3-SoapySDR installed (dnf install python3-SoapySDR)
        - SoapyPlutoSDR plugin installed
        - Antenna attached to the SMA port before powering on

    Important differences from HackRFReceiver:
        - Pluto has a single combined gain stage, not separate LNA/VGA.
        - Pluto requires explicit RF bandwidth configuration.
        - Pluto defaults to AGC; this wrapper forces manual gain mode.
    """

    # Default safe receive settings
    # 1090 MHz is the only AU-legal Mimir band that falls inside Pluto's
    # 325–3800 MHz tuning range.
    DEFAULT_CENTER_FREQ_HZ: float = 1_090_000_000.0   # 1090 MHz — ADS-B
    DEFAULT_SAMPLE_RATE_HZ: float = 2_000_000        # 2 MHz bandwidth
    DEFAULT_GAIN_DB: float = 30.0                   # provisional, see module docstring
    DEFAULT_BANDWIDTH_HZ: float | None = None         # defaults to sample_rate_hz

    # Gain range as specified for this phase. The driver may report a
    # slightly different maximum; the spec value is source of truth.
    MIN_GAIN_DB: float = 0.0
    MAX_GAIN_DB: float = 74.5

    def __init__(
        self,
        center_freq_hz: float = DEFAULT_CENTER_FREQ_HZ,
        sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
        gain_db: float = DEFAULT_GAIN_DB,
        bandwidth_hz: float | None = DEFAULT_BANDWIDTH_HZ,
    ) -> None:
        """
        Initialise the Pluto receiver configuration.

        This does NOT open the hardware yet. Call open() or use the
        object as a context manager (with statement).

        Args:
            center_freq_hz: Frequency to tune to in Hz. Default: 1090 MHz.
            sample_rate_hz: Samples per second. Default: 2 MHz.
            gain_db: Combined receive gain in dB (0–74.5 dB). Default: 30 dB.
            bandwidth_hz: RF filter bandwidth in Hz. If None, defaults to
                sample_rate_hz. Pluto requires this to be set explicitly.

        Raises:
            ValueError: If gain_db is outside the valid range.
        """
        self._center_freq_hz = center_freq_hz
        self._sample_rate_hz = sample_rate_hz
        self._bandwidth_hz = bandwidth_hz

        # Validate gain range up front so an invalid constructor argument
        # fails early, matching set_gain's behaviour.
        if gain_db < self.MIN_GAIN_DB or gain_db > self.MAX_GAIN_DB:
            raise ValueError(
                f"Gain {gain_db} dB out of range. "
                f"Valid range: {self.MIN_GAIN_DB}–{self.MAX_GAIN_DB} dB."
            )
        self._gain_db = gain_db

        self._device = None   # SoapySDR device object — set in open()
        self._stream = None   # RX stream — set in open()
        self._is_open = False
        self._uri: str | None = None   # selected device URI

        # Receive direction constant, captured from SoapySDR in open().
        # Never hardcoded — see the module docstring for why.
        self._rx: int | None = None

    # ── Lifecycle ───────────────────────────────────────────────────────

    def open(self) -> None:
        """
        Open the ADALM-PLUTO hardware and configure the receiver.

        Raises:
            RuntimeError: If no Pluto is found, hardware fails to open,
                or AGC cannot be disabled.
        """
        try:
            import SoapySDR
            from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
        except ImportError as e:
            raise RuntimeError(
                "SoapySDR Python bindings not found. "
                "Install with: sudo dnf install python3-SoapySDR"
            ) from e

        logger.info("Opening ADALM-PLUTO (RX only)...")

        # Enumerate available devices. We use driver=plutosdr so we only
        # see Pluto results, not any other SoapySDR devices on the machine.
        # SoapySDR returns SoapySDRKwargs objects — SWIG wrappers around a
        # C++ map, not dicts. They have no .get() method. Convert once here
        # at the boundary so the .get() calls below operate on real dicts.
        results = [dict(r) for r in SoapySDR.Device.enumerate("driver=plutosdr")]
        if not results:
            raise RuntimeError(
                "No ADALM-PLUTO device found. "
                "Check USB connection and run 'iio_info' to verify hardware."
            )

        # Prefer the USB URI. Pluto also advertises ip:pluto.local paths
        # over the RNDIS network interface, but those are slower and less
        # reliable for sustained IQ streaming. The USB URI changes on every
        # replug, so we must not hardcode it — we scan for any uri=usb:*.
        selected = None
        for result in results:
            uri = result.get("uri", "")
            if isinstance(uri, str) and uri.startswith("usb:"):
                selected = result
                break

        if selected is None:
            selected = results[0]
            logger.warning(
                "No USB ADALM-PLUTO found; falling back to %s",
                selected.get("uri", "unknown"),
            )

        self._uri = selected.get("uri")
        # Pass args as a STRING, not a dict. SoapySDR's SWIG binding does not
        # reliably marshal a Python dict into the Kwargs the plutosdr plugin's
        # find() produced — Device({"driver": "plutosdr", "uri": ...}) raises
        # "make() no match" on real hardware, while the identical values as a
        # string open the device. Verified 2026-07-17: string OK, dict failed,
        # same URI, fresh process, no contention. hackrf_rx.py has always used
        # the string form, which is why it has always worked.
        open_args = f"driver=plutosdr,uri={self._uri}"
        self._device = SoapySDR.Device(open_args)

        # Mark open immediately after the handle is acquired. If any call
        # below raises, close() must still tear the device down rather
        # than no-op and leak it.
        self._is_open = True

        # Capture the real receive direction constant. Every direction-
        # taking call in this class uses self._rx from here on, so there
        # is one source of truth and it is SoapySDR's own value.
        self._rx = SOAPY_SDR_RX

        # ── Configure receive channel 0 ────────────────────────────────
        # Channel 0 is the only receive channel on the ADALM-PLUTO.

        # Force manual gain mode. Pluto defaults to slow_attack AGC, which
        # silently varies gain between captures. That makes every PSD
        # incomparable, embeddings drift, and ChromaDB matching degrade —
        # with no error raised. We disable AGC and verify the read-back.
        self._device.setGainMode(self._rx, 0, False)
        if self._device.getGainMode(self._rx, 0):
            raise RuntimeError(
                "ADALM-PLUTO AGC could not be disabled. "
                "Manual gain mode is required for comparable captures."
            )

        # Set explicit RF bandwidth. Pluto's SoapySDR plugin does not auto-
        # manage this, unlike the HackRF plugin. Default to sample rate.
        bandwidth_hz = (
            self._bandwidth_hz
            if self._bandwidth_hz is not None
            else self._sample_rate_hz
        )
        self._device.setBandwidth(self._rx, 0, bandwidth_hz)

        self._device.setSampleRate(self._rx, 0, self._sample_rate_hz)
        self._device.setFrequency(self._rx, 0, self._center_freq_hz)
        self._device.setGain(self._rx, 0, self._gain_db)

        # Set up the receive stream
        # SOAPY_SDR_CF32 = complex float32 = IQ samples as complex numbers.
        self._stream = self._device.setupStream(self._rx, SOAPY_SDR_CF32)
        self._device.activateStream(self._stream)

        logger.info(
            "ADALM-PLUTO opened: "
            f"freq={self._center_freq_hz / 1e6:.3f} MHz, "
            f"rate={self._sample_rate_hz / 1e6:.1f} MHz, "
            f"bandwidth={bandwidth_hz / 1e6:.1f} MHz, "
            f"gain={self._gain_db} dB"
        )

    def close(self) -> None:
        """
        Release the ADALM-PLUTO hardware and free all resources.

        Safe to call after a partially failed open(): the device handle is
        torn down whenever it exists, regardless of whether configuration
        completed.
        """
        had_resources = self._stream is not None or self._device is not None
        try:
            if self._stream is not None and self._device is not None:
                self._device.deactivateStream(self._stream)
                self._device.closeStream(self._stream)
        except (RuntimeError, OSError):
            logger.exception("Error while closing ADALM-PLUTO stream")
        finally:
            self._stream = None
            self._device = None
            self._uri = None
            self._rx = None
            self._is_open = False
        if had_resources:
            logger.info("ADALM-PLUTO closed.")

    def __enter__(self) -> "PlutoReceiver":
        self.open()
        return self

    # ── Receive operations ─────────────────────────────────────────────

    def device_info(self) -> dict:
        """Return device identification information."""
        if not self._is_open:
            return {"status": "not open"}
        return {
            "driver": self._device.getDriverKey(),
            "hardware": self._device.getHardwareKey(),
            "uri": self._uri,
        }

    def set_center_frequency(self, freq_hz: float) -> None:
        """
        Tune the receiver to a new centre frequency.

        Args:
            freq_hz: Frequency in Hz. Examples:
                     915_000_000   = 915 MHz (ISM / LoRa — AU)
                     1_090_000_000 = 1090 MHz (ADS-B aircraft)
        """
        self._center_freq_hz = freq_hz
        if self._is_open:
            if self._stream is not None:
                self._device.deactivateStream(self._stream)
            self._device.setFrequency(self._rx, 0, freq_hz)
            if self._stream is not None:
                self._device.activateStream(self._stream)
                time.sleep(0.25)
            logger.debug("Centre frequency set to %.3f MHz", freq_hz / 1e6)

    def set_sample_rate(self, rate_hz: float) -> None:
        """
        Set the sample rate (how many IQ samples per second).

        Args:
            rate_hz: Samples per second. Pluto supports up to ~5 MSPS
                over USB 2.0 in practice. Common value: 2_000_000.
        """
        self._sample_rate_hz = rate_hz
        if self._is_open:
            self._device.setSampleRate(self._rx, 0, rate_hz)
            logger.debug("Sample rate set to %.1f MHz", rate_hz / 1e6)

    def set_gain(self, gain_db: float) -> None:
        """
        Set combined receive gain.

        Pluto has a single combined gain stage, not separate LNA/VGA
        controls. The gain range for this phase is 0–74.5 dB.

        Args:
            gain_db: Gain in dB (0–74.5 dB).

        Raises:
            ValueError: If gain_db is outside the valid range.
        """
        if gain_db < self.MIN_GAIN_DB or gain_db > self.MAX_GAIN_DB:
            raise ValueError(
                f"Gain {gain_db} dB out of range. "
                f"Valid range: {self.MIN_GAIN_DB}–{self.MAX_GAIN_DB} dB."
            )
        self._gain_db = gain_db
        if self._is_open:
            self._device.setGain(self._rx, 0, gain_db)
            logger.debug("Gain set to %.1f dB", gain_db)

    def read_samples(self, num_samples: int) -> np.ndarray:
        """
        Capture IQ samples from the ADALM-PLUTO receiver.

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
            RuntimeError: If the device is not open or capture fails after
                one stream-reset retry.

        Timeout retry behaviour:
            SoapySDR error code -4 means the hardware did not deliver samples
            within the 10-second deadline. This can occur during band switches,
            when USB bandwidth is saturated, or when the Pluto firmware is
            temporarily unresponsive. When a timeout is detected, the method
            deactivates and reactivates the SoapySDR stream (with a 50 ms gap
            and 100 ms settle) to reset the USB transfer pipeline, then retries
            the capture once. If the retry also fails, a RuntimeError is raised.
            A warning is logged with the current centre frequency so operators
            can see when the hardware is struggling.
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
                if sr.ret == -4 and retry_count < 1:
                    logger.warning(
                        "readStream timeout at %.3f MHz — resetting stream before retry",
                        self._center_freq_hz / 1e6,
                    )
                    if self._stream is not None:
                        self._device.deactivateStream(self._stream)
                        time.sleep(0.05)
                        self._device.activateStream(self._stream)
                        time.sleep(0.1)
                    retry_count += 1
                    total = 0
                    output = np.zeros(num_samples, dtype=np.complex64)
                    continue
                raise RuntimeError(
                    f"ADALM-PLUTO read failed (SoapySDR error code {sr.ret}). "
                    f"Try reducing sample rate or checking USB connection."
                )
            total += sr.ret
            if sr.ret == 0:
                break

        return output[:total]

    # ── Transmit — all permanently blocked ────────────────────────────
    # These override DeviceBase and add explicit Pluto-specific naming.

    def transmit(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("PlutoReceiver.transmit")

    def write_samples(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("PlutoReceiver.write_samples")

    def writeStream(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("PlutoReceiver.writeStream")

    def set_tx_gain(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("PlutoReceiver.set_tx_gain")

    def set_tx_frequency(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("PlutoReceiver.set_tx_frequency")

    def setupTxStream(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("PlutoReceiver.setupTxStream")

    def activateTxStream(self, *args, **kwargs) -> None:
        """BLOCKED — TX is a criminal offence without an ACMA licence."""
        transmit_guard("PlutoReceiver.activateTxStream")

    # ── Properties (read-only view of current config) ──────────────────

    @property
    def center_freq_hz(self) -> float:
        return self._center_freq_hz

    @property
    def sample_rate_hz(self) -> float:
        return self._sample_rate_hz

    @property
    def gain_db(self) -> float:
        return self._gain_db

    @property
    def is_open(self) -> bool:
        return self._is_open