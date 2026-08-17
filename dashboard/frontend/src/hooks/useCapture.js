import { useCallback, useEffect, useRef, useState } from 'react'

const RETRY_DELAY_MS = 3000

/**
 * Manual capture state machine.
 *
 * Phase 67 split the original ManualCaptureButton into CaptureButton (top
 * control row) and CaptureResultPanel (right sidebar). The state machine
 * is consumed by both via this hook so they share a single source of
 * truth.
 *
 * @returns {{
 *   state: object,
 *   pending: boolean,
 *   handleClick: () => void
 * }}
 */
export default function useCapture() {
  const [state, setState] = useState({ status: 'idle' })
  const mountedRef = useRef(true)
  const retryTimerRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (retryTimerRef.current !== null) {
        clearTimeout(retryTimerRef.current)
      }
      if (abortRef.current) {
        abortRef.current.abort()
      }
    }
  }, [])

  const scheduleReturnToIdle = useCallback(() => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current)
    }
    retryTimerRef.current = setTimeout(() => {
      retryTimerRef.current = null
      if (mountedRef.current) setState({ status: 'idle' })
    }, RETRY_DELAY_MS)
  }, [])

  const handleClick = useCallback(() => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller
    setState({ status: 'pending' })

    fetch('/api/capture', { method: 'POST', signal: controller.signal })
      .then(async (res) => {
        if (!mountedRef.current || controller.signal.aborted) return
        if (!res.ok) {
          setState({
            status: 'unexpected',
            message: 'Unexpected server response',
          })
          scheduleReturnToIdle()
          return
        }
        let body
        try {
          body = await res.json()
        } catch {
          if (!mountedRef.current || controller.signal.aborted) return
          setState({
            status: 'unexpected',
            message: 'Unexpected server response',
          })
          scheduleReturnToIdle()
          return
        }
        if (!mountedRef.current || controller.signal.aborted) return
        switch (body?.status) {
          case 'ok':
            setState({
              status: 'ok',
              file: String(body.file ?? ''),
              fingerprint: body.fingerprint ?? null,
              is_burst: body.is_burst ?? false,
            })
            break
          case 'error':
            setState({
              status: 'error',
              message: `Capture failed: ${String(body.cause ?? 'unknown cause')}`,
            })
            scheduleReturnToIdle()
            break
          case 'timeout':
            setState({
              status: 'timeout',
              message: 'No response from scanner — try again',
            })
            scheduleReturnToIdle()
            break
          case 'scanner_unavailable':
            setState({
              status: 'scanner_unavailable',
              message: 'Scanner is not running',
            })
            scheduleReturnToIdle()
            break
          default:
            setState({
              status: 'unexpected',
              message: 'Unexpected server response',
            })
            scheduleReturnToIdle()
        }
      })
      .catch(() => {
        if (!mountedRef.current || controller.signal.aborted) return
        setState({
          status: 'transport_error',
          message: 'Capture request failed at transport level',
        })
        scheduleReturnToIdle()
      })
  }, [scheduleReturnToIdle])

  const pending = state.status === 'pending'

  return {
    state,
    pending,
    handleClick,
  }
}