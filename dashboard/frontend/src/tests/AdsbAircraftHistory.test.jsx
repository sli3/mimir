import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'
import AdsbAircraftPanel from '../components/AdsbAircraftPanel.jsx'

const makeAircraft = (icao, callsign = null) => ({
  icao,
  callsign,
  altitude_ft: 35000,
  groundspeed: 450,
  track: 270,
  receivedAt: Date.now(),
})

describe('AdsbAircraftPanel — previously seen section', () => {
  it('does not render PREVIOUSLY SEEN when history is empty', () => {
    render(
      <AdsbAircraftPanel
        adsbAircraft={{}}
        adsbAircraftHistory={[]}
        focusedFreq={1090000000}
      />
    )
    expect(screen.queryByText(/PREVIOUSLY SEEN/)).toBeNull()
  })

  it('does not render PREVIOUSLY SEEN when all history aircraft are still active', () => {
    const ac = makeAircraft('ABC123', 'QFA1')
    render(
      <AdsbAircraftPanel
        adsbAircraft={{ ABC123: ac }}
        adsbAircraftHistory={[ac]}
        focusedFreq={1090000000}
      />
    )
    expect(screen.queryByText(/PREVIOUSLY SEEN/)).toBeNull()
  })

  it('renders PREVIOUSLY SEEN section when history has aircraft not in active dict', () => {
    const active = makeAircraft('ABC123', 'QFA1')
    const old = makeAircraft('XYZ789', 'JST4')
    render(
      <AdsbAircraftPanel
        adsbAircraft={{ ABC123: active }}
        adsbAircraftHistory={[active, old]}
        focusedFreq={1090000000}
      />
    )
    expect(screen.getByText(/PREVIOUSLY SEEN/)).toBeInTheDocument()
    expect(screen.getByText('JST4')).toBeInTheDocument()
  })

  it('renders PREVIOUSLY SEEN count in header', () => {
    const active = makeAircraft('ABC123')
    const old1 = makeAircraft('XYZ789', 'JST4')
    const old2 = makeAircraft('DEF456', 'VOZ8')
    render(
      <AdsbAircraftPanel
        adsbAircraft={{ ABC123: active }}
        adsbAircraftHistory={[active, old1, old2]}
        focusedFreq={1090000000}
      />
    )
    expect(screen.getByText(/PREVIOUSLY SEEN \(2\)/)).toBeInTheDocument()
  })

  it('active aircraft do not appear in PREVIOUSLY SEEN section', () => {
    const ac = makeAircraft('ABC123', 'QFA1')
    const old = makeAircraft('XYZ789', 'JST4')
    render(
      <AdsbAircraftPanel
        adsbAircraft={{ ABC123: ac }}
        adsbAircraftHistory={[ac, old]}
        focusedFreq={1090000000}
      />
    )
    // QFA1 is active — should appear in active table only (once)
    // JST4 is previously seen only
    const qfa = screen.getAllByText('QFA1')
    expect(qfa).toHaveLength(1)
    expect(screen.getByText('JST4')).toBeInTheDocument()
  })
})