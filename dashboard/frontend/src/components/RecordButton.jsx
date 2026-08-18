import React from 'react'

/**
 * Record button for the main spectrum view (Phase 68).
 *
 * Two visual states:
 * - IDLE: themed styling matching the existing .manual-capture-button
 *   class (neon-cyan), label "RECORD", no dot.
 * - RECORDING: neon-red styling with a small red dot beside the label
 *   (the dot pulses via the shared `@keyframes blink` from
 *   cyberpunk.css), plus an inline mm:ss elapsed readout. Once the
 *   elapsed time reaches 60 s the readout recolours to neon-amber —
 *   a display-only warning. There is deliberately NO auto-stop and no
 *   banner: the recording runs until the operator stops it.
 *
 * This component is presentation only: the parent owns the click
 * handler, which fires POST /api/record/start while idle and
 * POST /api/record/stop while recording.
 *
 * Passive receive display only: the endpoints file-write
 * already-received samples and have no TX capability.
 *
 * @param {object} props
 * @param {boolean} props.recording - true while a recording is active.
 * @param {() => void} props.onClick - click handler (no args). Parent
 *   decides start vs stop based on its own state.
 * @param {number} props.elapsedSec - whole seconds since recording
 *   started (client-side timer; display only).
 * @param {boolean} props.warning - true once elapsedSec >= 60. Only
 *   recolours the elapsed readout; never stops the recording.
 */
function formatElapsed(totalSec) {
  const safe = Number.isFinite(totalSec) && totalSec >= 0 ? totalSec : 0
  const mm = String(Math.floor(safe / 60)).padStart(2, '0')
  const ss = String(Math.floor(safe % 60)).padStart(2, '0')
  return `${mm}:${ss}`
}

export default function RecordButton({ recording, onClick, elapsedSec, warning }) {
  const idleStyle = {
    fontFamily: 'var(--font-display)',
    fontSize: '12px',
    letterSpacing: '1px',
    textTransform: 'uppercase',
    color: 'var(--neon-cyan)',
    background: 'rgba(0,255,255,0.08)',
    border: '1px solid var(--neon-cyan)',
    padding: '5px 14px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  }
  const recordingStyle = {
    ...idleStyle,
    color: 'var(--neon-red)',
    background: 'rgba(255,68,68,0.18)',
    border: '1px solid var(--neon-red)',
  }
  return (
    <button
      type="button"
      data-testid="record-button"
      onClick={onClick}
      style={recording ? recordingStyle : idleStyle}
    >
      {recording && (
        <span
          data-testid="record-dot"
          style={{
            display: 'inline-block',
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: 'var(--neon-red)',
            marginRight: '6px',
            animation: 'blink 1s infinite',
          }}
        />
      )}
      RECORD
      {recording && (
        <span
          data-testid="record-elapsed"
          style={{
            marginLeft: '8px',
            color: warning ? 'var(--neon-amber)' : 'var(--neon-red)',
          }}
        >
          {formatElapsed(elapsedSec)}
        </span>
      )}
    </button>
  )
}
