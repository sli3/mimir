import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFocusFrequency.mockClear()
    useSocket.mockReturnValue(defaultUseSocket())
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

  it('renders SIGNAL INTERCEPT section', () => {
    render(<App />)
    expect(screen.getByText('SIGNAL INTERCEPT')).toBeInTheDocument()
  })

  it('does not render ADS-B AIRCRAFT sub-panel when focusedFreq is null', () => {
    render(<App />)
    expect(screen.queryByText('ADS-B AIRCRAFT')).toBeNull()
  })

  it('does not render ACARS MESSAGES sub-panel when focusedFreq is null', () => {
    render(<App />)
    expect(screen.queryByText('ACARS MESSAGES')).toBeNull()
  })

  it('does not render AIS VESSELS sub-panel when focusedFreq is null', () => {
    render(<App />)
    expect(screen.queryByText('AIS VESSELS')).toBeNull()
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

  function makeAiReasoning(overrides) {
    return {
      freq_hz: 98000000,
      signal_type: 'fm_broadcast',
      confidence: 'high',
      confidence_score: 0.95,
      au_legal_status: 'LEGAL RX',
      reasoning: 'Signal matches FM broadcast characteristics',
      timestamp: '2026-07-14T12:00:00.000Z',
      peak_power_db: -72.0,
      peak_bin_power_db: -70.0,
      snr_db: 8.0,
      bandwidth_hz: 200000,
      spectral_flatness: 0.45,
      chroma_distance: 0.123,
      signal_threshold_db: 10.0,
      snr_margin_db: -2.0,
      novel: false,
      source: null,
      ...overrides,
    }
  }

  function findRowValue(container, label) {
    const allSpans = [...container.querySelectorAll('span')]
    const labelSpan = allSpans.find((s) => s.textContent === label)
    if (!labelSpan) return null
    const rowDiv = labelSpan.parentElement
    return rowDiv.querySelectorAll('span')[1]
  }

  describe('App confidence provenance gate (Phase 32)', () => {
    it('dims CONFIDENCE value when source=fingerprint and no measurement', () => {
      useSocket.mockReturnValueOnce({
        ...defaultUseSocket(),
        focusedFreq: 98000000,
        aiReasoning: makeAiReasoning({
          source: 'fingerprint',
          snr_db: null,
          bandwidth_hz: null,
          reasoning: 'Frequency match only — no real signal',
        }),
      })
      const { container } = render(<App />)
      const confidenceValue = findRowValue(container, 'CONFIDENCE')
      expect(confidenceValue).toBeTruthy()
      expect(confidenceValue.textContent).toBe('95%')
      expect(confidenceValue.style.color).toBe('var(--text-dim)')
    })

    it('keeps CONFIDENCE value bright when source=decode even without measurement', () => {
      useSocket.mockReturnValueOnce({
        ...defaultUseSocket(),
        focusedFreq: 1090000000,
        aiReasoning: makeAiReasoning({
          source: 'decode',
          signal_type: 'adsb',
          snr_db: null,
          bandwidth_hz: null,
          confidence_score: 1.0,
          reasoning: 'Confirmed ADS-B decode',
        }),
      })
      const { container } = render(<App />)
      const confidenceValue = findRowValue(container, 'CONFIDENCE')
      expect(confidenceValue.style.color).toBe('var(--neon-green)')
    })

    it('keeps CONFIDENCE value bright when source=fingerprint and measurement present', () => {
      useSocket.mockReturnValueOnce({
        ...defaultUseSocket(),
        focusedFreq: 98000000,
        aiReasoning: makeAiReasoning({
          source: 'fingerprint',
          snr_db: 12.0,
          bandwidth_hz: 200000,
        }),
      })
      const { container } = render(<App />)
      const confidenceValue = findRowValue(container, 'CONFIDENCE')
      expect(confidenceValue.style.color).toBe('var(--neon-green)')
    })
  })

  describe('App unsupported-band tooltip (Phase 38-Hotfix-1)', () => {
    // Phase 38-Hotfix-1 regression lock: an unsupported band button
    // must render with a title attribute (so the native tooltip fires
    // on hover) AND must NOT carry the HTML disabled attribute (which
    // removes the element from hit-testing and suppresses the tooltip).
    // Click is blocked by the onClick omission, not by disabled.

    const plutoReason = {
      fm_broadcast: "Below Pluto's 325 MHz tuning floor (98 MHz)",
      aviation: "Below Pluto's 325 MHz tuning floor (127 MHz)",
      acars: "Below Pluto's 325 MHz tuning floor (129.125 MHz)",
      aprs: "Below Pluto's 325 MHz tuning floor (145.175 MHz)",
      ais: "Below Pluto's 325 MHz tuning floor (162 MHz)",
    }

    it('BAND_GROUPS unsupported button has title and is not disabled (Pluto)', () => {
      useSocket.mockReturnValueOnce({
        ...defaultUseSocket(),
        device: 'plutosdr',
        unsupportedBands: plutoReason,
      })
      const { container } = render(<App />)
      // FM is the BAND_GROUPS "BROADCAST" band
      const buttons = [...container.querySelectorAll('button')]
      const fmButton = buttons.find((b) => b.textContent === 'FM')
      expect(fmButton).toBeDefined()
      // Title must be the reason string
      expect(fmButton.getAttribute('title')).toBe(plutoReason.fm_broadcast)
      // CRITICAL: the disabled attribute must NOT be present.
      // Both attribute-presence and JS-property-presence must fail
      // to catch every way the regression could re-appear.
      expect(fmButton.hasAttribute('disabled')).toBe(false)
      expect(fmButton.disabled).toBe(false)
    })

    it('clicking an unsupported BAND_GROUPS button does not call focusFrequency', () => {
      useSocket.mockReturnValueOnce({
        ...defaultUseSocket(),
        device: 'plutosdr',
        unsupportedBands: plutoReason,
      })
      render(<App />)
      const buttons = [...document.querySelectorAll('button')]
      const fmButton = buttons.find((b) => b.textContent === 'FM')
      fireEvent.click(fmButton)
      expect(mockFocusFrequency).not.toHaveBeenCalled()
    })

    it('OVERVIEW_BANDS unsupported cell has title and data-unsupported', () => {
      useSocket.mockReturnValueOnce({
        ...defaultUseSocket(),
        device: 'plutosdr',
        unsupportedBands: plutoReason,
      })
      const { container } = render(<App />)
      // The overview strip cells are divs with data-unsupported="true"
      const unsupportedCells = container.querySelectorAll('div[data-unsupported="true"]')
      // Five of seven cells (fm, aviation, acars, aprs, ais) are unsupported on Pluto
      expect(unsupportedCells.length).toBe(5)
      // The first one (FM BROADCAST) must carry the reason as title
      expect(unsupportedCells[0].getAttribute('title')).toBe(plutoReason.fm_broadcast)
    })

    it('clicking an unsupported OVERVIEW_BANDS cell does not call focusFrequency', () => {
      useSocket.mockReturnValueOnce({
        ...defaultUseSocket(),
        device: 'plutosdr',
        unsupportedBands: plutoReason,
      })
      render(<App />)
      const unsupportedCells = document.querySelectorAll('div[data-unsupported="true"]')
      // Click the first unsupported overview cell
      fireEvent.click(unsupportedCells[0])
      expect(mockFocusFrequency).not.toHaveBeenCalled()
    })
  })
})
