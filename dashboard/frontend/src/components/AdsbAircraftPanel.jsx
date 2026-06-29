import React, { useEffect, useState } from 'react'

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

function formatAltitude(value) {
  if (value === null || value === undefined || value === '---') return '—'
  return Number(value).toLocaleString()
}

function formatSpeed(value) {
  if (value === null || value === undefined || value === '---') return '—'
  return Math.round(Number(value)).toString()
}

function formatTrack(value) {
  if (value === null || value === undefined || value === '---') return '—'
  const deg = Math.round(Number(value)) % 360
  return `${String(deg).padStart(3, '0')}°`
}

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
      {isAdsbFreq && (
        <div style={{ marginTop: '8px', borderTop: '1px solid var(--border)', paddingTop: '6px', display: 'flex', flexDirection: 'row', gap: '8px' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center',
                          justifyContent: 'space-between', marginBottom: '4px' }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 12,
                            color: 'var(--neon-cyan)', letterSpacing: '1px' }}>
                RAW DECODE
              </div>
              <div style={{ display: 'flex', flexDirection: 'row', gap: '0px' }}>
                {['hex', 'bin'].map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setRawView(mode)}
                    style={{
                      fontFamily: 'var(--font-data)',
                      fontSize: 12,
                      padding: '1px 6px',
                      background: rawView === mode ? 'rgba(0,255,255,0.1)' : 'transparent',
                      border: '1px solid var(--border)',
                      borderColor: rawView === mode ? 'var(--neon-cyan)' : 'var(--border)',
                      color: rawView === mode ? 'var(--neon-cyan)' : 'var(--text-dim)',
                      cursor: 'pointer',
                      letterSpacing: '1px',
                      textTransform: 'uppercase',
                    }}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
            {adsbRawLog.length === 0 ? (
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                            color: 'var(--text-dim)' }}>
                Awaiting frames...
              </div>
            ) : (
              <div style={{ overflow: 'auto' }}>
                {adsbRawLog.map((entry, idx) => {
                  const isPinned = pinnedFrame && entry.icao === pinnedFrame.icao && entry.raw_hex === pinnedFrame.raw_hex
                  const isNewest = !pinnedFrame && idx === 0
                  return (
                    <div
                      key={idx}
                      onClick={() => {
                        if (isPinned) {
                          setPinnedFrame(null)
                        } else {
                          setPinnedFrame(entry)
                        }
                      }}
                      style={{
                        display: 'flex',
                        flexDirection: 'row',
                        gap: '8px',
                        marginBottom: '2px',
                        alignItems: 'flex-start',
                        cursor: 'pointer',
                        background: isPinned ? 'rgba(0,255,255,0.07)' : isNewest ? 'rgba(0,255,255,0.03)' : 'transparent',
                        borderLeft: isPinned ? '2px solid var(--neon-cyan)' : 'none',
                        paddingLeft: isPinned ? '6px' : '8px',
                      }}
                    >
                      <span style={{ fontFamily: 'monospace', fontSize: 12,
                                     color: 'var(--neon-cyan)', whiteSpace: 'nowrap',
                                     flexShrink: 0 }}>
                        {entry.icao}
                      </span>
                      <span style={{ fontFamily: 'monospace', fontSize: 11,
                                     color: 'var(--text-dim)', wordBreak: 'break-all',
                                     lineHeight: '1.4' }}>
                        {rawView === 'hex'
                          ? hexToSpaced(entry.raw_hex)
                          : hexToBin(entry.raw_hex)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
          <div style={{ width: '1px', background: 'var(--border)', flexShrink: 0, margin: '0 8px' }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 12,
                            color: 'var(--neon-cyan)', letterSpacing: '1px' }}>
                FRAME INSPECTOR
              </div>
              {pinnedFrame && (
                <div style={{
                  fontFamily: 'var(--font-data)',
                  fontSize: 10,
                  color: 'var(--neon-amber)',
                  border: '1px solid var(--neon-amber)',
                  padding: '1px 5px',
                }}>
                  (PINNED)
                </div>
              )}
            </div>
            {adsbRawLog.length === 0 ? (
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                            color: 'var(--text-dim)' }}>
                Awaiting frames...
              </div>
            ) : frameData === null ? (
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                            color: 'var(--text-dim)' }}>
                Decoding...
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
                <div style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: 10,
                                 color: 'var(--text-dim)', letterSpacing: '1px',
                                 flexShrink: 0 }}>
                    DOWNLINK FORMAT
                  </span>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: 11,
                                 color: 'var(--text)', textAlign: 'right',
                                 marginLeft: 'auto' }}>
                    {frameData.df !== null && frameData.df !== undefined ? String(frameData.df) : '—'}
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: 10,
                                 color: 'var(--text-dim)', letterSpacing: '1px',
                                 flexShrink: 0 }}>
                    ICAO ADDRESS
                  </span>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: 11,
                                 color: 'var(--neon-cyan)', textAlign: 'right',
                                 marginLeft: 'auto' }}>
                    {frameData.icao ?? '—'}
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: 10,
                                 color: 'var(--text-dim)', letterSpacing: '1px',
                                 flexShrink: 0 }}>
                    TYPECODE
                  </span>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: 11,
                                 color: 'var(--text)', textAlign: 'right',
                                 marginLeft: 'auto' }}>
                    {frameData.typecode !== null && frameData.typecode !== undefined ? String(frameData.typecode) : '—'}
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: 10,
                                 color: 'var(--text-dim)', letterSpacing: '1px',
                                 flexShrink: 0 }}>
                    MESSAGE TYPE
                  </span>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: 11,
                                 color: 'var(--text)', textAlign: 'right',
                                 marginLeft: 'auto' }}>
                    {frameData.message_type ?? '—'}
                  </span>
                </div>
                {frameData.fields && Object.entries(frameData.fields).map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
                    <span style={{ fontFamily: 'var(--font-data)', fontSize: 10,
                                   color: 'var(--text-dim)', letterSpacing: '1px',
                                   flexShrink: 0 }}>
                      {k.toUpperCase()}
                    </span>
                    <span style={{ fontFamily: 'var(--font-data)', fontSize: 11,
                                   color: 'var(--text)', textAlign: 'right',
                                   marginLeft: 'auto' }}>
                      {v}
                    </span>
                  </div>
                ))}
                <div style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: 10,
                                 color: 'var(--text-dim)', letterSpacing: '1px',
                                 flexShrink: 0 }}>
                    CRC
                  </span>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: 11,
                                 textAlign: 'right',
                                 marginLeft: 'auto',
                                 color: frameData.crc_ok === true ? 'var(--neon-green)' : frameData.crc_ok === false ? 'var(--neon-red)' : 'var(--text-dim)' }}>
                    {frameData.crc_ok === true ? 'OK ✓' : frameData.crc_ok === false ? 'FAIL ✗' : '—'}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
