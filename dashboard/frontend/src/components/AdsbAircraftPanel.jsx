import React, { useEffect, useState } from 'react'
import {
  formatAltitude,
  formatSpeed,
  formatTrack,
  formatBearing,
  formatDeltaR,
} from '../utils/aircraftFormat.js'

/**
 * Convert a hex string to space-separated 8-bit binary groups.
 * Example: "A3D4" -> "10100011 11010100"
 * Used in the RAW DECODE view's binary mode to show the Mode S
 * frame bits at a glance.
 * @param {string} hex - Hex string (e.g. "A3D4F0")
 * @returns {string} Space-separated 8-bit binary groups
 */
function hexToBin(hex) {
  return hex.match(/.{1,2}/g)
    .map((byte) => parseInt(byte, 16).toString(2).padStart(8, '0'))
    .join(' ')
}

/**
 * Format a hex string as uppercase space-separated byte pairs.
 * Example: "a3d4" -> "A3 D4"
 * Used in the RAW DECODE view's hex mode to make the Mode S frame
 * readable at a glance.
 * @param {string} hex - Hex string (e.g. "A3D4F0")
 * @returns {string} Uppercase space-separated byte pairs
 */
function hexToSpaced(hex) {
  return hex.match(/.{1,2}/g).join(' ').toUpperCase()
}

const MAX_AIRCRAFT = 30

// formatAltitude / formatSpeed / formatTrack / formatBearing /
// formatDeltaR now live in ../utils/aircraftFormat.js (Phase 51
// extraction, shared with AircraftDetailPanel) and are imported above.

function elapsedSeconds(receivedAt) {
  if (!receivedAt) return '—'
  return Math.floor((Date.now() - receivedAt) / 1000)
}

/**
 * ADS-B aircraft tracking panel with raw decode view and frame inspector.
 * Shows active aircraft in a table, previously-seen aircraft below, and a
 * two-column layout when tuned to 1090 MHz:
 *   - Left: RAW DECODE view showing recent Mode S frames (hex/binary toggle)
 *   - Right: FRAME INSPECTOR showing parsed frame data from /api/adsb/parse
 *
 * @param {Object} adsbAircraft - Map of ICAO address -> aircraft state
 * @param {Array}  adsbAircraftHistory - Recently departed aircraft (ring buffer)
 * @param {number|null} focusedFreq - Currently tuned frequency in Hz
 * @param {Array}  adsbRawLog - Recent raw Mode S frames {icao, raw_hex}
 * @param {string|null} pinnedFrame - Hex string of currently pinned frame, or null
 * @param {Object|null} frameData - Parsed frame data from /api/adsb/parse, or null
 * @param {Function} setPinnedFrame - Function to set pinned frame state
 * @param {Function} setFrameData - Function to set frame data state
 * @param {string} rawView - Current view mode ('hex' or 'bin')
 * @param {Function} setRawView - Function to set raw view mode
 */
export default function AdsbAircraftPanel({ adsbAircraft = {}, adsbAircraftHistory = [], focusedFreq, adsbRawLog = [] }) {
  const [now, setNow] = useState(Date.now())
  const [rawView, setRawView] = useState('hex')
  const [pinnedFrame, setPinnedFrame] = useState(null)
  const [frameData, setFrameData] = useState(null)
  const isAdsbFreq = focusedFreq && (
    Math.abs(focusedFreq - 1_090_000_000) <= 2_000_000
  )

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  const targetHex = pinnedFrame ? pinnedFrame.raw_hex : adsbRawLog[0]?.raw_hex ?? null

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
                  <th style={{ textAlign: 'left', padding: '2px 4px' }}>Δr (°/s)</th>
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
                    <th style={{ textAlign: 'left', padding: '2px 4px' }}>Δr (°/s)</th>
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
