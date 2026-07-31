import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import React from 'react'

vi.mock('socket.io-client', () => ({
  io: vi.fn(),
}))

import { useSocket } from '../hooks/useSocket.js'
import { mergeAircraftRecord } from '../utils/mergeAircraftRecord.js'
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
      source: null,
      peak_power_db: null,
      peak_bin_power_db: null,
      snr_db: null,
      bandwidth_hz: null,
      spectral_flatness: null,
      chroma_distance: null,
      signal_threshold_db: null,
      snr_margin_db: null,
      novel: null,
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
      source: null,
      peak_power_db: null,
      peak_bin_power_db: null,
      snr_db: null,
      bandwidth_hz: null,
      spectral_flatness: null,
      chroma_distance: null,
      signal_threshold_db: null,
      snr_margin_db: null,
      novel: null,
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
      peak_bin_power_db: null,
      snr_db: null,
      bandwidth_hz: null,
      spectral_flatness: null,
      chroma_distance: null,
      signal_threshold_db: null,
      snr_margin_db: null,
      novel: null,
      source: null,
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
      peak_bin_power_db: -70.5,
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
      peak_bin_power_db: -70.5,
      snr_db: 8.4,
      bandwidth_hz: 0,
      spectral_flatness: 0.123,
      chroma_distance: 0.456,
      signal_threshold_db: null,
      snr_margin_db: null,
      novel: null,
      source: null,
    })
  })

  it('scan_result with source="decode" propagates to aiReasoning.source', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['scan_result'][0]

    act(() => {
      result.current.focusFrequency(1090000000)
    })

    act(() => {
      handler({
        center_freq_hz: 1090000000,
        signal_type: 'adsb',
        confidence: 'high',
        confidence_score: 1.0,
        au_legal_status: 'LEGAL RX',
        reasoning: 'Confirmed ADS-B decode',
        timestamp: '2026-07-14T12:00:00.000Z',
        source: 'decode',
      })
    })

    expect(result.current.aiReasoning.source).toBe('decode')
  })

  it('scan_result with source="fingerprint" propagates to aiReasoning.source', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['scan_result'][0]

    act(() => {
      result.current.focusFrequency(98000000)
    })

    act(() => {
      handler({
        center_freq_hz: 98000000,
        signal_type: 'fm_broadcast',
        confidence: 'high',
        confidence_score: 0.95,
        au_legal_status: 'LEGAL RX',
        reasoning: 'Strong FM carrier',
        timestamp: '2026-07-14T12:00:00.000Z',
        source: 'fingerprint',
        snr_db: 12.0,
        bandwidth_hz: 200000,
      })
    })

    expect(result.current.aiReasoning.source).toBe('fingerprint')
  })

  it('scan_result stores peak_bin_power_db in scanResults entry', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['scan_result'][0]

    const payload = {
      timestamp: '2026-06-03T12:00:00.000Z',
      center_freq_hz: 98000000,
      signal_type: 'fm_broadcast',
      confidence: 'high',
      confidence_score: 0.95,
      peak_power_db: -72.1,
      peak_bin_power_db: -65.0,
    }

    act(() => {
      handler(payload)
    })

    expect(result.current.scanResults[0].peak_bin_power_db).toBe(-65.0)
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

  it('scan_result propagates novel field into aiReasoning', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['scan_result'][0]

    act(() => {
      result.current.focusFrequency(98000000)
    })

    act(() => {
      handler({
        center_freq_hz: 98000000,
        signal_type: 'unknown_signal',
        confidence: 'low',
        confidence_score: 0.3,
        au_legal_status: 'verify_before_use',
        reasoning: 'Signal does not match known fingerprints',
        timestamp: '2026-06-03T12:00:00.000Z',
        novel: true,
      })
    })

    expect(result.current.aiReasoning.novel).toBe(true)
  })

  it('disconnects socket on unmount', () => {
    const { unmount } = renderHook(() => useSocket())
    unmount()
    expect(mockSocket.off).toHaveBeenCalled()
    expect(mockSocket.disconnect).toHaveBeenCalled()
  })

  it('system_stats event exposes device and unsupportedBands on the hook return', () => {
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['system_stats'][0]

    // Before any system_stats arrives, both default to safe values
    expect(result.current.device).toBeNull()
    expect(result.current.unsupportedBands).toEqual({})

    act(() => {
      handler({
        hackrf_status: 'CONNECTED',
        active_frequency_hz: 98000000,
        scan_count: 42,
        device: 'plutosdr',
        unsupported_bands: {
          fm_broadcast: "Below Pluto's 325 MHz tuning floor (98 MHz)",
          aviation: "Below Pluto's 325 MHz tuning floor (127 MHz)",
        },
      })
    })

    expect(result.current.device).toBe('plutosdr')
    expect(result.current.unsupportedBands).toEqual({
      fm_broadcast: "Below Pluto's 325 MHz tuning floor (98 MHz)",
      aviation: "Below Pluto's 325 MHz tuning floor (127 MHz)",
    })
  })

  it('system_stats event without device/unsupported_bands keys keeps null/{}-defaults', () => {
    // Legacy / older server payload (Phase 35 and earlier do not emit
    // these keys) — the hook must still default cleanly, not crash.
    const { result } = renderHook(() => useSocket())
    const handler = eventHandlers['system_stats'][0]

    act(() => {
      handler({
        hackrf_status: 'CONNECTED',
        active_frequency_hz: 98000000,
        scan_count: 42,
      })
    })

    expect(result.current.device).toBeNull()
    expect(result.current.unsupportedBands).toEqual({})
  })

  // ------------------------------------------------------------------
  // BUG-06 — field-preserving merge for adsb_aircraft
  // Mode S typecodes carry disjoint field sets (typecode 4 = callsign,
  // typecode 19 = velocity, typecodes 9-18 = position). The old wholesale
  // replace clobbered known fields with nulls on every partial frame.
  // ------------------------------------------------------------------
  describe('BUG-06 adsb_aircraft field-preserving merge', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    const FULL_FRAME = {
      icao: 'ABCDEF',
      callsign: 'JST681',
      altitude_ft: 37000,
      latitude: -34.5,
      longitude: 138.6,
      groundspeed: 450,
      track: 90,
      vertical_rate: 0,
      bearing_deg: 45,
      delta_r_deg_per_sec: 0.5,
      range_nm: 12.3,
      timestamp: '2026-07-31T10:00:00Z',
      raw_hex: '8D4840D6202CC371C32CE057A8CF',
    }

    it('adsb_aircraft with position fields followed by velocity-only frame preserves altitude/lat/lon', () => {
      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['adsb_aircraft'][0]

      act(() => {
        handler({
          icao: 'ABCDEF',
          callsign: null,
          altitude_ft: 37000,
          latitude: -34.5,
          longitude: 138.6,
          groundspeed: null,
          track: null,
          vertical_rate: null,
          timestamp: '2026-07-31T10:00:00Z',
          raw_hex: '8D4840D6202CC371C32CE057A8CF',
        })
      })
      act(() => {
        handler({
          icao: 'ABCDEF',
          callsign: null,
          altitude_ft: null,
          latitude: null,
          longitude: null,
          groundspeed: 450,
          track: 90,
          vertical_rate: -64,
          timestamp: '2026-07-31T10:00:01Z',
          raw_hex: '8D4840D6994001B8380B22A1B3E4',
        })
      })

      const ac = result.current.adsbAircraft['ABCDEF']
      expect(ac.altitude_ft).toBe(37000)
      expect(ac.latitude).toBe(-34.5)
      expect(ac.longitude).toBe(138.6)
      expect(ac.groundspeed).toBe(450)
      expect(ac.track).toBe(90)
      expect(ac.vertical_rate).toBe(-64)
    })

    it('adsb_aircraft with identification frame (callsign only) does not wipe previously-known altitude/groundspeed/track', () => {
      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['adsb_aircraft'][0]

      act(() => {
        handler({ ...FULL_FRAME, callsign: null })
      })
      act(() => {
        handler({
          icao: 'ABCDEF',
          callsign: 'JST681',
          altitude_ft: null,
          latitude: null,
          longitude: null,
          groundspeed: null,
          track: null,
          vertical_rate: null,
          timestamp: '2026-07-31T10:00:01Z',
          raw_hex: '8D4840D6202CC371C32CE057A8CF',
        })
      })

      const ac = result.current.adsbAircraft['ABCDEF']
      expect(ac.callsign).toBe('JST681')
      expect(ac.altitude_ft).toBe(37000)
      expect(ac.groundspeed).toBe(450)
      expect(ac.track).toBe(90)
    })

    it('adsb_aircraft non-null incoming value overwrites a stored value', () => {
      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['adsb_aircraft'][0]

      act(() => {
        handler({ ...FULL_FRAME })
      })
      act(() => {
        handler({ ...FULL_FRAME, altitude_ft: 36000, timestamp: '2026-07-31T10:00:02Z' })
      })

      expect(result.current.adsbAircraft['ABCDEF'].altitude_ft).toBe(36000)
    })

    it('adsb_aircraft with brand-new ICAO stores correctly with no prior record', () => {
      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['adsb_aircraft'][0]

      act(() => {
        handler({ ...FULL_FRAME })
      })

      const ac = result.current.adsbAircraft['ABCDEF']
      expect(ac).toBeDefined()
      expect(ac.icao).toBe('ABCDEF')
      expect(ac.callsign).toBe('JST681')
      expect(ac.altitude_ft).toBe(37000)
      expect(ac.receivedAt).toBeDefined()
    })

    it('adsb_aircraft receivedAt updates on a frame that carries no new field data', () => {
      vi.useFakeTimers()
      const t0 = new Date('2026-07-31T10:00:00Z').getTime()
      vi.setSystemTime(t0)

      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['adsb_aircraft'][0]

      act(() => {
        handler({ ...FULL_FRAME })
      })
      const firstReceivedAt = result.current.adsbAircraft['ABCDEF'].receivedAt
      expect(firstReceivedAt).toBe(t0)

      const t1 = t0 + 5000
      vi.setSystemTime(t1)
      act(() => {
        handler({
          icao: 'ABCDEF',
          callsign: null,
          altitude_ft: null,
          latitude: null,
          longitude: null,
          groundspeed: null,
          track: null,
          vertical_rate: null,
          timestamp: '2026-07-31T10:00:05Z',
          raw_hex: '8D4840D6202CC371C32CE057A8CF',
        })
      })

      const ac = result.current.adsbAircraft['ABCDEF']
      expect(ac.receivedAt).toBe(t1)
      expect(ac.receivedAt).toBeGreaterThan(firstReceivedAt)
      // Field data preserved despite the empty frame
      expect(ac.altitude_ft).toBe(37000)
      expect(ac.callsign).toBe('JST681')
    })

    it('adsb_aircraft 90-second cutoff still evicts a genuinely silent aircraft', () => {
      vi.useFakeTimers()
      const t0 = new Date('2026-07-31T10:00:00Z').getTime()
      vi.setSystemTime(t0)

      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['adsb_aircraft'][0]

      act(() => {
        handler({ ...FULL_FRAME, icao: 'SILENT' })
      })
      expect(result.current.adsbAircraft['SILENT']).toBeDefined()

      // 100 seconds later a different aircraft transmits — the cutoff
      // pass inside the same update must evict the silent one.
      vi.setSystemTime(t0 + 100000)
      act(() => {
        handler({ ...FULL_FRAME, icao: 'ACTIVE' })
      })

      expect(result.current.adsbAircraft['SILENT']).toBeUndefined()
      expect(result.current.adsbAircraft['ACTIVE']).toBeDefined()
    })

    it('adsb_aircraft bearing_deg / delta_r_deg_per_sec / range_nm survive a subsequent position-less frame', () => {
      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['adsb_aircraft'][0]

      act(() => {
        handler({ ...FULL_FRAME })
      })
      act(() => {
        handler({
          icao: 'ABCDEF',
          callsign: 'JST681',
          altitude_ft: null,
          latitude: null,
          longitude: null,
          groundspeed: null,
          track: null,
          vertical_rate: null,
          bearing_deg: null,
          delta_r_deg_per_sec: null,
          range_nm: null,
          timestamp: '2026-07-31T10:00:01Z',
          raw_hex: '8D4840D6202CC371C32CE057A8CF',
        })
      })

      const ac = result.current.adsbAircraft['ABCDEF']
      expect(ac.bearing_deg).toBe(45)
      expect(ac.delta_r_deg_per_sec).toBe(0.5)
      expect(ac.range_nm).toBe(12.3)
    })

    it('adsb_aircraft history entry also merges field-by-field (not just the active dict)', () => {
      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['adsb_aircraft'][0]

      act(() => {
        handler({ ...FULL_FRAME, callsign: null })
      })
      act(() => {
        handler({
          icao: 'ABCDEF',
          callsign: 'JST681',
          altitude_ft: null,
          latitude: null,
          longitude: null,
          groundspeed: null,
          track: null,
          vertical_rate: null,
          timestamp: '2026-07-31T10:00:01Z',
          raw_hex: '8D4840D6202CC371C32CE057A8CF',
        })
      })

      // One entry per ICAO, carrying the best-known merged snapshot.
      expect(result.current.adsbAircraftHistory.length).toBe(1)
      const hist = result.current.adsbAircraftHistory[0]
      expect(hist.icao).toBe('ABCDEF')
      expect(hist.callsign).toBe('JST681')
      expect(hist.altitude_ft).toBe(37000)
      expect(hist.latitude).toBe(-34.5)
      expect(hist.groundspeed).toBe(450)
      expect(hist.bearing_deg).toBe(45)
    })
  })

  // ------------------------------------------------------------------
  // BUG-06 — mergeAircraftRecord pure helper
  // ------------------------------------------------------------------
  describe('mergeAircraftRecord helper', () => {
    const NOW = 1753965600000

    it('mergeAircraftRecord: brand-new ICAO returns data with receivedAt = now', () => {
      const data = { icao: 'ABCDEF', callsign: 'JST681', altitude_ft: 37000 }
      const merged = mergeAircraftRecord(null, data, NOW)
      expect(merged.icao).toBe('ABCDEF')
      expect(merged.callsign).toBe('JST681')
      expect(merged.altitude_ft).toBe(37000)
      expect(merged.receivedAt).toBe(NOW)
    })

    it('mergeAircraftRecord: incoming non-null field overwrites prev', () => {
      const prev = { icao: 'ABCDEF', altitude_ft: 37000, receivedAt: NOW - 1000 }
      const data = { icao: 'ABCDEF', altitude_ft: 36000 }
      const merged = mergeAircraftRecord(prev, data, NOW)
      expect(merged.altitude_ft).toBe(36000)
    })

    it('mergeAircraftRecord: incoming null field preserves prev', () => {
      const prev = { icao: 'ABCDEF', altitude_ft: 37000, groundspeed: 450, receivedAt: NOW - 1000 }
      const data = { icao: 'ABCDEF', altitude_ft: null, groundspeed: null }
      const merged = mergeAircraftRecord(prev, data, NOW)
      expect(merged.altitude_ft).toBe(37000)
      expect(merged.groundspeed).toBe(450)
    })

    it('mergeAircraftRecord: prev keys not in data are preserved (e.g. bearing from a prior frame)', () => {
      const prev = { icao: 'ABCDEF', bearing_deg: 45, delta_r_deg_per_sec: 0.5, receivedAt: NOW - 1000 }
      const data = { icao: 'ABCDEF', groundspeed: 450 }
      const merged = mergeAircraftRecord(prev, data, NOW)
      expect(merged.bearing_deg).toBe(45)
      expect(merged.delta_r_deg_per_sec).toBe(0.5)
      expect(merged.groundspeed).toBe(450)
      expect(merged.receivedAt).toBe(NOW)
    })

    it('mergeAircraftRecord: returns a NEW object (not a reference to prev or data)', () => {
      const prev = { icao: 'ABCDEF', altitude_ft: 37000, receivedAt: NOW - 1000 }
      const data = { icao: 'ABCDEF', altitude_ft: 36000 }
      const merged = mergeAircraftRecord(prev, data, NOW)
      expect(merged).not.toBe(prev)
      expect(merged).not.toBe(data)
      // Inputs must not be mutated by the merge
      expect(prev.altitude_ft).toBe(37000)
      expect(data.receivedAt).toBeUndefined()
    })
  })
})
