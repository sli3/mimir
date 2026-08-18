import { useCallback, useEffect, useRef, useState } from 'react'

const WARNING_THRESHOLD_SEC = 60

/**
 * Operator "Record" state machine (Phase 68).
 *
 * Different lifecycle from useCapture.js (single-shot): recording is a
 * long-lived state machine — idle → recording → stopped. The backend
 * accumulates scan-cycle samples in memory between POST /api/record/start
 * and POST /api/record/stop, then writes one SigMF file.
 *
 * There is deliberately NO client-side auto-stop and NO backend cap: the
 * recording runs until the operator stops it. The 60-second mark only
 * flips a `warning` flag the UI uses to recolour the elapsed readout.
 *
 * @returns {{
 *   recording: boolean,
 *   elapsedSec: number,
 *   warning: boolean,
 *   recordResult: object | null,
 *   startRecording: () => void,
 *   stopRecording: () => void
 * }}
 */
export default function useRecording() {
  const [recording, setRecording] = useState(false)
  const [elapsedSec, setElapsedSec] = useState(0)
  const [recordResult, setRecordResult] = useState(null)
  const mountedRef = useRef(true)
  const abortRef = useRef(null)
  const startTsRef = useRef(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (abortRef.current) {
        abortRef.current.abort()
      }
    }
  }, [])

  // Client-side elapsed timer: 1 Hz while recording, cleared when not.
  // Display-only — the backend has no awareness of elapsed time.
  useEffect(() => {
    if (!recording) return undefined
    const interval = setInterval(() => {
      if (startTsRef.current === null) return
      setElapsedSec(Math.floor((Date.now() - startTsRef.current) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [recording])

  const startRecording = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller

    fetch('/api/record/start', { method: 'POST', signal: controller.signal })
      .then(async (res) => {
        if (!mountedRef.current || controller.signal.aborted) return
        if (!res.ok) {
          setRecordResult({
            status: 'error',
            cause: 'Unexpected server response',
          })
          return
        }
        let body
        try {
          body = await res.json()
        } catch {
          if (!mountedRef.current || controller.signal.aborted) return
          setRecordResult({
            status: 'error',
            cause: 'Unexpected server response',
          })
          return
        }
        if (!mountedRef.current || controller.signal.aborted) return
        if (body?.status === 'ok') {
          startTsRef.current = Date.now()
          setElapsedSec(0)
          setRecordResult(null)
          setRecording(true)
        } else if (body?.status === 'already_recording') {
          // Another operator action beat us to it; adopt the recording
          // state so the UI matches the backend.
          setRecording(true)
        } else if (body?.status === 'scanner_unavailable') {
          setRecordResult({
            status: 'error',
            cause: 'Scanner is not running',
          })
        } else {
          setRecordResult({
            status: 'error',
            cause: 'Unexpected server response',
          })
        }
      })
      .catch(() => {
        if (!mountedRef.current || controller.signal.aborted) return
        setRecordResult({
          status: 'error',
          cause: 'Record request failed at transport level',
        })
      })
  }, [])

  const stopRecording = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller
    // Flip the local state immediately so the UI and the elapsed timer
    // stop without waiting for the concatenate + file write to return.
    setRecording(false)

    fetch('/api/record/stop', { method: 'POST', signal: controller.signal })
      .then(async (res) => {
        if (!mountedRef.current || controller.signal.aborted) return
        if (!res.ok) {
          setRecordResult({
            status: 'error',
            cause: 'Unexpected server response',
          })
          return
        }
        let body
        try {
          body = await res.json()
        } catch {
          if (!mountedRef.current || controller.signal.aborted) return
          setRecordResult({
            status: 'error',
            cause: 'Unexpected server response',
          })
          return
        }
        if (!mountedRef.current || controller.signal.aborted) return
        switch (body?.status) {
          case 'ok':
            setRecordResult({
              status: 'ok',
              file: String(body.file ?? ''),
              duration_sec: Number(body.duration_sec ?? 0),
              cycle_count: Number(body.cycle_count ?? 0),
            })
            break
          case 'error':
            setRecordResult({
              status: 'error',
              cause: String(body.cause ?? 'unknown cause'),
            })
            break
          case 'not_recording':
            setRecordResult({
              status: 'error',
              cause: 'No recording was in progress',
            })
            break
          case 'scanner_unavailable':
            setRecordResult({
              status: 'error',
              cause: 'Scanner is not running',
            })
            break
          default:
            setRecordResult({
              status: 'error',
              cause: 'Unexpected server response',
            })
        }
      })
      .catch(() => {
        if (!mountedRef.current || controller.signal.aborted) return
        setRecordResult({
          status: 'error',
          cause: 'Record request failed at transport level',
        })
      })
  }, [])

  return {
    recording,
    elapsedSec,
    warning: elapsedSec >= WARNING_THRESHOLD_SEC,
    recordResult,
    startRecording,
    stopRecording,
  }
}
