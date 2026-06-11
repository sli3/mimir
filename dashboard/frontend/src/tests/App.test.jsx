import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

vi.mock('../hooks/useSocket.js', () => ({
  useSocket: () => ({
    scanResults: [],
    spectrumUpdates: [],
    systemStats: null,
    focusedFreq: null,
    focusFrequency: vi.fn(),
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
  }),
}))

import App from '../App.jsx'

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without crashing', () => {
    render(<App />)
  })

  it('renders MIMIR header', () => {
    render(<App />)
    expect(screen.getByText('MIMIR')).toBeInTheDocument()
  })

  it('renders waterfall slot', () => {
    render(<App />)
    const slot = document.getElementById('waterfall-slot')
    expect(slot).toBeInTheDocument()
    const canvases = slot.querySelectorAll('canvas')
    expect(canvases.length).toBe(8)
  })

  it('renders AWAITING SIGNAL...', () => {
    render(<App />)
    expect(screen.getByText('AWAITING SIGNAL...')).toBeInTheDocument()
  })

  it('renders OPERATOR', () => {
    render(<App />)
    expect(screen.getByText('OPERATOR')).toBeInTheDocument()
  })

  it('renders SDR STATUS', () => {
    render(<App />)
    expect(screen.getByText('SDR STATUS')).toBeInTheDocument()
  })
})
