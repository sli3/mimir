import { describe, it, expect, vi, afterEach } from 'vitest'
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

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

/**
 * TestHarness — exercises RecordButton through the real production
 * useRecording hook, the same wiring App.jsx uses. The parent owns the
 * click handler (start vs stop decided from the recording state) and
 * renders the minimal inline result readout, mirroring App.jsx.
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
        <span data-testid="record-result">
          {recordResult.status === 'ok'
            ? `Recorded ${recordResult.duration_sec.toFixed(1)}s / ${recordResult.cycle_count} cycles`
            : `Recording failed: ${recordResult.cause}`}
        </span>
      )}
    </div>
  )
}

describe('RecordButton', () => {
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
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, opts] = fetchMock.mock.calls[0]
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
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [url, opts] = fetchMock.mock.calls[1]
    expect(url).toBe('/api/record/stop')
    expect(opts.method).toBe('POST')
    // Back to idle visual state, with the minimal inline result readout.
    const button = screen.getByTestId('record-button')
    expect(button.style.color).toBe('var(--neon-cyan)')
    expect(screen.getByTestId('record-result')).toHaveTextContent(
      'Recorded 12.4s / 45 cycles'
    )
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
    // NEVER called — no auto-stop, no backend cap.
    expect(screen.getByTestId('record-dot')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/record/start')
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
