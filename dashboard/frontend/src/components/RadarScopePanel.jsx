import React, { useMemo, useRef } from 'react'
import { projectToScope, isWithinRange, isValidContact } from './radar/projection.js'
import { PREDICTION_HORIZON_SEC, derivePredictionVector, projectPosition } from '../utils/pathPrediction.js'
import { formatDeltaR } from '../utils/aircraftFormat.js'

// The timestamp arriving from the backend is an ISO 8601 string (see server.py:666),
// and the trail buffer does arithmetic on it, so it must be coerced to numeric ms
// at the point of use. See parseFrameTs.js for the full rationale.
import { parseFrameTs } from '../utils/parseFrameTs.js'

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
 * @param {string|null} selectedIcao - ICAO of the currently selected
 *   aircraft; its blip gets an amber highlight ring (Phase 51)
 * @param {Function} [onSelectAircraft] - Called with the icao string
 *   when a blip is clicked (Phase 51)
 */
export default function RadarScopePanel({
  adsbAircraft = {},
  focusedFreq,
  maxRangeNm = 40,
  selectedIcao = null,
  onSelectAircraft,
  trailsRef: trailsRefProp = null,   // NEW: optional lifted ref (Phase 52)
}) {
  const isAdsbFreq = focusedFreq && (
    Math.abs(focusedFreq - 1_090_000_000) <= 2_000_000
  )

  // Per-ICAO trail history: icao -> [{ bearing_deg, range_nm, ts }, ...],
  // oldest first, capped at TRAIL_MAX_POINTS. A ref, not state, because
  // trail mutation is a side effect of processing adsbAircraft and must
  // not itself trigger an extra re-render.
  // Phase 52: trailsRef is normally owned by RadarPage so the new
  // PathPredictionPanel can read the same history. The own-ref fallback
  // keeps standalone mounting (e.g. existing tests) working without
  // violating the rules of hooks: useRef is called unconditionally
  // every render, the ?? pick is just at the read site.
  const ownTrailsRef = useRef(new Map())
  const trailsRef = trailsRefProp ?? ownTrailsRef

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
        const ts = parseFrameTs(ac.timestamp)
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
      const ts = parseFrameTs(ac.timestamp)
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
                <g
                  key={ac.icao}
                  data-testid="radar-blip"
                  data-icao={ac.icao}
                  onClick={() => onSelectAircraft?.(ac.icao)}
                  style={{ cursor: 'pointer' }}
                >
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
                  {/* Phase 52: projected ghost line for the selected aircraft only.
                      Physics-only linear extrapolation from oldest/newest trail points,
                      fading toward the projected end. No prediction renders if <2 trail
                      points exist yet (normal startup state, not an error). Rendered
                      before the main blip so the cyan blip and amber selection ring
                      still visually sit on top (consistent with existing z-order). */}
                  {ac.icao === selectedIcao && (() => {
                    const history = trailsRef.current.get(ac.icao)
                    // ADV-02 (Phase 58-FIX): a trail can yield a truthy
                    // but non-finite vector (e.g. a NaN bearing_deg in an
                    // older fix produces thetaDegPerSec = NaN). Collapse
                    // any such vector to null so the box falls back to
                    // the ICAO-only path rather than rendering "θ NaN" on
                    // a live monitoring display.
                    const rawV = history && history.length >= 2
                      ? derivePredictionVector(history)
                      : null
                    const v = rawV
                      && Number.isFinite(rawV.thetaDegPerSec)
                      && Number.isFinite(rawV.deltaRNmPerSec)
                      ? rawV
                      : null
                    const proj = v
                      ? projectPosition(ac.bearing_deg, ac.range_nm, v.thetaDegPerSec, v.deltaRNmPerSec, PREDICTION_HORIZON_SEC)
                      : null
                    const label = ac.callsign || ac.icao
                    // Real direction vector, computed EARLY (moved up from
                    // its previous position after the box) because the box's
                    // side-placement now depends on it. `there` and `proj`
                    // are still needed for the dashed line's direction too —
                    // this is the SAME computation, just no longer
                    // duplicated or deferred.
                    //
                    // Clamp the projected range to the outer ring: an aircraft
                    // projecting beyond maxRangeNm still shows a line ending at
                    // the ring edge, rather than vanishing. A fast-departing
                    // aircraft hitting the ring is genuinely informative, not
                    // noise (Phase 52 follow-up — originally this branch
                    // silently hid the line past maxRangeNm; the bearing is
                    // unaffected by the clamp, only the range component).
                    const clampedRangeNm = proj ? Math.min(proj.range_nm, maxRangeNm) : null
                    const here = projectToScope(ac.bearing_deg, ac.range_nm, maxRangeNm, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
                    const there = proj
                      ? projectToScope(proj.bearing_deg, clampedRangeNm, maxRangeNm, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
                      : null
                    const dx = there ? there.x - here.x : 0
                    const dy = there ? there.y - here.y : 0
                    // Keep the detail box away from the ACTUAL direction the
                    // line/dots point on screen — not just the sign of
                    // thetaDegPerSec. Fixed 2026-08-09 (live traffic:
                    // 7C389F, 7C2EB8): the old theta-only heuristic ignored
                    // deltaR's contribution to the real (dx, dy) direction,
                    // so whenever range-rate's effect outweighed bearing-
                    // rate's, the box landed on the SAME side as the line
                    // instead of away from it, causing visible overlap. dx
                    // (horizontal screen direction) is the correct signal:
                    // if the true direction points right, put the box left,
                    // and vice versa.
                    const boxOnLeft = !v || dx >= 0
                    // BOX_PAD_X: horizontal gap (px) between the rect's
                    // border and the text sitting inside it. Previously
                    // 0 — boxX (the text's own anchor coordinate) was
                    // reused as the rect's edge coordinate, so text sat
                    // flush against the border on the anchor side, with
                    // no inset (Phase 58-FIX-2, live-verified against
                    // Prin's screenshot).
                    const BOX_PAD_X = 6
                    const boxWidth = 86
                    // The rect's outer edge is unchanged from before —
                    // only the text is inset from it by BOX_PAD_X.
                    const rectEdgeX = r2(ac.x + (boxOnLeft ? -10 - boxWidth : 10))
                    const rectX = rectEdgeX
                    const boxX = r2(boxOnLeft ? rectEdgeX + boxWidth - BOX_PAD_X : rectEdgeX + BOX_PAD_X)
                    const textAnchor = boxOnLeft ? 'end' : 'start'
                    // Box top stays fixed relative to the blip. The per-line
                    // baselines are derived FROM rectY below so the box's
                    // vertical position is decoupled from the line spacing
                    // (the Phase 58-FIX padding correction increases the
                    // box height without shifting the box top).
                    const rectY = r2(ac.y - (v ? 25 : 13))
                    // Vector box is 43px tall (was 36) to give ~6px of
                    // internal padding top and bottom around the 3-line
                    // readout at 9px font. The extra 7px extends the box
                    // downward (the top stays at ac.y - 25); the box sits
                    // to the SIDE of the blip (>=10px gap), so the taller
                    // box does not collide with the blip or selection ring.
                    const boxHeight = v ? 43 : 14
                    const box = (
                      <g data-testid="radar-prediction-box" data-icao={ac.icao}>
                        <rect
                          x={rectX}
                          y={rectY}
                          width={boxWidth}
                          height={boxHeight}
                          fill="var(--bg-header, #050C11)"
                          stroke="var(--neon-amber)"
                          strokeWidth={0.6}
                          opacity={0.92}
                        />
                        <text
                          x={boxX}
                          y={r2(rectY + (v ? 15 : 10))}
                          textAnchor={textAnchor}
                          fontFamily="var(--font-data)"
                          fontSize={9}
                          fill="var(--neon-cyan)"
                        >
                          {label}
                        </text>
                        {v && (
                          <>
                            <text
                              x={boxX}
                              y={r2(rectY + 26)}
                              textAnchor={textAnchor}
                              fontFamily="var(--font-data)"
                              fontSize={9}
                              fill="var(--text-primary)"
                            >
                              {`θ ${formatDeltaR(v.thetaDegPerSec)}`}
                            </text>
                            <text
                              x={boxX}
                              y={r2(rectY + 37)}
                              textAnchor={textAnchor}
                              fontFamily="var(--font-data)"
                              fontSize={9}
                              fill="var(--text-primary)"
                            >
                              {`Δr ${v.deltaRNmPerSec.toFixed(2)}nm/s`}
                            </text>
                          </>
                        )}
                      </g>
                    )
                    if (!proj) return box
                    // Direction indicator: a fixed-length on-screen line from a point
                    // offset 8 px from `here` (the blip centre) toward the same true
                    // bearing+range direction as the underlying vector (`here` -> `there`),
                    // with three evenly-spaced marker dots along it. The start offset keeps
                    // the near end of the line and dot1 clear of the blip's own selection
                    // ring (r=6). This is NOT a to-scale forecast of where the aircraft
                    // will physically be at any time horizon — it is a supplementary
                    // visual cue only, normalised to a constant on-screen length so
                    // the direction reads at a glance regardless of the true rate's
                    // magnitude. The dashed line shares the same start/end points as the
                    // dots (both end at dot3), so only the vector box shows the true
                    // 45s clamped position (`there`).
                    //
                    // Multiplier 0.22 (increased from the original 0.15 spec
                    // default): live-verified 2026-08-08 against real
                    // traffic (7C6DB4) that 0.15 with no ring offset put
                    // dot1 landing inside the blip's own selection ring
                    // (r=6, see radar-blip-highlight above), visually
                    // merging the near end of the indicator with the ring
                    // rather than reading as a separate directional cue.
                    // 33px on a 150px scope radius gives clearer separation
                    // between dot1/dot2/dot3 while still staying clear of
                    // the vector box (>= 10 px to the side of the blip), now
                    // that the box itself is placed using the real direction.
                    const trueLength = Math.sqrt(dx * dx + dy * dy)
                    const GHOST_LINE_LENGTH_PX = SCOPE_MAX_R * 0.22
                    // RING_CLEARANCE_PX: the indicator's start point is offset
                    // outward from `here` (the blip centre) by this distance,
                    // along the same direction, so the near end of the line
                    // and dot1 sit clear of the blip's own selection ring
                    // instead of overlapping it. 8px covers the ring's larger
                    // radius (6px, close-range case) plus a small margin so
                    // the line's dash pattern and dot1's own radius (1.8px)
                    // don't touch the ring either.
                    const RING_CLEARANCE_PX = 8
                    // Degenerate guard: a non-null vector can still produce a
                    // sub-pixel on-screen displacement (tiny theta/deltaR). In
                    // that case render the line + box but NO dots — no NaN or
                    // zero-length direction may leak into SVG attributes. The
                    // box's θ/Δr readouts correctly indicate "no meaningful
                    // motion" for this case, so nothing is lost. In the
                    // degenerate case the line falls back to the true
                    // (unclamped-endpoint) `there`, consistent with the box.
                    const indicator = trueLength >= 0.01 ? (() => {
                      const ux = dx / trueLength
                      const uy = dy / trueLength
                      // Indicator start: `here` pushed out past the selection
                      // ring, along the same direction as the true vector, so
                      // the near end of the line and dot1 sit clear of the
                      // ring instead of overlapping it.
                      const startX = here.x + ux * RING_CLEARANCE_PX
                      const startY = here.y + uy * RING_CLEARANCE_PX
                      const fixedDx = ux * GHOST_LINE_LENGTH_PX
                      const fixedDy = uy * GHOST_LINE_LENGTH_PX
                      return {
                        start: { x: startX, y: startY },
                        dot1: { x: startX + fixedDx * (1 / 3), y: startY + fixedDy * (1 / 3) },
                        dot2: { x: startX + fixedDx * (2 / 3), y: startY + fixedDy * (2 / 3) },
                        dot3: { x: startX + fixedDx, y: startY + fixedDy },
                      }
                    })() : null
                    // Line endpoint: when the indicator renders
                    // (non-degenerate), the dashed line runs from the SAME
                    // ring-cleared start point to the SAME dot3 endpoint as
                    // the ghost dots — never a separate/different endpoint.
                    // Fixed 2026-08-08 (live traffic: 7C7772) after the line
                    // and dots previously used two different endpoints and
                    // visibly diverged. In the degenerate case (no
                    // indicator), the line falls back to `here` -> `there`,
                    // consistent with the box's θ/Δr readout.
                    const lineStart = indicator ? indicator.start : here
                    const lineEnd = indicator ? indicator.dot3 : there
                    const ghosts = indicator ? (
                      // Ghost dots render AFTER the line so they are not
                      // occluded by the dashed stroke. Size and opacity
                      // increase along the direction of travel (nearest
                      // dim/small, furthest bright/large). Colour matches
                      // the line (neon-amber). Every coordinate passes
                      // through r2() so no NaN or float noise can reach an
                      // SVG attribute.
                      <g data-testid="radar-prediction-ghosts" data-icao={ac.icao}>
                        <circle
                          data-testid="radar-prediction-ghost-dot"
                          data-position="1"
                          cx={r2(indicator.dot1.x)}
                          cy={r2(indicator.dot1.y)}
                          r={1.8}
                          fill="var(--neon-amber)"
                          opacity={0.35}
                        />
                        <circle
                          data-testid="radar-prediction-ghost-dot"
                          data-position="2"
                          cx={r2(indicator.dot2.x)}
                          cy={r2(indicator.dot2.y)}
                          r={2.4}
                          fill="var(--neon-amber)"
                          opacity={0.6}
                        />
                        <circle
                          data-testid="radar-prediction-ghost-dot"
                          data-position="3"
                          cx={r2(indicator.dot3.x)}
                          cy={r2(indicator.dot3.y)}
                          r={3.0}
                          fill="var(--neon-amber)"
                          opacity={0.85}
                        />
                      </g>
                    ) : null
                    return (
                      <>
                        <g data-testid="radar-prediction-line" data-icao={ac.icao}>
                          <line
                            x1={r2(lineStart.x)}
                            y1={r2(lineStart.y)}
                            x2={r2(lineEnd.x)}
                            y2={r2(lineEnd.y)}
                            stroke="var(--neon-amber)"
                            strokeWidth={1.2}
                            strokeDasharray="4 3"
                            opacity={0.7}
                          />
                        </g>
                        {ghosts}
                        {box}
                      </>
                    )
                  })()}

                  {/* Close contacts (inner 25% of range) get a larger blip. */}
                  <circle
                    cx={ac.x}
                    cy={ac.y}
                    r={ac.range_nm < maxRangeNm * 0.25 ? 3.1 : 2.2}
                    fill="var(--neon-cyan)"
                    filter="url(#mimir-radar-glow)"
                  />
                  {/* Selection ring (Phase 51). MUST render AFTER the
                      main blip circle above: existing tests select the
                      first circle inside a blip group and expect the
                      main blip's coordinates. Amber is distinct from
                      the cyan glow so the selection reads at a glance. */}
                  {ac.icao === selectedIcao && (
                    <circle
                      data-testid="radar-blip-highlight"
                      cx={ac.x}
                      cy={ac.y}
                      r={ac.range_nm < maxRangeNm * 0.25 ? 6 : 5}
                      fill="none"
                      stroke="var(--neon-amber)"
                      strokeWidth={1.2}
                    />
                  )}
                  {ac.icao !== selectedIcao && (
                    <text
                      x={r2(ac.x + 7)}
                      y={r2(ac.y + 3)}
                      fontFamily="var(--font-data)"
                      fontSize={10}
                      fill="var(--neon-cyan)"
                    >
                      {ac.callsign || ac.icao}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
        </div>
      )}
    </div>
  )
}