/**
 * Project a (bearing, range) pair from the local receiver position to a
 * pixel coordinate inside a square PPI scope.
 *
 * Convention: bearing 0 deg = true north, increasing clockwise. Y is
 * inverted because screen Y grows downward, so north (bearing 0) maps
 * to the TOP of the scope (y < cy).
 *
 * @param {number} bearingDeg  Bearing in degrees, 0-360 (true north = 0, clockwise)
 * @param {number} rangeNm     Range from receiver, in nautical miles
 * @param {number} maxRangeNm  Maximum range displayed on the scope, in nautical miles
 * @param {number} cx          Pixel x-coordinate of the scope centre
 * @param {number} cy          Pixel y-coordinate of the scope centre
 * @param {number} maxR        Pixel radius of the outer range ring
 * @returns {{x: number, y: number}}  Pixel coordinate
 */
export function projectToScope(bearingDeg, rangeNm, maxRangeNm, cx, cy, maxR) {
  const rel = Math.min(rangeNm / maxRangeNm, 1)
  const t = bearingDeg * Math.PI / 180
  const x = cx + Math.sin(t) * rel * maxR
  const y = cy - Math.cos(t) * rel * maxR
  return { x, y }
}

/**
 * Null-safe range check. Returns false for null, undefined, NaN,
 * negative or out-of-range values.
 *
 * @param {number|null|undefined} rangeNm
 * @param {number} maxRangeNm
 * @returns {boolean}
 */
export function isWithinRange(rangeNm, maxRangeNm) {
  if (rangeNm === null || rangeNm === undefined) return false
  if (Number.isNaN(rangeNm)) return false
  if (rangeNm < 0) return false
  return rangeNm <= maxRangeNm
}

/**
 * Check whether a truthy frequency is within 2 MHz of the ADS-B centre.
 *
 * @param {number|null|undefined} freqHz - Focused frequency in Hz
 * @returns {boolean}
 */
export function isAdsbFrequency(freqHz) {
  return Boolean(freqHz && Math.abs(freqHz - 1_090_000_000) <= 2_000_000)
}

/**
 * Determines whether an aircraft record is a valid, in-range contact
 * that should be counted and rendered on the radar scope.
 *
 * Single source of truth for the "valid contact" rule (Phase 50),
 * shared by RadarScopePanel (blip/trail rendering) and RadarPage
 * (header contact count) so the two can never disagree — see TD-49-6.
 *
 * bearing_deg is guarded separately from rangeNm: isWithinRange() only
 * covers the range field, but a contact with a missing/NaN bearing_deg
 * still cannot be projected even if its range is fine.
 *
 * @param {Object} ac - Aircraft state record
 * @param {number|null|undefined} ac.bearing_deg
 * @param {number|null|undefined} ac.range_nm
 * @param {number} maxRangeNm - Maximum displayed range, in nautical miles
 * @returns {boolean}
 */
export function isValidContact(ac, maxRangeNm) {
  if (ac.bearing_deg === null || ac.bearing_deg === undefined) return false
  if (Number.isNaN(ac.bearing_deg)) return false
  return isWithinRange(ac.range_nm, maxRangeNm)
}