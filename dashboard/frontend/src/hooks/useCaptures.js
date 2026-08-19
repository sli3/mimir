import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Capture-listing state machine for the /replay page picker.
 *
 * Fetches GET /api/captures once on mount, returning a lightweight
 * listing of every .sigmf-meta file in data/captures/. The paired
 * .sigmf-data files are never requested by this endpoint.
 *
 * State shape:
 *   { status: 'idle' }
 *   { status: 'loading' }
 *   { status: 'ok', captures: [...] }
 *   { status: 'failure', message: str }
 *
 * The hook owns the fetch lifecycle and aborts any in-flight request
 * on unmount, matching the useCapture.js AbortController pattern.
 *
 * @returns {{
 *   state: object,
 *   loading: boolean,
 *   refetch: () => void
 * }}
 */
export default function useCaptures() {
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

  const fetchCaptures = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller
    setState({ status: 'loading' })

    fetch('/api/captures', { signal: controller.signal })
      .then(async (res) => {
        if (!mountedRef.current || controller.signal.aborted) return
        let body
        try {
          body = await res.json()
        } catch {
          if (!mountedRef.current || controller.signal.aborted) return
          setState({
            status: 'failure',
            message: 'Unexpected server response',
          })
          return
        }
        if (!mountedRef.current || controller.signal.aborted) return
        if (!res.ok || body.error) {
          setState({
            status: 'failure',
            message: body.detail || body.error || `HTTP ${res.status}`,
          })
          return
        }
        setState({
          status: 'ok',
          captures: Array.isArray(body.captures) ? body.captures : [],
        })
      })
      .catch(() => {
        if (!mountedRef.current || controller.signal.aborted) return
        setState({
          status: 'failure',
          message: 'Could not reach capture server',
        })
      })
  }, [])

  useEffect(() => {
    fetchCaptures()
  }, [fetchCaptures])

  const loading = state.status === 'loading'

  return {
    state,
    loading,
    refetch: fetchCaptures,
  }
}
