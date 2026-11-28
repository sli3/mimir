import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import AdsbAircraftPanel from '../components/AdsbAircraftPanel.jsx'

const makeAircraft = (icao, callsign = null) => ({
  icao,
  callsign,
  altitude_ft: 35000,
  groundspeed: 450,
  track: 270,
  receivedAt: Date.now(),
})

afterEach(() => {
  vi.useRealTimers()
})

describe('AdsbAircraftPanel — previously seen section', () => {
  it('advances seconds-ago text in both tables without new aircraft data', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-28T06:00:00Z'))
    const active = makeAircraft('ABC123', 'QFA1')
    const old = makeAircraft('XYZ789', 'JST4')
    render(
      <AdsbAircraftPanel
        adsbAircraft={{ ABC123: active }}
        adsbAircraftHistory={[old]}
        focusedFreq={1090000000}
      />
    )

    expect(screen.getAllByText('0s')).toHaveLength(2)
    // The component's interval must re-render even when its props stay fixed.
    act(() => { vi.advanceTimersByTime(3000) })
    expect(screen.getAllByText('3s')).toHaveLength(2)
    expect(screen.queryByText('0s')).not.toBeInTheDocument()
  })

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
