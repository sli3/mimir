import React from 'react'

const neonGreen = '#00ff41'
const neonPink = '#ff0055'

export default function AisVesselPanel({ aisMessages = [], focusedFreq }) {
  const isAisFreq = focusedFreq && (
    Math.abs(focusedFreq - 161_975_000) <= 100_000
  )

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '8px' }}>
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: 10,
        color: 'var(--neon-cyan)',
        marginBottom: '8px',
        textShadow: '0 0 6px var(--neon-cyan)',
      }}>
        AIS VESSELS
      </div>
      {aisMessages.length === 0 ? (
        <div style={{
          fontFamily: 'var(--font-data)',
          fontSize: 10,
          color: 'var(--text-dim)',
        }}>
          {isAisFreq
            ? 'Listening on 161.975 MHz...'
            : 'Not tuned to AIS frequency'}
        </div>
      ) : (
        <table style={{
          width: '100%',
          fontFamily: 'var(--font-data)',
          fontSize: 10,
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
    </div>
  )
}
