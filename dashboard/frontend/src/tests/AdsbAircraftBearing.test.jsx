import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'
import AdsbAircraftPanel from '../components/AdsbAircraftPanel.jsx'

const makeAircraft = (overrides = {}) => ({
  icao: 'ABC123',
  callsign: 'QFA1',
  altitude_ft: 35000,
  groundspeed: 450,
  track: 270,
  bearing_deg: null,
  delta_r_deg_per_sec: null,
  receivedAt: Date.now(),
  ...overrides,
})

describe('AdsbAircraftPanel — bearing and Δr columns', () => {
  it('test_bearing_renders_045_for_45_2_degrees', () => {
    const ac = makeAircraft({ bearing_deg: 45.2, delta_r_deg_per_sec: 2.34 })
    render(
      <AdsbAircraftPanel
        adsbAircraft={{ ABC123: ac }}
        adsbAircraftHistory={[]}
        focusedFreq={1090000000}
      />
    )
    expect(screen.getByText('045°')).toBeInTheDocument()
    expect(screen.getByText('+2.3°/s')).toBeInTheDocument()
  })

  it('test_delta_r_renders_em_dash_for_null', () => {
    const ac = makeAircraft({ bearing_deg: 270, delta_r_deg_per_sec: null })
    render(
      <AdsbAircraftPanel
        adsbAircraft={{ ABC123: ac }}
        adsbAircraftHistory={[]}
        focusedFreq={1090000000}
      />
    )
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('null')).toBeNull()
  })

  it('test_delta_r_renders_negative_with_sign', () => {
    const ac = makeAircraft({ bearing_deg: 180, delta_r_deg_per_sec: -1.75 })
    render(
      <AdsbAircraftPanel
        adsbAircraft={{ ABC123: ac }}
        adsbAircraftHistory={[]}
        focusedFreq={1090000000}
      />
    )
    expect(screen.getByText('-1.8°/s')).toBeInTheDocument()
  })
})
