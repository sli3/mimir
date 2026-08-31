import { describe, it, expect } from 'vitest'
import { freqMatches, findCanonicalValue, FREQ_TOLERANCE_HZ } from '../utils/frequency.js'

const FREQ_LABEL_MAP = {
  98000000: '98.0 MHz',
  127000000: '127.0 MHz',
  129125000: '129.125 MHz',
  145175000: '145.175 MHz',
  162000000: '162.000 MHz',
  915000000: '915.0 MHz',
  1090000000: '1090.0 MHz',
}

describe('freqMatches', () => {
  it('returns true for the real bug case: ADS-B offset 30 kHz', () => {
    expect(freqMatches(1_090_030_000, 1_090_000_000)).toBe(true)
  })

  it('returns true for exact canonical match', () => {
    expect(freqMatches(1_090_000_000, 1_090_000_000)).toBe(true)
  })

  it('returns true exactly at the tolerance boundary', () => {
    expect(freqMatches(1_090_100_000, 1_090_000_000)).toBe(true)
  })

  it('returns false just past the tolerance boundary', () => {
    expect(freqMatches(1_090_100_001, 1_090_000_000)).toBe(false)
  })

  it('returns false for wildly different frequencies', () => {
    expect(freqMatches(98_000_000, 1_090_000_000)).toBe(false)
  })

  it('returns false for Aviation vs ACARS cross-band gap', () => {
    expect(freqMatches(127_000_000, 129_125_000)).toBe(false)
  })

  it('treats null inputs as non-matching', () => {
    expect(freqMatches(null, 1_000_000)).toBe(false)
    expect(freqMatches(1_000_000, null)).toBe(false)
    expect(freqMatches(null, null)).toBe(false)
  })

  it('treats NaN inputs as non-matching', () => {
    expect(freqMatches(NaN, 1_000_000)).toBe(false)
    expect(freqMatches(1_000_000, NaN)).toBe(false)
  })

  it('honours a custom tolerance', () => {
    expect(freqMatches(1_090_050_000, 1_090_000_000, 30_000)).toBe(false)
    expect(freqMatches(1_090_050_000, 1_090_000_000)).toBe(true)
  })
})

describe('findCanonicalValue', () => {
  it('returns the canonical label for an offset ADS-B frequency', () => {
    expect(findCanonicalValue(1_090_030_000, FREQ_LABEL_MAP)).toBe('1090.0 MHz')
  })

  it('returns null when no canonical key matches', () => {
    expect(findCanonicalValue(200_000_000, FREQ_LABEL_MAP)).toBeNull()
  })

  it('returns null when freq is null', () => {
    expect(findCanonicalValue(null, FREQ_LABEL_MAP)).toBeNull()
  })

  it('returns null for an empty map', () => {
    expect(findCanonicalValue(1_090_000_000, {})).toBeNull()
  })

  it('preserves object values', () => {
    const map = { 98000000: { label: 'FM', colour: 'cyan' } }
    expect(findCanonicalValue(98_000_000, map)).toEqual({ label: 'FM', colour: 'cyan' })
  })

  it('preserves primitive values', () => {
    const map = { 98000000: 'FM' }
    expect(findCanonicalValue(98_000_000, map)).toBe('FM')
  })
})

describe('FREQ_TOLERANCE_HZ', () => {
  it('exists and equals 100 kHz', () => {
    expect(FREQ_TOLERANCE_HZ).toBe(100_000)
  })
})
