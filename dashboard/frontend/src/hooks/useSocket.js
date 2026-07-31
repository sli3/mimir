import { useEffect, useState, useRef, useCallback } from 'react'
import { io } from 'socket.io-client'
import { mergeAircraftRecord } from '../utils/mergeAircraftRecord.js'

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:5000'

/** Initial state for the AI reasoning slot. Every field is null at startup
 *  and is populated from `scan_result` events by the LLM pipeline or the
 *  decoder-driven path (Phase 32). The new ``source`` field indicates which
 *  path produced the entry: ``"fingerprint"`` for LLM-classified scans or
 *  ``"decode"`` for confirmed ADS-B decodes.
 *  TODO(tech-debt TD-45-5): Burst-detection fields (burst_ratio_db,
 *  expected_noise_ratio_db, burst_excess_db, is_burst) are omitted here.
 *  This is benign because the AI Reasoning panel does not render the [PEAK]
 *  tag — only SignalHistoryLog does, and it reads directly from scanResults.
 *  @type {{ [key: string]: null }} */
const INITIAL_AI_REASONING = {
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
}

export function useSocket() {
  const [scanResults, setScanResults] = useState([])
  const [spectrumUpdates, setSpectrumUpdates] = useState([])
  const [systemStats, setSystemStats] = useState(null)
  const [focusedFreq, setFocusedFreq] = useState(98000000)
  const [isConnected, setIsConnected] = useState(false)
  const [aiReasoning, setAiReasoning] = useState(INITIAL_AI_REASONING)
  const [acarsMessages, setAcarsMessages] = useState([])
  const [aisMessages, setAisMessages] = useState([])
  const [adsbAircraft, setAdsbAircraft] = useState({})
  const [adsbAircraftHistory, setAdsbAircraftHistory] = useState([])
  const [adsbRawLog, setAdsbRawLog] = useState([])
  // acarsRawLog — ring buffer (max 50 entries) of ACARS raw decode text.
  // Each entry: { registration, raw, timestamp }. Populated from the
  // acars_message event's "raw" field. Rendered by AcarsMessagePanel's
  // RAW DECODE section. Wraps via slice(0, 50).
  const [acarsRawLog, setAcarsRawLog] = useState([])
  // aisRawLog — ring buffer (max 50 entries) of AIS raw NMEA sentences.
  // Each entry: { mmsi, raw, timestamp }. Populated from the ais_message
  // event's "raw" field. Rendered by AisVesselPanel's RAW DECODE section.
  // Wraps via slice(0, 50).
  const [aisRawLog, setAisRawLog] = useState([])
  const socketRef = useRef(null)
  const psdMapRef = useRef({})
  const focusedFreqRef = useRef(98000000)

  useEffect(() => {
    const socket = io(SOCKET_URL)
    socketRef.current = socket

    socket.on('connect', () => {
      setIsConnected(true)
      if (focusedFreqRef.current !== null) {
        socket.emit('set_focus_frequency', { freq_hz: focusedFreqRef.current })
      }
    })
    socket.on('disconnect', () => setIsConnected(false))

    socket.on('scan_result', (data) => {
      setScanResults((prev) => {
        const next = [{ ...data }, ...prev]
        return next.slice(0, 200)
      })
      if (data.center_freq_hz === focusedFreqRef.current) {
        // TODO(tech-debt TD-45-5): Burst-detection fields are omitted from this
        // mapper. Benign because the AI Reasoning panel does not render [PEAK] —
        // SignalHistoryLog reads is_burst directly from scanResults instead.
        setAiReasoning({
          freq_hz: data.center_freq_hz,
          signal_type: data.signal_type || null,
          confidence: data.confidence || null,
          confidence_score: data.confidence_score ?? null,   // ?? not || — 0 is a valid confidence score
          au_legal_status: data.au_legal_status || null,
          reasoning: data.reasoning || null,
          timestamp: data.timestamp || null,
          source: data.source ?? null,
          peak_power_db: data.peak_power_db ?? null,
          peak_bin_power_db: data.peak_bin_power_db ?? null,
          snr_db: data.snr_db ?? null,
          bandwidth_hz: data.bandwidth_hz ?? null,
          spectral_flatness: data.spectral_flatness ?? null,
          chroma_distance: data.chroma_distance ?? null,
          signal_threshold_db: data.signal_threshold_db ?? null,
          snr_margin_db: data.snr_margin_db ?? null,
          novel: data.novel ?? null,
        })
      }
    })

    socket.on('spectrum_update', (data) => {
      const entry = {
        center_freq_hz: data.center_freq_hz,
        psd_db: data.psd_db,
        ts: Date.now(),
      }
      psdMapRef.current[data.center_freq_hz] = data.psd_db
      setSpectrumUpdates((prev) => {
        const next = [entry, ...prev]
        return next.slice(0, 50)
      })
    })

    socket.on('system_stats', (data) => {
      setSystemStats(data)
    })

    socket.on('acars_message', (data) => {
      setAcarsMessages((prev) => {
        const next = [data, ...prev]
        return next.slice(0, 20)
      })
      setAcarsRawLog((prev) => {
        if (!data.raw) return prev
        const entry = {
          registration: data.registration || '---',
          raw: data.raw,
          timestamp: data.timestamp,
        }
        return [entry, ...prev].slice(0, 50)
      })
    })

    socket.on('ais_message', (data) => {
      setAisMessages((prev) => {
        const next = [data, ...prev]
        return next.slice(0, 20)
      })
      setAisRawLog((prev) => {
        if (!data.raw) return prev
        const entry = {
          mmsi: data.mmsi || '---',
          raw: data.raw,
          timestamp: data.timestamp,
        }
        return [entry, ...prev].slice(0, 50)
      })
    })

    socket.on('adsb_aircraft', (data) => {
      const now = Date.now()
      setAdsbAircraft((prev) => {
        // BUG-06: merge field-by-field instead of wholesale replace.
        // Mode S typecodes carry disjoint field sets (callsign-only,
        // velocity-only, position-only), so a partial frame must not
        // clobber previously-known fields with nulls. receivedAt always
        // updates so the 90-second cutoff below still tracks liveness.
        const merged = mergeAircraftRecord(prev[data.icao] || null, data, now)
        const updated = { ...prev, [data.icao]: merged }
        const cutoff = now - 90000
        return Object.fromEntries(
          Object.entries(updated).filter(([, v]) => v.receivedAt > cutoff)
        )
      })
      setAdsbAircraftHistory((prev) => {
        // BUG-06: the history is a most-recent-per-ICAO snapshot ring
        // buffer (consumed as previouslySeenList in AdsbAircraftPanel),
        // so its entries need the same field-preserving merge — the user
        // wants the best-known snapshot of a dropped aircraft, not the
        // partial last frame it happened to send.
        const existing = prev.find((ac) => ac.icao === data.icao) || null
        const merged = mergeAircraftRecord(existing, data, now)
        const filtered = prev.filter((ac) => ac.icao !== data.icao)
        return [merged, ...filtered].slice(0, 50)
      })
      setAdsbRawLog((prev) => {
        if (!data.raw_hex) return prev
        const entry = { icao: data.icao, raw_hex: data.raw_hex, timestamp: data.timestamp }
        return [entry, ...prev].slice(0, 50)
      })
    })

    return () => {
      socket.off('connect')
      socket.off('disconnect')
      socket.off('scan_result')
      socket.off('spectrum_update')
      socket.off('system_stats')
      socket.off('acars_message')
      socket.off('ais_message')
      socket.off('adsb_aircraft')
      socket.disconnect()
    }
  }, [])

  const focusFrequency = useCallback((freqHz) => {
    setFocusedFreq(freqHz)
    focusedFreqRef.current = freqHz
    setAiReasoning(INITIAL_AI_REASONING)
    const socket = socketRef.current
    if (socket) {
      socket.emit('set_focus_frequency', { freq_hz: freqHz })
    }
  }, [])

  const getPsdDb = useCallback((freqHz) => {
    return psdMapRef.current[freqHz] || null
  }, [])

  // Phase 38 — device-aware band UI. Both come from the same system_stats
  // event that already populates systemStats. Defaults are chosen so
  // consumers can read these before the first system_stats event arrives
  // without a null-check on the structure itself.
  // - device: string|null — null until first system_stats arrives. The
  //   dashboard currently uses the side panel for status, not this hook
  //   value, so this is mostly for the band greying logic.
  // - unsupportedBands: object — empty {} for HackRF and pre-first-stats
  //   (this empty case is the "zero visual change" guarantee documented
  //   in Phase 38). Keys are band_key strings (e.g. "fm_broadcast"),
  //   values are reason strings (e.g. "Below Pluto's 325 MHz tuning
  //   floor (98 MHz)").
  const device = systemStats?.device ?? null
  const unsupportedBands = systemStats?.unsupported_bands ?? {}

  return {
    scanResults,
    spectrumUpdates,
    systemStats,
    device,
    unsupportedBands,
    focusedFreq,
    focusFrequency,
    getPsdDb,
    isConnected,
    aiReasoning,
    acarsMessages,
    aisMessages,
    aisVessels: aisMessages,
    adsbAircraft,
    adsbAircraftHistory,
    adsbRawLog,
    acarsRawLog,
    aisRawLog,
  }
}
