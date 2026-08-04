import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

vi.mock('../hooks/useSocket.js')

import { useSocket } from '../hooks/useSocket.js'
import RadarPage from '../pages/RadarPage.jsx'

const makeMock = (overrides = {}) => ({
  adsbAircraft: {},
  focusedFreq: null,
  systemStats: null,
  ...overrides,
})

describe('RadarPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.className = ''
  })

  it('renders empty state with zero contacts and no aircraft', () => {
    useSocket.mockReturnValue(makeMock())
    render(<RadarPage />)
    // Phase 50: RadarPage owns the header exclusively — RadarScopePanel
    // no longer renders its own duplicate header (dedup fix, was
    // TD-49-6). Exactly one match expected for each, not "at least one".
    expect(screen.getAllByText('RADAR SCOPE').length).toBe(1)
    expect(screen.getAllByText(/0 CONTACTS · 40NM/).length).toBe(1)
    // Not tuned to 1090 MHz, so the scope body shows its placeholder.
    expect(screen.getByText('Not tuned to ADS-B frequency')).toBeInTheDocument()
    expect(screen.queryByTestId('radar-blip')).toBeNull()
  })

  it('renders contacts when tuned and aircraft data is present', () => {
    useSocket.mockReturnValue(makeMock({
      systemStats: { active_frequency_hz: 1090000000 },
      adsbAircraft: {
        ABC123: { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45, range_nm: 10 },
      },
    }))
    render(<RadarPage />)
    // Phase 50: only RadarPage's header renders the count now — exactly
    // one match, not "at least two" (that assumed the old duplicate
    // header in RadarScopePanel, which has been removed).
    expect(screen.getAllByText(/1 CONTACTS · 40NM/).length).toBe(1)
    // RadarScopePanel received the aircraft and projected a blip.
    expect(screen.getByTestId('radar-blip')).toBeInTheDocument()
    // Phase 51: callsign now renders in two places, the RadarScopePanel blip
    // label AND the new AircraftDetailPanel list row, so assert exactly 2.
    expect(screen.getAllByText('TEST1').length).toBe(2)
  })

  it('passes maxRangeNm down to RadarScopePanel explicitly', () => {
    // Phase 50 regression guard: RadarPage must pass its MAX_RANGE_NM
    // constant to RadarScopePanel rather than relying on the two
    // components' default values happening to agree (was a silent gap —
    // RadarPage previously never passed maxRangeNm at all).
    useSocket.mockReturnValue(makeMock({
      systemStats: { active_frequency_hz: 1090000000 },
      adsbAircraft: {
        ABC123: { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45, range_nm: 35 },
      },
    }))
    render(<RadarPage />)
    expect(screen.getByTestId('radar-blip')).toBeInTheDocument()
    expect(screen.getAllByText(/40NM/).length).toBe(1)
  })

  it('reads focused frequency from systemStats.active_frequency_hz, not from the 98 MHz default (HIGH-01)', () => {
    // Regression guard: RadarPage must pass systemStats.active_frequency_hz
    // to RadarScopePanel, NOT the useSocket default of 98 MHz. Otherwise
    // every /radar page load would either (a) show "Not tuned to ADS-B
    // frequency" despite the SDR being on 1090 MHz, or (b) trigger an
    // unwanted retune of the SDR back to 98 MHz on connect (guarded
    // separately by the skipInitialRetune option on useSocket).
    useSocket.mockReturnValue(makeMock({
      systemStats: { active_frequency_hz: 1090000000 },
    }))
    render(<RadarPage />)
    // With systemStats reporting 1090 MHz, the scope should NOT show the
    // "not tuned" placeholder — the bug was that RadarPage passed the
    // hook's default of 98 MHz through to RadarScopePanel, which made
    // isAdsbFreq false and rendered this placeholder.
    expect(screen.queryByText('Not tuned to ADS-B frequency')).toBeNull()
  })

  it('adds radar-page class to body and removes it on unmount', () => {
    useSocket.mockReturnValue(makeMock())
    const { unmount } = render(<RadarPage />)
    expect(document.body.classList.contains('radar-page')).toBe(true)
    unmount()
    expect(document.body.classList.contains('radar-page')).toBe(false)
  })
})