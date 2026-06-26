import React from 'react'

const neonGreen = '#00ff41'
const neonPink = '#ff0055'
const textDim = '#8899aa'

/**
 * AcarsMessagePanel — renders decoded ACARS messages and raw decode log.
 *
 * @param {Object[]} acarsMessages - Decoded ACARS message objects emitted
 *   via the acars_message SocketIO event. Fields: timestamp, freq_hz,
 *   registration, label, block_id, text, crc_ok.
 * @param {number|null} focusedFreq - Currently focused frequency in Hz.
 *   Controls whether the ACARS table and RAW DECODE section are shown.
 * @param {Object[]} acarsRawLog - Ring buffer of ACARS raw decode entries
 *   (max 50). Each entry has { registration, raw, timestamp }. Sourced
 *   from the "raw" field of acars_message events. Rendered in the RAW
 *   DECODE section below the messages table as a scrollable monospace log
 *   of decoded ACARS text per aircraft registration.
 */
export default function AcarsMessagePanel({ acarsMessages = [], focusedFreq, acarsRawLog = [] }) {
  const isAcarsFreq = focusedFreq && (
    Math.abs(focusedFreq - 129_125_000) <= 5_000 ||
    Math.abs(focusedFreq - 130_025_000) <= 5_000
  )

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '8px' }}>
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: 12,
        color: 'var(--neon-cyan)',
        marginBottom: '8px',
      }}>
        ACARS DECODE
      </div>
      {acarsMessages.length === 0 ? (
        <div style={{
          fontFamily: 'var(--font-data)',
          fontSize: 12,
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
          fontSize: 12,
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
      {isAcarsFreq && (
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
          {acarsRawLog.length === 0 ? (
            <div style={{
              fontFamily: 'var(--font-data)',
              fontSize: 12,
              color: 'var(--text-dim)',
            }}>
              Awaiting decodes...
            </div>
          ) : (
            <div style={{ maxHeight: '120px', overflow: 'auto' }}>
              {acarsRawLog.slice(0, 20).map((entry, idx) => (
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
                    REG
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-data)',
                    fontSize: 11,
                    color: 'var(--neon-cyan)',
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}>
                    {entry.registration}
                  </span>
                  <span style={{
                    fontFamily: 'monospace',
                    fontSize: 11,
                    color: 'var(--text)',
                    wordBreak: 'break-all',
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
