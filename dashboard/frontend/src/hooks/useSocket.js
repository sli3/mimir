import { useEffect, useState, useRef, useCallback } from 'react'
import { io } from 'socket.io-client'

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:5000'

const INITIAL_AI_REASONING = {
  freq_hz: null,
  signal_type: null,
  confidence: null,
  confidence_score: null,
  au_legal_status: null,
  reasoning: null,
  timestamp: null,
  peak_power_db: null,
  peak_bin_power_db: null,
  snr_db: null,
  bandwidth_hz: null,
  spectral_flatness: null,
  chroma_distance: null,
  signal_threshold_db: null,
  snr_margin_db: null,
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
        setAiReasoning({
          freq_hz: data.center_freq_hz,
          signal_type: data.signal_type || null,
          confidence: data.confidence || null,
          confidence_score: data.confidence_score ?? null,   // ?? not || — 0 is a valid confidence score
          au_legal_status: data.au_legal_status || null,
          reasoning: data.reasoning || null,
          timestamp: data.timestamp || null,
          peak_power_db: data.peak_power_db ?? null,
          peak_bin_power_db: data.peak_bin_power_db ?? null,
          snr_db: data.snr_db ?? null,
          bandwidth_hz: data.bandwidth_hz ?? null,
          spectral_flatness: data.spectral_flatness ?? null,
          chroma_distance: data.chroma_distance ?? null,
          signal_threshold_db: data.signal_threshold_db ?? null,
          snr_margin_db: data.snr_margin_db ?? null,
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
    })

    socket.on('ais_message', (data) => {
      setAisMessages((prev) => {
        const next = [data, ...prev]
        return next.slice(0, 20)
      })
    })

    socket.on('adsb_aircraft', (data) => {
      setAdsbAircraft((prev) => {
        const now = Date.now()
        const updated = { ...prev, [data.icao]: { ...data, receivedAt: now } }
        const cutoff = now - 90000
        return Object.fromEntries(
          Object.entries(updated).filter(([, v]) => v.receivedAt > cutoff)
        )
      })
      setAdsbAircraftHistory((prev) => {
        const entry = { ...data, receivedAt: Date.now() }
        const filtered = prev.filter((ac) => ac.icao !== data.icao)
        return [entry, ...filtered].slice(0, 50)
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

  return {
    scanResults,
    spectrumUpdates,
    systemStats,
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
  }
}
