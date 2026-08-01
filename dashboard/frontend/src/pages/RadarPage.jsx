import React, { useEffect, useMemo } from 'react'
import { useSocket } from '../hooks/useSocket.js'
import RadarScopePanel from '../components/RadarScopePanel.jsx'
import { isWithinRange } from '../components/radar/projection.js'
import './RadarPage.css'

// Mirrors RadarScopePanel's default maxRangeNm so the page header's
// contact count and range readout agree with the scope's own header.
const MAX_RANGE_NM = 40

/**
 * Standalone /radar page (UI-OVERHAUL Change 7a).
 *
 * Hosts the existing RadarScopePanel (unchanged) on its own full-viewport
 * page, mirroring how /vectordb hosts VectorSpacePage. The Flask backend
 * serves index.html at /radar; main.jsx inspects window.location.pathname
 * and mounts this page instead of the main dashboard App.
 *
 * Passive receive display only — no TX capability.
 */
export default function RadarPage() {
  const socket = useSocket({ skipInitialRetune: true })
  const { adsbAircraft, systemStats } = socket

  // Read the actual SDR focused frequency from system_stats (not from the
  // useSocket default of 98 MHz, which is only correct for the main dashboard).
  const effectiveFocusedFreq = systemStats?.active_frequency_hz ?? null

  useEffect(() => {
    document.body.classList.add('radar-page')
    return () => document.body.classList.remove('radar-page')
  }, [])

  // Contact count for the page header, computed with the same guard and
  // range filter RadarScopePanel applies before projecting blips, so the
  // header readout matches what the scope actually shows.
  const contactCount = useMemo(() => (
    Object.values(adsbAircraft || {})
      .filter((ac) => {
        if (ac.bearing_deg === null || ac.bearing_deg === undefined) return false
        if (Number.isNaN(ac.bearing_deg)) return false
        return isWithinRange(ac.range_nm, MAX_RANGE_NM)
      })
      .length
  ), [adsbAircraft])

  return (
    <div className="radar-shell">
      <header className="radar-header">
        <div className="radar-header-title">
          <h1>RADAR SCOPE</h1>
          <span className="radar-header-subtitle">
            Passive ADS-B PPI display // 1090.000 MHz
          </span>
        </div>
        <div className="radar-header-stats">
          <span className="radar-header-stat">
            {contactCount} CONTACTS · {MAX_RANGE_NM}NM
          </span>
        </div>
      </header>
      <div className="radar-scope-container">
        <RadarScopePanel adsbAircraft={adsbAircraft} focusedFreq={effectiveFocusedFreq} />
      </div>
    </div>
  )
}
