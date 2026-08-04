/**
 * Shared ADS-B aircraft field formatters.
 *
 * Extracted from AdsbAircraftPanel.jsx in Phase 51 so the new
 * AircraftDetailPanel (/radar page) can render identical values without
 * duplicating the formatting logic (plan-reviewer clarification C3).
 *
 * Convention: every formatter returns the em-dash glyph (U+2014) for
 * null / undefined / '---' input, matching the long-standing
 * AdsbAircraftPanel display convention. The em-dash is a UI-rendered
 * display value only - never used in comments or identifiers.
 */

/**
 * Altitude in feet, locale-grouped (e.g. "35,000").
 * @param {number|null|undefined|string} value - altitude in feet
 * @returns {string}
 */
export function formatAltitude(value) {
  if (value === null || value === undefined || value === '---') return '—'
  return Number(value).toLocaleString()
}

/**
 * Groundspeed in knots, rounded to a whole number.
 * @param {number|null|undefined|string} value - groundspeed in knots
 * @returns {string}
 */
export function formatSpeed(value) {
  if (value === null || value === undefined || value === '---') return '—'
  return Math.round(Number(value)).toString()
}

/**
 * Track (heading over ground) as a zero-padded 3-digit degree value
 * (e.g. "270°").
 * @param {number|null|undefined|string} value - track in degrees
 * @returns {string}
 */
export function formatTrack(value) {
  if (value === null || value === undefined || value === '---') return '—'
  const deg = Math.round(Number(value)) % 360
  return `${String(deg).padStart(3, '0')}°`
}

/**
 * Bearing from receiver as a zero-padded 3-digit degree value
 * (e.g. "045°").
 * @param {number|null|undefined|string} value - bearing in degrees
 * @returns {string}
 */
export function formatBearing(value) {
  if (value === null || value === undefined || value === '---') return '—'
  const deg = Math.round(Number(value)) % 360
  return `${String(deg).padStart(3, '0')}°`
}

/**
 * Bearing rate of change with explicit sign (e.g. "+2.3°/s").
 * @param {number|null|undefined|string} value - bearing rate in deg/s
 * @returns {string}
 */
export function formatDeltaR(value) {
  if (value === null || value === undefined || value === '---') return '—'
  const num = Number(value)
  const sign = num >= 0 ? '+' : '-'
  return `${sign}${Math.abs(num).toFixed(1)}°/s`
}

// Dead-zone: 200 ft/min. Below this, vertical rate is within typical
// ADS-B barometric altitude noise and should not be labelled climbing
// or descending. Genuine climb/descent for light aircraft starts
// ~500 ft/min. ICAO level-flight threshold is 300 ft/min.
const VERTICAL_RATE_DEAD_ZONE_FPM = 200

/**
 * Vertical rate classification for the pinned aircraft detail card.
 * Returns "Climbing", "Descending", or "Level" (inside the 200 ft/min
 * dead-zone). Null, undefined, non-numeric, and exactly-zero values
 * return the em-dash placeholder, matching the other formatters: a
 * zero vertical rate on an ADS-B feed usually means "no data encoded"
 * rather than a measured level state.
 * @param {number|null|undefined|string} value - vertical rate in ft/min
 * @returns {string}
 */
export function formatVerticalRate(value) {
  if (value === null || value === undefined || value === '---') return '—'
  const num = Number(value)
  if (Number.isNaN(num) || num === 0) return '—'
  if (num > VERTICAL_RATE_DEAD_ZONE_FPM) return 'Climbing'
  if (num < -VERTICAL_RATE_DEAD_ZONE_FPM) return 'Descending'
  return 'Level'
}
