import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import React from 'react'

import RecordButton from '../components/RecordButton.jsx'
import useRecording from '../hooks/useRecording.js'

const mockFetchOk = (body) =>
  vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve(body),
    })
  )

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetchOk({ status: 'ok', recording: false }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

/**
 * TestHarness — exercises RecordButton through the real production
 * useRecording hook, matching the dashboard's recording wiring in
 * pages/DashboardPage.jsx through hooks/useCaptureControls.js. The parent
 * owns the click handler (start vs stop decided from the recording state)
 * and renders the inline result readout, including the memory-cap suffix,
 * mirroring BandNavBar. Data attributes expose the hook's normalised result.
 */
function TestHarness() {
  const {
    recording,
    elapsedSec,
    warning,
    recordResult,
    startRecording,
    stopRecording,
  } = useRecording()
  const handleClick = () => (recording ? stopRecording() : startRecording())
  return (
    <div data-testid="record-harness">
      <RecordButton
        recording={recording}
        onClick={handleClick}
        elapsedSec={elapsedSec}
        warning={warning}
      />
      {recordResult && !recording && (
        <span
          data-testid="record-result"
          data-status={recordResult.status}
          data-cap-reached={String(recordResult.cap_reached)}
        >
          {recordResult.status === 'ok'
            ? `Recorded ${recordResult.duration_sec.toFixed(1)}s / ${recordResult.cycle_count} cycles${recordResult.cap_reached ? ' (stopped at memory cap)' : ''}`
            : `Recording failed: ${recordResult.cause}`}
        </span>
      )}
    </div>
  )
}

describe('RecordButton', () => {
  it('adopts an in-progress recording and its warning timer on mount', async () => {
    const fetchMock = mockFetchOk({ status: 'ok', recording: true, elapsed_sec: 75 })
    vi.stubGlobal('fetch', fetchMock)
    render(<TestHarness />)
    await waitFor(() =>
      expect(screen.getByTestId('record-elapsed')).toHaveTextContent('01:15')
    )
    expect(screen.getByTestId('record-elapsed').style.color).toBe('var(--neon-amber)')
    expect(screen.getByTestId('record-dot')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/record/status')
    expect(fetchMock.mock.calls[0][1].method).toBe('GET')
  })

  it('stays idle when mount status reports no recording', async () => {
    const fetchMock = mockFetchOk({ status: 'ok', recording: false, elapsed_sec: 0 })
    vi.stubGlobal('fetch', fetchMock)
    render(<TestHarness />)
    await act(async () => {})
    expect(screen.queryByTestId('record-dot')).not.toBeInTheDocument()
    expect(screen.queryByTestId('record-elapsed')).not.toBeInTheDocument()
    expect(screen.queryByTestId('record-result')).not.toBeInTheDocument()
  })

  it.each(['network', 'http', 'json', 'scanner_unavailable'])(
    'silently stays idle when mount status fails: %s',
    async (failure) => {
      const fetchMock = vi.fn(() => {
        if (failure === 'network') return Promise.reject(new Error('offline'))
        return Promise.resolve({
          ok: failure !== 'http',
          json: () => failure === 'json'
            ? Promise.reject(new SyntaxError('bad JSON'))
            : Promise.resolve({ status: 'scanner_unavailable' }),
        })
      })
      vi.stubGlobal('fetch', fetchMock)
      render(<TestHarness />)
      await act(async () => {})
      expect(screen.queryByTestId('record-dot')).not.toBeInTheDocument()
      expect(screen.queryByTestId('record-elapsed')).not.toBeInTheDocument()
      expect(screen.queryByTestId('record-result')).not.toBeInTheDocument()
    }
  )

  it('ignores mount status arriving after the operator starts recording', async () => {
    let resolveStatus
    const statusResponse = new Promise((resolve) => { resolveStatus = resolve })
    vi.stubGlobal('fetch', vi.fn((url) => url === '/api/record/status'
      ? statusResponse
      : Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) })
    ))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('record-button'))
    await waitFor(() => expect(screen.getByTestId('record-dot')).toBeInTheDocument())
    await act(async () => {
      resolveStatus({
        ok: true,
        json: () => Promise.resolve({ status: 'ok', recording: true, elapsed_sec: 75 }),
      })
    })
    expect(screen.getByTestId('record-elapsed')).toHaveTextContent('00:00')
    expect(screen.getByTestId('record-elapsed').style.color).toBe('var(--neon-red)')
    expect(screen.getByTestId('record-dot')).toBeInTheDocument()
  })

  it('aborts mount status on unmount and ignores its late response', async () => {
    let resolveStatus
    const fetchMock = vi.fn(() => new Promise((resolve) => { resolveStatus = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    const { unmount } = render(<TestHarness />)
    const signal = fetchMock.mock.calls[0][1].signal
    unmount()
    expect(signal.aborted).toBe(true)
    await act(async () => {
      resolveStatus({
        ok: true,
        json: () => Promise.resolve({ status: 'ok', recording: true, elapsed_sec: 75 }),
      })
    })
    expect(screen.queryByTestId('record-dot')).not.toBeInTheDocument()
  })

  it('renders idle-themed by default', () => {
    render(<TestHarness />)
    const button = screen.getByTestId('record-button')
    expect(button).toBeInTheDocument()
    expect(button).toHaveTextContent('RECORD')
    // Idle theme matches the existing manual-capture-button palette.
    expect(button.style.color).toBe('var(--neon-cyan)')
    expect(button.style.border).toBe('1px solid var(--neon-cyan)')
    // No red dot, no elapsed readout while idle.
    expect(screen.queryByTestId('record-dot')).not.toBeInTheDocument()
    expect(screen.queryByTestId('record-elapsed')).not.toBeInTheDocument()
  })

  it('click while idle calls the start endpoint and transitions to recording', async () => {
    const fetchMock = mockFetchOk({ status: 'ok' })
    vi.stubGlobal('fetch', fetchMock)
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('record-button'))
    await waitFor(() =>
      expect(screen.getByTestId('record-dot')).toBeInTheDocument()
    )
    const startCalls = fetchMock.mock.calls.filter(([url]) => url === '/api/record/start')
    expect(startCalls).toHaveLength(1)
    const [url, opts] = startCalls[0]
    expect(url).toBe('/api/record/start')
    expect(opts.method).toBe('POST')
    // Recording visual state: red styling, dot present, elapsed readout.
    const button = screen.getByTestId('record-button')
    expect(button.style.color).toBe('var(--neon-red)')
    expect(button.style.border).toBe('1px solid var(--neon-red)')
    expect(button).toHaveTextContent('RECORD')
    expect(screen.getByTestId('record-elapsed')).toBeInTheDocument()
  })

  it('click while recording calls the stop endpoint and transitions back to idle', async () => {
    const fetchMock = vi.fn((url) =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            url === '/api/record/stop'
              ? {
                  status: 'ok',
                  file: '/tmp/rec.sigmf-meta',
                  duration_sec: 12.4,
                  cycle_count: 45,
                }
              : { status: 'ok' }
          ),
      })
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('record-button'))
    await waitFor(() =>
      expect(screen.getByTestId('record-dot')).toBeInTheDocument()
    )
    fireEvent.click(screen.getByTestId('record-button'))
    await waitFor(() =>
      expect(screen.queryByTestId('record-dot')).not.toBeInTheDocument()
    )
    const stopCalls = fetchMock.mock.calls.filter(([url]) => url === '/api/record/stop')
    expect(stopCalls).toHaveLength(1)
    const [url, opts] = stopCalls[0]
    expect(url).toBe('/api/record/stop')
    expect(opts.method).toBe('POST')
    // Back to idle visual state, with the minimal inline result readout.
    const button = screen.getByTestId('record-button')
    expect(button.style.color).toBe('var(--neon-cyan)')
    expect(screen.getByTestId('record-result')).toHaveTextContent(
      'Recorded 12.4s / 45 cycles'
    )
  })

  it('reports a capped recording as a successful save with the memory-cap suffix', async () => {
    const fetchMock = vi.fn((url) =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(
          url === '/api/record/stop'
            ? {
                status: 'cap_reached',
                file: '/tmp/capped.sigmf-meta',
                duration_sec: 12.4,
                cycle_count: 45,
              }
            : { status: 'ok' }
        ),
      })
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('record-button'))
    await waitFor(() =>
      expect(screen.getByTestId('record-dot')).toBeInTheDocument()
    )
    fireEvent.click(screen.getByTestId('record-button'))
    await waitFor(() =>
      expect(screen.getByTestId('record-result')).toHaveTextContent(
        'Recorded 12.4s / 45 cycles (stopped at memory cap)'
      )
    )
    const result = screen.getByTestId('record-result')
    expect(result).toHaveAttribute('data-status', 'ok')
    expect(result).toHaveAttribute('data-cap-reached', 'true')
    expect(result).not.toHaveTextContent('Recording failed')
    expect(screen.queryByTestId('record-dot')).not.toBeInTheDocument()
  })

  it('elapsed timer increments while recording', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.stubGlobal('fetch', mockFetchOk({ status: 'ok' }))
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('record-button'))
    await waitFor(() =>
      expect(screen.getByTestId('record-dot')).toBeInTheDocument()
    )
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByTestId('record-elapsed')).toHaveTextContent('00:03')
  })

  it('warning state at 60s recolours the readout without auto-stop', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const fetchMock = mockFetchOk({ status: 'ok' })
    vi.stubGlobal('fetch', fetchMock)
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('record-button'))
    await waitFor(() =>
      expect(screen.getByTestId('record-dot')).toBeInTheDocument()
    )
    // Before the threshold the readout is neon-red.
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByTestId('record-elapsed').style.color).toBe(
      'var(--neon-red)'
    )
    // Past 60 s the readout recolours to neon-amber...
    act(() => {
      vi.advanceTimersByTime(58000)
    })
    const elapsed = screen.getByTestId('record-elapsed')
    expect(elapsed).toHaveTextContent('01:01')
    expect(elapsed.style.color).toBe('var(--neon-amber)')
    // ...but the recording is STILL active and the stop endpoint was
    // NEVER called: the timer warning does not stop or save the recording.
    expect(screen.getByTestId('record-dot')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/record/start')).toHaveLength(1)
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/record/stop')).toHaveLength(0)
  })

  it('surfaces a stop-time error cause in the inline readout', async () => {
    const fetchMock = vi.fn((url) =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            url === '/api/record/stop'
              ? { status: 'error', cause: 'disk full' }
              : { status: 'ok' }
          ),
      })
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<TestHarness />)
    fireEvent.click(screen.getByTestId('record-button'))
    await waitFor(() =>
      expect(screen.getByTestId('record-dot')).toBeInTheDocument()
    )
    fireEvent.click(screen.getByTestId('record-button'))
    await waitFor(() =>
      expect(screen.getByTestId('record-result')).toHaveTextContent(
        'Recording failed: disk full'
      )
    )
    expect(screen.queryByTestId('record-dot')).not.toBeInTheDocument()
  })
})
