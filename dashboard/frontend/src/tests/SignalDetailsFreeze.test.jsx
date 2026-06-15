import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

vi.mock('../hooks/useSocket.js', () => ({
  useSocket: vi.fn(),
}))

import { useSocket } from '../hooks/useSocket.js'
import App from '../App.jsx'

const mockFocusFrequency = vi.fn()

describe('Signal Details freeze', () => {
  it('displays frozen signal details on render', async () => {
    useSocket.mockReturnValue({
      scanResults: [],
      spectrumUpdates: [],
      systemStats: null,
      focusedFreq: 98000000,
      focusFrequency: mockFocusFrequency,
      isConnected: false,
      acarsMessages: [],
      aiReasoning: {
        freq_hz: 98000000,
        signal_type: 'fm_broadcast',
        confidence: 'high',
        confidence_score: 0.95,
        au_legal_status: 'LEGAL RX',
        reasoning: 'Strong FM broadcast signal',
        timestamp: '2026-06-15T12:00:00.000Z',
      },
      aisVessels: [],
      adsbAircraft: {},
    })
    render(<App />)
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(screen.getByText('FM_BROADCAST')).toBeInTheDocument()
    expect(screen.getByText('95%')).toBeInTheDocument()
  })

  it('shows IDLE when no signal_type', async () => {
    useSocket.mockReturnValue({
      scanResults: [],
      spectrumUpdates: [],
      systemStats: null,
      focusedFreq: null,
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
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(screen.getByText('● IDLE')).toBeInTheDocument()
  })
})
