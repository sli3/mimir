import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

vi.mock('../hooks/useSocket.js', () => ({
  useSocket: vi.fn(),
}))

import { useSocket } from '../hooks/useSocket.js'
import App from '../App.jsx'

const mockFocusFrequency = vi.fn()

describe('Decoded signals visibility', () => {
  const makeMock = (focusedFreq) => ({
    scanResults: [],
    spectrumUpdates: [],
    systemStats: null,
    device: null,
    unsupportedBands: {},
    focusedFreq,
    focusFrequency: mockFocusFrequency,
    isConnected: false,
    acarsMessages: [],
    aiReasoning: {
      freq_hz: null,
      signal_type: null,
      confidence: null,
      confidence_score: null,
      au_legal_status: null,
      reasoning: null,
      timestamp: null,
    },
    aisVessels: [],
    adsbAircraft: {},
    adsbAircraftHistory: [],
    acarsRawLog: [],
    aisRawLog: [],
  })

  it('shows only ADS-B sub-panel when focusedFreq is 1090000000', () => {
    useSocket.mockReturnValue(makeMock(1090000000))
    render(<App />)
    // ADS-B sub-panel header is present (one or more matches OK — App + component both render)
    expect(screen.getAllByText('ADS-B AIRCRAFT').length).toBeGreaterThanOrEqual(1)
    // ACARS and AIS sub-panel headers must be absent entirely
    expect(screen.queryAllByText('ACARS MESSAGES').length).toBe(0)
    expect(screen.queryAllByText('AIS VESSELS').length).toBe(0)
    // UI-OVERHAUL (Change 6): all three decoded-signal columns are active
    // when tuned to ADS-B, so no column shows the fallback.
    expect(screen.queryAllByText('NO DECODER FOR THIS BAND').length).toBe(0)
  })

  it('shows only ACARS sub-panel when focusedFreq is 129125000', () => {
    useSocket.mockReturnValue(makeMock(129125000))
    render(<App />)
    // ACARS sub-panel header is present (one or more matches OK — App + component both render)
    expect(screen.getAllByText('ACARS MESSAGES').length).toBeGreaterThanOrEqual(1)
    // ADS-B and AIS sub-panel headers must be absent entirely
    expect(screen.queryAllByText('ADS-B AIRCRAFT').length).toBe(0)
    expect(screen.queryAllByText('AIS VESSELS').length).toBe(0)
    // UI-OVERHAUL (Change 6): SIGNAL INTERCEPT has a decoder, but the
    // ADS-B-only RAW DECODE and FRAME INSPECTOR columns show the fallback.
    expect(screen.queryAllByText('NO DECODER FOR THIS BAND').length).toBe(2)
  })

  it('shows only ACARS sub-panel when focusedFreq is 130025000', () => {
    useSocket.mockReturnValue(makeMock(130025000))
    render(<App />)
    expect(screen.getAllByText('ACARS MESSAGES').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryAllByText('ADS-B AIRCRAFT').length).toBe(0)
    expect(screen.queryAllByText('AIS VESSELS').length).toBe(0)
    expect(screen.queryAllByText('NO DECODER FOR THIS BAND').length).toBe(2)
  })

  it('shows only AIS sub-panel when focusedFreq is 162000000', () => {
    useSocket.mockReturnValue(makeMock(162000000))
    render(<App />)
    // AIS sub-panel header is present (one or more matches OK — App + component both render)
    expect(screen.getAllByText('AIS VESSELS').length).toBeGreaterThanOrEqual(1)
    // ADS-B and ACARS sub-panel headers must be absent entirely
    expect(screen.queryAllByText('ADS-B AIRCRAFT').length).toBe(0)
    expect(screen.queryAllByText('ACARS MESSAGES').length).toBe(0)
    // UI-OVERHAUL (Change 6): ADS-B-only columns 2 and 3 show the fallback.
    expect(screen.queryAllByText('NO DECODER FOR THIS BAND').length).toBe(2)
  })

  it('shows placeholder when focusedFreq is 98000000 (FM — no decoder)', () => {
    useSocket.mockReturnValue(makeMock(98000000))
    render(<App />)
    expect(screen.queryAllByText('ADS-B AIRCRAFT').length).toBe(0)
    expect(screen.queryAllByText('ACARS MESSAGES').length).toBe(0)
    expect(screen.queryAllByText('AIS VESSELS').length).toBe(0)
    // All three decoded-signal columns show the fallback.
    expect(screen.queryAllByText('NO DECODER FOR THIS BAND').length).toBe(3)
  })

  it('shows placeholder when focusedFreq is null', () => {
    useSocket.mockReturnValue(makeMock(null))
    render(<App />)
    expect(screen.queryAllByText('ADS-B AIRCRAFT').length).toBe(0)
    expect(screen.queryAllByText('ACARS MESSAGES').length).toBe(0)
    expect(screen.queryAllByText('AIS VESSELS').length).toBe(0)
    expect(screen.queryAllByText('NO DECODER FOR THIS BAND').length).toBe(3)
  })
})