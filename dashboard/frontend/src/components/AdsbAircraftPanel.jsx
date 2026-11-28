import { useEffect, useState } from 'react'
import {
  formatAltitude,
  formatSpeed,
  formatTrack,
  formatBearing,
  formatDeltaR,
} from '../utils/aircraftFormat.js'

const MAX_AIRCRAFT = 30

// formatAltitude / formatSpeed / formatTrack / formatBearing /
// formatDeltaR now live in ../utils/aircraftFormat.js (Phase 51
// extraction, shared with AircraftDetailPanel) and are imported above.

function elapsedSeconds(receivedAt) {
  if (!receivedAt) return '—'
  return Math.floor((Date.now() - receivedAt) / 1000)
}

/**
 * ADS-B aircraft tracking panel.
 * Shows active aircraft in a table with previously-seen aircraft below.
 * When both lists are empty, shows a listening or not-tuned message based
 * on the currently tuned frequency. Lazily initialised clock state drives a
 * one-second re-render without reading the state value itself, keeping
 * elapsed-seconds readouts advancing without new aircraft data.
 *
 * @param {Object} adsbAircraft - Map of ICAO address -> aircraft state
 * @param {Array}  adsbAircraftHistory - Recently departed aircraft (ring buffer)
 * @param {number|null} focusedFreq - Currently tuned frequency in Hz
 */
