import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import useWaterfallMarkers from '../hooks/useWaterfallMarkers.js'

describe('useWaterfallMarkers', () => {
  it('addCaptureMarker adds one marker with type=capture, given freqHz, rowOffset=0, and a numeric id', () => {
    const { result } = renderHook(() => useWaterfallMarkers())
    act(() => result.current.addCaptureMarker(98000000))
    expect(result.current.markers).toHaveLength(1)
    expect(result.current.markers[0].type).toBe('capture')
    expect(result.current.markers[0].freqHz).toBe(98000000)
    expect(result.current.markers[0].rowOffset).toBe(0)
    expect(typeof result.current.markers[0].id).toBe('number')
  })

  it('addRecordStartMarker and addRecordStopMarker each create one marker, both at the same freq', () => {
    const { result } = renderHook(() => useWaterfallMarkers())
    act(() => {
      result.current.addRecordStartMarker(129125000)
      result.current.addRecordStopMarker(129125000)
    })
    expect(result.current.markers).toHaveLength(2)
    const types = result.current.markers.map((m) => m.type).sort()
    expect(types).toEqual(['record_start', 'record_stop'])
    for (const m of result.current.markers) {
      expect(m.freqHz).toBe(129125000)
    }
  })

  it('tickAndPrune increments rowOffset for matching-freq markers and leaves other-freq markers untouched', () => {
    const { result } = renderHook(() => useWaterfallMarkers())
    act(() => {
      result.current.addCaptureMarker(98000000)
      result.current.addCaptureMarker(129125000)
    })
    act(() => result.current.tickAndPrune(98000000, 100))
    const freq1 = result.current.markers.find((m) => m.freqHz === 98000000)
    const freq2 = result.current.markers.find((m) => m.freqHz === 129125000)
    expect(freq1.rowOffset).toBe(1)
    expect(freq2.rowOffset).toBe(0)
  })

  it('tickAndPrune removes a marker once rowOffset reaches canvas height (no unbounded growth)', () => {
    const { result } = renderHook(() => useWaterfallMarkers())
    act(() => result.current.addCaptureMarker(98000000))
    act(() => result.current.tickAndPrune(98000000, 5))
    expect(result.current.markers[0].rowOffset).toBe(1)
    act(() => result.current.tickAndPrune(98000000, 5))
    act(() => result.current.tickAndPrune(98000000, 5))
    act(() => result.current.tickAndPrune(98000000, 5))
    act(() => result.current.tickAndPrune(98000000, 5))
    expect(result.current.markers).toHaveLength(0)
  })

  it('addCaptureMarker with null or undefined freqHz is a no-op', () => {
    const { result } = renderHook(() => useWaterfallMarkers())
    act(() => result.current.addCaptureMarker(null))
    act(() => result.current.addCaptureMarker(undefined))
    expect(result.current.markers).toHaveLength(0)
  })

  it('multiple markers of the same type at the same freq all coexist with distinct ids', () => {
    const { result } = renderHook(() => useWaterfallMarkers())
    act(() => {
      result.current.addCaptureMarker(98000000)
      result.current.addCaptureMarker(98000000)
      result.current.addCaptureMarker(98000000)
    })
    expect(result.current.markers).toHaveLength(3)
    const ids = result.current.markers.map((m) => m.id)
    expect(new Set(ids).size).toBe(3)
    for (const m of result.current.markers) {
      expect(m.type).toBe('capture')
      expect(m.freqHz).toBe(98000000)
      expect(m.rowOffset).toBe(0)
    }
  })

  it('captures createdAt at add time and preserves it across ticks', () => {
    const { result } = renderHook(() => useWaterfallMarkers())
    const before = Date.now()
    act(() => result.current.addCaptureMarker(98000000))
    const after = Date.now()
    const createdAt = result.current.markers[0].createdAt
    expect(typeof createdAt).toBe('number')
    expect(createdAt).toBeGreaterThanOrEqual(before)
    expect(createdAt).toBeLessThanOrEqual(after)
    // Tick a few times — createdAt must NOT change.
    act(() => result.current.tickAndPrune(98000000, 100))
    act(() => result.current.tickAndPrune(98000000, 100))
    act(() => result.current.tickAndPrune(98000000, 100))
    expect(result.current.markers[0].createdAt).toBe(createdAt)
  })
})