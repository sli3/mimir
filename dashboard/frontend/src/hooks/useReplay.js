import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Replay state machine for the /replay page results view.
 *
 * Accepts a capture filename and POSTs it to /api/replay. The endpoint
 * runs the saved capture through the fingerprint pipeline again under
 * today's band thresholds and returns a field-by-field comparison.
 *
 * State shape:
 *   { status: 'idle' }
 *   { status: 'loading' }
 *   { status: 'ok', result: object }
 *   { status: 'failure', error_code: str, message: str }
 *
 * The caller must explicitly invoke replay(filename) to start the POST;
 * this hook does not auto-fetch on mount, unlike useCaptures.
 *
 * @returns {{
 *   state: object,
 *   loading: boolean,
 *   replay: (filename: string) => void
 * }}
 */
export default function useReplay() {
  const [state, setState] = useState({ status: 'idle' })
  const mountedRef = useRef(true)
  const abortRef = useRef(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (abortRef.current) {
        abortRef.current.abort()
      }
    }
  }, [])

  const replay = useCallback((filename) => {
    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller
    setState({ status: 'loading' })

    fetch('/api/replay', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: String(filename ?? '') }),
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!mountedRef.current || controller.signal.aborted) return
        let body
        try {
          body = await res.json()
        } catch {
          if (!mountedRef.current || controller.signal.aborted) return
          setState({
            status: 'failure',
            error_code: 'parse_error',
            message: 'Unexpected server response',
          })
          return
        }
        if (!mountedRef.current || controller.signal.aborted) return
        if (!res.ok) {
          const code = body.error || 'replay_failed'
          let message
          if (code === 'busy') {
            message = 'Another replay is in progress; try again in a moment'
          } else {
            message = `Replay failed: ${body.detail || code}`
          }
          setState({
            status: 'failure',
            error_code: code,
            message,
          })
          return
        }
        setState({ status: 'ok', result: body })
      })
      .catch(() => {
        if (!mountedRef.current || controller.signal.aborted) return
        setState({
          status: 'failure',
          error_code: 'transport_error',
          message: 'Could not reach replay server',
        })
      })
  }, [])

  const loading = state.status === 'loading'

  return {
    state,
    loading,
    replay,
  }
}
