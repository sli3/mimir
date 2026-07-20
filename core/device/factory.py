"""
core/device/factory.py
Mimir RF Scanner — Device Factory

LEGAL NOTICE
────────────
Jurisdiction : Australia — South Australia (Adelaide)
Authority    : ACMA (Australian Communications and Media Authority)
Law          : Radiocommunications Act 1992 (Cth)
Licence held : NONE

Both devices constructible here (HackRF One, ADALM-PLUTO) are TX-CAPABLE
hardware operating under a zero-transmit legal constraint. This factory
imports no TX API and opens no stream; every device it returns carries
the software TX block enforced by core/legal/compliance_guard.py via
DeviceBase. Any transmit call raises HardwareTransmitError immediately.

WHAT THIS FILE DOES
───────────────────
Provides a single function, build_device(), that constructs an UN-OPENED
receiver instance for a named SoapySDR driver. Callers select hardware via
the --device command-line flag (see scan.py) and open the device
themselves, so the factory never touches USB.

WHY CENTRALISED
───────────────
Before Phase 37, scan.py constructed HackRFReceiver directly. Adding a
second device would have forced every entry point to grow its own
if/else over driver names and gain models. Centralising the mapping here
means:

  - There is exactly one place that knows which driver string maps to
    which wrapper class.
  - The HackRF split gain model (LNA + VGA) and the Pluto combined gain
    model are translated in one place: the factory accepts the HackRF
    gain vocabulary (because MimirConfig speaks it) and deliberately does
    NOT forward it to PlutoReceiver, whose gain semantics differ. Pluto
    is constructed with its own class default (PlutoReceiver.DEFAULT_GAIN_DB)
    until its band profiles are calibrated in Phase 39.
  - Future devices add one branch here and nothing anywhere else.

TX-SAFETY NOTE
──────────────
HackRFReceiver and PlutoReceiver are RX-only wrappers: they never call a
SoapySDR TX entry point and they override every TX-adjacent method name
with a transmit_guard() block. This factory adds no capability of any
kind — it only decides which RX-only wrapper to construct.
"""

from __future__ import annotations

import logging

from core.device.device_base import DeviceBase
from core.device.hackrf_rx import HackRFReceiver
from core.device.pluto_rx import PlutoReceiver

logger = logging.getLogger(__name__)


def build_device(
    driver: str,
    *,
    lna_gain_db: float = 24.0,
    vga_gain_db: float = 26.0,
    amp_enable: bool = False,
) -> DeviceBase:
    """Construct an un-opened receiver for the named device driver.

    The returned instance has NOT been opened: no USB access has occurred
    and no hardware is touched. The caller must call open() itself, which
    keeps factory use testable and lets startup checks (e.g. the Pluto
    supported-frequency check in scan.py) run before the device is opened.

    Args:
        driver: SoapySDR driver key — "hackrf" or "plutosdr". Passed via
            the --device command-line flag.
        lna_gain_db: HackRF LNA (low-noise amplifier) gain in dB. Ignored
            for "plutosdr", which has a single combined gain stage.
        vga_gain_db: HackRF VGA (variable gain amplifier) gain in dB.
            Ignored for "plutosdr".
        amp_enable: HackRF RF amplifier enable flag. Ignored for
            "plutosdr".

    Returns:
        An un-opened DeviceBase instance (HackRFReceiver or PlutoReceiver).

    Raises:
        ValueError: If driver is not a known device driver key.
    """
    if driver == "hackrf":
        logger.debug(
            "Building HackRFReceiver: lna=%.1f dB, vga=%.1f dB, amp=%s",
            lna_gain_db, vga_gain_db, amp_enable,
        )
        return HackRFReceiver(
            lna_gain_db=lna_gain_db,
            vga_gain_db=vga_gain_db,
            amp_enable=amp_enable,
        )
    if driver == "plutosdr":
        # Pluto uses a single combined gain stage (0–74.5 dB), not the
        # HackRF LNA/VGA split. There is no principled translation from a
        # split pair to one combined figure (see core/device/profiles.py),
        # and the BAND_PROFILES lna/vga values are HackRF-specific. Until
        # Pluto band profiles are calibrated (Phase 39), use the class
        # default explicitly.
        logger.debug(
            "Building PlutoReceiver: gain=%.1f dB (class default)",
            PlutoReceiver.DEFAULT_GAIN_DB,
        )
        return PlutoReceiver(gain_db=PlutoReceiver.DEFAULT_GAIN_DB)
    raise ValueError(
        f"Unknown device driver {driver!r} (passed via --device). "
        f"Valid drivers: 'hackrf', 'plutosdr'."
    )
