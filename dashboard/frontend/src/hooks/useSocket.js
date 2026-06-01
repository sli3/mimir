import { useEffect, useState, useRef, useCallback } from 'react'
import { io } from 'socket.io-client'

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:5000'

export function useSocket() {
  const [scanResults, setScanResults] = useState([])
  const [spectrumUpdates, setSpectrumUpdates] = useState([])
  const [systemStats, setSystemStats] = useState(null)
  const [focusedFreq, setFocusedFreq] = useState(null)
  const [isConnected, setIsConnected] = useState(false)
  const socketRef = useRef(null)
  const psdMapRef = useRef({})

  useEffect(() => {
    const socket = io(SOCKET_URL)
    socketRef.current = socket

    socket.on('connect', () => setIsConnected(true))
    socket.on('disconnect', () => setIsConnected(false))

    socket.on('scan_result', (data) => {
      setScanResults((prev) => {
        const next = [{ ...data }, ...prev]
        return next.slice(0, 200)
      })
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
    const socket = socketRef.current
    if (socket) {
      socket.emit('focus_frequency', { frequency_hz: freqHz })
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
  }
}
