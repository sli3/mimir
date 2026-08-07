import React, { useMemo } from 'react'
import { isValidContact } from './radar/projection.js'
import {
  PREDICTION_HORIZON_SEC,
  derivePredictionVector,
  projectPosition,
} from '../utils/pathPrediction.js'
import LlmReasoningPanel from './LlmReasoningPanel.jsx'
import PredictionGlyph from './PredictionGlyph.jsx'

// Must mirror llm/path_reasoner.py's _EMERGENCY_SQUAWKS set.
const EMERGENCY_SQUAWKS = new Set(['7500', '7600', '7700'])

// Squawk is read from the per-frame aircraft object, not motion-derived.
const RAPID_ALTITUDE_CHANGE_FT_PER_MIN = 3000

// Must stay paired with llm/path_reasoner.py:_HIGH_TURN_RATE_DEG_PER_SEC.
// Contract test: tests/llm/test_path_reasoner_thresholds.py
const HIGH_TURN_RATE_DEG_PER_SEC = 3.0

/**
 * Path & Trajectory Prediction strip for the /radar page (Phase 52;
 * LLM column wired in Phase 53; restructured Phase 58-FIX-4).
 *
 * Sits below the radar-scope-container as a fixed-height strip. The
 * panel is a single-column flex container (Phase 58-FIX-4 replaced the
 * old 2-column grid, whose right-hand anomaly sidebar read as a
 * disconnected floating box). In state 3 the prediction glyph and the
 * anomaly flag strip sit side-by-side inside .radar-prediction-glyph-
 * row, with the Phase 53 LlmReasoningPanel (a manual "ANALYSE PATH WITH
 * LLM" button that POSTs the physics facts to /api/radar/reason and
 * renders the verdict) full-width underneath. In state 2 the anomaly
 * strip is a sibling block below the gathering text. PathPredictionPanel
 * itself still makes NO network, socket, or inference call of any kind
 * — all request state lives inside the child component.
 *
 * The θ/Δr physics readout that previously lived here as a third
 * on-screen copy was removed in Phase 58-FIX: that data now lives in
 * the floating scope box on the selected aircraft's blip, so rendering
 * it a third time here was redundant.
 *
 * Three render states, mirroring the AircraftDetailPanel pattern:
 *   1. No selection (or the selected ICAO is gone) — placeholder text.
 *   2. Selection but fewer than 2 trail fixes — "gathering" text, with
 *      the anomaly strip as a sibling below .radar-prediction-main.
 *   3. Selection with 2+ trail fixes — prediction glyph + anomaly strip
 *      inside .radar-prediction-glyph-row, plus LlmReasoningPanel full-
 *      width underneath (the anomaly strip renders in states 2 and 3;
 *      only its position in the tree differs between them).
 *
 * Passive receive display only — no TX capability, no inference calls
 * from this component (the LLM column is a separate child).
 *
 * @param {Object} adsbAircraft - Map of ICAO address -> aircraft state
 * @param {string|null} selectedIcao - Currently selected ICAO address
 * @param {Object} trailsRef - Read-only access to the shared
 *   Map<icao, trail[]> owned (and solely written) by RadarScopePanel
 * @param {number} maxRangeNm - Maximum displayed range, in nautical
 *   miles. Only used for the "has a current position" guard, mirroring
 *   the valid-contact rule the scope and detail panel apply.
 *
 * Child components:
 *   LlmReasoningPanel — receives icao/callsign/squawk, the per-frame
 *   ADS-B fields (altitude_ft, track, groundspeed, vertical_rate), the
 *   current bearing_deg/range_nm, the derived motion vector, the 45 s
 *   projected position, and the trail length. Owns the entire fetch
 *   lifecycle (idle/loading/result/error) for the LLM column.
 */
