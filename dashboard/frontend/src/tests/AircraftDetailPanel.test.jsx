import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import React from 'react'

import AircraftDetailPanel from '../components/AircraftDetailPanel.jsx'
import { formatVerticalRate } from '../utils/aircraftFormat.js'

// Every fixture is a valid in-range contact by default (isValidContact
// checks bearing_deg and range_nm only). Altitudes are kept under 1000
// so locale grouping never enters the assertions.
const makeAircraft = (overrides = {}) => ({
  icao: 'ABC123',
  callsign: 'QFA1',
  altitude_ft: 500,
  groundspeed: 450,
  track: 270,
  squawk: '2000',
  vertical_rate: 0,
  bearing_deg: 45,
  range_nm: 10,
  receivedAt: Date.now(),
  ...overrides,
})

describe('AircraftDetailPanel', () => {
  it('renders the empty list state and the no-selection placeholder', () => {
    render(
      <AircraftDetailPanel adsbAircraft={{}} maxRangeNm={40} />
    )
    expect(screen.getByText('No in-range contacts')).toBeInTheDocument()
    expect(screen.getByText('No aircraft selected')).toBeInTheDocument()
  })

  it('renders one row per in-range contact and skips invalid contacts', () => {
    const adsbAircraft = {
      ABC123: makeAircraft(),
      DEF456: makeAircraft({ icao: 'DEF456', callsign: 'VOZ2' }),
      // Null bearing: not a valid contact, must not appear in the list.
      GHI789: makeAircraft({ icao: 'GHI789', callsign: 'QLK3', bearing_deg: null }),
      // Out of range on a 40 NM scope: excluded.
      JKL012: makeAircraft({ icao: 'JKL012', callsign: 'JST4', range_nm: 45 }),
    }
    const { container } = render(
      <AircraftDetailPanel adsbAircraft={adsbAircraft} maxRangeNm={40} />
    )
    expect(container.querySelectorAll('[data-testid="radar-detail-row"]').length).toBe(2)
    expect(screen.getByText('QFA1')).toBeInTheDocument()
    expect(screen.getByText('VOZ2')).toBeInTheDocument()
    expect(screen.queryByText('QLK3')).toBeNull()
    expect(screen.queryByText('JST4')).toBeNull()
  })

  it('renders the em-dash placeholder for every missing field without skipping the row', () => {
    const adsbAircraft = {
      ABC123: makeAircraft({
        callsign: null,
        altitude_ft: null,
        track: null,
        groundspeed: null,
      }),
    }
    const { container } = render(
      <AircraftDetailPanel adsbAircraft={adsbAircraft} maxRangeNm={40} />
    )
    const rows = container.querySelectorAll('[data-testid="radar-detail-row"]')
    expect(rows.length).toBe(1)
    const cells = rows[0].querySelectorAll('span')
    expect(cells.length).toBe(4)
    for (const cell of cells) {
      expect(cell.textContent).toBe('—')
    }
    // A missing groundspeed must not gain a bare "kt" suffix.
    expect(rows[0].textContent).not.toContain('kt')
  })

  it('renders populated row fields with units', () => {
    const adsbAircraft = { ABC123: makeAircraft() }
    const { container } = render(
      <AircraftDetailPanel adsbAircraft={adsbAircraft} maxRangeNm={40} />
    )
    const row = container.querySelector('[data-testid="radar-detail-row"]')
    expect(row.textContent).toContain('QFA1')
    expect(row.textContent).toContain('500')
    expect(row.textContent).toContain('270°')
    expect(row.textContent).toContain('450kt')
  })

  it('fires onSelectAircraft with the correct icao when a row is clicked', () => {
    const onSelectAircraft = vi.fn()
    const adsbAircraft = {
      ABC123: makeAircraft(),
      DEF456: makeAircraft({ icao: 'DEF456', callsign: 'VOZ2' }),
    }
    const { container } = render(
      <AircraftDetailPanel
        adsbAircraft={adsbAircraft}
        maxRangeNm={40}
        onSelectAircraft={onSelectAircraft}
      />
    )
    fireEvent.click(container.querySelector('[data-icao="DEF456"]'))
    expect(onSelectAircraft).toHaveBeenCalledTimes(1)
    expect(onSelectAircraft).toHaveBeenCalledWith('DEF456')
  })

  it('applies the selected-row highlight class only to the selected row', () => {
    const adsbAircraft = {
      ABC123: makeAircraft(),
      DEF456: makeAircraft({ icao: 'DEF456', callsign: 'VOZ2' }),
    }
    const { container } = render(
      <AircraftDetailPanel
        adsbAircraft={adsbAircraft}
        maxRangeNm={40}
        selectedIcao="ABC123"
      />
    )
    expect(container.querySelector('[data-icao="ABC123"]').className)
      .toContain('radar-detail-row-selected')
    expect(container.querySelector('[data-icao="DEF456"]').className)
      .not.toContain('radar-detail-row-selected')
  })

  it('shows the fixed-height placeholder in the pinned section with no selection', () => {
    render(
      <AircraftDetailPanel
        adsbAircraft={{ ABC123: makeAircraft() }}
        maxRangeNm={40}
        selectedIcao={null}
      />
    )
    const pinned = screen.getByTestId('radar-detail-pinned')
    expect(pinned).toBeInTheDocument()
    expect(screen.getByText('No aircraft selected')).toBeInTheDocument()
    // No detail grid when nothing is selected.
    expect(screen.queryByText('Squawk')).toBeNull()
  })

  it('shows the placeholder when the selected icao is no longer present', () => {
    render(
      <AircraftDetailPanel
        adsbAircraft={{ ABC123: makeAircraft() }}
        maxRangeNm={40}
        selectedIcao="ZZZ999"
      />
    )
    expect(screen.getByText('No aircraft selected')).toBeInTheDocument()
  })

  it('shows the full detail grid when a matching aircraft is selected', () => {
    const adsbAircraft = {
      ABC123: makeAircraft({ vertical_rate: 1200 }),
    }
    render(
      <AircraftDetailPanel
        adsbAircraft={adsbAircraft}
        maxRangeNm={40}
        selectedIcao="ABC123"
      />
    )
    // Static identity column (labels are unique to the pinned grid;
    // values also appear in the list row, so scope those lookups).
    const pinned = within(screen.getByTestId('radar-detail-pinned'))
    expect(pinned.getByText('Callsign')).toBeInTheDocument()
    expect(pinned.getByText('ICAO')).toBeInTheDocument()
    expect(pinned.getByText('Squawk')).toBeInTheDocument()
    expect(pinned.getByText('QFA1')).toBeInTheDocument()
    expect(pinned.getByText('ABC123')).toBeInTheDocument()
    expect(pinned.getByText('2000')).toBeInTheDocument()
    // Dynamic per-frame column.
    expect(pinned.getByText('Altitude (ft)')).toBeInTheDocument()
    expect(pinned.getByText('Track')).toBeInTheDocument()
    expect(pinned.getByText('Groundspeed')).toBeInTheDocument()
    expect(pinned.getByText('Vertical rate')).toBeInTheDocument()
    expect(pinned.getByText('500')).toBeInTheDocument()
    expect(pinned.getByText('270°')).toBeInTheDocument()
    expect(pinned.getByText('450kt')).toBeInTheDocument()
    expect(pinned.getByText('Climbing')).toBeInTheDocument()
    expect(screen.queryByText('No aircraft selected')).toBeNull()
  })

  it('renders the em-dash for missing fields inside the pinned detail grid', () => {
    const adsbAircraft = {
      ABC123: makeAircraft({
        callsign: null,
        squawk: null,
        altitude_ft: null,
        track: null,
        groundspeed: null,
        vertical_rate: null,
      }),
    }
    render(
      <AircraftDetailPanel
        adsbAircraft={adsbAircraft}
        maxRangeNm={40}
        selectedIcao="ABC123"
      />
    )
    // Callsign, squawk, altitude, track, groundspeed, vertical rate are
    // all missing: six em-dash placeholders in the pinned grid (the
    // list row has its own placeholders, so scope the count to the
    // pinned section), ICAO still present.
    const pinned = within(screen.getByTestId('radar-detail-pinned'))
    expect(pinned.getAllByText('—').length).toBe(6)
    expect(pinned.getByText('ABC123')).toBeInTheDocument()
  })

  it('renders the squawk value in the pinned detail when present (Phase 54)', () => {
    const adsbAircraft = {
      ABC123: makeAircraft({ squawk: '2000' }),
    }
    render(
      <AircraftDetailPanel
        adsbAircraft={adsbAircraft}
        maxRangeNm={40}
        selectedIcao="ABC123"
      />
    )
    const pinned = within(screen.getByTestId('radar-detail-pinned'))
    expect(pinned.getByText('Squawk')).toBeInTheDocument()
    expect(pinned.getByText('2000')).toBeInTheDocument()
  })

  it('renders the em-dash for squawk when null (Phase 54)', () => {
    const adsbAircraft = {
      ABC123: makeAircraft({ squawk: null }),
    }
    render(
      <AircraftDetailPanel
        adsbAircraft={adsbAircraft}
        maxRangeNm={40}
        selectedIcao="ABC123"
      />
    )
    const pinned = within(screen.getByTestId('radar-detail-pinned'))
    // The squawk field specifically: label present, value is the em-dash.
    const squawkField = pinned.getByText('Squawk').closest('.radar-detail-field')
    expect(within(squawkField).getByText('—')).toBeInTheDocument()
  })
})

