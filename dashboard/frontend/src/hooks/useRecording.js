import { useCallback, useEffect, useRef, useState } from 'react'

const WARNING_THRESHOLD_SEC = 60

/**
 * Operator "Record" state machine (Phase 68).
 *
 * Different lifecycle from useCapture.js (single-shot): recording is a
 * long-lived state machine — idle → recording → stopped. The backend
 * accumulates scan-cycle samples in memory between POST /api/record/start
 * and POST /api/record/stop, then writes one SigMF file.
 * On mount, GET /api/record/status silently restores an active recording
 * and its elapsed time unless the operator has already acted locally.
 *
 * The backend stops accumulation at its memory cap and saves when the
 * operator stops it. The UI learns of the cap in the stop response and
 * reports a successful save with cap_reached: true. The elapsed timer
 * keeps counting until stop; the 60-second mark only flips a `warning`
 * flag the UI uses to recolour the elapsed readout.
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
  const operatorActedRef = useRef(false)

  useEffect(() => {
    mountedRef.current = true
    operatorActedRef.current = false
    const controller = new AbortController()
    fetch('/api/record/status', { method: 'GET', signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) return
        const body = await res.json()
        if (!mountedRef.current || controller.signal.aborted || operatorActedRef.current) return
        if (body?.status === 'ok' && body.recording === true) {
          const elapsed = body.elapsed_sec
          startTsRef.current = Date.now() - elapsed * 1000
          setElapsedSec(Math.floor(elapsed))
          setRecording(true)
        }
      })
      .catch(() => {
        // Status restoration is best-effort; failures leave the hook idle.
      })
    return () => {
      mountedRef.current = false
      controller.abort()
      if (abortRef.current) {
        abortRef.current.abort()
      }
    }
  }, [])

  // Display elapsed time at 1 Hz from a local start or the restored backend
  // duration. Cleared when idle; the warning never stops the recording.
  useEffect(() => {
    if (!recording) return undefined
    const interval = setInterval(() => {
      if (startTsRef.current === null) return
      setElapsedSec(Math.floor((Date.now() - startTsRef.current) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [recording])

  const startRecording = useCallback(() => {
    operatorActedRef.current = true
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
          // state and seed a running timer if no start time is known.
          if (startTsRef.current === null) startTsRef.current = Date.now()
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
    operatorActedRef.current = true
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
          case 'cap_reached':
            setRecordResult({
              status: 'ok',
              file: String(body.file ?? ''),
              duration_sec: Number(body.duration_sec ?? 0),
              cycle_count: Number(body.cycle_count ?? 0),
              cap_reached: true,
            })
            break
          case 'ok':
            setRecordResult({
              status: 'ok',
              file: String(body.file ?? ''),
              duration_sec: Number(body.duration_sec ?? 0),
              cycle_count: Number(body.cycle_count ?? 0),
              cap_reached: false,
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
