import React from 'react'
import { freqMatches, findCanonicalValue } from '../utils/frequency.js'

/** Colour mapping for AU band frequencies. */
const FREQ_COLOUR_MAP = {
  98000000: '--neon-cyan',
  127000000: '--neon-cyan',
  129125000: '--neon-amber',
  145175000: '--neon-green',
  162000000: '--neon-red',
  915000000: '--neon-amber',
  1090000000: '--neon-magenta',
}

const FREQ_LABEL_MAP = {
  98000000: '98.0 MHz',
  127000000: '127.0 MHz',
  129125000: '129.125 MHz',
  145175000: '145.175 MHz',
  162000000: '162.000 MHz',
  915000000: '915.0 MHz',
  1090000000: '1090.0 MHz',
}

function formatTime(ts) {
  if (!ts) return '--:--:--'
  const d = new Date(ts)
  return d.toLocaleTimeString('en-AU', { hour12: false })
}

function freqLabel(freqHz) {
  return findCanonicalValue(freqHz, FREQ_LABEL_MAP) || `${(freqHz / 1e6).toFixed(3)} MHz`
}

/** Scrolling log of all scan results. Each row shows timestamp, frequency,
 *  signal type, and confidence percentage. Supports pin-to-AIReasoningPanel
 *  via onPinReasoning + pinnedTimestamp props.
 *
 *  The amber [PEAK] tag is driven by the backend's ``is_burst`` boolean field
 *  (Phase 45), computed via per-bin max-hold ratio detection in
 *  ``fingerprint_spectrum()``. The tag renders only when ``is_burst === true``,
 *  with strict equality so undefined/null/false all suppress it. FM broadcast
 *  may trigger false positives; suspected carrier sweep across ±75 kHz, not yet
 *  confirmed on hardware (tech-debt TD-45-2).
 *
 *  @param {{ scanResults: Array, onPinReasoning?: function, pinnedTimestamp?: string|null }} props
 *  @param {Array} props.scanResults — ordered newest-first from useSocket
 *  @param {function} [props.onPinReasoning] — called with entry on click; toggles pin
 *  @param {string|null} [props.pinnedTimestamp] — currently pinned entry's timestamp for visual highlight
 *
 *  Custom-compare React.memo: check content equality (length + head timestamp)
 *  plus pinnedTimestamp to avoid re-render on every spectrum_update (~4-5 Hz)
 *  while still re-rendering when pin state changes or new scan results arrive. */
const SignalHistoryLog = React.memo(function SignalHistoryLog({ scanResults, onPinReasoning, pinnedTimestamp }) {
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
          const colourVar = findCanonicalValue(entry.center_freq_hz, FREQ_COLOUR_MAP) || '--neon-white'
          const colour = `var(${colourVar})`
          const isPinned = entry.timestamp === pinnedTimestamp
          // TODO(tech-debt TD-45-2): FM broadcast may trigger false-positive [PEAK] tags
          // because the carrier sweeps ±75 kHz, so single-bin max-hold substantially exceeds
          // the average even though FM is continuous. This is a known limitation of the
          // per-bin max-hold ratio method.
          const isPeakBurst = entry.is_burst === true
          const signalTypeColour = entry.signal_type === 'llm_offline'
            ? 'var(--neon-amber)'
            : 'var(--text-bright)'

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
              <span style={{ color: signalTypeColour }}>
                {entry.signal_type || entry.label}
              </span>{' '}
              <span style={{ color: colour }}>
                ({entry.confidence_score != null ? Math.round(entry.confidence_score * 100) : '?'}%)
              </span>
              {isPeakBurst && (
                <span style={{ color: 'var(--neon-amber)' }}>
                  {' [PEAK]'}
                </span>
              )}
            </div>
          )
        })
      )}
    </div>
  )
}, (prevProps, nextProps) => {
  if (prevProps.pinnedTimestamp !== nextProps.pinnedTimestamp) return false
  const prev = prevProps.scanResults
  const next = nextProps.scanResults
  if (prev === next) return true
  if (!prev || !next) return false
  if (prev.length !== next.length) return false
  if (prev.length > 0 && next.length > 0) {
    return prev[0].timestamp === next[0].timestamp
  }
  return false
})

export default SignalHistoryLog
