import { describe, it, expect } from 'vitest'
import { computeScaleWindow, selectDeviceProfile } from '../hooks/useWaterfall.js'

const NUM_PSD_BINS = 2048

// Profiles mirroring DEVICE_SCALE_PROFILES, spelled out so the tests pin the
// exact spec values rather than importing the (unexported) table itself.
const HACKRF_PROFILE = { floorPercentile: 0.70, floorPadDb: 2, ceilPadDb: 6, minSpanDb: 30 }
const PLUTO_PROFILE = { floorPercentile: 0.70, floorPadDb: 2, ceilPadDb: 6, minSpanDb: 15 }
const DEFAULT_PROFILE = { floorPercentile: 0.70, floorPadDb: 2, ceilPadDb: 6, minSpanDb: 0 }

/** Deterministic flat-ish noise row: all values within a 5 dB band around -95. */
function deadBandRow() {
  const row = new Array(NUM_PSD_BINS)
  for (let i = 0; i < NUM_PSD_BINS; i++) {
    row[i] = -95 + ((i * 7) % 50) / 10 - 2.5
  }
  return row
}

describe('computeScaleWindow', () => {
  it('DEAD band regression guard: min-span floor keeps span >= minSpanDb', () => {
    // Flat noise around -95 dB (all values within ~5 dB). Without the floor,
    // the natural span would be ~11 dB and noise would stretch across the
    // palette. With minSpanDb 30 the window must be at least 30 dB wide.
    const { scaleMin, scaleMax } = computeScaleWindow(deadBandRow(), HACKRF_PROFILE)
    expect(scaleMax - scaleMin).toBeGreaterThanOrEqual(30)
    // Sanity: the floor genuinely bound (natural peak is far below scaleMax).
    expect(scaleMax).toBeGreaterThan(-95)
  })

  it('STRONG signal: natural span is used and the min-span floor does NOT bind', () => {
    // Row max 30 dB above the noise floor: -65 peak over -95 noise.
    const row = new Array(NUM_PSD_BINS).fill(-95)
    row[NUM_PSD_BINS - 1] = -65
    const { scaleMin, scaleMax } = computeScaleWindow(row, HACKRF_PROFILE)
    // Natural ceiling: rowMax + ceilPadDb. The 70th percentile of this row is
    // -95, so scaleMin = -97 and scaleMin + minSpanDb = -67 < -59: the floor
    // must not bind.
    expect(scaleMin).toBe(-97)
    expect(scaleMax).toBe(-65 + HACKRF_PROFILE.ceilPadDb)
    expect(scaleMax).toBeGreaterThan(scaleMin + HACKRF_PROFILE.minSpanDb)
  })

  it('Pluto profile: min-span floor binds at 15 dB on a dead band', () => {
    const { scaleMin, scaleMax } = computeScaleWindow(deadBandRow(), PLUTO_PROFILE)
    expect(scaleMax - scaleMin).toBeGreaterThanOrEqual(15)
  })

  it('_default profile: zero visual change vs pre-Phase-42 behaviour', () => {
    const row = deadBandRow()
    let rowMax = -Infinity
    for (const v of row) if (v > rowMax) rowMax = v
    const { scaleMax } = computeScaleWindow(row, DEFAULT_PROFILE)
    // minSpanDb 0 means no floor: scaleMax is exactly rowMax + ceilPadDb,
    // byte-for-byte the pre-fix formula.
    expect(scaleMax).toBe(rowMax + DEFAULT_PROFILE.ceilPadDb)
  })

  it('non-finite row falls back safely (all NaN / Infinity)', () => {
    const row = new Array(NUM_PSD_BINS).fill(NaN)
    row[0] = Infinity
    row[1] = -Infinity
    const { scaleMin, scaleMax } = computeScaleWindow(row, DEFAULT_PROFILE)
    // Existing fallback: rowMax -> 0, noiseFloor -> null -> -100.
    expect(scaleMin).toBe(-100 - DEFAULT_PROFILE.floorPadDb)
    expect(scaleMax).toBe(0 + DEFAULT_PROFILE.ceilPadDb)
    expect(Number.isFinite(scaleMin)).toBe(true)
    expect(Number.isFinite(scaleMax)).toBe(true)
  })

  it('non-finite row still honours the min-span floor', () => {
    const row = new Array(NUM_PSD_BINS).fill(NaN)
    const { scaleMin, scaleMax } = computeScaleWindow(row, HACKRF_PROFILE)
    // Fallback window is 108 dB wide already (well over 30), so the floor
    // does not distort the fallback — it only ever widens a too-narrow one.
    expect(scaleMax - scaleMin).toBeGreaterThanOrEqual(HACKRF_PROFILE.minSpanDb)
  })
})

describe('selectDeviceProfile', () => {
  it('resolves the hackrf profile', () => {
    expect(selectDeviceProfile('hackrf')).toEqual(HACKRF_PROFILE)
  })

  it('resolves the plutosdr profile', () => {
    expect(selectDeviceProfile('plutosdr')).toEqual(PLUTO_PROFILE)
  })

  it('falls back to _default for null (pre-first-system_stats)', () => {
    expect(selectDeviceProfile(null)).toEqual(DEFAULT_PROFILE)
  })

  it('falls back to _default for undefined (device not threaded)', () => {
    expect(selectDeviceProfile(undefined)).toEqual(DEFAULT_PROFILE)
  })

  it('falls back to _default for an unrecognised device string', () => {
    expect(selectDeviceProfile('garbage')).toEqual(DEFAULT_PROFILE)
  })
})
