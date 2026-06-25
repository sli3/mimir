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
  })

  it('shows only ADS-B sub-panel when focusedFreq is 1090000000', () => {
    useSocket.mockReturnValue(makeMock(1090000000))
    render(<App />)
    expect(screen.getByText('ADS-B AIRCRAFT')).toBeInTheDocument()
    expect(screen.queryByText('ACARS MESSAGES')).toBeNull()
    expect(screen.queryByText('AIS VESSELS')).toBeNull()
    expect(screen.queryByText('NO DECODER FOR THIS BAND')).toBeNull()
  })

  it('shows only ACARS sub-panel when focusedFreq is 129125000', () => {
    useSocket.mockReturnValue(makeMock(129125000))
    render(<App />)
    expect(screen.getByText('ACARS MESSAGES')).toBeInTheDocument()
    expect(screen.queryByText('ADS-B AIRCRAFT')).toBeNull()
    expect(screen.queryByText('AIS VESSELS')).toBeNull()
    expect(screen.queryByText('NO DECODER FOR THIS BAND')).toBeNull()
  })

  it('shows only ACARS sub-panel when focusedFreq is 130025000', () => {
    useSocket.mockReturnValue(makeMock(130025000))
    render(<App />)
    expect(screen.getByText('ACARS MESSAGES')).toBeInTheDocument()
    expect(screen.queryByText('ADS-B AIRCRAFT')).toBeNull()
    expect(screen.queryByText('AIS VESSELS')).toBeNull()
    expect(screen.queryByText('NO DECODER FOR THIS BAND')).toBeNull()
  })

  it('shows only AIS sub-panel when focusedFreq is 162000000', () => {
    useSocket.mockReturnValue(makeMock(162000000))
    render(<App />)
    expect(screen.getByText('AIS VESSELS')).toBeInTheDocument()
    expect(screen.queryByText('ADS-B AIRCRAFT')).toBeNull()
    expect(screen.queryByText('ACARS MESSAGES')).toBeNull()
    expect(screen.queryByText('NO DECODER FOR THIS BAND')).toBeNull()
  })

  it('shows placeholder when focusedFreq is 98000000 (FM — no decoder)', () => {
    useSocket.mockReturnValue(makeMock(98000000))
    render(<App />)
    expect(screen.queryByText('ADS-B AIRCRAFT')).toBeNull()
    expect(screen.queryByText('ACARS MESSAGES')).toBeNull()
    expect(screen.queryByText('AIS VESSELS')).toBeNull()
    expect(screen.getByText('NO DECODER FOR THIS BAND')).toBeInTheDocument()
  })

  it('shows placeholder when focusedFreq is null', () => {
    useSocket.mockReturnValue(makeMock(null))
    render(<App />)
    expect(screen.queryByText('ADS-B AIRCRAFT')).toBeNull()
    expect(screen.queryByText('ACARS MESSAGES')).toBeNull()
    expect(screen.queryByText('AIS VESSELS')).toBeNull()
    expect(screen.getByText('NO DECODER FOR THIS BAND')).toBeInTheDocument()
  })
})
