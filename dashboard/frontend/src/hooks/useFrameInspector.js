import { useState, useEffect } from 'react'

/**
 * Share raw-frame view, pinning and parsed data between the decode panels.
 * Parsed results are keyed by target hex, so an absent or changed target
 * immediately hides stale data; effect cleanup ignores superseded responses.
 * @param {Array} adsbRawLog Latest ADS-B raw frames, newest first.
 * @returns {Object} Frame inspector state and view/pinning setters.
 */
export default function useFrameInspector(adsbRawLog) {
  // UI-OVERHAUL (Change 6): RAW DECODE / FRAME INSPECTOR state now lives
  // in this hook so the two standalone column panels share it.
  // The /api/adsb/parse effect below previously lived in AdsbAircraftPanel.
  const [rawView, setRawView] = useState('hex')
  const [pinnedFrame, setPinnedFrame] = useState(null)
  const [parsedFrame, setParsedFrame] = useState(null)

  const targetHex = pinnedFrame ? pinnedFrame.raw_hex : adsbRawLog?.[0]?.raw_hex ?? null

  useEffect(() => {
    if (targetHex === null) return
    let active = true

    fetch(`/api/adsb/parse?hex=${targetHex}`)
      .then((r) => r.json())
      .then((data) => {
        if (active) setParsedFrame({ targetHex, data })
      })
      .catch(() => {
        if (active) setParsedFrame({ targetHex, data: null })
      })

    return () => { active = false }
  }, [targetHex])

  const frameData = targetHex !== null && parsedFrame?.targetHex === targetHex
    ? parsedFrame.data
    : null

  return { rawView, setRawView, pinnedFrame, setPinnedFrame, frameData }
}
