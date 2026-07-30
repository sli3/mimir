import React, { useEffect, useMemo } from 'react'
import { projectToScope, isWithinRange } from './radar/projection.js'

// Phase 49 tech-debt markers (recorded in AGENTS.md by the /finalise-build
// run, NOT by this build):
// TD-49-1 — Label overlap: callsign labels are placed at their projected
//   coordinate with no collision-avoidance solver. Two close aircraft
//   will overprint each other's labels, and the blip glow filter makes
//   overlapping markers visually merge as well. Out of scope for Phase 49.

const SCOPE_CX = 190
const SCOPE_CY = 162.5
const SCOPE_MAX_R = 150

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
 * @param {Object} adsbAircraft - Map of ICAO address -> aircraft state
 * @param {number|null} focusedFreq - Currently tuned frequency in Hz
 * @param {number} maxRangeNm - Maximum displayed range, in nautical miles
 */
export default function RadarScopePanel({ adsbAircraft = {}, focusedFreq, maxRangeNm = 40 }) {
  const isAdsbFreq = focusedFreq && (
    Math.abs(focusedFreq - 1_090_000_000) <= 2_000_000
  )

  // Intentionally empty body, load-bearing dep. The SVG below is only
  // mounted when tuned to 1090 MHz; keeping this effect keyed on
  // isAdsbFreq preserves the tune-in mount-lifecycle contract fixed by
  // CRIT-01 for any future renderer state that attaches here. With the
  // SVG renderer there is nothing to measure, so the body is trivially
  // safe.
  useEffect(() => {}, [isAdsbFreq])

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

  // Filter and project aircraft. Guard BEFORE projecting so no NaN
  // coordinate can reach the SVG.
  const contacts = useMemo(() => (
    Object.values(adsbAircraft)
      .filter((ac) => {
        if (ac.bearing_deg === null || ac.bearing_deg === undefined) return false
        if (Number.isNaN(ac.bearing_deg)) return false  // NaN passes null/undefined check; would reach sin/cos and emit NaN into SVG
        return isWithinRange(ac.range_nm, maxRangeNm)
      })
      .map((ac) => {
        const pos = projectToScope(
          ac.bearing_deg, ac.range_nm, maxRangeNm,
          SCOPE_CX, SCOPE_CY, SCOPE_MAX_R,
        )
        return { ...ac, x: r2(pos.x), y: r2(pos.y) }
      })
  ), [adsbAircraft, maxRangeNm])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{
        height: '28px',
        flexShrink: 0,
        background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        padding: '0 10px',
        justifyContent: 'space-between',
      }}>
        <span style={{
          fontSize: '11px',
          color: 'var(--neon-cyan)',
          letterSpacing: '2px',
          fontFamily: 'var(--font-data)',
        }}>
          RADAR SCOPE
        </span>
        <span style={{
          fontSize: '11px',
          color: 'var(--text-dim)',
          letterSpacing: '1px',
          fontFamily: 'var(--font-data)',
        }}>
          {contacts.length} CONTACTS · {maxRangeNm}NM
        </span>
      </div>
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
            {contacts.map((ac) => (
              <g key={ac.icao} data-testid="radar-blip">
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
            ))}
          </svg>
        </div>
      )}
    </div>
  )
}
