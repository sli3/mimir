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
}

export function useSocket() {
  const [scanResults, setScanResults] = useState([])
  const [spectrumUpdates, setSpectrumUpdates] = useState([])
  const [systemStats, setSystemStats] = useState(null)
  const [focusedFreq, setFocusedFreq] = useState(null)
  const [isConnected, setIsConnected] = useState(false)
  const [aiReasoning, setAiReasoning] = useState(INITIAL_AI_REASONING)
  const socketRef = useRef(null)
  const psdMapRef = useRef({})
  const focusedFreqRef = useRef(null)

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
          confidence_score: data.confidence_score || null,
          au_legal_status: data.au_legal_status || null,
          reasoning: data.reasoning || null,
          timestamp: data.timestamp || null,
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

    return () => {
      socket.off('connect')
      socket.off('disconnect')
      socket.off('scan_result')
      socket.off('spectrum_update')
      socket.off('system_stats')
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
  }
}
