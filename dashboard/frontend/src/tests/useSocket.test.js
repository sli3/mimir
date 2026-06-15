import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import React from 'react'

vi.mock('socket.io-client', () => ({
  io: vi.fn(),
}))

import { useSocket } from '../hooks/useSocket.js'
import { io } from 'socket.io-client'

describe('useSocket', () => {
  let mockSocket
  let eventHandlers

  beforeEach(() => {
    eventHandlers = {}
    mockSocket = {
      on: vi.fn((event, cb) => {
        if (!eventHandlers[event]) eventHandlers[event] = []
        eventHandlers[event].push(cb)
        return mockSocket
      }),
      off: vi.fn(),
      emit: vi.fn(),
      disconnect: vi.fn(),
    }
    io.mockReturnValue(mockSocket)
  })

  it('connects and returns initial state', () => {
    const { result } = renderHook(() => useSocket())
    expect(io).toHaveBeenCalled()
    expect(result.current.scanResults).toEqual([])
    expect(result.current.spectrumUpdates).toEqual([])
    expect(result.current.systemStats).toBeNull()
    expect(result.current.focusedFreq).toBe(98000000)
    expect(result.current.isConnected).toBe(false)
    expect(result.current.aiReasoning).toEqual({
      freq_hz: null,
      signal_type: null,
      confidence: null,
      confidence_score: null,
      au_legal_status: null,
      reasoning: null,
      timestamp: null,
      peak_power_db: null,
      snr_db: null,
      bandwidth_hz: null,
      spectral_flatness: null,
      chroma_distance: null,
    })
  })

  it('focusFrequency calls socket.emit with correct payload', () => {
    const { result } = renderHook(() => useSocket())
    act(() => {
      result.current.focusFrequency(98000000)
    })
    expect(mockSocket.emit).toHaveBeenCalledWith('set_focus_frequency', { freq_hz: 98000000 })
    expect(result.current.focusedFreq).toBe(98000000)
  })

  it('connect re-syncs set_focus_frequency when a frequency is focused', () => {
    const { result } = renderHook(() => useSocket())
    act(() => {
      result.current.focusFrequency(98000000)
    })
    mockSocket.emit.mockClear()
    act(() => {
      eventHandlers['connect'][0]()
    })
    expect(mockSocket.emit).toHaveBeenCalledWith('set_focus_frequency', { freq_hz: 98000000 })
  })

  it('scan_result event prepends to scanResults and caps at 200', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['scan_result'][0]

    act(() => {
      for (let i = 0; i < 250; i++) {
        handler({ timestamp: i, center_freq_hz: 98000000, label: 'FM', confidence_score: 0.9 })
      }
    })
    expect(result.current.scanResults.length).toBe(200)
    expect(result.current.scanResults[0].timestamp).toBe(249)
  })

  it('spectrum_update event prepends to spectrumUpdates', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['spectrum_update'][0]

    act(() => {
      handler({ center_freq_hz: 98000000, psd_db: [0.1, 0.2, 0.3] })
    })
    expect(result.current.spectrumUpdates.length).toBe(1)
    expect(result.current.spectrumUpdates[0].center_freq_hz).toBe(98000000)
    expect(result.current.spectrumUpdates[0].psd_db).toEqual([0.1, 0.2, 0.3])
    expect(result.current.spectrumUpdates[0].ts).toBeDefined()
  })

  it('system_stats event updates systemStats', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['system_stats'][0]

    act(() => {
      handler({ hackrf_status: 'CONNECTED', active_frequency_hz: 98000000, scan_count: 42 })
    })
    expect(result.current.systemStats).toEqual({ hackrf_status: 'CONNECTED', active_frequency_hz: 98000000, scan_count: 42 })
  })

  it('focusFrequency resets aiReasoning to initial state', () => {
    const { result } = renderHook(() => useSocket())
    act(() => {
      result.current.focusFrequency(98000000)
    })
    expect(result.current.aiReasoning).toEqual({
      freq_hz: null,
      signal_type: null,
      confidence: null,
      confidence_score: null,
      au_legal_status: null,
      reasoning: null,
      timestamp: null,
      peak_power_db: null,
      snr_db: null,
      bandwidth_hz: null,
      spectral_flatness: null,
      chroma_distance: null,
    })
  })

  it('scan_result matching focusedFreq updates aiReasoning', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['scan_result'][0]

    act(() => {
      result.current.focusFrequency(98000000)
    })

    const payload = {
      center_freq_hz: 98000000,
      signal_type: 'fm_broadcast',
      confidence: 'high',
      confidence_score: 0.95,
      au_legal_status: 'LEGAL RX',
      reasoning: 'Signal matches FM broadcast characteristics',
      timestamp: '2026-06-03T12:00:00.000Z',
    }

    act(() => {
      handler(payload)
    })

    expect(result.current.aiReasoning).toEqual({
      freq_hz: 98000000,
      signal_type: 'fm_broadcast',
      confidence: 'high',
      confidence_score: 0.95,
      au_legal_status: 'LEGAL RX',
      reasoning: 'Signal matches FM broadcast characteristics',
      timestamp: '2026-06-03T12:00:00.000Z',
      peak_power_db: null,
      snr_db: null,
      bandwidth_hz: null,
      spectral_flatness: null,
      chroma_distance: null,
    })
  })

  it('scan_result with fingerprint fields populates aiReasoning', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['scan_result'][0]

    act(() => {
      result.current.focusFrequency(98000000)
    })

    const payload = {
      center_freq_hz: 98000000,
      signal_type: 'fm_broadcast',
      confidence: 'high',
      confidence_score: 0.95,
      au_legal_status: 'LEGAL RX',
      reasoning: 'Strong FM carrier',
      timestamp: '2026-06-03T12:00:00.000Z',
      peak_power_db: -72.1,
      snr_db: 8.4,
      bandwidth_hz: 0,
      spectral_flatness: 0.123,
      chroma_distance: 0.456,
    }

    act(() => {
      handler(payload)
    })

    expect(result.current.aiReasoning).toEqual({
      freq_hz: 98000000,
      signal_type: 'fm_broadcast',
      confidence: 'high',
      confidence_score: 0.95,
      au_legal_status: 'LEGAL RX',
      reasoning: 'Strong FM carrier',
      timestamp: '2026-06-03T12:00:00.000Z',
      peak_power_db: -72.1,
      snr_db: 8.4,
      bandwidth_hz: 0,
      spectral_flatness: 0.123,
      chroma_distance: 0.456,
    })
  })

  it('scan_result NOT matching focusedFreq does NOT update aiReasoning', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['scan_result'][0]

    act(() => {
      result.current.focusFrequency(98000000)
    })

    const payload = {
      center_freq_hz: 1090000000,
      signal_type: 'adsb',
      confidence: 'high',
      confidence_score: 0.98,
      au_legal_status: 'LEGAL RX',
      reasoning: 'ADS-B signal detected',
      timestamp: '2026-06-03T12:00:00.000Z',
    }

    act(() => {
      handler(payload)
    })

    expect(result.current.aiReasoning.signal_type).toBeNull()
  })

  it('disconnects socket on unmount', () => {
    const { unmount } = renderHook(() => useSocket())
    unmount()
    expect(mockSocket.off).toHaveBeenCalled()
    expect(mockSocket.disconnect).toHaveBeenCalled()
  })
})
