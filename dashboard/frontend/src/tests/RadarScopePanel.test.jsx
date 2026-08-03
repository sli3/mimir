import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

import { projectToScope, isWithinRange, isValidContact } from '../components/radar/projection.js'
import RadarScopePanel from '../components/RadarScopePanel.jsx'

// Scope geometry constants mirrored from RadarScopePanel.jsx so position
// assertions do not hardcode magic numbers in every test.
const SCOPE_CX = 190
const SCOPE_CY = 162.5
const SCOPE_MAX_R = 150

// Same 2-decimal rounding the component applies before writing SVG
// attributes, so projected expectations compare exactly.
const r2 = (n) => Number(n.toFixed(2))

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

  it('isValidContact rejects missing/NaN bearing_deg regardless of range_nm', () => {
    // Phase 50: single source of truth for the "valid contact" rule,
    // shared by RadarScopePanel and RadarPage — see TD-49-6.
    expect(isValidContact({ bearing_deg: null, range_nm: 10 }, 40)).toBe(false)
    expect(isValidContact({ bearing_deg: undefined, range_nm: 10 }, 40)).toBe(false)
    expect(isValidContact({ bearing_deg: NaN, range_nm: 10 }, 40)).toBe(false)
    expect(isValidContact({ bearing_deg: 45, range_nm: null }, 40)).toBe(false)
    expect(isValidContact({ bearing_deg: 45, range_nm: 10 }, 40)).toBe(true)
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
    // Neither aircraft is valid, so no blips render. Contact count is no
    // longer asserted here — RadarScopePanel no longer renders a header;
    // that readout now lives exclusively in RadarPage (Phase 50 dedup,
    // was TD-49-6). See RadarPage.test.jsx for count assertions.
    expect(container.querySelectorAll('[data-testid="radar-blip"]').length).toBe(0)
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

  it('renders the scope (not the not-tuned message) when tuned', () => {
    // Phase 50: RadarScopePanel no longer renders its own header text
    // ("RADAR SCOPE ... CONTACTS") — that moved to RadarPage exclusively
    // (dedup fix, was TD-49-6). This asserts the scope body itself
    // (SVG + chrome) renders instead of the placeholder message.
    const { container } = render(
      <RadarScopePanel adsbAircraft={{}} focusedFreq={TUNED_FREQ} />
    )
    expect(screen.queryByText('Not tuned to ADS-B frequency')).toBeNull()
    expect(container.querySelector('svg')).not.toBeNull()
    expect(container.querySelector('[data-testid="radar-chrome"]')).not.toBeNull()
  })

  it('test_radar_renders_scope_after_tuning_to_adsb', () => {
    // First-use flow: the dashboard boots on 98 MHz (not tuned), then the
    // operator clicks the ADS-B band. The mount-lifecycle behaviour must
    // re-evaluate when isAdsbFreq flips true, or the scope stays blank.
    const { container, rerender } = render(
      <RadarScopePanel adsbAircraft={{}} focusedFreq={98_000_000} />
    )
    expect(screen.getByText('Not tuned to ADS-B frequency')).toBeInTheDocument()
    rerender(
      <RadarScopePanel adsbAircraft={{}} focusedFreq={TUNED_FREQ} />
    )
    expect(screen.queryByText('Not tuned to ADS-B frequency')).toBeNull()
    expect(container.querySelector('svg')).not.toBeNull()
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

  describe('breadcrumb trail (Phase 50)', () => {
    it('renders no trail on first sighting (only the current blip)', () => {
      const adsbAircraft = {
        ABC123: { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45, range_nm: 10, timestamp: 1000 },
      }
      const { container } = render(
        <RadarScopePanel adsbAircraft={adsbAircraft} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelector('polyline')).toBeNull()
    })

    it('accumulates trail points across successive renders', () => {
      const base = { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45, range_nm: 10 }
      const { container, rerender } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, timestamp: 1000 } }} focusedFreq={TUNED_FREQ} />
      )
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 50, timestamp: 2000 } }} focusedFreq={TUNED_FREQ} />
      )
      // One prior point stored -> one trail point rendered (excludes
      // the current position, which renders as the main blip).
      expect(container.querySelector('polyline')).not.toBeNull()
      expect(container.querySelectorAll('[data-testid="radar-blip"] circle[r]').length).toBeGreaterThanOrEqual(1)
    })

    it('caps trail history at TRAIL_MAX_POINTS (8), evicting oldest first', () => {
      const base = { icao: 'ABC123', callsign: 'TEST1', range_nm: 10 }
      const { container, rerender } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 0, timestamp: 0 } }} focusedFreq={TUNED_FREQ} />
      )
      // Push 9 more distinct-timestamp updates (10 total) -> history
      // should cap at 8 stored points, so 7 trail points render
      // (8 stored minus 1 for the current position).
      for (let i = 1; i <= 9; i++) {
        rerender(
          <RadarScopePanel
            adsbAircraft={{ ABC123: { ...base, bearing_deg: i * 5, timestamp: i * 1000 } }}
            focusedFreq={TUNED_FREQ}
          />
        )
      }
      const allCircles = container.querySelectorAll('[data-testid="radar-blip"] circle')
      // Blip circle (1) + trail-point circles (<= 7) per aircraft.
      expect(allCircles.length).toBeLessThanOrEqual(8)
    })

    it('clears the trail after a gap exceeding the staleness cutoff', () => {
      const base = { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45, range_nm: 10 }
      const { container, rerender } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, timestamp: 0 } }} focusedFreq={TUNED_FREQ} />
      )
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 50, timestamp: 5000 } }} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelector('polyline')).not.toBeNull()
      // Gap > TRAIL_STALE_MS (90000ms) -> trail clears, fresh start.
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 55, timestamp: 200000 } }} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelector('polyline')).toBeNull()
    })

    it('keeps the existing trail when a frame has null bearing_deg (gap-skip, not reset)', () => {
      const base = { icao: 'ABC123', callsign: 'TEST1', range_nm: 10 }
      const { container, rerender } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 45, timestamp: 1000 } }} focusedFreq={TUNED_FREQ} />
      )
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 50, timestamp: 2000 } }} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelector('polyline')).not.toBeNull()
      // Bad frame: null bearing_deg. With the Phase 50 passthrough fix,
      // the aircraft still renders from its last-known position, so this
      // frame produces a blip. Stored history is untouched for next time.
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: null, timestamp: 3000 } }} focusedFreq={TUNED_FREQ} />
      )
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 60, timestamp: 4000 } }} focusedFreq={TUNED_FREQ} />
      )
      // History survived the gap frame instead of resetting.
      expect(container.querySelector('polyline')).not.toBeNull()
    })

    it('does not render trail points that fall outside the current maxRangeNm', () => {
      const base = { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45 }
      // Frame 1: aircraft at range 30 on a 40 NM scope (in range, trail
      // point stored at 30). Frame 2: aircraft at range 35 (in range,
      // trail point stored at 35). Frame 3: aircraft at range 3, scope
      // shrunk to 5 NM — the aircraft is still a valid contact (3 < 5),
      // but BOTH stored trail points (30 and 35) fall outside 5 NM, so
      // the per-point isWithinRange() filter at the render boundary is
      // the only thing that removes them. The blip at range 3 must
      // still render. (Earlier points must ALL be out of the shrunken
      // range: slice(0, -1) keeps every stored point except the current
      // one, so a surviving in-range earlier point would still draw a
      // polyline and the test could not isolate the per-point filter.)
      const { container, rerender } = render(
        <RadarScopePanel
          adsbAircraft={{ ABC123: { ...base, range_nm: 30, timestamp: 1000 } }}
          focusedFreq={TUNED_FREQ}
          maxRangeNm={40}
        />
      )
      rerender(
        <RadarScopePanel
          adsbAircraft={{ ABC123: { ...base, range_nm: 35, timestamp: 2000 } }}
          focusedFreq={TUNED_FREQ}
          maxRangeNm={40}
        />
      )
      // One stored prior point at range 30, in range on the 40 NM
      // scope -> trail renders.
      expect(container.querySelector('polyline')).not.toBeNull()
      // Shrink the scope. Aircraft at range 3 is still a valid contact
      // (3 <= 5), so it reaches the render path; the stored points at
      // 30 and 35 are not, and are dropped by the per-point filter.
      rerender(
        <RadarScopePanel
          adsbAircraft={{ ABC123: { ...base, range_nm: 3, timestamp: 3000 } }}
          focusedFreq={TUNED_FREQ}
          maxRangeNm={5}
        />
      )
      expect(container.querySelector('polyline')).toBeNull()
      // Blip still renders (range 3 <= 5 NM).
      expect(container.querySelectorAll('[data-testid="radar-blip"]').length).toBe(1)
    })

    it('renders a blip during a bad-bearing frame using last-stored position', () => {
      // Phase 50 false-flicker fix-pass: many ADS-B message types (callsign,
      // altitude, velocity-only frames) carry no position at all. One
      // position-less frame must NOT blank an aircraft that has a
      // recent last-known position.
      const base = { icao: 'ABC123', callsign: 'TEST1', range_nm: 10 }
      const { container, rerender } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 45, timestamp: 1000 } }} focusedFreq={TUNED_FREQ} />
      )
      // Bad frame: null bearing_deg, gap well under TRAIL_STALE_MS.
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: null, timestamp: 2000 } }} focusedFreq={TUNED_FREQ} />
      )
      const blips = container.querySelectorAll('[data-testid="radar-blip"]')
      expect(blips.length).toBe(1)
      // The main blip circle (the one carrying the glow filter) must sit
      // at the last valid frame's projected coordinates, not be absent
      // or NaN.
      const expected = projectToScope(45, 10, 40, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
      const main = container.querySelector('[data-testid="radar-blip"] circle[filter="url(#mimir-radar-glow)"]')
      expect(main).not.toBeNull()
      expect(Number(main.getAttribute('cx'))).toBe(r2(expected.x))
      expect(Number(main.getAttribute('cy'))).toBe(r2(expected.y))
      expect(container.innerHTML).not.toContain('NaN')
    })

    it('aircraft disappears once gap exceeds TRAIL_STALE_MS despite bad frames', () => {
      // The passthrough is bounded: the last-known position is only
      // trusted for TRAIL_STALE_MS (90s) past the last VALID frame.
      // Because a bad frame never pushes to history, the staleness
      // clock keeps running from the last good timestamp.
      const base = { icao: 'ABC123', callsign: 'TEST1', range_nm: 10 }
      const { container, rerender } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 45, timestamp: 0 } }} focusedFreq={TUNED_FREQ} />
      )
      // Gap 60s < 90s from the last good frame -> still passes through.
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: null, timestamp: 60000 } }} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelectorAll('[data-testid="radar-blip"]').length).toBe(1)
      // Gap 95s > 90s from the last good frame (timestamp 0) -> excluded.
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: null, timestamp: 95000 } }} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelectorAll('[data-testid="radar-blip"]').length).toBe(0)
    })
  })
})