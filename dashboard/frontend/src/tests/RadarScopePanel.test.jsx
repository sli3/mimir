import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

import { projectToScope, isWithinRange } from '../components/radar/projection.js'
import RadarScopePanel from '../components/RadarScopePanel.jsx'

// Scope geometry constants mirrored from RadarScopePanel.jsx so position
// assertions do not hardcode magic numbers in every test.
const SCOPE_CX = 190
const SCOPE_CY = 162.5

const TUNED_FREQ = 1_090_000_000

describe('projection', () => {
  it('projects north bearing to top of scope', () => {
    const { x, y } = projectToScope(0, 40, 40, 100, 100, 90)
    expect(y).toBeLessThan(100)
    expect(x).toBeCloseTo(100, 5)
  })

  it('projects east bearing to right of scope', () => {
    const { x, y } = projectToScope(90, 40, 40, 100, 100, 90)
    expect(x).toBeGreaterThan(100)
    expect(y).toBeCloseTo(100, 5)
  })

  it('clamps range beyond max to the outer ring', () => {
    // Range 80 NM on a 40 NM scope must still land on the ring (rel = 1).
    const clamped = projectToScope(90, 80, 40, 100, 100, 90)
    const onRing = projectToScope(90, 40, 40, 100, 100, 90)
    expect(clamped.x).toBeCloseTo(onRing.x, 5)
    expect(clamped.y).toBeCloseTo(onRing.y, 5)
  })

  it('isWithinRange rejects null, undefined, NaN and out-of-range', () => {
    expect(isWithinRange(null, 40)).toBe(false)
    expect(isWithinRange(undefined, 40)).toBe(false)
    expect(isWithinRange(NaN, 40)).toBe(false)
    expect(isWithinRange(41, 40)).toBe(false)
    expect(isWithinRange(40, 40)).toBe(true)
    expect(isWithinRange(0, 40)).toBe(true)
  })
})