export default function PathPredictionPanel({
  adsbAircraft = {},
  selectedIcao = null,
  trailsRef = { current: new Map() },
  maxRangeNm = 40,
}) {
  // Same defensive pattern as AircraftDetailPanel.jsx: a selected ICAO
  // that has dropped out of the aircraft map is treated as no selection.
  // `?? {}` covers an explicit null adsbAircraft, which the prop default
  // (undefined only) does not.
  const acMap = adsbAircraft ?? {}
  const selected = selectedIcao ? (acMap[selectedIcao] ?? null) : null

  const prediction = useMemo(() => {
    // Guard invalid (passthrough) frames here too: projectPosition on a
    // null bearing would produce NaN. The render path below also checks
    // isValidContact, but the memo should never compute garbage.
    if (!selected || !isValidContact(selected, maxRangeNm)) return null
    // PathPredictionPanel MUST NOT mutate trailsRef; RadarScopePanel is
    // the sole writer. This component only ever reads the Map, so no
    // cross-component write race can exist. Optional chaining covers an
    // explicit null trailsRef, which the prop default does not.
    const history = trailsRef?.current?.get(selectedIcao)
    const vector = derivePredictionVector(history)
    if (!vector) return { history, vector: null, projected: null }
    // Project from the aircraft's CURRENT reported position (this
    // frame's bearing/range), not the last trail point: the trail's
    // newest fix can lag the live frame by one update.
    const projected = projectPosition(
      selected.bearing_deg,
      selected.range_nm,
      vector.thetaDegPerSec,
      vector.deltaRNmPerSec,
      PREDICTION_HORIZON_SEC,
    )
    return { history, vector, projected }
  }, [selectedIcao, adsbAircraft]) // eslint-disable-line react-hooks/exhaustive-deps
  // trailsRef is a stable ref; including it would not change memo hits.

  // State 1: no selection, selected aircraft gone, or — spec "your
  // call" decision — the selected aircraft currently carries no valid
  // position (a passthrough frame). An aircraft with no current
  // position is not a valid contact by the existing projection.js rule,
  // and extrapolating from a frame with no position would be
  // meaningless, so it renders the no-selection placeholder. The text
  // differs from the plain "nothing selected" case so the operator can
  // tell the two apart.
  if (!selected) {
    return (
      <div className="radar-prediction-panel">
        <div
          className="radar-prediction-placeholder"
          data-testid="radar-prediction-placeholder"
        >
          No aircraft selected
        </div>
      </div>
    )
  }
  if (!isValidContact(selected, maxRangeNm)) {
    return (
      <div className="radar-prediction-panel">
        <div
          className="radar-prediction-placeholder"
          data-testid="radar-prediction-placeholder"
        >
          No current position for selected aircraft
        </div>
      </div>
    )
  }

  const isEmergencySquawk = EMERGENCY_SQUAWKS.has(selected.squawk)
  const isRapidAltitude = Number.isFinite(selected.vertical_rate)
    && Math.abs(selected.vertical_rate) > RAPID_ALTITUDE_CHANGE_FT_PER_MIN
  const isHighTurnRate = Boolean(
    prediction?.vector
    && Math.abs(prediction.vector.thetaDegPerSec) > HIGH_TURN_RATE_DEG_PER_SEC,
  )
  const anomalyStrip = (
    <div className="radar-anomaly-strip" data-testid="radar-anomaly-strip">
      {isEmergencySquawk && (
        <div data-testid="anomaly-flag-squawk" className="anomaly-flag anomaly-flag-emergency">
          ⚠ EMERGENCY SQUAWK {selected.squawk}
        </div>
      )}
      {isRapidAltitude && (
        <div data-testid="anomaly-flag-altitude" className="anomaly-flag anomaly-flag-warn">
          ▲ RAPID ALTITUDE {selected.vertical_rate > 0 ? 'CLIMB' : 'DESCENT'} {Math.abs(selected.vertical_rate)} ft/min
        </div>
      )}
      {isHighTurnRate && (
        <div data-testid="anomaly-flag-turn" className="anomaly-flag anomaly-flag-warn">
          ↻ HIGH TURN RATE {Math.abs(prediction.vector.thetaDegPerSec).toFixed(1)}°/s
        </div>
      )}
      {!isEmergencySquawk && !isRapidAltitude && !isHighTurnRate && (
        <div data-testid="anomaly-strip-clear" className="anomaly-strip-clear">NO ANOMALIES</div>
      )}
    </div>
  )

  // State 2: selected, but not enough history to derive a rate yet.
  // Normal startup state, not an error. The anomaly strip still
  // renders (squawk / rapid-altitude flags are vector-independent);
  // only the high-turn-rate flag is gated on a vector, so it cannot
  // fire in this state.
  if (!prediction || !prediction.vector) {
    const fixCount = prediction?.history?.length ?? 0
    return (
      <div className="radar-prediction-panel">
        <div className="radar-prediction-main">
          <div
            className="radar-prediction-gathering"
            data-testid="radar-prediction-gathering"
          >
            {`${selected.callsign || selected.icao} — gathering position history (${fixCount} fix)`}
          </div>
        </div>
        {anomalyStrip}
      </div>
    )
  }

  // State 3: prediction glyph + anomaly strip sit side-by-side inside
  // .radar-prediction-glyph-row (Phase 58-FIX-4), with LlmReasoningPanel
  // full-width underneath in the same .radar-prediction-main column.
  // The standalone θ/Δr physics readout that used to live here was
  // removed in Phase 58-FIX — its data is in the floating scope box on
  // the selected aircraft's blip, so a third copy here was redundant.
  return (
    <div className="radar-prediction-panel">
      <div className="radar-prediction-main">
        <div className="radar-prediction-glyph-row">
          <PredictionGlyph vector={prediction.vector} />
          {anomalyStrip}
        </div>
        <LlmReasoningPanel
          icao={selectedIcao}
          callsign={selected.callsign ?? null}
          squawk={selected.squawk ?? null}
          altitude_ft={selected.altitude_ft ?? null}
          track={selected.track ?? null}
          groundspeed={selected.groundspeed ?? null}
          vertical_rate={selected.vertical_rate ?? null}
          bearing_deg={selected.bearing_deg}
          range_nm={selected.range_nm}
          vector={prediction.vector}
          projected={prediction.projected}
          trailLength={prediction.history?.length ?? 0}
        />
      </div>
    </div>
  )
}
