import React, { useMemo, useRef } from 'react'
import { projectToScope, isWithinRange, isValidContact } from './radar/projection.js'

// Phase 49 tech-debt markers (recorded in AGENTS.md by the /finalise-build
// run, NOT by this build):
// TD-49-1 — Label overlap: callsign labels are placed at their projected
//   coordinate with no collision-avoidance solver. Two close aircraft
//   will overprint each other's labels, and the blip glow filter makes
//   overlapping markers visually merge as well. Out of scope for Phase 49.

const SCOPE_CX = 190
const SCOPE_CY = 162.5
const SCOPE_MAX_R = 150

// Trail history. TRAIL_STALE_MS mirrors useSocket.js's adsbAircraft
// cutoff (useSocket.js:174) and the backend's AIRCRAFT_EXPIRY_SEC — both
// are meant to represent "how long before we consider an aircraft's last
// known position too old to trust", but are currently three independent
// hardcoded literals with no shared source. Documented pre-existing
// pattern; not something Phase 50 fixes.
const TRAIL_MAX_POINTS = 8
const TRAIL_STALE_MS = 90000

// Round to 2 decimal places so no float noise (e.g. 162.49999999999999)
// ever reaches an SVG attribute.
const r2 = (n) => Number(n.toFixed(2))

/**
 * PPI-style radar scope panel rendering decoded ADS-B aircraft as an SVG
 * polar plot. Passive receive display only.
 *
 * Rendering boundary: projection.js produces renderer-agnostic scope
 * coordinates; this component maps them straight onto SVG primitives
 * inside a fixed 380x325 viewBox. preserveAspectRatio scales the scope
 * to whatever size the panel body ends up, so no runtime measurement,
 * ResizeObserver, or font metric is involved.
 *
 * Header: RadarPage owns the page-level header (title, contact count,
 * range readout) exclusively. This panel renders scope content only —
 * see TD-49-6 / Phase 50 header-dedup fix.
 *
 * Trail and passthrough: Each aircraft maintains a breadcrumb trail of
 * up to 8 historical positions (TRAIL_MAX_POINTS). When a frame lacks
 * position data (e.g. callsign/altitude/velocity-only ADS-B messages),
 * the passthrough branch re-renders the aircraft from its last known
 * position, preventing flicker while keeping the stored trail untouched.
 *
 * @param {Object} adsbAircraft - Map of ICAO address -> aircraft state
 * @param {number|null} focusedFreq - Currently tuned frequency in Hz
 * @param {number} maxRangeNm - Maximum displayed range, in nautical miles
 */
