import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import React from 'react'

import CaptureButton from '../components/CaptureButton.jsx'
import CaptureResultPanel from '../components/CaptureResultPanel.jsx'
import useCapture from '../hooks/useCapture.js'
import {
  buildCaptureVerdict,
  VERDICT_WIDE,
  VERDICT_NARROW,
  VERDICT_BURST,
  VERDICT_FALLBACK,
} from '../components/ManualCaptureButton.jsx'

// Full seven-key fingerprint as the backend's ok response carries it,
// with per-test overrides for the verdict-driving fields.
const makeFingerprint = (overrides = {}) => ({
  peak_freq_hz: 98100000,
  peak_power_db: -12.5,
  noise_floor_db: -78.0,
  snr_db: 65.5,
  bandwidth_hz: 200000,
  occupied_bins: 205,
  spectral_flatness: 0.42,
  ...overrides,
})

// Phase 67: the /api/capture ok response now carries `is_burst` as a
// top-level sibling of `fingerprint`. okBody takes TWO args — fingerprint
// overrides + top-level overrides — so tests can drive either layer
// independently. Default is no top-level overrides (matches the
// pre-Phase-67 behaviour and lets existing scenarios keep working).
const okBody = (fingerprintOverrides = {}, topLevelOverrides = {}) => ({
  status: 'ok',
  file: '/tmp/cap.sigmf-meta',
  fingerprint: makeFingerprint(fingerprintOverrides),
  ...topLevelOverrides,
})

const mockFetchOk = (body) =>
  vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve(body),
    })
  )

// A fetch that never settles, used for the pending-state test.
const mockFetchPending = () =>
  vi.fn((_url, _opts) => new Promise(() => {}))

const mockFetchReject = () =>
  vi.fn(() => Promise.reject(new TypeError('Failed to fetch')))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

/**
 * TestHarness — exercises CaptureButton + CaptureResultPanel through the
 * real production useCapture hook, the same wiring App.jsx uses now that
 * the state machine has been extracted. End-to-end component tests
 * continue to drive both surfaces via one shared state source.
 */
function TestHarness() {
  const { state, pending, handleClick } = useCapture()
  return (
    <div data-testid="manual-capture">
      <CaptureButton onClick={handleClick} pending={pending} />
      <CaptureResultPanel state={state} />
    </div>
  )
}

describe('ManualCaptureContainer', () => {
  it('renders an idle button with the CAPTURE NOW label', () => {
    render(<TestHarness />)
    const button = screen.getByTestId('manual-capture-button')
    expect(button).toBeInTheDocument()
    expect(button).toHaveTextContent('CAPTURE NOW')
    expect(button).not.toBeDisabled()
    expect(screen.queryByTestId('manual-capture-result')).not.toBeInTheDocument()
  })

  it('sets state to pending and disables the button after click', () => {
    vi.stubGlobal('fetch', mockFetchPending())
    render(<TestHarness />)
    const button = screen.getByTestId('manual-capture-button')
    fireEvent.click(button)
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('CAPTURING…')
  })

  it('renders the wide-bandwidth verdict for occupied_bins >= 20', async () => {
    vi.stubGlobal('fetch', mockFetchOk(okBody({ occupied_bins: 250 })))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(VERDICT_WIDE)
    )
    const result = screen.getByTestId('manual-capture-result')
    expect(result).toHaveTextContent('occupied bins: 250')
    expect(result).toHaveTextContent('SNR: 65.5 dB')
    expect(result).toHaveTextContent('peak: 98.100 MHz')
    expect(result).toHaveTextContent('/tmp/cap.sigmf-meta')
    // The button returns to idle immediately on success.
    expect(screen.getByTestId('manual-capture-button')).not.toBeDisabled()
  })

  it('renders the weak/narrow verdict for occupied_bins <= 9 without burst', async () => {
    vi.stubGlobal('fetch', mockFetchOk(okBody({ occupied_bins: 3 }, { is_burst: false })))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(VERDICT_NARROW)
    )
  })

  it('renders the burst verdict when is_burst overrides a narrow reading', async () => {
    vi.stubGlobal('fetch', mockFetchOk(okBody({ occupied_bins: 3 }, { is_burst: true })))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(VERDICT_BURST)
    )
  })

  it('renders the burst verdict when is_burst overrides a wide reading', async () => {
    vi.stubGlobal('fetch', mockFetchOk(okBody({ occupied_bins: 250 }, { is_burst: true })))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(VERDICT_BURST)
    )
  })

  it('renders the fallback verdict for the ambiguous 10-19 bin middle', async () => {
    vi.stubGlobal('fetch', mockFetchOk(okBody({ occupied_bins: 15 }, { is_burst: false })))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(VERDICT_FALLBACK)
    )
  })

  it('renders the cause on status error and returns to idle after the retry delay', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.stubGlobal('fetch', mockFetchOk({ status: 'error', cause: 'disk full' }))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent('disk full')
    )
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.queryByTestId('manual-capture-result')).not.toBeInTheDocument()
    expect(screen.getByTestId('manual-capture-button')).not.toBeDisabled()
    expect(screen.getByTestId('manual-capture-button')).toHaveTextContent('CAPTURE NOW')
  })

  it('renders the no-response message on status timeout', async () => {
    vi.stubGlobal('fetch', mockFetchOk({ status: 'timeout' }))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(
        'No response from scanner — try again'
      )
    )
  })

  it('renders the scanner-not-running message on status scanner_unavailable', async () => {
    vi.stubGlobal('fetch', mockFetchOk({ status: 'scanner_unavailable' }))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(
        'Scanner is not running'
      )
    )
  })

  it('renders the transport-failure message when fetch rejects', async () => {
    vi.stubGlobal('fetch', mockFetchReject())
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(
        'Capture request failed at transport level'
      )
    )
  })
})

