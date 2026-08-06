import React, { useEffect, useRef, useState } from 'react'
import PredictionGlyph from './PredictionGlyph.jsx'

/**
 * LLM Reasoning column for the /radar Path & Trajectory Prediction
 * panel (Phase 53).
 *
 * This component owns ALL request state for the manual LLM trajectory
 * analysis. It is only ever mounted by PathPredictionPanel in State 3
 * (a selected aircraft with 2+ trail fixes), so the trigger button is
 * effectively always present when this component renders.
 *
 * Four states:
 *   1. idle    — button enabled, inviting the click.
 *   2. loading — button replaced by a two-stage message: "ANALYSING…"
 *      for the first 10 s, then "ANALYSING — SERVER BUSY…" past 10 s.
 *   3. result  — verdict headline, confidence word (colour-coded), notes.
 *   4. error   — one of three user-facing messages, mapped from the
 *      structured cause the fetch wrapper attaches (see ERROR_MESSAGES).
 *
 * Lifecycle guards (the sharp edges of this state machine):
 *   a. Reset to idle whenever the selected ICAO changes — a stale
 *      verdict for aircraft A must never display against aircraft B.
 *   b. Every fetch carries an AbortController; the in-flight request is
 *      aborted when the ICAO changes or the component unmounts.
 *   c. A late response (resolving after the ICAO changed) is dropped:
 *      the request's captured ICAO is compared against a live ref.
 *   d. No setState after unmount: a mounted ref is checked before every
 *      state transition in the async continuation.
 *
 * Passive receive display only — the endpoint performs inference over
 * already-received ADS-B data; no TX capability of any kind.
 *
 * @param {string} icao - Selected aircraft ICAO address (6 hex chars)
 * @param {string|null} callsign - Last known callsign, or null
 * @param {string|null} squawk - Transponder code, or null. Always null
 *   from real data today (TD-53-A: Mimir's PipeDecoder does not decode
 *   the DF4/DF5 replies that carry squawk) — accepted for future use.
 * @param {number|null} altitude_ft
 * @param {number|null} track
 * @param {number|null} groundspeed
 * @param {number|null} vertical_rate
 * @param {number} bearing_deg - Current bearing from receiver (degrees)
 * @param {number} range_nm - Current range from receiver (nautical miles)
 * @param {{thetaDegPerSec: number, deltaRNmPerSec: number}|null} vector -
 *   derivePredictionVector() result (non-null in State 3)
 * @param {{bearing_deg: number, range_nm: number}|null} projected -
 *   projectPosition() result (non-null in State 3)
 * @param {number} trailLength - Number of trail fixes the vector was
 *   derived from
 */

// Milliseconds before the loading message escalates to the "server busy"
// variant. Matches the two-stage copy defined in the Phase 53 spec.
const BUSY_MESSAGE_DELAY_MS = 10000

const LOADING_MESSAGE = 'ANALYSING…'
const LOADING_BUSY_MESSAGE = 'ANALYSING — SERVER BUSY…'

// User-facing error text keyed on the structured cause attached by
// postReasonRequest (or forwarded from the server's unavailable payload).
// Anything unrecognised falls through to the generic message.
// "rejected" (Phase 55) covers HTTP 400 validation rejections - see the
// comment at the !res.ok branch in postReasonRequest for why a 400 must
// not be disguised as a connectivity failure. The copy is terse with no
// trailing full stop, matching the existing entries.
const ERROR_MESSAGES = {
  timeout: 'LLM timed out — server busy, retry shortly',
  network: 'LLM unreachable',
  parse: 'Response unreadable',
  rejected: 'Invalid request — payload rejected',
}
const ERROR_MESSAGE_GENERIC = 'LLM unavailable'

// Module-level constant so the reset effect can setState with an
// identical reference on mount and React bails out of the no-op update.
const IDLE_STATE = { status: 'idle' }

