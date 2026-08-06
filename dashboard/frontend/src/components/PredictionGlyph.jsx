import React from 'react'

/**
 * Prediction glyph for the /radar LLM reasoning result block (Phase 55).
 *
 * A small SVG showing the derived prediction vector as a horizontal row
 * of five dots joined by a dashed connector: two solid "history" dots on
 * the left, three "ghost" projection dots on the right. The 2-solid +
 * 3-ghost split was chosen (over 3+2) to give the projection more visual
 * room - the operator cares where the aircraft is GOING more than where
 * it has been, and three ghost dots let the opacity decay (1.0 -> 0.6 ->
 * 0.3) read as a trail fading into the future, reusing the established
 * trail-fade convention.
 *
 * Angle derivation:
 *   visualAngle = clamp(vector.thetaDegPerSec, -45, +45), applied as a
 *   rotation of the whole dot row about its centre dot. Linear scale:
 *   1 deg/s of bearing rate = 1 degree of visual deflection, capped at
 *   +/-45 degrees. Zero thetaDegPerSec renders flat horizontal with NO
 *   rotation transform applied at all.
 *
 *   thetaDegPerSec describes angular motion around the receiver and so
 *   maps naturally onto a visual rotation angle. deltaRNmPerSec
 *   describes range change (closing/opening) and has no natural mapping
 *   onto a visual rotation angle; it is deliberately UNUSED in the angle
 *   computation and stands as a documented future extension point (for
 *   example, pulse speed or dot spacing could one day encode range
 *   rate) - not an omission. The spec's "the glyph's angle is derived
 *   from the vector prop" is read as "the prop containing both fields
 *   is available"; this component elects the theta field for the angle.
 *
 *   The clamp is VISUAL ONLY: the prop is never mutated and the clamped
 *   value never leaves this component, so nothing here affects the
 *   payload posted to /api/radar/reason.
 *
 * Purity contract: no hooks, no socket listeners, no timers, no
 * requestAnimationFrame - the pulse animation is CSS-only (the
 * .prediction-glyph-pulse keyframes in RadarPage.css, gated on
 * prefers-reduced-motion). Wrapped in React.memo because the component
 * is a pure function of one small prop object; without memo it would
 * re-render on every LlmReasoningPanel state change (loading-message
 * escalation, result arrival) for an identical SVG.
 *
 * viewBox "0 0 200 90": the dot row is 120 units long, so at the +/-45
 * degree clamp its endpoints swing 60 * sin(45°) ~= 42.4 units above and
 * below the row centre. Centring the row at y=45 in a 90-unit-tall box
 * keeps the endpoints at y ~= 2.6..87.4 - never clipped at the visual
 * extremes - while staying short enough to sit above the verdict
 * without fighting the result text for vertical space.
 *
 * Passive receive display only - re-presents the already-derived
 * prediction vector; no data is requested and no TX capability exists.
 *
 * @param {{thetaDegPerSec: number, deltaRNmPerSec: number}|null} vector -
 *   derivePredictionVector() result. Null/undefined renders nothing; the
 *   parent owns the absent state.
 */
const VISUAL_ANGLE_CLAMP_DEG = 45

function PredictionGlyph({ vector }) {
  if (vector === null || vector === undefined) return null

  // Defensive: a non-finite theta collapses to zero (flat) rather than
  // producing a broken transform string. Finite values clamp to the
  // +/-45 degree visual range.
  const theta = Number.isFinite(vector.thetaDegPerSec) ? vector.thetaDegPerSec : 0
  const visualAngle = Math.max(
    -VISUAL_ANGLE_CLAMP_DEG,
    Math.min(VISUAL_ANGLE_CLAMP_DEG, theta),
  )

  // Dot geometry: five dots on y=45, spaced 30 units apart from x=40
  // (leftmost solid) to x=160 (rightmost ghost). The rotation centre is
  // the middle dot at (100, 45). The first two dots are solid cyan
  // (history); the last three are amber ghosts with a linearly decaying
  // opacity (projection).
  const dots = [
    { cx: 40, solid: true, opacity: 1 },
    { cx: 70, solid: true, opacity: 1 },
    { cx: 100, solid: false, opacity: 1 },
    { cx: 130, solid: false, opacity: 0.6 },
    { cx: 160, solid: false, opacity: 0.3 },
  ]

  return (
    <svg
      data-testid="prediction-glyph"
      className="prediction-glyph"
      viewBox="0 0 200 90"
      aria-hidden="true"
    >
      <g
        data-testid="prediction-glyph-row"
        transform={
          visualAngle === 0 ? undefined : `rotate(${visualAngle} 100 45)`
        }
      >
        {/* Dashed connector behind the dots, amber to match the ghost
            projection colour. */}
        <line
          x1="40"
          y1="45"
          x2="160"
          y2="45"
          stroke="var(--neon-amber, #FFCC00)"
          strokeWidth="1"
          strokeDasharray="4 3"
        />
        {dots.map((d) => (
          <circle
            key={d.cx}
            cx={d.cx}
            cy="45"
            r="4"
            fill={
              d.solid
                ? 'var(--neon-cyan, #00FFFF)'
                : 'var(--neon-amber, #FFCC00)'
            }
            opacity={d.opacity}
          />
        ))}
        {/* Pulse marker: a small amber dot the CSS keyframes translate
            along the row from the leftmost solid dot to the rightmost
            ghost dot (translateX 0 -> 120 units). It lives inside the
            rotated group so the pulse travels along the projected
            direction, not the screen horizontal. Animation is CSS-only;
            see .prediction-glyph-pulse in RadarPage.css. */}
        <circle
          className="prediction-glyph-pulse"
          cx="40"
          cy="45"
          r="2"
          fill="var(--neon-amber, #FFCC00)"
        />
      </g>
    </svg>
  )
}

export default React.memo(PredictionGlyph)
