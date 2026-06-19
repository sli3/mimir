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
  })

  it('does NOT render NOT TUNED prompt when focusedFreq is 161975000', () => {
    useSocket.mockReturnValue(makeMock(161975000))
    render(<App />)
    expect(screen.queryByText(/TUNE TO 161\.975 MHz TO DECODE AIS/)).toBeNull()
    expect(screen.getByText('Listening on 161.975 MHz...')).toBeInTheDocument()
  })

  it('renders NOT TUNED prompt when focusedFreq is null', () => {
    useSocket.mockReturnValue(makeMock(null))
    render(<App />)
    expect(screen.getByText(/TUNE TO 161\.975 MHz TO DECODE AIS/)).toBeInTheDocument()
    expect(screen.queryByText('Listening on 161.975 MHz...')).toBeNull()
  })
})