/**
 * POST the reasoning request. Isolates all network logic from the React
 * state machine: resolves with the parsed body on success, or rejects
 * with an Error carrying a `.cause` field of "timeout" | "network" |
 * "parse" | "rejected" (400 validation rejection, Phase 55). An
 * AbortError from the caller's own controller propagates
 * unchanged so the effect can recognise and ignore it.
 *
 * The server never 500s on LLM failure — it returns 200 with
 * status:"unavailable" and a cause — so a structured failure body is
 * translated into the same thrown-Error shape as a transport failure.
 */
async function postReasonRequest({ payload, signal }) {
  let res
  try {
    res = await fetch('/api/radar/reason', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (err) {
    if (err?.name === 'AbortError') throw err
    // fetch only rejects on transport failure — no connection, DNS, etc.
    const wrapped = new Error('LLM request failed at transport level')
    wrapped.cause = 'network'
    throw wrapped
  }

  let body
  try {
    body = await res.json()
  } catch (err) {
    // Re-throw AbortError from the body read — the first catch handles
    // aborts during the fetch() call itself; this one catches aborts that
    // fire while reading the stream. Making the docstring exactly true.
    if (err?.name === 'AbortError') throw err
    const wrapped = new Error('LLM response was not valid JSON')
    wrapped.cause = 'parse'
    throw wrapped
  }

  if (!res.ok) {
    // 400 is a validation rejection: the panel sent a payload the server
    // could not accept. This is now an operator-visible condition
    // (since Phase 55 widened the theta bound, a 400 is no longer
    // only a Mimir-side programming error) and must not be disguised
    // as a connectivity failure.
    //
    // Every other non-200 status (500, 502, 503, ...) is still a
    // network-class error: the request reached the server but the
    // server did not produce a usable answer.
    const cause = res.status === 400 ? 'rejected' : 'network'
    const wrapped = new Error(body?.error || 'Request rejected by server')
    wrapped.cause = cause
    throw wrapped
  }

  if (body?.status !== 'ok') {
    const serverCause = body?.cause
    const wrapped = new Error(body?.notes || 'LLM unavailable')
    // Forward the server's cause when it is one the UI distinguishes;
    // "http"/"unknown"/missing all collapse to "network" (unreachable-ish).
    wrapped.cause =
      serverCause === 'timeout' || serverCause === 'parse'
        ? serverCause
        : 'network'
    throw wrapped
  }

  return body
}

export default function LlmReasoningPanel({
  icao,
  callsign = null,
  squawk = null,
  altitude_ft = null,
  track = null,
  groundspeed = null,
  vertical_rate = null,
  bearing_deg,
  range_nm,
  vector = null,
  projected = null,
  trailLength = 0,
}) {
  const [state, setState] = useState(IDLE_STATE)
  const [loadingMessage, setLoadingMessage] = useState(LOADING_MESSAGE)

  // Guard (d): no setState after unmount. Flipped false by the unmount
  // cleanup below and checked before every async state transition.
  const mountedRef = useRef(true)
  // Guard (b): the in-flight request's controller, so a new selection or
  // an unmount can abort it.
  const abortRef = useRef(null)
  // Guard (c): live mirror of the icao prop, so an async continuation can
  // compare the CURRENT selection against the selection the request was
  // fired for. Assigned during render — writing a ref in render is safe
  // here because the value is only read from async callbacks, never
  // during render itself.
  const icaoRef = useRef(icao)
  icaoRef.current = icao

  // Unmount: mark unmounted and abort any in-flight request.
  useEffect(() => {
    return () => {
      mountedRef.current = false
      abortRef.current?.abort()
    }
  }, [])

  // Guard (a) + (b) on selection change: reset to idle and abort the
  // in-flight request whenever the selected ICAO changes. Runs on mount
  // too; the reset is a no-op there because IDLE_STATE is reference-equal
  // to the current state and React bails out.
  useEffect(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setState(IDLE_STATE)
  }, [icao])

  // Two-stage loading message: escalate the copy after
  // BUSY_MESSAGE_DELAY_MS so an operator waiting on a loaded 4B model
  // can tell "thinking" apart from "stuck". The timeout is cleared on
  // unmount and on any transition out of the loading state.
  useEffect(() => {
    if (state.status !== 'loading') return undefined
    const timer = setTimeout(() => {
      if (mountedRef.current) setLoadingMessage(LOADING_BUSY_MESSAGE)
    }, BUSY_MESSAGE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [state.status])

  const handleClick = () => {
    const controller = new AbortController()
    abortRef.current = controller
    // Capture the selection this request belongs to — the late-response
    // guard compares it against icaoRef.current when the fetch resolves.
    const requestIcao = icao

    // The payload mirrors the endpoint's validated schema exactly:
    // snake_case keys, nulls (not undefined) for absent per-frame fields,
    // and defensive fallbacks for vector/projected even though State 3
    // guarantees both are non-null.
    const payload = {
      icao,
      callsign: callsign ?? null,
      squawk: squawk ?? null,
      altitude_ft: altitude_ft ?? null,
      track: track ?? null,
      groundspeed: groundspeed ?? null,
      vertical_rate: vertical_rate ?? null,
      bearing_deg,
      range_nm,
      theta_deg_per_sec: vector?.thetaDegPerSec ?? 0,
      delta_r_nm_per_sec: vector?.deltaRNmPerSec ?? 0,
      projected_bearing_deg: projected?.bearing_deg ?? bearing_deg,
      projected_range_nm: projected?.range_nm ?? range_nm,
      trail_length: trailLength ?? 0,
    }

    setLoadingMessage(LOADING_MESSAGE)
    setState({ status: 'loading' })

    postReasonRequest({ payload, signal: controller.signal })
      .then((body) => {
        // Guards (c) + (d): drop a response that arrives after unmount,
        // after abort, or after the operator changed selection.
        if (!mountedRef.current || controller.signal.aborted) return
        if (requestIcao !== icaoRef.current) return
        // Defensive clamp: the server already clamps confidence to the
        // allowed set, but never let an unexpected value reach a CSS
        // class name.
        const confidence = ['high', 'medium', 'low'].includes(body.confidence)
          ? body.confidence
          : 'low'
        setState({
          status: 'result',
          verdict: String(body.verdict ?? ''),
          confidence,
          notes: String(body.notes ?? ''),
        })
      })
      .catch((err) => {
        // Our own abort is a normal lifecycle event, not an error.
        if (err?.name === 'AbortError') return
        if (!mountedRef.current || controller.signal.aborted) return
        if (requestIcao !== icaoRef.current) return
        setState({
          status: 'error',
          message: ERROR_MESSAGES[err?.cause] ?? ERROR_MESSAGE_GENERIC,
        })
      })
  }

  return (
    <div className="radar-prediction-llm" data-testid="radar-prediction-llm">
      {state.status === 'idle' && (
        <div className="radar-prediction-llm-idle">
          <button
            type="button"
            className="radar-prediction-llm-idle-button"
            onClick={handleClick}
          >
            ANALYSE PATH WITH LLM
          </button>
        </div>
      )}
      {state.status === 'loading' && (
        <div className="radar-prediction-llm-loading">
          <button
            type="button"
            className="radar-prediction-llm-idle-button"
            disabled
          >
            ANALYSE PATH WITH LLM
          </button>
          <span className="radar-prediction-llm-loading-message">
            {loadingMessage}
          </span>
        </div>
      )}
      {state.status === 'result' && (
        <div className="radar-prediction-llm-result">
          {/* Glyph placed ABOVE the verdict (Phase 55): the directional
              projection gives context that frames the verdict text, the
              same way a compass rose precedes a bearing readout. The
              glyph renders nothing when the vector is absent, so no
              guard is needed here. */}
          <PredictionGlyph vector={vector} />
          <div className="radar-prediction-llm-verdict">{state.verdict}</div>
          <div
            className={`radar-prediction-llm-confidence radar-prediction-llm-confidence-${state.confidence}`}
          >
            {state.confidence.toUpperCase()} CONFIDENCE
          </div>
          <div className="radar-prediction-llm-notes">{state.notes}</div>
        </div>
      )}
      {state.status === 'error' && (
        <div className="radar-prediction-llm-error">{state.message}</div>
      )}
    </div>
  )
}