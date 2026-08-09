import { describe, it, expect } from 'vitest'

import {
  PREDICTION_HORIZON_SEC,
  derivePredictionVector,
  projectPosition,
} from '../utils/pathPrediction.js'

describe('PREDICTION_HORIZON_SEC', () => {
  it('is exported and equals 45', () => {
    expect(PREDICTION_HORIZON_SEC).toBe(45)
  })

  // Phase 59 (TD-59-1): the 45s ghost-dot in RadarScopePanel.jsx reuses `there`
  // (projected at PREDICTION_HORIZON_SEC) with data-horizon="45"; keep in lockstep.
  it('stays at 45 to match the data-horizon="45" ghost-dot in RadarScopePanel', () => {
    expect(PREDICTION_HORIZON_SEC).toBe(45)
  })
})

describe('derivePredictionVector', () => {
  it('converts milliseconds to seconds when computing rates (ms->s)', () => {
    // Direct regression test for Phase 52-HOTFIX. Before the fix
    // this computed as 0.5 / 1000 = 0.0005, which renders as
    // "+0.0°/s" on screen. With the ms->s conversion, it is 0.5.
    // Use exact equality (not toBeCloseTo) so any future
    // regression that drops the /1000 fails this test
    // unambiguously.
    const history = [
      { bearing_deg: 0, range_nm: 10, ts: 0 },
      { bearing_deg: 0.5, range_nm: 10, ts: 1000 },
    ]
    const v = derivePredictionVector(history)
    expect(v).not.toBeNull()
    expect(v.thetaDegPerSec).toBe(0.5)
  })

  it('produces a single-digit deg/s rate for a realistic 1-second ADSB scenario', () => {
    // Sanity-check at realistic scale: a typical aircraft covers
    // a few degrees of bearing in 1 second. The rate must be
    // single-digit (not ~0.00x), proving the ms->s conversion is
    // applied. The exact value is a plausible example, not a
    // precise production rate.
    const history = [
      { bearing_deg: 45, range_nm: 12, ts: 0 },
      { bearing_deg: 46.5, range_nm: 11.9, ts: 1000 },
    ]
    const v = derivePredictionVector(history)
    expect(v).not.toBeNull()
    expect(v.thetaDegPerSec).toBeGreaterThan(1)
    expect(v.thetaDegPerSec).toBeLessThan(10)
    expect(v.deltaRNmPerSec).toBeCloseTo(-0.1, 10)
  })

  it('returns null on an empty array', () => {
    expect(derivePredictionVector([])).toBeNull()
  })

  it('returns null on a single-point history', () => {
    expect(
      derivePredictionVector([{ bearing_deg: 45, range_nm: 10, ts: 1000 }])
    ).toBeNull()
  })

  it('returns null on non-array input', () => {
    expect(derivePredictionVector(null)).toBeNull()
    expect(derivePredictionVector(undefined)).toBeNull()
    expect(derivePredictionVector('not an array')).toBeNull()
    expect(derivePredictionVector({ bearing_deg: 45 })).toBeNull()
  })

  it('returns null when oldest and newest share a timestamp (zero elapsed)', () => {
    const history = [
      { bearing_deg: 45, range_nm: 10, ts: 1000 },
      { bearing_deg: 50, range_nm: 9, ts: 1000 },
    ]
    expect(derivePredictionVector(history)).toBeNull()
  })

  it('returns null when newest.ts is before oldest.ts (negative elapsed)', () => {
    const history = [
      { bearing_deg: 45, range_nm: 10, ts: 2000 },
      { bearing_deg: 50, range_nm: 9, ts: 1000 },
    ]
    expect(derivePredictionVector(history)).toBeNull()
  })

  it('returns null when newest.ts is NaN', () => {
    const history = [
      { bearing_deg: 45, range_nm: 10, ts: 1000 },
      { bearing_deg: 50, range_nm: 9, ts: NaN },
    ]
    expect(derivePredictionVector(history)).toBeNull()
  })

  it('returns null when a fix is null', () => {
    expect(
      derivePredictionVector([null, { bearing_deg: 50, range_nm: 9, ts: 1000 }])
    ).toBeNull()
    expect(
      derivePredictionVector([{ bearing_deg: 45, range_nm: 10, ts: 0 }, undefined])
    ).toBeNull()
  })

  it('uses OLDEST and NEWEST fixes, not the last two', () => {
    // Oldest->newest: bearing 0 -> 180 over 20 s (20000 ms) = 9 deg/s;
    // range 10 -> 20 over 20 s = 0.5 nm/s. Deriving from the last two
    // points instead would give 18 deg/s and 0.5 nm/s (different theta).
    const history = [
      { bearing_deg: 0, range_nm: 10, ts: 0 },
      { bearing_deg: 90, range_nm: 15, ts: 10000 },
      { bearing_deg: 180, range_nm: 20, ts: 20000 },
    ]
    const v = derivePredictionVector(history)
    expect(v).not.toBeNull()
    expect(v.thetaDegPerSec).toBeCloseTo(9, 10)
    expect(v.deltaRNmPerSec).toBeCloseTo(0.5, 10)
  })

  it('discriminates oldest/newest from last-two when they differ', () => {
    // Oldest->newest: (180-0)/20 s = 9 deg/s, (20-10)/20 s = 0.5 nm/s.
    // Last-two would give (180-5)/10 = 17.5 deg/s, (20-12)/10 = 0.8 nm/s.
    const history = [
      { bearing_deg: 0, range_nm: 10, ts: 0 },
      { bearing_deg: 5, range_nm: 12, ts: 10000 },
      { bearing_deg: 180, range_nm: 20, ts: 20000 },
    ]
    const v = derivePredictionVector(history)
    expect(v.thetaDegPerSec).toBeCloseTo(9, 10)
    expect(v.deltaRNmPerSec).toBeCloseTo(0.5, 10)
  })

  it('wraps clockwise across the 360/0 axis (shortest path)', () => {
    // 350 -> 10 is +20 clockwise, NOT -340.
    const history = [
      { bearing_deg: 350, range_nm: 10, ts: 0 },
      { bearing_deg: 10, range_nm: 10, ts: 10000 },
    ]
    const v = derivePredictionVector(history)
    expect(v.thetaDegPerSec).toBeCloseTo(2.0, 10)
    expect(v.deltaRNmPerSec).toBeCloseTo(0, 10)
  })

  it('wraps counter-clockwise across the 360/0 axis (shortest path)', () => {
    // 10 -> 350 is -20 counter-clockwise, NOT +340.
    const history = [
      { bearing_deg: 10, range_nm: 10, ts: 0 },
      { bearing_deg: 350, range_nm: 10, ts: 10000 },
    ]
    const v = derivePredictionVector(history)
    expect(v.thetaDegPerSec).toBeCloseTo(-2.0, 10)
  })

  it('reports a negative range rate for a closing aircraft', () => {
    const history = [
      { bearing_deg: 90, range_nm: 20, ts: 0 },
      { bearing_deg: 90, range_nm: 15, ts: 10000 },
    ]
    const v = derivePredictionVector(history)
    expect(v.deltaRNmPerSec).toBeLessThan(0)
    expect(v.deltaRNmPerSec).toBeCloseTo(-0.5, 10)
  })

  it('reports a positive range rate for an opening aircraft', () => {
    const history = [
      { bearing_deg: 90, range_nm: 10, ts: 0 },
      { bearing_deg: 90, range_nm: 18, ts: 10000 },
    ]
    const v = derivePredictionVector(history)
    expect(v.deltaRNmPerSec).toBeGreaterThan(0)
    expect(v.deltaRNmPerSec).toBeCloseTo(0.8, 10)
  })

  it('reports zero rates for a station-keeping aircraft', () => {
    const history = [
      { bearing_deg: 45, range_nm: 10, ts: 0 },
      { bearing_deg: 45, range_nm: 10, ts: 10000 },
    ]
    const v = derivePredictionVector(history)
    expect(v.thetaDegPerSec).toBe(0)
    expect(v.deltaRNmPerSec).toBe(0)
  })
})

