import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

vi.mock('../hooks/useSocket.js', () => ({
  useSocket: vi.fn(),
}))

import { useSocket } from '../hooks/useSocket.js'
import App from '../App.jsx'

const mockFocusFrequency = vi.fn()

describe('ADS-B tuned state', () => {
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

  it('does NOT render NOT TUNED prompt when focusedFreq is 1090000000', () => {
    useSocket.mockReturnValue(makeMock(1090000000))
    render(<App />)
    expect(screen.queryByText(/TUNE TO 1090\.000 MHz TO DECODE ADS-B/)).toBeNull()
    expect(screen.getByText('Listening on 1090.000 MHz...')).toBeInTheDocument()
  })

  it('hides ADS-B sub-panel when focusedFreq is null', () => {
    useSocket.mockReturnValue(makeMock(null))
    render(<App />)
    expect(screen.queryByText('ADS-B AIRCRAFT')).toBeNull()
  })
})