export default function RadarScopePanel({ adsbAircraft = {}, focusedFreq, maxRangeNm = 40 }) {
  const isAdsbFreq = focusedFreq && (
    Math.abs(focusedFreq - 1_090_000_000) <= 2_000_000
  )

  // Per-ICAO trail history: icao -> [{ bearing_deg, range_nm, ts }, ...],
  // oldest first, capped at TRAIL_MAX_POINTS. A ref, not state, because
  // trail mutation is a side effect of processing adsbAircraft and must
  // not itself trigger an extra re-render.
  const trailsRef = useRef(new Map())

  // Static chrome: range rings, radial spokes, centre crosshair, compass
  // labels. Never varies with range or traffic, so computed once.
  const chrome = useMemo(() => {
    const rings = []
    for (let i = 1; i <= 4; i++) {
      const outer = i === 4
      rings.push(
        <circle
          key={`ring-${i}`}
          cx={SCOPE_CX}
          cy={SCOPE_CY}
          r={r2(SCOPE_MAX_R * i / 4)}
          stroke="var(--text-dim)"
          fill="none"
          strokeWidth={outer ? 1 : 0.6}
          opacity={outer ? 0.75 : 0.4}
        />
      )
    }
    const spokes = []
    for (let s = 0; s < 12; s++) {
      const deg = s * 30
      const t = deg * Math.PI / 180
      const cardinal = deg % 90 === 0
      spokes.push(
        <line
          key={`spoke-${deg}`}
          x1={SCOPE_CX}
          y1={SCOPE_CY}
          x2={r2(SCOPE_CX + Math.sin(t) * SCOPE_MAX_R)}
          y2={r2(SCOPE_CY - Math.cos(t) * SCOPE_MAX_R)}
          stroke="var(--text-dim)"
          strokeWidth={cardinal ? 0.7 : 0.4}
          opacity={cardinal ? 0.5 : 0.22}
        />
      )
    }
    return (
      <g data-testid="radar-chrome">
        {rings}
        {spokes}
        {/* fill="none" is mandatory: SVG paths default to fill black. */}
        <path
          d={`M${SCOPE_CX - 6} ${SCOPE_CY} H${SCOPE_CX + 6} M${SCOPE_CX} ${SCOPE_CY - 6} V${SCOPE_CY + 6}`}
          stroke="var(--neon-cyan)"
          strokeWidth={0.9}
          opacity={0.85}
          fill="none"
        />
        <text x={SCOPE_CX} y={SCOPE_CY - SCOPE_MAX_R - 4} textAnchor="middle" fontFamily="var(--font-data)" fontSize={10} fill="var(--text-dim)">N</text>
        <text x={SCOPE_CX + SCOPE_MAX_R + 8} y={SCOPE_CY + 3} textAnchor="middle" fontFamily="var(--font-data)" fontSize={10} fill="var(--text-dim)">E</text>
        <text x={SCOPE_CX} y={SCOPE_CY + SCOPE_MAX_R + 11} textAnchor="middle" fontFamily="var(--font-data)" fontSize={10} fill="var(--text-dim)">S</text>
        <text x={SCOPE_CX - SCOPE_MAX_R - 8} y={SCOPE_CY + 3} textAnchor="middle" fontFamily="var(--font-data)" fontSize={10} fill="var(--text-dim)">W</text>
      </g>
    )
  }, [])

  // Filter, project, and trail-track aircraft. Guard BEFORE projecting so
  // no NaN coordinate can reach the SVG.
  //
  // Trail update/prune runs in this same useMemo (not a separate
  // useEffect) so the trail mutation happens in the same tick as the
  // render it feeds. A useEffect would run one render behind, showing
  // stale trail points on the first render after adsbAircraft changes.
  // This is a deliberate departure from normal React purity conventions —
  // flagged explicitly so a code reviewer doesn't read it as an
  // accidental anti-pattern.
  const contacts = useMemo(() => {
    const trails = trailsRef.current
    const liveIcaos = new Set(Object.keys(adsbAircraft))

    // Drop trail history for any ICAO no longer present at all.
    for (const icao of trails.keys()) {
      if (!liveIcaos.has(icao)) trails.delete(icao)
    }

    const result = []
    for (const ac of Object.values(adsbAircraft)) {
      if (!isValidContact(ac, maxRangeNm)) {
        // Bad frame (e.g. a callsign/altitude/velocity-only ADS-B
        // message carries no position): do NOT drop the aircraft for
        // this frame if we have a recent last-known position. ADS-B
        // messages are irregular, so one position-less frame does not
        // mean the aircraft's position became unknown. Passthrough of
        // last-known state only: no push, no evict, no staleness-clear
        // — the stored trail is left byte-for-byte untouched.
        const history = trails.get(ac.icao)
        if (!history || history.length === 0) continue
        const last = history[history.length - 1]
        const ts = ac.timestamp ?? Date.now()
        if (ts - last.ts > TRAIL_STALE_MS) continue
        const pos = projectToScope(
          last.bearing_deg, last.range_nm, maxRangeNm,
          SCOPE_CX, SCOPE_CY, SCOPE_MAX_R,
        )
        // Same trail projection as the valid path, over the existing
        // history, so the trail still renders behind the stale blip.
        const trailPoints = history
          .slice(0, -1)
          .filter((pt) => isWithinRange(pt.range_nm, maxRangeNm))
          .map((pt) => {
            const p = projectToScope(pt.bearing_deg, pt.range_nm, maxRangeNm, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
            return { x: r2(p.x), y: r2(p.y) }
          })
        result.push({
          ...ac,
          // Render from last-known position, not this frame's bad data.
          // Callsign still comes from the current frame (may fall back
          // to ICAO); the close/far blip radius uses the last-stored
          // range_nm — cosmetic only, both accepted by the Phase 50
          // fix-pass plan review.
          bearing_deg: last.bearing_deg,
          range_nm: last.range_nm,
          x: r2(pos.x),
          y: r2(pos.y),
          trailPoints,
        })
        continue
      }

      const pos = projectToScope(
        ac.bearing_deg, ac.range_nm, maxRangeNm,
        SCOPE_CX, SCOPE_CY, SCOPE_MAX_R,
      )

      // Trail bookkeeping. Note: gap-skip on null/NaN bearing_deg was
      // handled by the passthrough branch above, so the trail is only
      // ever mutated here for valid contacts. If a contact disappears
      // for a frame and reappears later, the staleness check below
      // will clear the trail appropriately.
      const ts = ac.timestamp ?? Date.now()
      let history = trails.get(ac.icao)
      if (!history) {
        history = []
        trails.set(ac.icao, history)
      }
      const last = history[history.length - 1]
      if (last && ts - last.ts > TRAIL_STALE_MS) {
        // Gap too large to imply continuous motion — start fresh
        // rather than drawing a straight line across dead time.
        history.length = 0
      }
      if (!last || last.ts !== ts) {
        history.push({ bearing_deg: ac.bearing_deg, range_nm: ac.range_nm, ts })
        if (history.length > TRAIL_MAX_POINTS) history.shift()
      }

      // Trail points, projected, excluding the current position
      // (which renders separately as the main blip). Only render
      // points that are still within the currently displayed range —
      // storage above is not range-limited, only rendering is.
      // `history` above is guaranteed non-null at this point.
      const trailPoints = history
        .slice(0, -1)
        .filter((pt) => isWithinRange(pt.range_nm, maxRangeNm))
        .map((pt) => {
          const p = projectToScope(pt.bearing_deg, pt.range_nm, maxRangeNm, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
          return { x: r2(p.x), y: r2(p.y) }
        })

      result.push({ ...ac, x: r2(pos.x), y: r2(pos.y), trailPoints })
    }
    return result
  }, [adsbAircraft, maxRangeNm])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {!isAdsbFreq ? (
        <div style={{
          padding: '8px 10px',
          fontFamily: 'var(--font-data)',
          fontSize: 12,
          color: 'var(--text-dim)',
        }}>
          Not tuned to ADS-B frequency
        </div>
      ) : (
        <div style={{ position: 'relative', flex: 1, overflow: 'hidden' }}>
          <svg
            width="100%"
            height="100%"
            viewBox="0 0 380 325"
            preserveAspectRatio="xMidYMid meet"
          >
            <defs>
              <filter id="mimir-radar-glow" x="-80%" y="-80%" width="260%" height="260%">
                <feGaussianBlur stdDeviation="2.4" result="blur"/>
                <feMerge>
                  <feMergeNode in="blur"/>
                  <feMergeNode in="SourceGraphic"/>
                </feMerge>
              </filter>
            </defs>
            {chrome}
            {contacts.map((ac) => {
              const showTrail = ac.trailPoints.length > 0
              const n = ac.trailPoints.length
              return (
                <g key={ac.icao} data-testid="radar-blip">
                  {showTrail && (
                    <>
                      <polyline
                        points={[...ac.trailPoints, { x: ac.x, y: ac.y }].map((p) => `${p.x},${p.y}`).join(' ')}
                        fill="none"
                        stroke="var(--neon-cyan)"
                        strokeWidth={1.2}
                        opacity={0.4}
                      />
                      {ac.trailPoints.map((pt, i) => (
                        <circle
                          key={`trail-${ac.icao}-${i}`}
                          cx={pt.x}
                          cy={pt.y}
                          r={r2(1.4 + (i / n) * 1.2)}
                          fill="var(--neon-cyan)"
                          opacity={r2(0.15 + (i / n) * 0.55)}
                        />
                      ))}
                    </>
                  )}
                  {/* Close contacts (inner 25% of range) get a larger blip. */}
                  <circle
                    cx={ac.x}
                    cy={ac.y}
                    r={ac.range_nm < maxRangeNm * 0.25 ? 3.1 : 2.2}
                    fill="var(--neon-cyan)"
                    filter="url(#mimir-radar-glow)"
                  />
                  <text
                    x={r2(ac.x + 7)}
                    y={r2(ac.y + 3)}
                    fontFamily="var(--font-data)"
                    fontSize={10}
                    fill="var(--neon-cyan)"
                  >
                    {ac.callsign || ac.icao}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>
      )}
    </div>
  )
}