describe('RadarScopePanel', () => {
  it('test_skips_aircraft_with_null_range_nm', () => {
    const adsbAircraft = {
      ABC123: {
        icao: 'ABC123',
        callsign: 'TEST1',
        bearing_deg: 45,
        range_nm: null,
      },
      DEF456: {
        icao: 'DEF456',
        callsign: 'TEST2',
        bearing_deg: null,
        range_nm: 20,
      },
    }
    let container
    expect(() => {
      container = render(
        <RadarScopePanel adsbAircraft={adsbAircraft} focusedFreq={TUNED_FREQ} />
      ).container
    }).not.toThrow()
    // Skipped aircraft must not produce labels (and no NaN anywhere).
    expect(container.textContent).not.toContain('TEST1')
    expect(container.textContent).not.toContain('TEST2')
    expect(container.textContent).not.toContain('NaN')
    // Header shows zero valid contacts.
    expect(screen.getByText('0 CONTACTS · 40NM')).toBeInTheDocument()
  })

  it('renders the not-tuned message when off frequency', () => {
    render(
      <RadarScopePanel adsbAircraft={{}} focusedFreq={98_000_000} />
    )
    expect(screen.getByText('Not tuned to ADS-B frequency')).toBeInTheDocument()
  })

  it('renders the not-tuned message when focusedFreq is null', () => {
    render(
      <RadarScopePanel adsbAircraft={{}} focusedFreq={null} />
    )
    expect(screen.getByText('Not tuned to ADS-B frequency')).toBeInTheDocument()
  })

  it('renders the panel header when tuned', () => {
    render(
      <RadarScopePanel adsbAircraft={{}} focusedFreq={TUNED_FREQ} />
    )
    expect(screen.getByText('RADAR SCOPE')).toBeInTheDocument()
    expect(screen.queryByText('Not tuned to ADS-B frequency')).toBeNull()
  })

  it('test_radar_renders_scope_after_tuning_to_adsb', () => {
    // First-use flow: the dashboard boots on 98 MHz (not tuned), then the
    // operator clicks the ADS-B band. The mount-lifecycle effect must
    // re-run when isAdsbFreq flips true, or the scope stays blank.
    const { rerender } = render(
      <RadarScopePanel adsbAircraft={{}} focusedFreq={98_000_000} />
    )
    expect(screen.getByText('Not tuned to ADS-B frequency')).toBeInTheDocument()
    rerender(
      <RadarScopePanel adsbAircraft={{}} focusedFreq={TUNED_FREQ} />
    )
    expect(screen.getByText('RADAR SCOPE')).toBeInTheDocument()
    expect(screen.queryByText('Not tuned to ADS-B frequency')).toBeNull()
  })

  it('test_renders_svg_element_when_tuned', () => {
    const { container } = render(
      <RadarScopePanel adsbAircraft={{}} focusedFreq={TUNED_FREQ} />
    )
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('test_renders_four_range_rings', () => {
    // Strategy: the static chrome (rings, spokes, crosshair, compass
    // labels) is wrapped in a single <g data-testid="radar-chrome">.
    // The four range rings are the only <circle> elements inside it —
    // blip circles live in separate data-testid="radar-blip" groups —
    // so counting chrome circles is an exact ring count.
    const { container } = render(
      <RadarScopePanel adsbAircraft={{}} focusedFreq={TUNED_FREQ} />
    )
    const rings = container.querySelectorAll('[data-testid="radar-chrome"] circle')
    expect(rings.length).toBe(4)
  })

  it('test_renders_one_blip_per_visible_aircraft', () => {
    const adsbAircraft = {
      ABC123: { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45, range_nm: 10 },
      DEF456: { icao: 'DEF456', callsign: 'TEST2', bearing_deg: 270, range_nm: 30 },
    }
    const { container } = render(
      <RadarScopePanel adsbAircraft={adsbAircraft} focusedFreq={TUNED_FREQ} />
    )
    expect(container.querySelectorAll('[data-testid="radar-blip"]').length).toBe(2)
  })

  it('test_blip_positioned_north_for_zero_bearing', () => {
    // Max range, due north: must land on the outer ring at the TOP of
    // the scope (y < centre), horizontally centred.
    const adsbAircraft = {
      ABC123: { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 0, range_nm: 40 },
    }
    const { container } = render(
      <RadarScopePanel adsbAircraft={adsbAircraft} focusedFreq={TUNED_FREQ} />
    )
    const blip = container.querySelector('[data-testid="radar-blip"] circle')
    const cx = Number(blip.getAttribute('cx'))
    const cy = Number(blip.getAttribute('cy'))
    expect(cy).toBeLessThan(SCOPE_CY)
    expect(cx).toBeCloseTo(SCOPE_CX, 1)
  })

  it('test_blip_positioned_east_for_ninety_bearing', () => {
    // Max range, due east: must land on the outer ring at the RIGHT of
    // the scope (x > centre), vertically centred.
    const adsbAircraft = {
      ABC123: { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 90, range_nm: 40 },
    }
    const { container } = render(
      <RadarScopePanel adsbAircraft={adsbAircraft} focusedFreq={TUNED_FREQ} />
    )
    const blip = container.querySelector('[data-testid="radar-blip"] circle')
    const cx = Number(blip.getAttribute('cx'))
    const cy = Number(blip.getAttribute('cy'))
    expect(cx).toBeGreaterThan(SCOPE_CX)
    expect(cy).toBeCloseTo(SCOPE_CY, 1)
  })

  it('test_renders_callsign_label_for_each_blip', () => {
    const adsbAircraft = {
      ABC123: { icao: 'ABC123', callsign: 'VOZ123', bearing_deg: 45, range_nm: 10 },
      DEF456: { icao: 'DEF456', callsign: 'QLK456', bearing_deg: 200, range_nm: 25 },
    }
    render(
      <RadarScopePanel adsbAircraft={adsbAircraft} focusedFreq={TUNED_FREQ} />
    )
    expect(screen.getByText('VOZ123')).toBeInTheDocument()
    expect(screen.getByText('QLK456')).toBeInTheDocument()
  })

  it('test_no_nan_in_rendered_svg_attributes', () => {
    // A malformed aircraft mix must be filtered before projection, so
    // no 'NaN' string can appear anywhere in the serialised SVG markup.
    const adsbAircraft = {
      ABC123: { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45, range_nm: NaN },
      DEF456: { icao: 'DEF456', callsign: 'TEST2', bearing_deg: null, range_nm: 20 },
      GHI789: { icao: 'GHI789', callsign: 'TEST3', bearing_deg: NaN, range_nm: 15 },
      JKL012: { icao: 'JKL012', callsign: 'VALID', bearing_deg: 90, range_nm: 15 },
    }
    const { container } = render(
      <RadarScopePanel adsbAircraft={adsbAircraft} focusedFreq={TUNED_FREQ} />
    )
    expect(container.innerHTML).not.toContain('NaN')
    // The one valid aircraft still renders.
    expect(container.querySelectorAll('[data-testid="radar-blip"]').length).toBe(1)
  })
})
