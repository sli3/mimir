import React from 'react'

const neonGreen = '#00ff41'
const neonPink = '#ff0055'

/**
 * AisVesselPanel — renders decoded AIS vessel messages and raw NMEA log.
 *
 * @param {Object[]} aisMessages - Decoded AIS vessel objects emitted via
 *   the ais_message SocketIO event. Fields: timestamp, mmsi, vessel_name,
 *   lat, lon, speed, course, channel.
 * @param {number|null} focusedFreq - Currently focused frequency in Hz.
 *   Controls whether the AIS table and RAW DECODE section are shown.
 * @param {Object[]} aisRawLog - Ring buffer of AIS raw NMEA entries
 *   (max 50). Each entry has { mmsi, raw, timestamp }. Sourced from the
 *   "raw" field of ais_message events. Rendered in the RAW DECODE section
 *   below the vessels table as a scrollable monospace log of NMEA-0183
 *   sentences per vessel MMSI.
 */
export default function AisVesselPanel({ aisMessages = [], focusedFreq, aisRawLog = [] }) {
  const isAisFreq = focusedFreq && (
    Math.abs(focusedFreq - 162_000_000) <= 100_000
  )

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '8px' }}>
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: 12,
        color: 'var(--neon-cyan)',
        marginBottom: '8px',
      }}>
        AIS DECODE
      </div>
      {aisMessages.length === 0 ? (
        <div style={{
          fontFamily: 'var(--font-data)',
          fontSize: 12,
          color: 'var(--text-dim)',
        }}>
          {isAisFreq
            ? 'Listening on 162.000 MHz...'
            : 'Not tuned to AIS frequency'}
        </div>
      ) : (
        <table style={{
          width: '100%',
          fontFamily: 'var(--font-data)',
          fontSize: 12,
          color: 'var(--text)',
          borderCollapse: 'collapse',
        }}>
          <thead>
            <tr style={{ color: 'var(--neon-cyan)', borderBottom: '1px solid var(--border)' }}>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Time</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>MMSI</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Name</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Lat</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Lon</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Spd</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Crs</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Ch</th>
            </tr>
          </thead>
          <tbody>
            {aisMessages.map((msg, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : '-'}
                </td>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.mmsi}
                </td>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.vessel_name}
                </td>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.lat !== '---' ? Number(msg.lat).toFixed(4) : '---'}
                </td>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.lon !== '---' ? Number(msg.lon).toFixed(4) : '---'}
                </td>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.speed !== '---' ? msg.speed : '---'}
                </td>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.course !== '---' ? msg.course : '---'}
                </td>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.channel}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {isAisFreq && (
        <div style={{ marginTop: '8px', borderTop: '1px solid var(--border)', paddingTop: '6px' }}>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 12,
            color: 'var(--neon-cyan)',
            letterSpacing: '1px',
            marginBottom: '4px',
          }}>
            RAW DECODE
          </div>
          {aisRawLog.length === 0 ? (
            <div style={{
              fontFamily: 'var(--font-data)',
              fontSize: 12,
              color: 'var(--text-dim)',
            }}>
              Awaiting decodes...
            </div>
          ) : (
            <div style={{ maxHeight: '120px', overflow: 'auto' }}>
              {aisRawLog.slice(0, 20).map((entry, idx) => (
                <div key={idx} style={{
                  display: 'flex',
                  flexDirection: 'row',
                  gap: '8px',
                  marginBottom: '2px',
                  alignItems: 'flex-start',
                }}>
                  <span style={{
                    fontFamily: 'var(--font-data)',
                    fontSize: 11,
                    color: 'var(--text-dim)',
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}>
                    {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '-'}
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: 12,
                    color: 'var(--neon-cyan)',
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}>
                    MMSI
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-data)',
                    fontSize: 11,
                    color: 'var(--neon-cyan)',
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}>
                    {entry.mmsi}
                  </span>
                  <span style={{
                    fontFamily: 'monospace',
                    fontSize: 11,
                    color: 'var(--text)',
                    whiteSpace: 'nowrap',
                    lineHeight: '1.4',
                  }}>
                    {entry.raw}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