describe('projectPosition', () => {
  it('returns the same position for zero rates and zero horizon', () => {
    const p = projectPosition(90, 20, 0, 0, 0)
    expect(p.bearing_deg).toBeCloseTo(90, 10)
    expect(p.range_nm).toBeCloseTo(20, 10)
  })

  it('linearly extrapolates bearing and range', () => {
    const p = projectPosition(90, 20, 2, -0.5, 10)
    expect(p.bearing_deg).toBeCloseTo(110, 10)
    expect(p.range_nm).toBeCloseTo(15, 10)
  })

  it('normalises bearing wraparound past 360', () => {
    // 350 + 2*10 = 370 -> 10
    const p = projectPosition(350, 20, 2, 0, 10)
    expect(p.bearing_deg).toBeCloseTo(10, 10)
  })

  it('normalises bearing wraparound below 0', () => {
    // 10 - 2*10 = -10 -> 350
    const p = projectPosition(10, 20, -2, 0, 10)
    expect(p.bearing_deg).toBeCloseTo(350, 10)
  })

  it('clamps range to 0 when a closing vector overshoots within the horizon', () => {
    // 5 + (-1)*10 = -5 -> clamped to 0
    const p = projectPosition(90, 5, 0, -1, 10)
    expect(p.range_nm).toBe(0)
  })

  it('never returns a negative range', () => {
    const cases = [
      projectPosition(90, 5, 0, -1, 10),
      projectPosition(0, 0, 0, -0.5, 45),
      projectPosition(180, 2, 1, -2, 45),
      projectPosition(270, 40, 0, 0.5, 45),
    ]
    for (const p of cases) {
      expect(p.range_nm).toBeGreaterThanOrEqual(0)
    }
  })

  it('always returns a bearing inside [0, 360)', () => {
    const cases = [
      projectPosition(350, 20, 2, 0, 10),
      projectPosition(10, 20, -2, 0, 10),
      projectPosition(0, 20, -1, 0, 45),
      projectPosition(359, 20, 1, 0, 45),
    ]
    for (const p of cases) {
      expect(p.bearing_deg).toBeGreaterThanOrEqual(0)
      expect(p.bearing_deg).toBeLessThan(360)
    }
  })
})