describe('ManualCaptureContainer regressions', () => {
  it('clears a pending retry timer when a new capture starts, so the old timer cannot wipe the newer result', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    // First click: server reports an error, which schedules the 3 s
    // return-to-idle timer and re-enables the button.
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: 'error', cause: 'disk full' }),
      })
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent('disk full')
    )
    // Second click before the 3 s timer fires; this capture succeeds.
    fetchMock.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(okBody({ occupied_bins: 250 })),
      })
    )
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(VERDICT_WIDE)
    )
    // Advance past the original timer's fire time. Without the fix the
    // stale timer fires now and resets the fresh ok state back to idle.
    act(() => {
      vi.advanceTimersByTime(4000)
    })
    expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(VERDICT_WIDE)
    expect(screen.getByTestId('manual-capture-button')).not.toBeDisabled()
  })

  it('still processes the fetch response under React Strict Mode double-invoked effects', async () => {
    // Strict Mode mounts, unmounts (cleanup flips mountedRef false),
    // then re-mounts. The effect setup must restore mountedRef to true
    // or every response after the first is silently dropped.
    vi.stubGlobal('fetch', mockFetchOk(okBody({ occupied_bins: 250 })))
    render(
      <React.StrictMode>
        <TestHarness />
      </React.StrictMode>
    )
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent(VERDICT_WIDE)
    )
  })

  it('aborts the in-flight request when the component unmounts', () => {
    let capturedSignal = null
    vi.stubGlobal(
      'fetch',
      vi.fn((_url, opts) => {
        capturedSignal = opts?.signal ?? null
        return new Promise(() => {})
      })
    )
    const { unmount } = render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    expect(capturedSignal).not.toBeNull()
    expect(capturedSignal.aborted).toBe(false)
    unmount()
    expect(capturedSignal.aborted).toBe(true)
  })

  it('ignores a late response that arrives after the request was aborted on unmount', async () => {
    let resolveFetch
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise((resolve) => { resolveFetch = resolve }))
    )
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { unmount } = render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    unmount()
    // The server-side work may still complete; resolving the promise late
    // must not throw, must not attempt a state update, and must not log.
    resolveFetch({ ok: true, json: () => Promise.resolve(okBody()) })
    await act(async () => {})
    expect(consoleErrorSpy).not.toHaveBeenCalled()
    expect(screen.queryByTestId('manual-capture-result')).not.toBeInTheDocument()
    consoleErrorSpy.mockRestore()
  })

  it('announces success politely and failure assertively to screen readers', async () => {
    vi.stubGlobal('fetch', mockFetchOk(okBody()))
    const { unmount } = render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toBeInTheDocument()
    )
    const okResult = screen.getByTestId('manual-capture-result')
    expect(okResult).toHaveAttribute('role', 'status')
    expect(okResult).toHaveAttribute('aria-live', 'polite')
    unmount()

    vi.stubGlobal('fetch', mockFetchOk({ status: 'error', cause: 'disk full' }))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('manual-capture-button'))
    await waitFor(() =>
      expect(screen.getByTestId('manual-capture-result')).toHaveTextContent('disk full')
    )
    expect(screen.getByTestId('manual-capture-result')).toHaveAttribute('role', 'alert')
  })
})

describe('buildCaptureVerdict', () => {
  // Phase 67: input shape changed from `(fingerprint)` to `(captureResult)`
  // where captureResult = { fingerprint, is_burst }. Tests construct that
  // shape explicitly so the verdict helper's two-key contract stays
  // exercised at the unit level.
  const wrap = (fingerprintOverrides = {}, is_burst = undefined) => ({
    fingerprint: makeFingerprint(fingerprintOverrides),
    is_burst,
  })

  it('classifies occupied_bins >= 20 as a wide real signal', () => {
    expect(buildCaptureVerdict(wrap({ occupied_bins: 20 }))).toEqual({
      category: 'wide',
      verdict: VERDICT_WIDE,
    })
    expect(buildCaptureVerdict(wrap({ occupied_bins: 400 })).category).toBe('wide')
  })

  it('classifies occupied_bins <= 9 without burst as weak/narrow', () => {
    expect(buildCaptureVerdict(wrap({ occupied_bins: 9 }, false))).toEqual({
      category: 'narrow',
      verdict: VERDICT_NARROW,
    })
    expect(buildCaptureVerdict(wrap({ occupied_bins: 5 })).category).toBe('narrow')
  })

  it('lets is_burst override both occupied_bins rules', () => {
    expect(buildCaptureVerdict(wrap({ occupied_bins: 3 }, true))).toEqual({
      category: 'burst',
      verdict: VERDICT_BURST,
    })
    expect(buildCaptureVerdict(wrap({ occupied_bins: 250 }, true)).category).toBe('burst')
  })

  it('lets is_burst override even wide occupied_bins readings', () => {
    // Phase 67: the burst branch wins regardless of occupied_bins.
    expect(buildCaptureVerdict(wrap({ occupied_bins: 250 }, true))).toEqual({
      category: 'burst',
      verdict: VERDICT_BURST,
    })
  })

  it('falls back for the ambiguous middle and for missing fields', () => {
    expect(buildCaptureVerdict(wrap({ occupied_bins: 15 }))).toEqual({
      category: 'fallback',
      verdict: VERDICT_FALLBACK,
    })
    expect(buildCaptureVerdict(null).category).toBe('fallback')
    expect(buildCaptureVerdict({}).category).toBe('fallback')
    expect(buildCaptureVerdict({ fingerprint: { occupied_bins: 'many' } }).category).toBe('fallback')
  })
})
