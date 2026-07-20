"""
core/device/profiles.py
Mimir RF Scanner — SDR Device Capability Profiles

WHAT THIS FILE DOES
───────────────────
This module is a pure-data catalogue of the SDR hardware Mimir knows how
to talk to. For each supported device it records the facts the rest of
the application needs BEFORE any hardware is opened: the SoapySDR driver
key, the physical tuning range, the gain model, and the Python wrapper
class that drives it.

Nothing in this file touches hardware. Importing it is safe on any
machine, with or without an SDR connected, because the wrapper classes
are only referenced here, never instantiated.

WHY THE FREQUENCY RANGE MATTERS
───────────────────────────────
Every SDR can only tune inside a physical frequency range set by its
radio chip. Asking a device to tune outside that range does not raise a
clean error at every layer of the stack — depending on the driver, the
device may silently return noise that looks exactly like a real capture.
That noise then flows through the FFT pipeline, gets turned into an
embedding, and lands in ChromaDB as if it were a genuine signal. Enough
of those phantom captures quietly pollute the vector store that every
future similarity match is made against.

Recording the range here lets Mimir fail loudly and early — before a
single sample is captured — instead of discovering the problem weeks
later as corrupted training data.

WHY THE GAIN MODEL MATTERS
──────────────────────────
"Gain" is how much the receiver amplifies the incoming signal. The same
number means different things on the two supported devices:

  - HackRF One uses a SPLIT gain model: two separate amplifier stages
    (LNA 0–40 dB and VGA 0–62 dB, plus an optional ~11 dB amp that
    Mimir keeps off).
  - ADALM-PLUTO uses a COMBINED gain model: one single stage from
    0–74.5 dB. It has no LNA or VGA at all.

BAND_PROFILES (dashboard/shared_state.py) speaks HackRF's split language
through its lna_gain_db / vga_gain_db keys. There is no correct automatic
translation from a split pair to a single combined figure — a HackRF
setting of LNA 24 / VGA 26 does not map onto any one Pluto number in a
principled way, because the two stages sit at different points in the
receive chain and contribute differently to noise and linearity. That
mismatch is resolved in Phase 37, not here.

A NOTE ON THE PLUTO RANGE
─────────────────────────
The 325–3800 MHz range is the STOCK AD9363 range with the firmware Mimir
runs. A widely circulated unofficial firmware modification (the "AD9364
hack") advertises 70 MHz–6 GHz. Mimir does not run that firmware, so the
wider range is deliberately NOT encoded here.

LEGAL NOTE
──────────
Both devices are TX-CAPABLE hardware operating under a zero-transmit
legal constraint (Radiocommunications Act 1992 (Cth)). This module is
data only: it cannot weaken the software TX block enforced in
core/legal/compliance_guard.py because it performs no I/O at all.

SOURCES
───────
  - HackRF One:    1 MHz – 6 GHz
    https://github.com/greatscottgadgets/hackrf/blob/main/docs/source/hackrf_one.rst
  - ADALM-PLUTO:   325 MHz – 3800 MHz (AD9363, stock firmware)
    https://wiki.analog.com/university/tools/pluto/devs/specs
"""

from __future__ import annotations

from core.device.hackrf_rx import HackRFReceiver
from core.device.pluto_rx import PlutoReceiver

# Keys are the exact SoapySDR driver strings: detect.py enumerates devices
# by driver and looks the result up by the same string, so the two must
# never drift apart.
DEVICE_PROFILES: dict = {
    "hackrf": {
        "driver": "hackrf",
        "display_name": "HackRF One",
        "min_freq_hz": 1_000_000,        # 1 MHz
        "max_freq_hz": 6_000_000_000,    # 6 GHz
        "gain_model": "split",           # LNA (0–40 dB) + VGA (0–62 dB) stages
        "max_gain_db": 62.0,             # VGA stage maximum — largest single stage
        "wrapper_class": HackRFReceiver,
    },
    "plutosdr": {
        "driver": "plutosdr",
        "display_name": "ADALM-PLUTO",
        "min_freq_hz": 325_000_000,      # 325 MHz — stock AD9363 floor
        "max_freq_hz": 3_800_000_000,    # 3.8 GHz — stock AD9363 ceiling
        "gain_model": "combined",        # single stage, no LNA/VGA split
        "max_gain_db": 74.5,
        "wrapper_class": PlutoReceiver,
    },
}
