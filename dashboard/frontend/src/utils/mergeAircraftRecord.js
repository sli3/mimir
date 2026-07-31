/**
 * Field-preserving merge for ADS-B aircraft records (BUG-06).
 *
 * Why this exists
 * ---------------
 * ADS-B Mode S messages arrive as disjoint field sets depending on the
 * typecode: typecode 4 carries callsign only, typecode 19 carries velocity
 * (groundspeed / track / vertical_rate), and typecodes 9-18 carry position
 * (altitude / latitude / longitude). The backend emits every decoded frame
 * as a single payload where fields not carried by that frame are null.
 *
 * The pre-BUG-06 frontend stored each incoming frame wholesale
 * (`{ ...data, receivedAt: now }`), so a callsign-only frame would clobber
 * the previously-known altitude, position, and velocity with nulls, and the
 * table would flicker between partial snapshots of the same aircraft.
 *
 * This helper merges field-by-field instead:
 *
 * - A field present and non-null in the incoming frame overwrites the
 *   stored value.
 * - A field null or undefined in the incoming frame preserves the stored
 *   value (the frame simply did not carry that field).
 * - A brand-new ICAO (no previous record) stores the incoming frame as-is.
 * - `receivedAt` ALWAYS updates to `now` on every frame, regardless of
 *   which fields were carried. This keeps the 90-second staleness cutoff
 *   in useSocket.js working: an aircraft that is still transmitting must
 *   not age out just because its recent frames carried no position data.
 * - `icao` and `timestamp` follow the same uniform rule as every other
 *   field (in practice they are always non-null on a decoded frame).
 * - `raw_hex` follows the same uniform rule as well, with no special-casing.
 *
 * The result is always a NEW object, never a mutation of `prev`, so React
 * state setters trigger a re-render.
 *
 * The function is pure: no React imports, no internal Date.now();
 * `now` is passed in by the caller so the same timestamp can be shared
 * across the active-aircraft merge and any cutoff arithmetic.
 *
 * @param {object|null} prev - the previously stored aircraft record, or
 *   null/undefined if this ICAO has not been seen before.
 * @param {object} data - the incoming adsb_aircraft payload. Fields not
 *   carried by this frame are null or absent.
 * @param {number} now - the current timestamp in milliseconds (e.g.
 *   Date.now()), used for the receivedAt field.
 * @returns {object} a new merged aircraft record with receivedAt = now.
 */
export function mergeAircraftRecord(prev, data, now) {
  const merged = {}
  const keys = new Set([...Object.keys(prev || {}), ...Object.keys(data)])
  for (const key of keys) {
    if (key === 'receivedAt') {
      merged[key] = now
      continue
    }
    const incoming = data[key]
    if (incoming !== null && incoming !== undefined) {
      merged[key] = incoming
    } else if (prev && prev[key] !== undefined) {
      merged[key] = prev[key]
    } else {
      // No prior value either, so keep the incoming null/undefined so a
      // brand-new ICAO stores the frame as-is (same shape as { ...data }).
      merged[key] = incoming
    }
  }
  // receivedAt is always set, even if neither side carried the key.
  merged.receivedAt = now
  return merged
}
