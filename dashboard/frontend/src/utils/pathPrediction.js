/**
 * Physics-only path prediction helpers for the /radar page (Phase 52).
 *
 * Given an aircraft's stored trail history (bearing/range fixes, oldest
 * first), derive a constant-rate motion vector and linearly extrapolate
 * the aircraft's position a fixed horizon into the future. This is a
 * dead-reckoning estimate ONLY: it assumes constant bearing rate and
 * constant range rate, which is a rough approximation for real aircraft
 * but adequate for a short-horizon visual aid.
 *
 * No LLM, no network, no I/O — pure functions over numbers. Passive
 * receive display only.
 */

/**
 * How far ahead the projection extends, in seconds. Fixed (not
 * configurable) in Phase 52 so the panel copy, the ghost line, and the
 * tests all refer to the same horizon.
 */
export const PREDICTION_HORIZON_SEC = 45

/**
 * Derive a constant-rate motion vector from a trail history.
 *
 * Uses the OLDEST and NEWEST stored fixes (not the last two): a longer
 * trail averages out per-fix jitter instead of tracking only the most
 * recent, possibly noisy, segment.
 *
 * The bearing delta is wrapped into [-180, 180] so an aircraft crossing
 * the 360/0 axis is treated as taking the shortest angular path (e.g.
 * 350 deg -> 10 deg is +20 deg, not -340 deg). Positive theta is
 * clockwise (the radar/projection convention).
 *
 * Returns null when no trustworthy rate can be derived: fewer than two
 * fixes, missing fixes, or non-positive elapsed time between them
 * (duplicate, reversed, or NaN timestamps).
 *
 * @param {Array<{bearing_deg: number, range_nm: number, ts: number}>} history
 *   Trail points, oldest first, as stored by RadarScopePanel's trailsRef.
 * @returns {{thetaDegPerSec: number, deltaRNmPerSec: number}|null}
 *   Signed bearing rate (deg/s, positive clockwise) and range rate
 *   (nm/s, negative = closing), or null if underivable.
 */
export function derivePredictionVector(history) {
  if (!Array.isArray(history)) return null
  if (history.length < 2) return null
  const oldest = history[0]
  const newest = history[history.length - 1]
  if (oldest === null || oldest === undefined) return null
  if (newest === null || newest === undefined) return null
  const elapsedSec = newest.ts - oldest.ts
  // <= 0 also rejects NaN (NaN comparisons are always false, so a NaN
  // elapsed fails the > 0 test below rather than this one — guard both).
  if (!(elapsedSec > 0)) return null

  let delta = newest.bearing_deg - oldest.bearing_deg
  while (delta > 180) delta -= 360
  while (delta <= -180) delta += 360

  return {
    thetaDegPerSec: delta / elapsedSec,
    deltaRNmPerSec: (newest.range_nm - oldest.range_nm) / elapsedSec,
  }
}

/**
 * Linearly extrapolate a (bearing, range) position by a constant-rate
 * motion vector over a horizon.
 *
 * The projected bearing is normalised into [0, 360) so wraparound at
 * the 360/0 axis produces a valid bearing (e.g. 350 + 20 = 370 -> 10,
 * and 10 - 20 = -10 -> 350). The projected range is clamped at 0: an
 * aircraft on a closing vector never projects to a negative range.
 *
 * @param {number} currentBearingDeg  Current bearing in degrees (0 = north, clockwise)
 * @param {number} currentRangeNm     Current range in nautical miles
 * @param {number} thetaDegPerSec     Bearing rate in deg/s (positive clockwise)
 * @param {number} deltaRNmPerSec     Range rate in nm/s (negative = closing)
 * @param {number} horizonSec         Extrapolation horizon in seconds
 * @returns {{bearing_deg: number, range_nm: number}}  Projected position
 */
export function projectPosition(
  currentBearingDeg,
  currentRangeNm,
  thetaDegPerSec,
  deltaRNmPerSec,
  horizonSec,
) {
  const bearing = currentBearingDeg + thetaDegPerSec * horizonSec
  // % can return a negative result for negative operands; the double-mod
  // maps into [0, 360) regardless of sign.
  const bearingDeg = ((bearing % 360) + 360) % 360
  const rangeNm = Math.max(0, currentRangeNm + deltaRNmPerSec * horizonSec)
  return { bearing_deg: bearingDeg, range_nm: rangeNm }
}
