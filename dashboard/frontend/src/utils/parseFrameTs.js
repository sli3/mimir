/**
 * Coerce a SocketIO frame timestamp to a finite numeric epoch-ms value.
 *
 * WHY THIS HELPER EXISTS (Phase 53-HOTFIX):
 *
 * The backend emits `timestamp` as an ISO 8601 STRING (see
 * dashboard/server.py:666, `msg.timestamp.isoformat()`). RadarScopePanel's
 * trail buffer does arithmetic on stored timestamps: `ts - last.ts >
 * TRAIL_STALE_MS` in the component, and `newest.ts - oldest.ts` inside
 * derivePredictionVector (utils/pathPrediction.js). Mixed string-vs-number
 * arithmetic returns NaN, and `NaN > 90000` is false, so with the raw
 * string on the wire the staleness clear never fired and the prediction
 * vector was always null against live data. The timestamp type MUST
 * therefore be normalised to a number at the boundary, before the trail
 * buffer ever sees it.
 *
 * The ISO string wire format is load-bearing across many other consumers
 * (AisVesselPanel, AcarsMessagePanel, App.jsx "LAST SEEN",
 * AIReasoningPanel, SignalHistoryLog, VectorSpacePage), all of which pass
 * it to `new Date(...)` or a string formatter. Do NOT change the payload;
 * normalise only at the point of arithmetic use.
 *
 * The fallback to Date.now() is intentional: a missing or malformed
 * timestamp must degrade to "now" rather than poison the trail buffer
 * with NaN, which would silently re-introduce exactly the bug this
 * helper fixes.
 *
 * Extracted as a shared helper rather than inlined at both call sites in
 * RadarScopePanel so the two sites cannot drift apart.
 *
 * @param {string|number|null|undefined} value
 *   Frame timestamp: ISO 8601 string, numeric epoch ms, or absent.
 * @returns {number} Finite epoch milliseconds. Never NaN.
 */
export function parseFrameTs(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    // Date.parse returns NaN for anything it cannot parse; only a
    // finite result is a trustworthy epoch-ms value.
    const parsed = Date.parse(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return Date.now()
}
