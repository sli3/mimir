import React from 'react'

/** Colour mapping for AU band frequencies. */
const FREQ_COLOUR_MAP = {
  98000000: '--neon-cyan',
  127000000: '--neon-cyan',
  129125000: '--neon-amber',
  145175000: '--neon-green',
  161975000: '--neon-red',
  915000000: '--neon-amber',
  1090000000: '--neon-magenta',
}

function formatTime(ts) {
  if (!ts) return '--:--:--'
  const d = new Date(ts)
  return d.toLocaleTimeString('en-AU', { hour12: false })
}

function freqLabel(freqHz) {
  if (freqHz === 98000000) return '98.0 MHz'
  if (freqHz === 127000000) return '127.0 MHz'
  if (freqHz === 129125000) return '129.125 MHz'
  if (freqHz === 145175000) return '145.175 MHz'
  if (freqHz === 161975000) return '161.975 MHz'
  if (freqHz === 915000000) return '915.0 MHz'
  if (freqHz === 1090000000) return '1090.0 MHz'
  return `${(freqHz / 1e6).toFixed(3)} MHz`
}

/** Scrolling log of all scan results. Each row shows timestamp, frequency,
 *  signal type, and confidence percentage. Supports pin-to-AIReasoningPanel
 *  via onPinReasoning + pinnedTimestamp props.
 *
 *  @param {{ scanResults: Array, onPinReasoning?: function, pinnedTimestamp?: string|null }} props
 *  @param {Array} props.scanResults — ordered newest-first from useSocket
 *  @param {function} [props.onPinReasoning] — called with entry on click; toggles pin
 *  @param {string|null} [props.pinnedTimestamp] — currently pinned entry's timestamp for visual highlight
 *
 *  TODO: Wrap with React.memo to avoid re-render on every spectrum_update
 *  (~4-5 Hz). scanResults reference changes each time even if content is
 *  unchanged because useSocket prepends new entries. */
export default function SignalHistoryLog({ scanResults, onPinReasoning, pinnedTimestamp }) {
  return (
    <div style={{
      overflowY: 'auto',
      height: '100%',
      padding: '4px 8px',
      fontFamily: 'var(--font-data)',
      fontSize: 12,
    }}>
      {(!scanResults || scanResults.length === 0) ? (
        <div style={{ color: 'var(--text-dim)', padding: 8 }}>
          No signals recorded
        </div>
      ) : (
        scanResults.map((entry, idx) => {
          const colourVar = FREQ_COLOUR_MAP[entry.center_freq_hz] || '--neon-white'
          const colour = `var(${colourVar})`
          const isPinned = entry.timestamp === pinnedTimestamp

          return (
            <div
              key={`${entry.timestamp}-${entry.center_freq_hz}-${idx}`}
              onClick={onPinReasoning ? () => onPinReasoning(entry) : undefined}
              data-pinned={isPinned ? true : undefined}
              style={{
                lineHeight: 1.6,
                borderLeft: isPinned ? '2px solid var(--neon-amber)' : '2px solid transparent',
                background: isPinned ? 'rgba(255, 170, 0, 0.07)' : 'transparent',
                cursor: onPinReasoning ? 'pointer' : 'default',
                paddingLeft: 4,
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
                ({entry.confidence_score != null ? Math.round(entry.confidence_score * 100) : '?'}%)
              </span>
            </div>
          )
        })
      )}
    </div>
  )
}
