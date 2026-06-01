import React from 'react'

const FREQ_COLOUR_MAP = {
  98000000: '--neon-cyan',
  145175000: '--neon-green',
  915000000: '--neon-amber',
  1090000000: '--neon-magenta',
}

function formatTime(ts) {
  if (!ts) return '--:--:--'
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('en-AU', { hour12: false })
}

function freqLabel(freqHz) {
  if (freqHz === 98000000) return '98.0 MHz'
  if (freqHz === 145175000) return '145.175 MHz'
  if (freqHz === 915000000) return '915.0 MHz'
  if (freqHz === 1090000000) return '1090.0 MHz'
  return `${(freqHz / 1e6).toFixed(3)} MHz`
}

export default function SignalHistoryLog({ scanResults }) {
  return (
    <div style={{
      overflowY: 'auto',
      height: '100%',
      padding: '4px 8px',
      fontFamily: 'var(--font-data)',
      fontSize: 9,
    }}>
      {(!scanResults || scanResults.length === 0) ? (
        <div style={{ color: 'var(--text-dim)', padding: 8 }}>
          No signals recorded
        </div>
      ) : (
        scanResults.map((entry, idx) => {
          const colourVar = FREQ_COLOUR_MAP[entry.center_freq_hz] || '--neon-white'
          const colour = `var(${colourVar})`

          return (
            <div
              key={`${entry.timestamp}-${entry.center_freq_hz}-${idx}`}
              style={{
                opacity: idx > 4 ? 0.5 : 1,
                lineHeight: 1.6,
              }}
            >
              <span style={{ color: 'var(--text-dim)' }}>
                [{formatTime(entry.timestamp)}]
              </span>{' '}
              <span style={{ color: colour }}>
                [{freqLabel(entry.center_freq_hz)}]
              </span>{' '}
              <span style={{ color: 'var(--text-bright)' }}>
                {entry.signal_type || entry.label}
              </span>{' '}
              <span style={{ color: colour }}>
                ({Math.round((entry.confidence || 0) * 100)}%)
              </span>
            </div>
          )
        })
      )}
    </div>
  )
}
