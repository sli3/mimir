/**
 * Frontend frequency-tolerance helpers — Phase 76 fourth fix.
 *
 * The backend (DemoProducer, SigMF replay, real captures) emits the
 * EXACT captured centre frequency, which is typically slightly offset
 * from the canonical band frequency (typical SDR tuning resolution is
 * ±tens of kHz; calibration drift adds more). Live mode masks this
 * because the hardware is tuned to the exact canonical value the user
 * clicked, so emitted and focused frequencies are byte-identical.
 *
 * Demo mode uniquely exposes the gap: a captured file's real centre
 * frequency (e.g. 1_090_030_000 Hz from capture_1090030000hz_*.sigmf-meta)
 * differs from the round canonical ADS-B frequency (1_090_000_000 Hz) by
 * tens of kHz, which fails every strict-equality (`===`) comparison in
 * the frontend.
 *
 * TOLERANCE VALUE: 100 kHz.
 *
 *   Large enough to absorb:
 *     - The observed 30 kHz offset in the demo file (3.3× margin)
 *     - Typical SDR crystal drift (≤ ±50 ppm at 1 GHz ≈ ±50 kHz)
 *     - Tuning resolution of consumer SDRs (often sub-kHz)
 *
 *   Small enough for safety against cross-band false matches:
 *     The frontend's effective canonical set (STRIP_CONFIGS, FREQ_CONFIGS,
 *     FREQ_COLOUR_MAP, FREQ_LABEL_MAP, BAND_GROUPS) all share seven
 *     entries including Aviation at 127 MHz. The smallest adjacent gap
 *     in that set is:
 *       AVIATION (127 MHz) ↔ ACARS (129.125 MHz) = 2.125 MHz
 *     which is 21× larger than the 100 kHz tolerance — no realistic
 *     single-band signal can match two different bands within tolerance.
 *
 *   IMPORTANT — NAME COLLISION WARNING:
 *     The backend has THREE pre-existing FREQ_TOLERANCE_HZ constants,
 *     each with a DIFFERENT purpose and magnitude:
 *       - modules/adsb/constants.py:11    → 2_000_000 Hz (2 MHz)
 *         Purpose: Emit gate (whether to emit a scan_result when user
 *         is "near" a band), NOT identity matching.
 *       - modules/ais/constants.py:16     → 100_000 Hz (100 kHz)
 *         Purpose: AIS chunk acceptance during decoding. IDENTICAL
 *         value to this frontend/backend pair, but completely different
 *         purpose — the strongest "looks identical" naming trap.
 *       - modules/acars/constants.py:20  → 5_000 Hz (5 kHz)
 *         Purpose: ACARS narrow window.
 *
 *     DO NOT "sync" this frontend value to match the backend's 2 MHz
 *     (ADS-B) — at 2 MHz, a 128.06 MHz query would fall within 2×tolerance
 *     of BOTH 127 MHz and 129.125 MHz (gap 2.125 MHz ≤ 4 MHz), re-introducing
 *     exactly the cross-match this module rejects. The four constants are
 *     deliberately different magnitudes for different purposes. This module
 *     is strictly identity-matching; 2 MHz would break that.
 *
 * @module utils/frequency
 */

/**
 * Tolerance constant. See module docstring for derivation rationale.
 *
 * Unit: Hz.
 *
 * @type {number}
 */
export const FREQ_TOLERANCE_HZ = 100_000

/**
 * Returns true iff `a` and `b` are non-null and |a − b| ≤ toleranceHz.
 * Treats null/undefined as never-matching (preserves `===` semantics for
 * the null case). NaN inputs naturally return false (NaN <= x is false).
 *
 * @param {number|null|undefined} a — first frequency in Hz
 * @param {number|null|undefined} b — second frequency in Hz
 * @param {number} [toleranceHz=FREQ_TOLERANCE_HZ] — maximum allowed |a−b|
 * @returns {boolean}
 */
export function freqMatches(a, b, toleranceHz = FREQ_TOLERANCE_HZ) {
  if (a == null || b == null) return false
  return Math.abs(a - b) <= toleranceHz
}

/**
 * Returns the value from `canonicalMap` whose key matches `freq` within
 * `toleranceHz`, or `null` if no key matches. The first matching key
 * (by Object.entries insertion order) wins.
 *
 * `canonicalMap` keys are coerced via `Number()` — pass a plain object
 * literal of `{freq_hz: value}`.
 *
 * First match wins. For integer-like keys (string representations of
 * positive integers, e.g. "98000000"), ECMA-262 §OrdinaryOwnPropertyKeys
 * mandates ascending numeric order — which matches the literal declaration
 * order here only because both maps (FREQ_COLOUR_MAP, FREQ_LABEL_MAP) are
 * declared ascending. Do not rely on this helper for non-ascending or
 * non-integer-keyed maps.
 *
 * @param {number|null|undefined} freq — the frequency to match (Hz)
 * @param {Object} canonicalMap — map of canonical freq (number) → value
 * @param {number} [toleranceHz=FREQ_TOLERANCE_HZ]
 * @returns {*|null} the matching value, or null if no key matches
 */
export function findCanonicalValue(freq, canonicalMap, toleranceHz = FREQ_TOLERANCE_HZ) {
  if (freq == null) return null
  for (const [key, value] of Object.entries(canonicalMap)) {
    if (freqMatches(Number(key), freq, toleranceHz)) {
      return value
    }
  }
  return null
}
