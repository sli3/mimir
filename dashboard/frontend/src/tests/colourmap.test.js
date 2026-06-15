import { describe, it, expect } from 'vitest'
import { psdToRgb, normalisePsd } from '../utils/colourmap.js'

describe('psdToRgb', () => {
  it('returns [3, 8, 16] for input 0', () => {
    const result = psdToRgb(0)
    expect(result).toEqual([3, 8, 16])
  })

  it('returns [255, 255, 255] for input 1', () => {
    const result = psdToRgb(1)
    expect(result).toEqual([255, 255, 255])
  })

  it('returns cyan-dominant values at 0.5 (signal range)', () => {
    const result = psdToRgb(0.5)
    expect(result[0]).toBeLessThanOrEqual(result[1])
    expect(result[2]).toBeLessThanOrEqual(result[1])
  })

  it('returns integers between 0 and 255', () => {
    for (let i = 0; i <= 10; i++) {
      const result = psdToRgb(i / 10)
      expect(Number.isInteger(result[0])).toBe(true)
      expect(Number.isInteger(result[1])).toBe(true)
      expect(Number.isInteger(result[2])).toBe(true)
      expect(result[0]).toBeGreaterThanOrEqual(0)
      expect(result[0]).toBeLessThanOrEqual(255)
      expect(result[1]).toBeGreaterThanOrEqual(0)
      expect(result[1]).toBeLessThanOrEqual(255)
      expect(result[2]).toBeGreaterThanOrEqual(0)
      expect(result[2]).toBeLessThanOrEqual(255)
    }
  })

  it('clamps input below 0 to valid range', () => {
    const result = psdToRgb(-0.5)
    expect(result).toEqual([3, 8, 16])
  })

  it('clamps input above 1 to valid range', () => {
    const result = psdToRgb(1.5)
    expect(result).toEqual([255, 255, 255])
  })

  it('returns amber at strong signal threshold (0.65)', () => {
    const result = psdToRgb(0.65)
    expect(result[0]).toBe(255)
    expect(result[1]).toBe(204)
    expect(result[2]).toBe(0)
  })

  it('returns dark blue at weak threshold (0.15)', () => {
    const result = psdToRgb(0.15)
    expect(result[0]).toBe(0)
    expect(result[1]).toBeGreaterThanOrEqual(48)
    expect(result[1]).toBeLessThanOrEqual(80)
  })
})

describe('normalisePsd', () => {
  it('returns 1.0 for maxDb value', () => {
    expect(normalisePsd(0, -80, 0)).toBe(1.0)
  })

  it('returns 0.0 for minDb value', () => {
    expect(normalisePsd(-80, -80, 0)).toBe(0.0)
  })

  it('clamps below minDb to 0.0', () => {
    expect(normalisePsd(-100, -80, 0)).toBe(0.0)
  })

  it('returns 0.5 for midpoint value', () => {
    expect(normalisePsd(-40, -80, 0)).toBe(0.5)
  })
})
