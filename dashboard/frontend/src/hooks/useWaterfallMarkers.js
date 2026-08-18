import { useState, useRef, useCallback } from 'react'

/**
 * useWaterfallMarkers — Phase 69 waterfall event markers.
 *
 * Manages the in-memory list of event markers drawn on each waterfall
 * strip's crosshair overlay canvas.  A marker records that an operator
 * event (a "Capture Now" capture, or a Record start/stop) fired while a
 * given frequency was being watched, so the operator can see WHERE in
 * the scrolling history the event happened.
 *
 * Marker shape:
 *   { id: number, type: 'capture'|'record_start'|'record_stop',
 *     freqHz: number, rowOffset: number, createdAt: number }
 *
 * Lifecycle:
 *   1. An add*Marker(freqHz) call appends a marker with rowOffset 0 —
 *      the marker is born on the "now" row (y = 0) of the strip whose
 *      config.freq_hz matches freqHz.
 *   2. Each time that strip scrolls (a new PSD row arrives, the same
 *      trigger useWaterfall uses), the strip calls
 *      tickAndPrune(freqHz, canvasHeight) via its onStripScroll prop.
 *      Every marker belonging to that frequency moves down one row
 *      (rowOffset + 1), keeping it glued to the signal data it was
 *      fired against.
 *   3. Once a marker's rowOffset reaches the canvas height it has
 *      scrolled off the bottom of the strip and is pruned.
 *
 * Per-frequency semantics: each waterfall strip owns its own scroll
 * lifecycle, so tickAndPrune only ever advances/prunes markers whose
 * freqHz matches the calling strip.  Markers for other frequencies are
 * passed through untouched — their strips tick them independently.
 *
 * No persistence: markers live in React state only.  A page refresh
 * clears them, which is the intended behaviour.
 *
 * The ID counter is a useRef (instance-scoped) rather than module-level
 * state, so a remount starts a fresh counter and tests stay isolated.
 *
 * @returns {{
 *   markers: Array<{ id: number, type: string, freqHz: number, rowOffset: number, createdAt: number }>,
 *   addCaptureMarker: (freqHz: number) => void,
 *   addRecordStartMarker: (freqHz: number) => void,
 *   addRecordStopMarker: (freqHz: number) => void,
 *   tickAndPrune: (freqHz: number, height: number) => void,
 * }}
 */
export default function useWaterfallMarkers() {
  const [markers, setMarkers] = useState([])
  const nextIdRef = useRef(1)

  const addMarker = useCallback((type, freqHz) => {
    // Guard: a marker with no frequency can never be matched to a strip,
    // so drop it silently rather than storing unreachable state.
    if (freqHz == null) return
    const id = nextIdRef.current
    nextIdRef.current += 1
    setMarkers((prev) => [
      ...prev,
      { id, type, freqHz, rowOffset: 0, createdAt: Date.now() },
    ])
  }, [])

  const addCaptureMarker = useCallback(
    (freqHz) => addMarker('capture', freqHz),
    [addMarker]
  )

  const addRecordStartMarker = useCallback(
    (freqHz) => addMarker('record_start', freqHz),
    [addMarker]
  )

  const addRecordStopMarker = useCallback(
    (freqHz) => addMarker('record_stop', freqHz),
    [addMarker]
  )

  const tickAndPrune = useCallback((freqHz, height) => {
    // Guard: height comes from a measured canvas; before the first
    // measurement it can be 0 or undefined, in which case there is no
    // meaningful row to advance to.
    if (typeof height !== 'number' || !Number.isFinite(height) || height <= 0) return
    setMarkers((prev) =>
      prev
        .map((m) => (m.freqHz === freqHz ? { ...m, rowOffset: m.rowOffset + 1 } : m))
        .filter((m) => !(m.freqHz === freqHz && m.rowOffset >= height))
    )
  }, [])

  return {
    markers,
    addCaptureMarker,
    addRecordStartMarker,
    addRecordStopMarker,
    tickAndPrune,
  }
}
