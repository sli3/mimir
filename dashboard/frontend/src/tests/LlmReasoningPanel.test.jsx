import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import React from 'react'

import LlmReasoningPanel from '../components/LlmReasoningPanel.jsx'

// Fixture mirrors the props PathPredictionPanel passes in State 3:
// a selected aircraft with a derived vector and a 45 s projection.
const makeProps = (overrides = {}) => ({
  icao: 'ABC123',
  callsign: 'QFA1',
  squawk: null,
  altitude_ft: 35000,
  track: 270,
  groundspeed: 450,
  vertical_rate: 0,
  bearing_deg: 45,
  range_nm: 10,
  vector: { thetaDegPerSec: 0.5, deltaRNmPerSec: -0.1 },
  projected: { bearing_deg: 67.5, range_nm: 5.5 },
  trailLength: 3,
  ...overrides,
})

const okBody = {
  status: 'ok',
  verdict: 'Steady cruise on a stable heading',
  confidence: 'high',
  notes: 'Projection consistent with current vector.',
  cause: null,
}

const mockFetchOk = (body = okBody) =>
  vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve(body),
    })
  )

// A fetch that never settles — used for loading-state, abort, and
// late-response tests where the promise resolution is controlled by
// capturing the signal rather than resolving.
const mockFetchPending = () =>
  vi.fn(
    (_url, _opts) => new Promise(() => {})
  )

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('LlmReasoningPanel', () => {
  describe('idle state', () => {
    it('renders the trigger button with the expected label', () => {
      render(<LlmReasoningPanel {...makeProps()} />)
      const button = screen.getByRole('button', { name: 'ANALYSE PATH WITH LLM' })
      expect(button).toBeInTheDocument()
      expect(button).not.toBeDisabled()
      expect(screen.getByTestId('radar-prediction-llm')).toBeInTheDocument()
    })

    it('posts the validated payload shape to the relative endpoint', async () => {
      const fetchMock = mockFetchOk()
      vi.stubGlobal('fetch', fetchMock)

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      expect(fetchMock).toHaveBeenCalledTimes(1)
      const [url, opts] = fetchMock.mock.calls[0]
      expect(url).toBe('/api/radar/reason')
      expect(opts.method).toBe('POST')
      const payload = JSON.parse(opts.body)
      expect(payload).toEqual({
        icao: 'ABC123',
        callsign: 'QFA1',
        squawk: null,
        altitude_ft: 35000,
        track: 270,
        groundspeed: 450,
        vertical_rate: 0,
        bearing_deg: 45,
        range_nm: 10,
        theta_deg_per_sec: 0.5,
        delta_r_nm_per_sec: -0.1,
        projected_bearing_deg: 67.5,
        projected_range_nm: 5.5,
        trail_length: 3,
      })
      await waitFor(() =>
        expect(screen.getByText('Steady cruise on a stable heading')).toBeInTheDocument()
      )
    })
  })

  describe('loading state', () => {
    it('disables the button and shows the analysing message after click', () => {
      vi.stubGlobal('fetch', mockFetchPending())

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      expect(screen.getByRole('button')).toBeDisabled()
      expect(screen.getByText('ANALYSING…')).toBeInTheDocument()
    })

    it('escalates the loading message after 10 seconds', () => {
      vi.useFakeTimers()
      vi.stubGlobal('fetch', mockFetchPending())

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))
      expect(screen.getByText('ANALYSING…')).toBeInTheDocument()

      act(() => {
        vi.advanceTimersByTime(10000)
      })

      expect(screen.getByText('ANALYSING — SERVER BUSY…')).toBeInTheDocument()
    })

    it('does not escalate the message before 10 seconds', () => {
      vi.useFakeTimers()
      vi.stubGlobal('fetch', mockFetchPending())

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      act(() => {
        vi.advanceTimersByTime(9999)
      })

      expect(screen.getByText('ANALYSING…')).toBeInTheDocument()
      expect(screen.queryByText('ANALYSING — SERVER BUSY…')).not.toBeInTheDocument()
    })
  })

  describe('result state', () => {
    it('renders verdict, colour-coded confidence and notes', async () => {
      vi.stubGlobal('fetch', mockFetchOk())

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() =>
        expect(screen.getByText('Steady cruise on a stable heading')).toBeInTheDocument()
      )
      const confidence = screen.getByText('HIGH CONFIDENCE')
      expect(confidence.className).toContain('radar-prediction-llm-confidence-high')
      expect(
        screen.getByText('Projection consistent with current vector.')
      ).toBeInTheDocument()
    })

    it('renders the prediction glyph above the verdict (Phase 55)', async () => {
      vi.stubGlobal('fetch', mockFetchOk())

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() =>
        expect(screen.getByText('Steady cruise on a stable heading')).toBeInTheDocument()
      )
      const glyph = screen.getByTestId('prediction-glyph')
      expect(glyph).toBeInTheDocument()
      // Placement contract: glyph precedes the verdict in the result block.
      const verdict = screen.getByText('Steady cruise on a stable heading')
      expect(
        glyph.compareDocumentPosition(verdict) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy()
    })

    it('clamps an unexpected confidence tier to the low styling', async () => {
      vi.stubGlobal(
        'fetch',
        mockFetchOk({ ...okBody, confidence: 'absolute' })
      )

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() =>
        expect(screen.getByText('LOW CONFIDENCE')).toBeInTheDocument()
      )
    })
  })

  describe('error state', () => {
    it('maps a transport failure to "LLM unreachable"', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() => Promise.reject(new TypeError('Failed to fetch')))
      )

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() =>
        expect(screen.getByText('LLM unreachable')).toBeInTheDocument()
      )
    })

    it('maps a server timeout cause to the timeout message', async () => {
      vi.stubGlobal(
        'fetch',
        mockFetchOk({ status: 'unavailable', verdict: 'unavailable', confidence: 'low', notes: 'timed out', cause: 'timeout' })
      )

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() =>
        expect(
          screen.getByText('LLM timed out — server busy, retry shortly')
        ).toBeInTheDocument()
      )
    })

    it('maps a server parse cause to "Response unreadable"', async () => {
      vi.stubGlobal(
        'fetch',
        mockFetchOk({ status: 'unavailable', verdict: 'unavailable', confidence: 'low', notes: 'bad json', cause: 'parse' })
      )

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() =>
        expect(screen.getByText('Response unreadable')).toBeInTheDocument()
      )
    })

    it('maps an unparseable response body to "Response unreadable"', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() =>
          Promise.resolve({
            ok: true,
            json: () => Promise.reject(new Error('invalid json')),
          })
        )
      )

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() =>
        expect(screen.getByText('Response unreadable')).toBeInTheDocument()
      )
    })

    it('maps a 400 validation rejection to the rejected message, not "LLM unreachable" (Phase 55)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() =>
          Promise.resolve({
            ok: false,
            status: 400,
            json: () => Promise.resolve({ error: 'Invalid theta_deg_per_sec' }),
          })
        )
      )

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() =>
        expect(
          screen.getByText('Invalid request — payload rejected')
        ).toBeInTheDocument()
      )
      expect(screen.queryByText('LLM unreachable')).not.toBeInTheDocument()
    })

    it('maps a 500 server failure to "LLM unreachable" (Phase 55)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() =>
          Promise.resolve({
            ok: false,
            status: 500,
            json: () => Promise.resolve({ error: 'Internal server error' }),
          })
        )
      )

      render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() =>
        expect(screen.getByText('LLM unreachable')).toBeInTheDocument()
      )
      expect(
        screen.queryByText('Invalid request — payload rejected')
      ).not.toBeInTheDocument()
    })
  })

  describe('lifecycle guards', () => {
    it('resets to idle when the selected icao changes', async () => {
      vi.stubGlobal('fetch', mockFetchOk())

      const { rerender } = render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))
      await waitFor(() =>
        expect(screen.getByText('Steady cruise on a stable heading')).toBeInTheDocument()
      )

      rerender(<LlmReasoningPanel {...makeProps({ icao: 'DEF456' })} />)

      expect(
        screen.queryByText('Steady cruise on a stable heading')
      ).not.toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'ANALYSE PATH WITH LLM' })
      ).not.toBeDisabled()
    })

    it('aborts the in-flight request on unmount', () => {
      let capturedSignal = null
      vi.stubGlobal(
        'fetch',
        vi.fn((_url, opts) => {
          capturedSignal = opts.signal
          return new Promise(() => {})
        })
      )

      const { unmount } = render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))
      expect(capturedSignal).not.toBeNull()
      expect(capturedSignal.aborted).toBe(false)

      unmount()

      expect(capturedSignal.aborted).toBe(true)
    })

    it('ignores a late response after the selection changes', async () => {
      let resolveRequest = null
      vi.stubGlobal(
        'fetch',
        vi.fn(
          () =>
            new Promise((resolve) => {
              resolveRequest = resolve
            })
        )
      )

      const { rerender } = render(<LlmReasoningPanel {...makeProps()} />)
      fireEvent.click(screen.getByRole('button'))

      // Selection changes while the request is in flight.
      rerender(<LlmReasoningPanel {...makeProps({ icao: 'DEF456' })} />)

      // The stale request now resolves — its verdict must be dropped.
      await act(async () => {
        resolveRequest({
          ok: true,
          json: () => Promise.resolve(okBody),
        })
      })

      expect(
        screen.queryByText('Steady cruise on a stable heading')
      ).not.toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'ANALYSE PATH WITH LLM' })
      ).toBeInTheDocument()
    })
  })
})