describe('AircraftDetailPanel deselect toggle contract (Phase 54)', () => {
  // The toggle itself lives in RadarPage (the state owner). The panel's
  // contract is simply: always call onSelectAircraft with the icao of the
  // clicked row, even when that row is the currently selected one. The
  // panel never decides to deselect itself.
  it('calls onSelectAircraft with the icao even for the currently selected row', () => {
    const onSelectAircraft = vi.fn()
    const adsbAircraft = { ABC123: makeAircraft() }
    const { container } = render(
      <AircraftDetailPanel
        adsbAircraft={adsbAircraft}
        maxRangeNm={40}
        selectedIcao="ABC123"
        onSelectAircraft={onSelectAircraft}
      />
    )
    fireEvent.click(container.querySelector('[data-icao="ABC123"]'))
    expect(onSelectAircraft).toHaveBeenCalledTimes(1)
    expect(onSelectAircraft).toHaveBeenCalledWith('ABC123')
  })

  it('calls onSelectAircraft with the icao for a non-selected row', () => {
    const onSelectAircraft = vi.fn()
    const adsbAircraft = {
      ABC123: makeAircraft(),
      DEF456: makeAircraft({ icao: 'DEF456', callsign: 'VOZ2' }),
    }
    const { container } = render(
      <AircraftDetailPanel
        adsbAircraft={adsbAircraft}
        maxRangeNm={40}
        selectedIcao="ABC123"
        onSelectAircraft={onSelectAircraft}
      />
    )
    fireEvent.click(container.querySelector('[data-icao="DEF456"]'))
    expect(onSelectAircraft).toHaveBeenCalledWith('DEF456')
  })
})

describe('formatVerticalRate', () => {
  it('classifies a genuine climb above the 200 ft/min dead-zone', () => {
    expect(formatVerticalRate(201)).toBe('Climbing')
    expect(formatVerticalRate(1200)).toBe('Climbing')
  })

  it('classifies a genuine descent below the 200 ft/min dead-zone', () => {
    expect(formatVerticalRate(-201)).toBe('Descending')
    expect(formatVerticalRate(-900)).toBe('Descending')
  })

  it('classifies rates inside the dead-zone as Level, boundaries included', () => {
    expect(formatVerticalRate(200)).toBe('Level')
    expect(formatVerticalRate(-200)).toBe('Level')
    expect(formatVerticalRate(150)).toBe('Level')
    expect(formatVerticalRate(-150)).toBe('Level')
    expect(formatVerticalRate(1)).toBe('Level')
  })

  it('renders the em-dash placeholder for zero, null, undefined and NaN', () => {
    expect(formatVerticalRate(0)).toBe('—')
    expect(formatVerticalRate(null)).toBe('—')
    expect(formatVerticalRate(undefined)).toBe('—')
    expect(formatVerticalRate(NaN)).toBe('—')
  })
})
