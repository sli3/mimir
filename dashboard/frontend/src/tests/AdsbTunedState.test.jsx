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
  it('does NOT render red NOT TUNED prompt when focusedFreq is 1090000000', () => {
    useSocket.mockReturnValue({
      scanResults: [],
      spectrumUpdates: [],
      systemStats: null,
      focusedFreq: 1090000000,
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
    render(<App />)
    const notTunedPrompt = screen.queryByText(/TUNE TO 1090\.000 MHz TO DECODE ADS-B/)
    expect(notTunedPrompt).toBeNull()
    expect(screen.getByText('Listening on 1090.000 MHz...')).toBeInTheDocument()
  })
})
