import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

vi.mock('../hooks/useSocket.js', () => ({
  useSocket: vi.fn(),
}))

import { useSocket } from '../hooks/useSocket.js'
import App from '../App.jsx'

const mockFocusFrequency = vi.fn()

describe('AIS tuned state', () => {
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

  it('does NOT render NOT TUNED prompt when focusedFreq is 162000000', () => {
    useSocket.mockReturnValue(makeMock(162000000))
    render(<App />)
    expect(screen.queryByText(/TUNE TO 162\.000 MHz TO DECODE AIS/)).toBeNull()
    expect(screen.getByText('Listening on 162.000 MHz...')).toBeInTheDocument()
  })

  it('hides AIS sub-panel when focusedFreq is null', () => {
    useSocket.mockReturnValue(makeMock(null))
    render(<App />)
    expect(screen.queryByText('AIS VESSELS')).toBeNull()
  })
})
