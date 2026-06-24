import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'

const mockFocusFrequency = vi.fn()

vi.mock('../hooks/useSocket.js', () => ({
  useSocket: () => ({
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
  }),
}))

import App from '../App.jsx'

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFocusFrequency.mockClear()
  })

  it('renders without crashing', () => {
    render(<App />)
  })

  it('renders MIMIR header', () => {
    render(<App />)
    expect(screen.getByText('MIMIR')).toBeInTheDocument()
  })

  it('renders PASSIVE RF INTELLIGENCE subtitle', () => {
    render(<App />)
    expect(screen.getByText(/PASSIVE RF INTELLIGENCE/)).toBeInTheDocument()
  })

  it('renders waterfall with singleBand mode (2 canvases for one strip)', () => {
    render(<App />)
    const waterfallSlot = screen.getByTestId('waterfall')
    const canvases = waterfallSlot.querySelectorAll('canvas')
    expect(canvases.length).toBe(2)
  })

  it('renders SIGNAL DETAILS panel', () => {
    render(<App />)
    expect(screen.getByText('SIGNAL DETAILS')).toBeInTheDocument()
  })

  it('renders SYSTEM STATUS section', () => {
    render(<App />)
    expect(screen.getByText('SYSTEM STATUS')).toBeInTheDocument()
  })

  it('renders SIGNAL HISTORY section', () => {
    render(<App />)
    expect(screen.getByText('SIGNAL HISTORY')).toBeInTheDocument()
  })

  it('renders AI REASONING section', () => {
    render(<App />)
    expect(screen.getByText('AI REASONING')).toBeInTheDocument()
  })

  it('renders DECODED SIGNALS section', () => {
    render(<App />)
    expect(screen.getByText('DECODED SIGNALS')).toBeInTheDocument()
  })

  it('renders ADS-B AIRCRAFT sub-panel', () => {
    render(<App />)
    expect(screen.getByText('ADS-B AIRCRAFT')).toBeInTheDocument()
  })

  it('renders ACARS MESSAGES sub-panel', () => {
    render(<App />)
    expect(screen.getByText('ACARS MESSAGES')).toBeInTheDocument()
  })

  it('renders AIS VESSELS sub-panel', () => {
    render(<App />)
    expect(screen.getByText('AIS VESSELS')).toBeInTheDocument()
  })

  it('renders OPERATOR indicator', () => {
    render(<App />)
    expect(screen.getByText('OPERATOR — MONITORING')).toBeInTheDocument()
  })

  it('renders 7 band buttons', () => {
    render(<App />)
    const buttons = screen.getAllByRole('button')
    const labels = buttons.map((b) => b.textContent)
    expect(labels).toContain('FM')
    expect(labels).toContain('AVIATION')
    expect(labels).toContain('ACARS')
    expect(labels).toContain('APRS')
    expect(labels).toContain('ISM')
    expect(labels).toContain('ADS-B')
    expect(labels).toContain('AIS')
  })

  it('clicking FM band button calls focusFrequency with 98000000', () => {
    render(<App />)
    const buttons = screen.getAllByRole('button')
    const fmButton = buttons.find((b) => b.textContent === 'FM')
    fireEvent.click(fmButton)
    expect(mockFocusFrequency).toHaveBeenCalledWith(98000000)
  })

  it('clicking ADS-B band button calls focusFrequency with 1090000000', () => {
    render(<App />)
    const buttons = screen.getAllByRole('button')
    const adsbButton = buttons.find((b) => b.textContent === 'ADS-B')
    fireEvent.click(adsbButton)
    expect(mockFocusFrequency).toHaveBeenCalledWith(1090000000)
  })

  it('clicking AIS band button calls focusFrequency with 162000000', () => {
    render(<App />)
    const buttons = screen.getAllByRole('button')
    const aisButton = buttons.find((b) => b.textContent === 'AIS')
    fireEvent.click(aisButton)
    expect(mockFocusFrequency).toHaveBeenCalledWith(162000000)
  })

  it('custom frequency TUNE button calls focusFrequency with parseFloat*1e6', () => {
    render(<App />)
    const input = document.querySelector('input[type="text"]')
    fireEvent.change(input, { target: { value: '162.025' } })
    const tuneButton = screen.getByText('TUNE ▶')
    fireEvent.click(tuneButton)
    expect(mockFocusFrequency).toHaveBeenCalledWith(162025000)
  })

  it('custom frequency Enter key calls focusFrequency', () => {
    render(<App />)
    const input = document.querySelector('input[type="text"]')
    fireEvent.change(input, { target: { value: '145.175' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(mockFocusFrequency).toHaveBeenCalledWith(145175000)
  })

  it('renders 4 mini band overview cells', () => {
    render(<App />)
    const spans = screen.getAllByText('FM BROADCAST')
    expect(spans.length).toBeGreaterThanOrEqual(1)
    const ismSpans = screen.getAllByText('ISM / LoRa')
    expect(ismSpans.length).toBeGreaterThanOrEqual(1)
  })

  it('renders mini band overview with correct frequencies', () => {
    render(<App />)
    expect(screen.getByText('98.000 MHz')).toBeInTheDocument()
    expect(screen.getByText('145.175 MHz')).toBeInTheDocument()
    expect(screen.getByText('162.000 MHz')).toBeInTheDocument()
    expect(screen.getByText('915.000 MHz')).toBeInTheDocument()
    expect(screen.getByText('1090.000 MHz')).toBeInTheDocument()
  })

  it('renders SDR STATUS disconnected when systemStats is null', () => {
    render(<App />)
    const disconnected = screen.getAllByText('DISCONNECTED')
    expect(disconnected.length).toBeGreaterThanOrEqual(1)
  })

  it('renders 0 ENTRIES when scanResults is empty', () => {
    render(<App />)
    expect(screen.getByText('0 ENTRIES')).toBeInTheDocument()
  })

  it('renders BACKLOG and IN QUEUE labels', () => {
    render(<App />)
    expect(screen.getByText('BACKLOG')).toBeInTheDocument()
    expect(screen.getByText('IN QUEUE')).toBeInTheDocument()
  })

  it('renders CLASSIFIED label', () => {
    render(<App />)
    expect(screen.getByText('CLASSIFIED')).toBeInTheDocument()
  })
})