export default function AdsbAircraftPanel({ adsbAircraft = {}, adsbAircraftHistory = [], focusedFreq }) {
  const [, setNow] = useState(() => Date.now())
  const isAdsbFreq = focusedFreq && (
    Math.abs(focusedFreq - 1_090_000_000) <= 2_000_000
  )

  // elapsedSeconds() reads Date.now() directly; this interval's re-render
  // advances both tables' seconds-ago text; the state value itself is not read.
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  const aircraftList = Object.values(adsbAircraft)
    .sort((a, b) => (b.receivedAt || 0) - (a.receivedAt || 0))
    .slice(0, MAX_AIRCRAFT)

  const activeIcaos = new Set(Object.keys(adsbAircraft))
  const previouslySeenList = adsbAircraftHistory
    .filter((ac) => !activeIcaos.has(ac.icao))
    .slice(0, 20)

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '8px' }}>
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: 12,
        color: 'var(--neon-cyan)',
        marginBottom: '8px',
      }}>
        ADS-B DECODE
        {aircraftList.length > 0 && (
          <span style={{
            marginLeft: '8px',
            padding: '1px 6px',
            borderRadius: '8px',
            background: 'var(--neon-cyan)',
            color: '#000',
            fontFamily: 'var(--font-data)',
            fontSize: 9,
          }}>
            {aircraftList.length}
          </span>
        )}
      </div>
      {aircraftList.length === 0 && previouslySeenList.length === 0 ? (
        <div style={{
          fontFamily: 'var(--font-data)',
          fontSize: 12,
          color: 'var(--text-dim)',
        }}>
          {isAdsbFreq
            ? 'Listening on 1090.000 MHz...'
            : 'Not tuned to ADS-B frequency'}
        </div>
      ) : (
        <>
          {aircraftList.length > 0 && (
            <table style={{
              width: '100%',
              fontFamily: 'var(--font-data)',
              fontSize: 12,
              color: 'var(--text)',
              borderCollapse: 'collapse',
            }}>
              <thead>
                <tr style={{ color: 'var(--neon-cyan)', borderBottom: '1px solid var(--border)' }}>
                  <th style={{ textAlign: 'left', padding: '2px 4px' }}>Callsign</th>
                  <th style={{ textAlign: 'left', padding: '2px 4px' }}>ICAO</th>
                  <th style={{ textAlign: 'left', padding: '2px 4px' }}>Alt (ft)</th>
                  <th style={{ textAlign: 'left', padding: '2px 4px' }}>Spd (kt)</th>
                  <th style={{ textAlign: 'left', padding: '2px 4px' }}>Track (°)</th>
                  <th style={{ textAlign: 'left', padding: '2px 4px' }}>Bearing (°)</th>
                  {/* BEARING rate from delta_r_deg_per_sec in °/s, not radar range rate Δr in nm/s (deltaRNmPerSec). */}
                  <th style={{ textAlign: 'left', padding: '2px 4px' }}>Brg Rate (°/s)</th>
                  <th style={{ textAlign: 'left', padding: '2px 4px' }}>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {aircraftList.map((ac) => {
                  const displayCallsign = ac.callsign || ac.icao
                  const callsignDim = !ac.callsign
                  return (
                    <tr key={ac.icao} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{
                        padding: '2px 4px',
                        whiteSpace: 'nowrap',
                        color: callsignDim ? 'var(--text-dim)' : 'var(--neon-cyan)',
                      }}>
                        {displayCallsign}
                      </td>
                      <td style={{ padding: '2px 4px', whiteSpace: 'nowrap', fontFamily: 'monospace' }}>
                        {ac.icao}
                      </td>
                      <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                        {formatAltitude(ac.altitude_ft)}
                      </td>
                      <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                        {formatSpeed(ac.groundspeed)}
                      </td>
                      <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                        {formatTrack(ac.track)}
                      </td>
                      <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                        {formatBearing(ac.bearing_deg)}
                      </td>
                      <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                        {formatDeltaR(ac.delta_r_deg_per_sec)}
                      </td>
                      <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                        {elapsedSeconds(ac.receivedAt)}s
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
          {previouslySeenList.length > 0 && (
            <div style={{ marginTop: '8px' }}>
              <div style={{
                fontFamily: 'var(--font-display)',
                fontSize: 9,
                color: 'var(--text-dim)',
                letterSpacing: '1px',
                marginBottom: '4px',
                borderTop: '1px solid var(--border)',
                paddingTop: '6px',
              }}>
                PREVIOUSLY SEEN ({previouslySeenList.length})
              </div>
              <table style={{
                width: '100%',
                fontFamily: 'var(--font-data)',
                fontSize: 10,
                color: 'var(--text-dim)',
                borderCollapse: 'collapse',
                opacity: 0.65,
              }}>
                <thead>
                  <tr style={{ color: 'var(--text-dim)', borderBottom: '1px solid var(--border)' }}>
                    <th style={{ textAlign: 'left', padding: '2px 4px' }}>Callsign</th>
                    <th style={{ textAlign: 'left', padding: '2px 4px' }}>ICAO</th>
                    <th style={{ textAlign: 'left', padding: '2px 4px' }}>Alt (ft)</th>
                    <th style={{ textAlign: 'left', padding: '2px 4px' }}>Spd (kt)</th>
                    <th style={{ textAlign: 'left', padding: '2px 4px' }}>Track (°)</th>
                    <th style={{ textAlign: 'left', padding: '2px 4px' }}>Bearing (°)</th>
                    <th style={{ textAlign: 'left', padding: '2px 4px' }}>Brg Rate (°/s)</th>
                    <th style={{ textAlign: 'left', padding: '2px 4px' }}>Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {previouslySeenList.map((ac) => {
                    const displayCallsign = ac.callsign || ac.icao
                    return (
                      <tr key={ac.icao} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                          {displayCallsign}
                        </td>
                        <td style={{ padding: '2px 4px', whiteSpace: 'nowrap', fontFamily: 'monospace' }}>
                          {ac.icao}
                        </td>
                        <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                          {formatAltitude(ac.altitude_ft)}
                        </td>
                        <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                          {formatSpeed(ac.groundspeed)}
                        </td>
                        <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                          {formatTrack(ac.track)}
                        </td>
                        <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                          {formatBearing(ac.bearing_deg)}
                        </td>
                        <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                          {formatDeltaR(ac.delta_r_deg_per_sec)}
                        </td>
                        <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                          {elapsedSeconds(ac.receivedAt)}s
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
