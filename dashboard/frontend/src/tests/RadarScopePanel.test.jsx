import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'

import { projectToScope, isWithinRange, isValidContact } from '../components/radar/projection.js'
import RadarScopePanel from '../components/RadarScopePanel.jsx'
import { derivePredictionVector, projectPosition } from '../utils/pathPrediction.js'

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
        ABC123: { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45, range_nm: 10, timestamp: '1970-01-01T00:00:01.000Z' },
      }
      const { container } = render(
        <RadarScopePanel adsbAircraft={adsbAircraft} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelector('polyline')).toBeNull()
    })

    it('accumulates trail points across successive renders', () => {
      const base = { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45, range_nm: 10 }
      const { container, rerender } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, timestamp: '1970-01-01T00:00:01.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 50, timestamp: '1970-01-01T00:00:02.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      // One prior point stored -> one trail point rendered (excludes
      // the current position, which renders as the main blip).
      expect(container.querySelector('polyline')).not.toBeNull()
      expect(container.querySelectorAll('[data-testid="radar-blip"] circle[r]').length).toBeGreaterThanOrEqual(1)
    })

    it('caps trail history at TRAIL_MAX_POINTS (8), evicting oldest first', () => {
      const base = { icao: 'ABC123', callsign: 'TEST1', range_nm: 10 }
      const { container, rerender } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 0, timestamp: '1970-01-01T00:00:00.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      // Push 9 more distinct-timestamp updates (10 total) -> history
      // should cap at 8 stored points, so 7 trail points render
      // (8 stored minus 1 for the current position).
      for (let i = 1; i <= 9; i++) {
        rerender(
          <RadarScopePanel
            adsbAircraft={{ ABC123: { ...base, bearing_deg: i * 5, timestamp: new Date(i * 1000).toISOString() } }}
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
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, timestamp: '1970-01-01T00:00:00.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 50, timestamp: '1970-01-01T00:00:05.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelector('polyline')).not.toBeNull()
      // Gap > TRAIL_STALE_MS (90000ms) -> trail clears, fresh start.
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 55, timestamp: '1970-01-01T00:03:20.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelector('polyline')).toBeNull()
    })

    it('keeps the existing trail when a frame has null bearing_deg (gap-skip, not reset)', () => {
      const base = { icao: 'ABC123', callsign: 'TEST1', range_nm: 10 }
      const { container, rerender } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 45, timestamp: '1970-01-01T00:00:01.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 50, timestamp: '1970-01-01T00:00:02.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelector('polyline')).not.toBeNull()
      // Bad frame: null bearing_deg. With the Phase 50 passthrough fix,
      // the aircraft still renders from its last-known position, so this
      // frame produces a blip. Stored history is untouched for next time.
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: null, timestamp: '1970-01-01T00:00:03.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 60, timestamp: '1970-01-01T00:00:04.000Z' } }} focusedFreq={TUNED_FREQ} />
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
          adsbAircraft={{ ABC123: { ...base, range_nm: 30, timestamp: '1970-01-01T00:00:01.000Z' } }}
          focusedFreq={TUNED_FREQ}
          maxRangeNm={40}
        />
      )
      rerender(
        <RadarScopePanel
          adsbAircraft={{ ABC123: { ...base, range_nm: 35, timestamp: '1970-01-01T00:00:02.000Z' } }}
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
          adsbAircraft={{ ABC123: { ...base, range_nm: 3, timestamp: '1970-01-01T00:00:03.000Z' } }}
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
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 45, timestamp: '1970-01-01T00:00:01.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      // Bad frame: null bearing_deg, gap well under TRAIL_STALE_MS.
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: null, timestamp: '1970-01-01T00:00:02.000Z' } }} focusedFreq={TUNED_FREQ} />
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
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: 45, timestamp: '1970-01-01T00:00:00.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      // Gap 60s < 90s from the last good frame -> still passes through.
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: null, timestamp: '1970-01-01T00:01:00.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelectorAll('[data-testid="radar-blip"]').length).toBe(1)
      // Gap 95s > 90s from the last good frame (timestamp 0) -> excluded.
      rerender(
        <RadarScopePanel adsbAircraft={{ ABC123: { ...base, bearing_deg: null, timestamp: '1970-01-01T00:01:35.000Z' } }} focusedFreq={TUNED_FREQ} />
      )
      expect(container.querySelectorAll('[data-testid="radar-blip"]').length).toBe(0)
    })
  })

  describe('selection (Phase 51)', () => {
    const twoAircraft = {
      ABC123: { icao: 'ABC123', callsign: 'TEST1', bearing_deg: 45, range_nm: 10 },
      DEF456: { icao: 'DEF456', callsign: 'TEST2', bearing_deg: 270, range_nm: 30 },
    }

    it('calls onSelectAircraft with the correct icao when a blip is clicked', () => {
      const onSelectAircraft = vi.fn()
      const { container } = render(
        <RadarScopePanel
          adsbAircraft={twoAircraft}
          focusedFreq={TUNED_FREQ}
          onSelectAircraft={onSelectAircraft}
        />
      )
      fireEvent.click(container.querySelector('[data-testid="radar-blip"][data-icao="DEF456"]'))
      expect(onSelectAircraft).toHaveBeenCalledTimes(1)
      expect(onSelectAircraft).toHaveBeenCalledWith('DEF456')
    })

    it('does not throw when a blip is clicked with no onSelectAircraft prop', () => {
      // Existing callers (and older tests) render without the callback;
      // the click handler must be a safe no-op in that case.
      const { container } = render(
        <RadarScopePanel adsbAircraft={twoAircraft} focusedFreq={TUNED_FREQ} />
      )
      expect(() => {
        fireEvent.click(container.querySelector('[data-testid="radar-blip"][data-icao="ABC123"]'))
      }).not.toThrow()
    })

    it('renders the amber highlight ring on the selected blip only', () => {
      const { container } = render(
        <RadarScopePanel
          adsbAircraft={twoAircraft}
          focusedFreq={TUNED_FREQ}
          selectedIcao="ABC123"
        />
      )
      const rings = container.querySelectorAll('[data-testid="radar-blip-highlight"]')
      expect(rings.length).toBe(1)
      // The ring sits inside the selected aircraft's blip group, not
      // the other one.
      const selectedGroup = container.querySelector('[data-testid="radar-blip"][data-icao="ABC123"]')
      const otherGroup = container.querySelector('[data-testid="radar-blip"][data-icao="DEF456"]')
      expect(selectedGroup.querySelector('[data-testid="radar-blip-highlight"]')).not.toBeNull()
      expect(otherGroup.querySelector('[data-testid="radar-blip-highlight"]')).toBeNull()
      // Amber stroke, no fill, larger radius than the main blip.
      const ring = rings[0]
      expect(ring.getAttribute('stroke')).toBe('var(--neon-amber)')
      expect(ring.getAttribute('fill')).toBe('none')
      const mainBlip = selectedGroup.querySelector('circle[filter="url(#mimir-radar-glow)"]')
      expect(Number(ring.getAttribute('r'))).toBeGreaterThan(Number(mainBlip.getAttribute('r')))
    })

    it('renders no highlight ring when nothing is selected', () => {
      const { container } = render(
        <RadarScopePanel
          adsbAircraft={twoAircraft}
          focusedFreq={TUNED_FREQ}
          selectedIcao={null}
        />
      )
      expect(container.querySelectorAll('[data-testid="radar-blip-highlight"]').length).toBe(0)
    })

    it('renders the highlight ring after the main blip circle inside the group', () => {
      // Placement guard: existing position tests select the FIRST
      // circle inside a blip group and expect the main blip, so the
      // ring must never precede it in document order.
      const { container } = render(
        <RadarScopePanel
          adsbAircraft={twoAircraft}
          focusedFreq={TUNED_FREQ}
          selectedIcao="ABC123"
        />
      )
      const selectedGroup = container.querySelector('[data-testid="radar-blip"][data-icao="ABC123"]')
      const circles = selectedGroup.querySelectorAll('circle')
      expect(circles[0].getAttribute('filter')).toBe('url(#mimir-radar-glow)')
      expect(circles[1].getAttribute('data-testid')).toBe('radar-blip-highlight')
    })
  })

  describe('Phase 53-HOTFIX — ISO timestamp coercion', () => {
    // Regression seam for the ISO-string wire timestamp bug: the backend
    // emits `timestamp` as an ISO 8601 string (dashboard/server.py:666,
    // `msg.timestamp.isoformat()`), and the trail buffer subtracts stored
    // ts values. String arithmetic yields NaN, so with the raw string the
    // staleness clear never fired and derivePredictionVector always
    // returned null against live data. parseFrameTs() now coerces to
    // epoch ms at the boundary; these tests prove it end to end.

    it('derives a non-null prediction vector from ISO-string frame timestamps', () => {
      // With the unfixed code the trail stores raw ISO strings, so
      // derivePredictionVector's `newest.ts - oldest.ts` is NaN and it
      // returns null. With parseFrameTs coercion the stored ts values
      // are epoch ms and a vector is derived.
      //
      // NOTE on units (updated by Phase 52-HOTFIX): the trail stores
      // epoch MILLISECONDS, and derivePredictionVector now applies the
      // ms->s conversion internally, so the rates are genuine
      // per-second values: 10 deg over 10000 ms (10 s) = 1.0 deg/s.
      // The load-bearing assertion below is that per-second value
      // (1.0 deg/s), not the pre-fix per-millisecond value (0.001).
      const trailsRef = { current: new Map() }
      const base = { icao: 'ABC123', callsign: 'TEST1', range_nm: 10 }
      const { rerender } = render(
        <RadarScopePanel
          adsbAircraft={{ ABC123: { ...base, bearing_deg: 0, timestamp: '2026-01-15T10:30:00.000Z' } }}
          focusedFreq={TUNED_FREQ}
          trailsRef={trailsRef}
        />
      )
      rerender(
        <RadarScopePanel
          adsbAircraft={{ ABC123: { ...base, bearing_deg: 5, timestamp: '2026-01-15T10:30:05.000Z' } }}
          focusedFreq={TUNED_FREQ}
          trailsRef={trailsRef}
        />
      )
      rerender(
        <RadarScopePanel
          adsbAircraft={{ ABC123: { ...base, bearing_deg: 10, timestamp: '2026-01-15T10:30:10.000Z' } }}
          focusedFreq={TUNED_FREQ}
          trailsRef={trailsRef}
        />
      )
      const history = trailsRef.current.get('ABC123')
      expect(history.length).toBeGreaterThanOrEqual(2)
      const v = derivePredictionVector(history)
      expect(v).not.toBeNull()
      expect(v.thetaDegPerSec).toBeCloseTo(1.0, 10)
      expect(v.deltaRNmPerSec).toBeCloseTo(0, 10)
    })

    it('clears the trail when an ISO-timestamped gap exceeds TRAIL_STALE_MS', () => {
      // Explicit regression companion to the existing staleness test:
      // with ISO string timestamps the > 90000 ms gap must actually
      // clear the trail rather than bridge it. (The +95 s fix below is
      // measured from the LAST STORED timestamp, 10:30:05, since the
      // staleness check compares against the newest trail entry.)
      const base = { icao: 'ABC123', callsign: 'TEST1', range_nm: 10 }
      const { container, rerender } = render(
        <RadarScopePanel
          adsbAircraft={{ ABC123: { ...base, bearing_deg: 45, timestamp: '2026-01-15T10:30:00.000Z' } }}
          focusedFreq={TUNED_FREQ}
        />
      )
      rerender(
        <RadarScopePanel
          adsbAircraft={{ ABC123: { ...base, bearing_deg: 50, timestamp: '2026-01-15T10:30:05.000Z' } }}
          focusedFreq={TUNED_FREQ}
        />
      )
      expect(container.querySelector('polyline')).not.toBeNull()
      rerender(
        <RadarScopePanel
          adsbAircraft={{ ABC123: { ...base, bearing_deg: 55, timestamp: '2026-01-15T10:31:40.000Z' } }}
          focusedFreq={TUNED_FREQ}
        />
      )
      expect(container.querySelector('polyline')).toBeNull()
    })
  })

  describe('selected prediction box (Phase 58)', () => {
    const aircraft = {
      ABC123: { icao: 'ABC123', callsign: 'VOZ123', bearing_deg: 45, range_nm: 10, timestamp: '1970-01-01T00:00:11.000Z' },
      DEF456: { icao: 'DEF456', callsign: 'QLK456', bearing_deg: 200, range_nm: 25, timestamp: '1970-01-01T00:00:11.000Z' },
    }
    const history = (bearing) => [
      { bearing_deg: bearing, range_nm: 12, ts: 1000 },
      { bearing_deg: bearing + 20, range_nm: 10, ts: 11000 },
    ]

    it('test_selected_aircraft_renders_box_not_plain_label', () => {
      const trailsRef = { current: new Map([['ABC123', history(45)]]) }
      const { container } = render(<RadarScopePanel adsbAircraft={aircraft} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />)
      const box = container.querySelector('[data-testid="radar-prediction-box"]')
      expect(box).toHaveTextContent('VOZ123')
      expect(box).toHaveTextContent('θ')
      expect(box).toHaveTextContent('Δr')
      expect(container.querySelector('[data-testid="radar-blip"][data-icao="DEF456"] > text')).not.toBeNull()
    })

    it('test_box_uses_2dp_for_delta_r', () => {
      const trailsRef = { current: new Map([['ABC123', history(45)]]) }
      const { container } = render(<RadarScopePanel adsbAircraft={{ ABC123: { ...aircraft.ABC123, timestamp: '1970-01-01T00:00:11.000Z' } }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />)
      expect(container.querySelector('[data-testid="radar-prediction-box"]').textContent).toMatch(/Δr -?0\.20nm\/s/)
    })

    it('test_box_falls_back_to_icao_only_when_vector_unavailable', () => {
      const trailsRef = { current: new Map([['ABC123', [{ bearing_deg: 45, range_nm: 10, ts: 1000 }]]]) }
      const { container } = render(<RadarScopePanel adsbAircraft={{ ABC123: { ...aircraft.ABC123, timestamp: '1970-01-01T00:00:01.000Z' } }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />)
      expect(container.querySelector('[data-testid="radar-prediction-box"]').textContent).toBe('VOZ123')
    })

    it('flips the box side based on the REAL screen direction, not theta sign alone', () => {
      // RENAMED and REWRITTEN 2026-08-09 (live traffic: 7C389F, 7C2EB8).
      // The box's side is now driven by the real (dx, dy) direction —
      // the same vector driving the line and dots — not by
      // v.thetaDegPerSec's sign in isolation. The OLD fixtures for this
      // test (bearing=45, deltaR=-0.2) are NOT usable under the new rule:
      // deltaR's contribution to dx was strong enough that BOTH the old
      // "positive theta" and "negative theta" fixtures produced dx < 0,
      // meaning boxOnLeft was the SAME for both — which is exactly the
      // bug this fix addresses. This test uses deltaR=0 fixtures instead,
      // isolating theta's effect on the real direction cleanly, so the
      // test verifies the intended behaviour without being confounded by
      // range-rate. See the companion test below for the deltaR-dominant
      // case that was actually broken on live traffic.
      const positiveRef = { current: new Map([['ABC123', [{ bearing_deg: 0, range_nm: 10, ts: 1000 }, { bearing_deg: 20, range_nm: 10, ts: 11000 }]]]) }
      const negativeRef = { current: new Map([['ABC123', [{ bearing_deg: 20, range_nm: 10, ts: 1000 }, { bearing_deg: 0, range_nm: 10, ts: 11000 }]]]) }
      const acAtNorth = { ...aircraft.ABC123, bearing_deg: 0, range_nm: 10 }
      const positive = render(<RadarScopePanel adsbAircraft={{ ABC123: acAtNorth }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={positiveRef} />)
      // Positive theta (clockwise sweep) at bearing 0 -> real direction
      // points RIGHT (dx > 0) -> box must sit LEFT of the blip.
      expect(Number(positive.container.querySelector('[data-testid="radar-prediction-box"] text').getAttribute('x'))).toBeLessThan(Number(positive.container.querySelector('[data-testid="radar-blip"] circle[filter]').getAttribute('cx')))
      positive.unmount()
      const negative = render(<RadarScopePanel adsbAircraft={{ ABC123: acAtNorth }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={negativeRef} />)
      // Negative theta at bearing 0 -> real direction points LEFT
      // (dx < 0) -> box must sit RIGHT of the blip.
      expect(Number(negative.container.querySelector('[data-testid="radar-prediction-box"] text').getAttribute('x'))).toBeGreaterThan(Number(negative.container.querySelector('[data-testid="radar-blip"] circle[filter]').getAttribute('cx')))
    })

    it('flips the box side by the real direction even when deltaR dominates and disagrees with theta sign', () => {
      // The actual regression this fix targets. A trail where theta is
      // POSITIVE but a strong closing deltaR pulls the real (dx, dy)
      // direction to the OTHER side than theta's sign alone would
      // suggest. Under the OLD (theta-only) rule this box would have
      // landed on the SAME side as the line, overlapping it — which is
      // exactly what was seen on live traffic (7C389F, 7C2EB8, where
      // theta and deltaR jointly determine the true direction).
      // Fixture: aircraft at bearing 45, range 20. theta=+2 deg/s
      // (positive -> old rule says box LEFT), but deltaR=-0.6 nm/s
      // (strongly closing) is enough to swing the true direction so
      // dx < 0 -> the box must sit on the RIGHT, opposite the old rule.
      const trail = [
        { bearing_deg: 45, range_nm: 20, ts: 1000 },
        { bearing_deg: 65, range_nm: 14, ts: 11000 },
      ]
      const trailsRef = { current: new Map([['ABC123', trail]]) }
      const v = derivePredictionVector(trail)
      expect(v.thetaDegPerSec).toBeGreaterThan(0)
      const ac = { ...aircraft.ABC123, bearing_deg: 45, range_nm: 20 }
      const { container } = render(<RadarScopePanel adsbAircraft={{ ABC123: ac }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />)
      const here = projectToScope(ac.bearing_deg, ac.range_nm, 40, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
      const proj = projectPosition(ac.bearing_deg, ac.range_nm, v.thetaDegPerSec, v.deltaRNmPerSec, 45)
      const there = projectToScope(proj.bearing_deg, Math.min(proj.range_nm, 40), 40, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
      const dx = there.x - here.x
      // Confirm the fixture actually produces the disagreement being
      // tested — if this fails, the fixture itself needs adjusting, not
      // the assertion below.
      expect(dx).toBeLessThan(0)
      const boxTextX = Number(container.querySelector('[data-testid="radar-prediction-box"] text').getAttribute('x'))
      const blipX = Number(container.querySelector('[data-testid="radar-blip"] circle[filter]').getAttribute('cx'))
      // dx < 0 (real direction points left) -> box must sit on the RIGHT
      // (boxTextX > blipX), regardless of theta's positive sign.
      expect(boxTextX).toBeGreaterThan(blipX)
    })

    it('test_non_selected_aircraft_unchanged', () => {
      const { container } = render(<RadarScopePanel adsbAircraft={aircraft} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" />)
      expect(container.querySelector('[data-testid="radar-blip"][data-icao="DEF456"] > text')).not.toBeNull()
      expect(container.querySelector('[data-testid="radar-blip"][data-icao="DEF456"] [data-testid="radar-prediction-box"]')).toBeNull()
    })

    it('test_box_falls_back_to_icao_only_when_vector_non_finite', () => {
      // ADV-02 (Phase 58-FIX): a trail whose newest fix carries a NaN
      // bearing makes derivePredictionVector return a truthy but
      // non-finite vector ({ thetaDegPerSec: NaN, ... }). The
      // Number.isFinite guard in RadarScopePanel must collapse that to
      // null so the box falls back to ICAO-only, rather than rendering
      // "θ NaN" on a live monitoring display.
      //
      // The NaN is placed in the NEWEST fix deliberately: the trail
      // polyline renderer projects history.slice(0, -1) (all stored
      // points EXCEPT the newest), so only the finite oldest fix is
      // drawn and no NaN leaks into the rendered SVG. The blip itself
      // uses the aircraft's own bearing_deg (45, valid), so it projects
      // normally; only the derived vector is poisoned. (Putting the NaN
      // in the oldest fix would also poison the trail polyline, which
      // is a separate pre-existing rendering concern, not what this
      // guard test is about.)
      const trails = [
        { bearing_deg: 45, range_nm: 12, ts: 1000 },
        { bearing_deg: NaN, range_nm: 10, ts: 11000 },
      ]
      const tref = { current: new Map([['ABC123', trails]]) }
      const { container } = render(
        <RadarScopePanel
          adsbAircraft={aircraft}
          focusedFreq={TUNED_FREQ}
          selectedIcao="ABC123"
          trailsRef={tref}
        />
      )
      const box = container.querySelector('[data-testid="radar-prediction-box"]')
      expect(box.textContent).toBe('VOZ123')
      expect(box.textContent).not.toContain('θ')
      expect(box.textContent).not.toContain('Δr')
      // No NaN/Infinity may leak into the serialised SVG markup.
      expect(container.innerHTML).not.toContain('NaN')
      expect(container.innerHTML).not.toContain('Infinity')
      expect(container.querySelectorAll('[data-testid="radar-prediction-ghost-dot"]').length).toBe(0) // TD-59-3: non-finite vector suppresses ghost dots too
    })
  })

  describe('selected prediction direction-indicator dots (Phase 59 rework)', () => {
    // Fixtures reused from the Phase 58 block's pattern. Each test
    // injects a pre-seeded trailsRef so the IIFE's derivePredictionVector
    // has >= 2 fixes to work with. The aircraft record's bearing_deg /
    // range_nm is the projection ORIGIN (ac.bearing_deg, ac.range_nm),
    // which is independent of the trail's newest fix — the indicator
    // starts from the aircraft's real current position.
    //
    // GHOST_LINE_LENGTH_PX and RING_CLEARANCE_PX mirror the component
    // constants. Increased from 0.15 to 0.22 and the ring-clearance
    // offset added on 2026-08-08 after live traffic (7C6DB4) showed
    // dot1 landing inside the blip's own selection ring (r=6) with no
    // offset — the indicator now starts 8px out from `here`, clear of
    // the ring, before the fixed-length vector is applied.
    const GHOST_LINE_LENGTH_PX = SCOPE_MAX_R * 0.22
    const RING_CLEARANCE_PX = 8

    // Compute the expected dot coordinates exactly as the component does:
    // unit vector of (there - here), start point offset RING_CLEARANCE_PX
    // out from `here` along that direction, then scaled to
    // GHOST_LINE_LENGTH_PX from that start, with dots at 1/3, 2/3 and
    // full length along it.
    const expectedDots = (ac, v) => {
      const here = projectToScope(ac.bearing_deg, ac.range_nm, 40, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
      const proj = projectPosition(ac.bearing_deg, ac.range_nm, v.thetaDegPerSec, v.deltaRNmPerSec, 45)
      const there = projectToScope(proj.bearing_deg, Math.min(proj.range_nm, 40), 40, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
      const dx = there.x - here.x
      const dy = there.y - here.y
      const trueLength = Math.sqrt(dx * dx + dy * dy)
      const ux = dx / trueLength
      const uy = dy / trueLength
      const startX = here.x + ux * RING_CLEARANCE_PX
      const startY = here.y + uy * RING_CLEARANCE_PX
      const fixedDx = ux * GHOST_LINE_LENGTH_PX
      const fixedDy = uy * GHOST_LINE_LENGTH_PX
      return {
        here,
        there,
        start: { x: r2(startX), y: r2(startY) },
        dot1: { x: r2(startX + fixedDx * (1 / 3)), y: r2(startY + fixedDy * (1 / 3)) },
        dot2: { x: r2(startX + fixedDx * (2 / 3)), y: r2(startY + fixedDy * (2 / 3)) },
        dot3: { x: r2(startX + fixedDx), y: r2(startY + fixedDy) },
      }
    }

    it('renders three dots at evenly-spaced positions along a fixed-length vector from here', () => {
      // Aircraft at bearing 0, range 10. Trail produces theta=1.0 deg/s,
      // deltaR=0 nm/s (10 deg bearing change over 10 s, range unchanged).
      const ac = { icao: 'ABC123', callsign: 'VOZ123', bearing_deg: 0, range_nm: 10, timestamp: '1970-01-01T00:00:11.000Z' }
      const trail = [
        { bearing_deg: 0, range_nm: 10, ts: 1000 },
        { bearing_deg: 10, range_nm: 10, ts: 11000 },
      ]
      const trailsRef = { current: new Map([['ABC123', trail]]) }
      const { container } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: ac }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />
      )
      const v = derivePredictionVector(trail)
      expect(v.thetaDegPerSec).toBeCloseTo(1.0, 10)
      expect(v.deltaRNmPerSec).toBeCloseTo(0, 10)
      const exp = expectedDots(ac, v)
      const dots = container.querySelectorAll('[data-testid="radar-prediction-ghost-dot"][data-position]')
      expect(dots.length).toBe(3)
      for (const [position, expected] of [['1', exp.dot1], ['2', exp.dot2], ['3', exp.dot3]]) {
        const dot = container.querySelector(`[data-testid="radar-prediction-ghost-dot"][data-position="${position}"]`)
        expect(dot).not.toBeNull()
        expect(Number(dot.getAttribute('cx'))).toBeCloseTo(expected.x, 2)
        expect(Number(dot.getAttribute('cy'))).toBeCloseTo(expected.y, 2)
      }
    })

    it('holds the total on-screen indicator length constant regardless of the true-vector length', () => {
      // Core regression guard for the normalisation. Two clearly different
      // rate fixtures must produce the SAME here->dot3 distance
      // (RING_CLEARANCE_PX + GHOST_LINE_LENGTH_PX — the ring-clearance
      // offset plus the fixed-length vector from that offset start point),
      // not the underlying true displacement.
      //
      // Slow case (original RXA4846-style): theta +0.6 deg/s,
      // deltaR +0.03 nm/s over 10 s of trail.
      // Hard-turn case: theta +3.1 deg/s, deltaR 0 nm/s over 10 s of trail.
      // r2() rounding contributes at most ~0.015 px of error, so precision 1
      // (tolerance 0.05) is used for the distance assertions.
      const fixtures = [
        [
          { bearing_deg: 0, range_nm: 10, ts: 1000 },
          { bearing_deg: 6, range_nm: 10.3, ts: 11000 },
        ],
        [
          { bearing_deg: 0, range_nm: 10, ts: 1000 },
          { bearing_deg: 31, range_nm: 10, ts: 11000 },
        ],
      ]
      for (const trail of fixtures) {
        const v = derivePredictionVector(trail)
        expect(v).not.toBeNull()
        const ac = { icao: 'ABC123', callsign: 'VOZ123', bearing_deg: 0, range_nm: 10, timestamp: '1970-01-01T00:00:11.000Z' }
        const trailsRef = { current: new Map([['ABC123', trail]]) }
        const { container, unmount } = render(
          <RadarScopePanel adsbAircraft={{ ABC123: ac }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />
        )
        const here = projectToScope(ac.bearing_deg, ac.range_nm, 40, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
        const dot3 = container.querySelector('[data-testid="radar-prediction-ghost-dot"][data-position="3"]')
        expect(dot3).not.toBeNull()
        const dist = Math.hypot(
          Number(dot3.getAttribute('cx')) - here.x,
          Number(dot3.getAttribute('cy')) - here.y,
        )
        expect(dist).toBeCloseTo(RING_CLEARANCE_PX + GHOST_LINE_LENGTH_PX, 1)
        unmount()
      }
    })

    it('renders no dots and no NaN/Infinity attributes for a degenerate near-zero displacement', () => {
      // A tiny but non-zero rate vector: theta=0.0001 deg/s,
      // deltaR=0.00001 nm/s. derivePredictionVector returns a non-null
      // vector, but the 45s on-screen displacement is ~0.003 px, below
      // the 0.01 px degenerate threshold. The line + box still render
      // (the box's θ/Δr readouts correctly indicate no meaningful
      // motion); the ghost-dot group must NOT render, and no NaN or
      // Infinity may leak into the SVG.
      const ac = { icao: 'ABC123', callsign: 'VOZ123', bearing_deg: 0, range_nm: 10, timestamp: '1970-01-01T00:00:11.000Z' }
      const trail = [
        { bearing_deg: 0, range_nm: 10, ts: 1000 },
        { bearing_deg: 0.001, range_nm: 10.0001, ts: 11000 },
      ]
      const v = derivePredictionVector(trail)
      expect(v).not.toBeNull()
      expect(v.thetaDegPerSec).not.toBe(0)
      expect(v.deltaRNmPerSec).not.toBe(0)
      const trailsRef = { current: new Map([['ABC123', trail]]) }
      const { container } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: ac }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />
      )
      expect(container.querySelectorAll('[data-testid="radar-prediction-ghost-dot"]').length).toBe(0)
      expect(container.querySelector('[data-testid="radar-prediction-ghosts"]')).toBeNull()
      // The box still renders with the (tiny) θ/Δr readouts.
      expect(container.querySelector('[data-testid="radar-prediction-box"]')).not.toBeNull()
      expect(container.innerHTML).not.toMatch(/NaN|Infinity/)
    })

    it('does not render ghost dots for a non-selected aircraft', () => {
      const ac = { icao: 'ABC123', callsign: 'VOZ123', bearing_deg: 0, range_nm: 10, timestamp: '1970-01-01T00:00:11.000Z' }
      const trail = [
        { bearing_deg: 0, range_nm: 10, ts: 1000 },
        { bearing_deg: 10, range_nm: 10, ts: 11000 },
      ]
      const trailsRef = { current: new Map([['ABC123', trail]]) }
      const { container } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: ac }} focusedFreq={TUNED_FREQ} selectedIcao="DEF456" trailsRef={trailsRef} />
      )
      expect(container.querySelectorAll('[data-testid="radar-prediction-ghost-dot"]').length).toBe(0)
      expect(container.querySelector('[data-testid="radar-prediction-ghosts"]')).toBeNull()
    })

    it('does not render ghost dots when the vector is unavailable (< 2 fixes)', () => {
      // With only one trail fix, derivePredictionVector returns null, v
      // is null, proj is null, and the !proj guard returns the box
      // before reaching the ghost-dot block. No dots should render.
      const ac = { icao: 'ABC123', callsign: 'VOZ123', bearing_deg: 0, range_nm: 10, timestamp: '1970-01-01T00:00:01.000Z' }
      const trailsRef = { current: new Map([['ABC123', [{ bearing_deg: 0, range_nm: 10, ts: 1000 }]]]) }
      const { container } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: ac }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />
      )
      expect(container.querySelectorAll('[data-testid="radar-prediction-ghost-dot"]').length).toBe(0)
      expect(container.querySelector('[data-testid="radar-prediction-ghosts"]')).toBeNull()
    })

    it('keeps the dashed line endpoint identical to dot3 (shared fixed-length endpoint), starting past the selection ring', () => {
      // Regression guard, covering TWO fixes in sequence:
      // 1. (2026-08-08, live traffic: 7C7772/VOZ1393) The line and dots
      //    must always share the SAME endpoint. Previously the line ran
      //    from `here` to the true-to-scale `there`, while the dots ran
      //    along a normalised fixed-length vector — two different
      //    endpoints that only coincided by chance.
      // 2. (2026-08-08, live traffic: 7C6DB4) The indicator's START point
      //    must clear the blip's own selection ring (r=6), not begin at
      //    `here` directly — otherwise dot1 visually overlaps the ring.
      //    The line's x1/y1 is therefore RING_CLEARANCE_PX out from
      //    `here`, not `here` itself.
      //
      // `there` (the true-to-scale clamped 45s projection) is still used
      // internally to derive the DIRECTION (dx, dy) — it is not the
      // line's rendered start or end point in the non-degenerate case.
      const ac = { icao: 'ABC123', callsign: 'VOZ123', bearing_deg: 0, range_nm: 10, timestamp: '1970-01-01T00:00:11.000Z' }
      const trail = [
        { bearing_deg: 0, range_nm: 10, ts: 1000 },
        { bearing_deg: 10, range_nm: 10, ts: 11000 },
      ]
      const trailsRef = { current: new Map([['ABC123', trail]]) }
      const { container } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: ac }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />
      )
      const v = derivePredictionVector(trail)
      const exp = expectedDots(ac, v)
      const line = container.querySelector('[data-testid="radar-prediction-line"] line')
      expect(line).not.toBeNull()
      // Line starts at the ring-cleared start point, NOT `here` directly.
      expect(Number(line.getAttribute('x1'))).toBeCloseTo(exp.start.x, 2)
      expect(Number(line.getAttribute('y1'))).toBeCloseTo(exp.start.y, 2)
      // Line ends at dot3's exact coordinate — the core alignment guard.
      expect(Number(line.getAttribute('x2'))).toBeCloseTo(exp.dot3.x, 2)
      expect(Number(line.getAttribute('y2'))).toBeCloseTo(exp.dot3.y, 2)
      const dot3 = container.querySelector('[data-testid="radar-prediction-ghost-dot"][data-position="3"]')
      expect(dot3).not.toBeNull()
      expect(Number(line.getAttribute('x2'))).toBeCloseTo(Number(dot3.getAttribute('cx')), 2)
      expect(Number(line.getAttribute('y2'))).toBeCloseTo(Number(dot3.getAttribute('cy')), 2)
      expect(container.querySelector('[data-testid="radar-prediction-box"]')).not.toBeNull()
    })

    it('falls back to `here` -> true-to-scale `there` for the line in the degenerate case', () => {
      // Companion to the degenerate-dots test above: when the on-screen
      // displacement is too small to normalise (< 0.01 px), no dots
      // render, and the line falls back to `here` -> the true
      // (unclamped-endpoint) `there` position, WITHOUT the ring-clearance
      // offset — there is no direction to offset along in this case.
      const ac = { icao: 'ABC123', callsign: 'VOZ123', bearing_deg: 0, range_nm: 10, timestamp: '1970-01-01T00:00:11.000Z' }
      const trail = [
        { bearing_deg: 0, range_nm: 10, ts: 1000 },
        { bearing_deg: 0.001, range_nm: 10.0001, ts: 11000 },
      ]
      const v = derivePredictionVector(trail)
      expect(v).not.toBeNull()
      const trailsRef = { current: new Map([['ABC123', trail]]) }
      const { container } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: ac }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />
      )
      const here = projectToScope(ac.bearing_deg, ac.range_nm, 40, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
      const proj = projectPosition(ac.bearing_deg, ac.range_nm, v.thetaDegPerSec, v.deltaRNmPerSec, 45)
      const there = projectToScope(proj.bearing_deg, Math.min(proj.range_nm, 40), 40, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)
      const line = container.querySelector('[data-testid="radar-prediction-line"] line')
      expect(line).not.toBeNull()
      expect(Number(line.getAttribute('x1'))).toBeCloseTo(r2(here.x), 1)
      expect(Number(line.getAttribute('y1'))).toBeCloseTo(r2(here.y), 1)
      expect(Number(line.getAttribute('x2'))).toBeCloseTo(r2(there.x), 1)
      expect(Number(line.getAttribute('y2'))).toBeCloseTo(r2(there.y), 1)
      expect(container.querySelectorAll('[data-testid="radar-prediction-ghost-dot"]').length).toBe(0)
    })

    it('sizes and opacities dot1 smaller and dimmer than dot3, in document order', () => {
      // The visual ramp (nearest dim/small -> furthest bright/large) is
      // still load-bearing for the direction cue. Assert the three dots
      // appear in document order 1 -> 2 -> 3 with monotonically
      // increasing r and opacity.
      const ac = { icao: 'ABC123', callsign: 'VOZ123', bearing_deg: 0, range_nm: 10, timestamp: '1970-01-01T00:00:11.000Z' }
      const trail = [
        { bearing_deg: 0, range_nm: 10, ts: 1000 },
        { bearing_deg: 10, range_nm: 10, ts: 11000 },
      ]
      const trailsRef = { current: new Map([['ABC123', trail]]) }
      const { container } = render(
        <RadarScopePanel adsbAircraft={{ ABC123: ac }} focusedFreq={TUNED_FREQ} selectedIcao="ABC123" trailsRef={trailsRef} />
      )
      const dots = Array.from(container.querySelectorAll('[data-testid="radar-prediction-ghost-dot"]'))
      expect(dots.map((d) => d.getAttribute('data-position'))).toEqual(['1', '2', '3'])
      const radii = dots.map((d) => Number(d.getAttribute('r')))
      const opacities = dots.map((d) => Number(d.getAttribute('opacity')))
      expect(radii[0]).toBeLessThan(radii[1])
      expect(radii[1]).toBeLessThan(radii[2])
      expect(opacities[0]).toBeLessThan(opacities[1])
      expect(opacities[1]).toBeLessThan(opacities[2])
    })
  })
})