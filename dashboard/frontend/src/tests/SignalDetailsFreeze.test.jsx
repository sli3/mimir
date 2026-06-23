import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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
      adsbAircraftHistory: [],
    })
    render(<App />)
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(screen.getAllByText('FM_BROADCAST').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('95%').length).toBeGreaterThanOrEqual(1)
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
      adsbAircraftHistory: [],
    })
    render(<App />)
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(screen.getByText('IDLE')).toBeInTheDocument()
  })

  it('pins and unpins reasoning when clicking the same SignalHistoryLog row twice', async () => {
    useSocket.mockReturnValue({
      scanResults: [{
        timestamp: '2026-06-15T12:00:00.000Z',
        center_freq_hz: 98000000,
        signal_type: 'fm_broadcast',
        label: 'FM',
        confidence: 'high',
        confidence_score: 0.95,
        au_legal_status: 'LEGAL RX',
        reasoning: 'Strong FM broadcast signal',
      }],
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
      adsbAircraftHistory: [],
    })
    render(<App />)
    await new Promise((resolve) => setTimeout(resolve, 100))

    // No PINNED badge initially
    expect(screen.queryByText(/PINNED/)).not.toBeInTheDocument()

    // Click the history row to pin
    fireEvent.click(screen.getByText('[98.0 MHz]'))
    await new Promise((resolve) => setTimeout(resolve, 100))

    // PINNED badge appears
    expect(screen.getByText(/PINNED/)).toBeInTheDocument()

    // Click the same history row again to unpin
    fireEvent.click(screen.getByText('[98.0 MHz]'))
    await new Promise((resolve) => setTimeout(resolve, 100))

    // PINNED badge disappears
    expect(screen.queryByText(/PINNED/)).not.toBeInTheDocument()
  })
})
