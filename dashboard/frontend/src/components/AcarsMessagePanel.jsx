import React from 'react'

const neonGreen = '#00ff41'
const neonPink = '#ff0055'
const textDim = '#8899aa'

export default function AcarsMessagePanel({ acarsMessages = [], focusedFreq }) {
  const isAcarsFreq = focusedFreq && (
    Math.abs(focusedFreq - 129_125_000) <= 5_000 ||
    Math.abs(focusedFreq - 130_025_000) <= 5_000
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
        ACARS MESSAGES
      </div>
      {acarsMessages.length === 0 ? (
        <div style={{
          fontFamily: 'var(--font-data)',
          fontSize: 10,
          color: 'var(--text-dim)',
        }}>
          {isAcarsFreq
            ? 'Listening on 129.125 MHz...'
            : 'Not tuned to ACARS frequency'}
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
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Freq</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Reg</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Label</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Text</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>CRC</th>
            </tr>
          </thead>
          <tbody>
            {acarsMessages.map((msg, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : '-'}
                </td>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {(msg.freq_hz / 1e6).toFixed(3)} MHz
                </td>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.registration}
                </td>
                <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                  {msg.label}
                </td>
                <td style={{
                  padding: '2px 4px',
                  maxWidth: '200px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}>
                  {msg.text}
                </td>
                <td style={{
                  padding: '2px 4px',
                  color: msg.crc_ok ? neonGreen : neonPink,
                }}>
                  {msg.crc_ok ? '✓' : '!'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
