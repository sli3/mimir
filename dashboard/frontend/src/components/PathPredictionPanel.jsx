import React, { useMemo } from 'react'
import { isValidContact } from './radar/projection.js'
import { formatDeltaR } from '../utils/aircraftFormat.js'
import {
  PREDICTION_HORIZON_SEC,
  derivePredictionVector,
  projectPosition,
} from '../utils/pathPrediction.js'
import LlmReasoningPanel from './LlmReasoningPanel.jsx'

/**
 * Path & Trajectory Prediction strip for the /radar page (Phase 52;
 * right column wired in Phase 53).
 *
 * Sits below the radar-scope-container as a fixed-height, two-column
 * strip. The LEFT column is a physics-only dead-reckoning readout:
 * bearing rate and range rate derived from the selected aircraft's
 * stored trail history, projected PREDICTION_HORIZON_SEC seconds ahead.
 * The RIGHT column is the Phase 53 LlmReasoningPanel child: a manual
 * "ANALYSE PATH WITH LLM" button that POSTs the physics facts to
 * /api/radar/reason and renders the verdict. PathPredictionPanel itself
 * still makes NO network, socket, or inference call of any kind — all
 * request state lives inside the child component.
 *
 * Three render states, mirroring the AircraftDetailPanel pattern:
 *   1. No selection (or the selected ICAO is gone) — placeholder text.
 *   2. Selection but fewer than 2 trail fixes — "gathering" text.
 *   3. Selection with 2+ trail fixes — physics readout + LlmReasoningPanel.
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

  // State 2: selected, but not enough history to derive a rate yet.
  // Normal startup state, not an error.
  if (!prediction || !prediction.vector) {
    const fixCount = prediction?.history?.length ?? 0
    return (
      <div className="radar-prediction-panel">
        <div
          className="radar-prediction-gathering"
          data-testid="radar-prediction-gathering"
        >
          {`${selected.callsign || selected.icao} — gathering position history (${fixCount} fix)`}
        </div>
      </div>
    )
  }

  // State 3: physics readout (left) + LlmReasoningPanel (right, Phase 53).
  // deltaR sign is rendered as-is via toFixed: a leading minus already
  // reads as "closing" and a bare number as "opening", so no explicit
  // '+' prefix is added (unlike formatDeltaR for theta).
  const { vector } = prediction
  return (
    <div className="radar-prediction-panel">
      <div
        className="radar-prediction-physics"
        data-testid="radar-prediction-physics"
      >
        {`θ: ${formatDeltaR(vector.thetaDegPerSec)}  Δr: ${vector.deltaRNmPerSec.toFixed(1)}nm/s — projecting ${PREDICTION_HORIZON_SEC}s ahead`}
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
  )
}
