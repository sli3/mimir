import { useEffect, useState, useRef } from 'react'
import { io } from 'socket.io-client'

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:5000'

export function useSocket() {
  const [scanResults, setScanResults] = useState([])
  const [focusedFreq, setFocusedFreq] = useState(null)
  const [spectrumData, setSpectrumData] = useState({})
  const socketRef = useRef(null)

  useEffect(() => {
    const socket = io(SOCKET_URL)
    socketRef.current = socket

    socket.on('scan_result', (data) => {
      setScanResults((prev) => [...prev, {
        timestamp: data.timestamp,
        center_freq_hz: data.center_freq_hz,
        signal_type: data.signal_type,
        confidence: data.confidence,
        confidence_score: data.confidence_score,
        novel: data.novel,
        au_legal_status: data.au_legal_status,
        reasoning: data.reasoning,
      }])
    })

    socket.on('spectrum_update', (data) => {
      setSpectrumData((prev) => ({
        ...prev,
        [data.center_freq_hz]: data.psd_db,
      }))
    })

    return () => {
      socket.off('scan_result')
      socket.off('spectrum_update')
      socket.disconnect()
    }
  }, [])

  function focusFrequency(freqHz) {
    setFocusedFreq(freqHz)
  }

  function getPsdDb(freqHz) {
    return spectrumData[freqHz] || null
  }

  return { scanResults, focusedFreq, focusFrequency, getPsdDb }
}
