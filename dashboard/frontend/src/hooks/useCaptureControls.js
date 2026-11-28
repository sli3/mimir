import { useRef, useCallback, useEffect } from 'react'
import useCapture from './useCapture.js'
import useRecording from './useRecording.js'
import useWaterfallMarkers from './useWaterfallMarkers.js'

/**
 * Coordinate capture and recording controls with waterfall event markers.
 * Add markers only on capture or recording state transitions, not band changes.
 * @param {number} focusedFreq Currently focused frequency in Hz.
 * @returns {Object} Capture/recording state, click handlers and marker controls.
 */
export default function useCaptureControls(focusedFreq) {
  const { state: captureState, pending: capturePending, handleClick: rawHandleCaptureClick } = useCapture()

  // Phase 68 "Record": long-lived operator-controlled capture. Fully
  // separate mechanism from the single-shot capture above — separate
  // hook, separate endpoints, separate button. The click handler
  // decides start vs stop from the recording state.
  const {
    recording,
    elapsedSec: recordElapsedSec,
    warning: recordWarning,
    recordResult,
    startRecording,
    stopRecording,
  } = useRecording()

  // Phase 69: waterfall event markers
  const {
    markers,
    addCaptureMarker,
    addRecordStartMarker,
    addRecordStopMarker,
    tickAndPrune,
  } = useWaterfallMarkers()

  // Phase 69: capture the freq at click time so a fast band-switch
  // between click and async response does not misattribute the marker.
  const pendingCaptureFreqRef = useRef(null)
  const pendingRecordFreqRef = useRef(null)

  const handleCaptureClick = useCallback(() => {
    pendingCaptureFreqRef.current = focusedFreq
    rawHandleCaptureClick()
  }, [focusedFreq, rawHandleCaptureClick])

  const handleRecordClick = useCallback(() => {
    if (recording) {
      stopRecording()
    } else {
      pendingRecordFreqRef.current = focusedFreq
      startRecording()
    }
  }, [recording, focusedFreq, startRecording, stopRecording])

  // Phase 69: fire markers on capture/record state transitions.
  useEffect(() => {
    if (captureState.status === 'ok') {
      addCaptureMarker(pendingCaptureFreqRef.current ?? focusedFreq)
      pendingCaptureFreqRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- Capture transitions alone add markers; band or callback changes must not add duplicates.
  }, [captureState.status])

  useEffect(() => {
    if (recording) {
      addRecordStartMarker(pendingRecordFreqRef.current ?? focusedFreq)
      // Do NOT clear the ref — the upcoming stop uses the same freq.
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- Recording transitions alone add start markers; band or callback changes must not add duplicates.
  }, [recording])

  useEffect(() => {
    if (recordResult?.status === 'ok') {
      addRecordStopMarker(pendingRecordFreqRef.current ?? focusedFreq)
      pendingRecordFreqRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- Record result transitions alone add stop markers; band or callback changes must not add duplicates.
  }, [recordResult])

  return {
    captureState,
    capturePending,
    handleCaptureClick,
    recording,
    recordElapsedSec,
    recordWarning,
    recordResult,
    handleRecordClick,
    markers,
    tickAndPrune,
  }
}
