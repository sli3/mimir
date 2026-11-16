import { useState, useEffect } from 'react'

/**
 * Share raw-frame view, pinning and parsed data between the decode panels.
 * @param {Array} adsbRawLog Latest ADS-B raw frames, newest first.
 * @returns {Object} Frame inspector state and view/pinning setters.
 */
export default function useFrameInspector(adsbRawLog) {
  // UI-OVERHAUL (Change 6): RAW DECODE / FRAME INSPECTOR state now lives
  // in this hook so the two standalone column panels share it.
  // The /api/adsb/parse effect below previously lived in AdsbAircraftPanel.
  const [rawView, setRawView] = useState('hex')
  const [pinnedFrame, setPinnedFrame] = useState(null)
  const [frameData, setFrameData] = useState(null)

  const targetHex = pinnedFrame ? pinnedFrame.raw_hex : adsbRawLog?.[0]?.raw_hex ?? null

  useEffect(() => {
    if (targetHex === null) {
      setFrameData(null)
      return
    }

    fetch(`/api/adsb/parse?hex=${targetHex}`)
      .then((r) => r.json())
      .then(setFrameData)
      .catch(() => setFrameData(null))
  }, [targetHex])

  return { rawView, setRawView, pinnedFrame, setPinnedFrame, frameData }
}
