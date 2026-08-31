"""
core.pipeline.frequency.py — Backend frequency-tolerance matching.

Mirrors dashboard/frontend/src/utils/frequency.js (Phase 76 Fix 4) on
the Python side. Both must use the same tolerance value (100 kHz) so
a signal within a band's canonical window is treated consistently
whether the frontend or backend does the comparison.

Why 100 kHz:
  Large enough to absorb the observed ~30 kHz offset in the demo file
  (3.3x margin) and typical SDR crystal drift (<= +/-50 ppm at 1 GHz
  is approximately +/-50 kHz).

  Small enough for safety: the focusable band set is the seven
  BAND_PROFILES centres in dashboard/shared_state.py
  (98.0 / 127.0 / 129.125 / 145.175 / 162.0 / 915.0 / 1090.0 MHz).
  The smallest adjacent gap is Aviation (127 MHz) to ACARS (129.125
  MHz) = 2.125 MHz = 21x the tolerance. No real single-band signal
  can match two different bands within tolerance.

NAME COLLISION — DO NOT CONFUSE WITH THREE SIBLING CONSTANTS:
  Three other modules export a constant literally named FREQ_TOLERANCE_HZ,
  with three different purposes and three different magnitudes:
    - modules/adsb/constants.py:11   — 2_000_000 (2 MHz)  — ADS-B near-band emit gate
    - modules/ais/constants.py:16    — 100_000  (100 kHz) — AIS chunk acceptance
    - modules/acars/constants.py:20  — 5_000    (5 kHz)   — ACARS narrow window
  The AIS one is the strongest "looks identical" trap: same value as our
  FOCUS_FREQ_TOLERANCE_HZ below, but a completely different purpose (it
  gates whether to accept an AIS chunk from the dual 161.975/162.025 MHz
  channels, not identity matching in a focus filter). Do not unify these.
  The names in this module (FOCUS_FREQ_TOLERANCE_HZ vs FREQ_TOLERANCE_HZ)
  are deliberately different so any caller importing both modules cannot
  silently get one when it wanted the other. The sibling constants are
  all correct for their own purposes.
"""
from __future__ import annotations

FOCUS_FREQ_TOLERANCE_HZ: int = 100_000


def freq_matches(
    a: float | int | None,
    b: float | int | None,
    tolerance_hz: float = FOCUS_FREQ_TOLERANCE_HZ,
) -> bool:
    """Return True iff |a - b| <= tolerance_hz.

    Either side being None returns False (mirrors the frontend helper's
    null semantics — NOTE: the "no filter" pass-through for callers
    like broadcast() comes from broadcast()'s own `focused is not None`
    guard, NOT from this helper. On the SCAN side, center_freq_hz=None
    with a focus set is dropped, identical to pre-fix behaviour. NaN
    inputs naturally return False (NaN <= x is False in Python).
    """
    if a is None or b is None:
        return False
    return abs(a - b) <= tolerance_hz
