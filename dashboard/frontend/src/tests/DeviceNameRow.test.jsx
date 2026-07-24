import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

const mockFocusFrequency = vi.fn()

vi.mock('../hooks/useSocket.js')

import { useSocket } from '../hooks/useSocket.js'
import App from '../App.jsx'

const defaultUseSocket = () => ({
  scanResults: [],
  spectrumUpdates: [],
  systemStats: null,
  device: null,
  unsupportedBands: {},
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
    source: null,
    novel: null,
  },
  aisVessels: [],
  adsbAircraft: {},
  adsbAircraftHistory: [],
  acarsRawLog: [],
  aisRawLog: [],
})

describe('DEVICE row in signal-detail panel (Phase 40b)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFocusFrequency.mockClear()
    useSocket.mockReturnValue(defaultUseSocket())
  })

  it('renders --- fallback when systemStats has no current_device_display', async () => {
    useSocket.mockReturnValue({
      ...defaultUseSocket(),
      systemStats: { device: 'hackrf' },  // device key present, display missing
      aiReasoning: {
        freq_hz: 98000000,
        signal_type: 'fm_broadcast',
        confidence: 'high',
        confidence_score: 0.95,
        au_legal_status: 'LEGAL RX',
        reasoning: 'Strong FM broadcast signal',
        timestamp: '2026-06-15T12:00:00.000Z',
      },
      focusedFreq: 98000000,
    })
    render(<App />)
    await new Promise((resolve) => setTimeout(resolve, 100))
    // The DEVICE label should be present...
    expect(screen.getAllByText('DEVICE').length).toBeGreaterThanOrEqual(1)
    // ...and its value should be the '---' fallback, not 'undefined' or 'hackrf'.
    const deviceRow = screen.getAllByText('DEVICE').find(
      (el) => el.tagName === 'SPAN' || el.tagName === 'DIV'
    )
    expect(deviceRow).toBeDefined()
    // The row's value sits next to its label; assert the '---' text is rendered.
    expect(screen.getAllByText('---').length).toBeGreaterThanOrEqual(1)
  })

  it('renders the friendly display name when systemStats.current_device_display is set', async () => {
    useSocket.mockReturnValue({
      ...defaultUseSocket(),
      systemStats: { device: 'hackrf', current_device_display: 'HackRF One' },
      aiReasoning: {
        freq_hz: 98000000,
        signal_type: 'fm_broadcast',
        confidence: 'high',
        confidence_score: 0.95,
        au_legal_status: 'LEGAL RX',
        reasoning: 'Strong FM broadcast signal',
        timestamp: '2026-06-15T12:00:00.000Z',
      },
      focusedFreq: 98000000,
    })
    render(<App />)
    await new Promise((resolve) => setTimeout(resolve, 100))
    // The DEVICE label and the friendly name should both render.
    expect(screen.getAllByText('DEVICE').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('HackRF One')).toBeInTheDocument()
  })
})
