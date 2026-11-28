import { useEffect, useMemo, useRef, useState } from 'react'
import { useSocket } from '../hooks/useSocket.js'
import HeaderBar from '../components/HeaderBar.jsx'
import RadarScopePanel from '../components/RadarScopePanel.jsx'
import AircraftDetailPanel from '../components/AircraftDetailPanel.jsx'
import PathPredictionPanel from '../components/PathPredictionPanel.jsx'
import { isValidContact, isAdsbFrequency } from '../components/radar/projection.js'
import './RadarPage.css'

// Sole source of truth for max displayed range. Passed down to
// RadarScopePanel explicitly (Phase 50) rather than relying on the two
// components' defaults happening to agree.
const MAX_RANGE_NM = 40

/**
 * Standalone /radar page (UI-OVERHAUL Change 7a).
 *
 * Hosts the existing RadarScopePanel on its own full-viewport page,
 * mirroring how /vectordb hosts VectorSpacePage. The Flask backend
 * serves index.html at /radar; main.jsx passes window.location.pathname
 * to AppRouter.jsx, which mounts this page for /radar instead of the main
 * dashboard App.
 *
 * Shared navigation sits above this page's title, contact count and
 * range readout. RadarScopePanel no longer renders its own
 * internal header (Phase 50 dedup fix, was TD-49-6: two independent
 * computations of the same contact count could silently disagree).
 * Both this page's contactCount and RadarScopePanel's contacts filter
 * now call the same isValidContact() function from projection.js, so
 * there is exactly one place the "valid, in-range contact" rule lives.
 * The shared isAdsbFrequency() gate keeps the count at zero off frequency.
 *
 * Passive receive display only — no TX capability.
 */
export default function RadarPage() {
  const socket = useSocket({ skipInitialRetune: true })
  const { adsbAircraft, systemStats } = socket

  // Selected aircraft (Phase 51): clicking a scope blip or a row in
  // the detail panel list sets this; both children receive it so the
  // amber scope ring, the highlighted list row, and the pinned detail
  // card always refer to the same aircraft.
  const [selectedIcao, setSelectedIcao] = useState(null)

  // Phase 54: deselect toggle lives here at the state-owner level, not
  // inside either child panel. Clicking an already-selected row (list or
  // scope blip) clears the selection; both children receive this same
  // callback so the behaviour is consistent.
  const handleSelectAircraft = (icao) => {
    setSelectedIcao((prev) => (prev === icao ? null : icao))
  }

  // Phase 52: trailsRef lifted out of RadarScopePanel so the new
  // PathPredictionPanel can read the same history. Single writer
  // (RadarScopePanel's contacts useMemo), read-only consumer here
  // and in PathPredictionPanel. The Map itself is intentionally
  // mutable in place — radar history is a stream, not React state.
  const trailsRef = useRef(new Map())

  // Read the actual SDR focused frequency from system_stats (not from the
  // useSocket default of 98 MHz, which is only correct for the main dashboard).
  const effectiveFocusedFreq = systemStats?.active_frequency_hz ?? null

  useEffect(() => {
    document.body.classList.add('radar-page')
    return () => document.body.classList.remove('radar-page')
  }, [])

  // Header count uses the scope's shared frequency gate and contact rule.
  // Retained aircraft data must not produce a count while tuned elsewhere.
  const contactCount = useMemo(() => (
    !isAdsbFrequency(effectiveFocusedFreq) ? 0 : Object.values(adsbAircraft || {})
      .filter((ac) => isValidContact(ac, MAX_RANGE_NM))
      .length
  ), [adsbAircraft, effectiveFocusedFreq])

  return (
    <div className="radar-shell">
      <HeaderBar current="radar" />
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
        <RadarScopePanel
          adsbAircraft={adsbAircraft}
          focusedFreq={effectiveFocusedFreq}
          maxRangeNm={MAX_RANGE_NM}
          selectedIcao={selectedIcao}
          onSelectAircraft={handleSelectAircraft}
          trailsRef={trailsRef}
        />
        <AircraftDetailPanel
          adsbAircraft={adsbAircraft}
          maxRangeNm={MAX_RANGE_NM}
          selectedIcao={selectedIcao}
          onSelectAircraft={handleSelectAircraft}
        />
      </div>
      <PathPredictionPanel
        adsbAircraft={adsbAircraft}
        selectedIcao={selectedIcao}
        trailsRef={trailsRef}
        maxRangeNm={MAX_RANGE_NM}
      />
    </div>
  )
}
