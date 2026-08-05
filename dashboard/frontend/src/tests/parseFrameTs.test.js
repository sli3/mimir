import { describe, it, expect } from 'vitest'

import { parseFrameTs } from '../utils/parseFrameTs.js'

// Fixed reference instant used across these tests. The expected epoch
// ms was verified with `node -e "console.log(Date.parse(...))"`.
const KNOWN_ISO = '2026-01-15T10:30:00.000Z'
const KNOWN_ISO_MS = 1768473000000

describe('parseFrameTs', () => {
  it('parses an ISO 8601 string to the correct epoch ms', () => {
    expect(parseFrameTs(KNOWN_ISO)).toBe(KNOWN_ISO_MS)
    expect(parseFrameTs(KNOWN_ISO)).toBe(new Date(KNOWN_ISO).getTime())
  })

  it('subtracts two ISO strings a known interval apart to that interval', () => {
    // This is the exact trail-buffer / derivePredictionVector operation
    // that returned NaN before Phase 53-HOTFIX.
    const a = parseFrameTs('2026-01-15T10:30:00.000Z')
    const b = parseFrameTs('2026-01-15T10:30:05.000Z')
    expect(b - a).toBe(5000)
  })

  it('passes a finite numeric timestamp through unchanged', () => {
    expect(parseFrameTs(1234567890)).toBe(1234567890)
    expect(parseFrameTs(0)).toBe(0)
  })

  it('falls back to ~Date.now() for null', () => {
    const before = Date.now()
    const result = parseFrameTs(null)
    expect(Math.abs(result - before)).toBeLessThan(1000)
  })

  it('falls back to ~Date.now() for undefined', () => {
    const before = Date.now()
    const result = parseFrameTs(undefined)
    expect(Math.abs(result - before)).toBeLessThan(1000)
  })

  it('falls back to ~Date.now() for an unparseable garbage string', () => {
    const before = Date.now()
    expect(Math.abs(parseFrameTs('not a date') - before)).toBeLessThan(1000)
    expect(Math.abs(parseFrameTs('') - before)).toBeLessThan(1000)
  })

  it('falls back to ~Date.now() for NaN and non-finite numbers', () => {
    const before = Date.now()
    expect(Math.abs(parseFrameTs(NaN) - before)).toBeLessThan(1000)
    expect(Math.abs(parseFrameTs(Infinity) - before)).toBeLessThan(1000)
    expect(Math.abs(parseFrameTs(-Infinity) - before)).toBeLessThan(1000)
  })

  it('always returns a finite number, never NaN', () => {
    const inputs = [
      KNOWN_ISO,
      1234567890,
      null,
      undefined,
      'not a date',
      '',
      NaN,
      Infinity,
      -Infinity,
      {},
      [],
    ]
    for (const input of inputs) {
      expect(Number.isFinite(parseFrameTs(input))).toBe(true)
    }
  })
})
