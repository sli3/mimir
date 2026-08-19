import React, { useEffect, useState } from 'react'
import useCaptures from '../hooks/useCaptures.js'
import useReplay from '../hooks/useReplay.js'
import './ReplayPage.css'

/**
 * Format a centre frequency in Hz as "<MHz> MHz" with one decimal place.
 */
function formatFreqMHz(freqHz) {
  if (!Number.isFinite(freqHz)) return '--- MHz'
  return `${(freqHz / 1e6).toFixed(1)} MHz`
}

/**
 * Format an ISO timestamp string into a short human-readable form.
 */
function formatTimestamp(isoString) {
  if (typeof isoString !== 'string' || !isoString) return '---'
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) return '---'
  return date.toLocaleString('en-AU', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/**
 * Format a signed numeric delta. Returns "+X" or "-X" without changing
 * the magnitude formatting. Non-finite values render as "---".
 */
function formatSignedDelta(value, decimals = 2) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '---'
  const sign = num >= 0 ? '+' : '-'
  return `${sign}${Math.abs(num).toFixed(decimals)}`
}

/**
 * Render one row of the seven-field comparison. Does NOT hardcode the
 * field names - it iterates the per-chunk field_results dict supplied by
 * /api/replay.
 */
function FieldRow({ name, saved, replayed, match, deltaDb, delta }) {
  // Only the three dB-scale fields carry a delta_db value.
  const isDbField = deltaDb !== undefined
  const isFlatness = name === 'spectral_flatness'
  let deltaText = ''
  if (isDbField) {
    deltaText = `${formatSignedDelta(deltaDb, 2)} dB`
  } else if (isFlatness) {
    // spectral_flatness delta is at 1e-9 scale; exponential keeps the
    // small value readable without losing precision.
    const num = Number(delta)
    deltaText = Number.isFinite(num) ? num.toExponential(2) : '---'
  }

  const mismatchStyle = match === false ? { color: 'var(--neon-red)' } : {}

  return (
    <div
      className="replay-field-row"
      data-testid={`replay-field-row-${name}`}
      style={mismatchStyle}
    >
      <span className="replay-field-name">{name}</span>
      <span className="replay-field-values">
        {String(saved ?? '---')} → {String(replayed ?? '---')}
        {deltaText ? ` (${deltaText})` : ''}
      </span>
    </div>
  )
}

/**
 * Header bar shared by both picker and results views.
 */
function Header() {
  return (
    <header className="replay-header">
      <span className="replay-header-title">REPLAY</span>
    </header>
  )
}

/**
 * Picker view - lists saved captures for the operator to choose from.
 */
function PickerView({ capturesState, onSelect }) {
  if (capturesState.status === 'loading') {
    return (
      <div
        className="replay-state-message"
        data-testid="captures-loading"
        role="status"
        aria-live="polite"
        style={{ color: 'var(--neon-amber)' }}
      >
        LOADING CAPTURES…
      </div>
    )
  }

  if (capturesState.status === 'failure') {
    return (
      <div
        className="replay-state-message"
        data-testid="captures-failure"
        role="alert"
        style={{ color: 'var(--neon-red)' }}
      >
        {capturesState.message}
      </div>
    )
  }

  if (capturesState.status === 'ok') {
    if (!capturesState.captures || capturesState.captures.length === 0) {
      return (
        <div
          className="replay-state-message"
          data-testid="captures-empty"
          style={{ color: 'var(--text-dim)' }}
        >
          NO CAPTURES RECORDED YET
        </div>
      )
    }

    return (
      <div className="replay-picker" data-testid="captures-list">
        {capturesState.captures.map((entry) => {
          const unknown = entry.mode === 'unknown'
          const modeBadge = `[${entry.mode}]`
          return (
            <button
              type="button"
              key={entry.filename}
              className={`replay-row ${unknown ? 'replay-row-unknown' : ''}`}
              data-testid={`capture-row-${entry.filename}`}
              disabled={unknown}
              onClick={() => onSelect(entry.filename)}
              title={unknown ? `Unrecognised file${entry.error ? `: ${entry.error}` : ''}` : 'Replay this capture'}
            >
              <span className="replay-row-freq">
                {formatFreqMHz(entry.core_frequency_hz)}
              </span>
              <span className="replay-row-device">{entry.device ?? '---'}</span>
              <span className="replay-row-time">
                {formatTimestamp(entry.timestamp)}
              </span>
              <span className="replay-row-chunks">{entry.chunk_count} chunk{entry.chunk_count === 1 ? '' : 's'}</span>
              <span className="replay-row-mode">{modeBadge}</span>
            </button>
          )
        })}
      </div>
    )
  }

  return null
}

/**
 * One-shot replay result card.
 */
function OneShotResult({ result }) {
  const chunk = result.per_chunk_results[0]
  const { comparison } = chunk
  const allMatch = comparison.all_match

  return (
    <div className="replay-result-body" data-testid="replay-oneshot-result">
      <div className="replay-summary-card">
        <span
          className="replay-status-dot"
          style={{ backgroundColor: allMatch ? 'var(--neon-green)' : 'var(--neon-red)' }}
        />
        <span className="replay-status-label">
          {allMatch ? 'EXACT MATCH' : 'MISMATCH'}
        </span>
      </div>
      <div className="replay-fields">
        {Object.entries(comparison.field_results).map(([name, field]) => (
          <FieldRow
            key={name}
            name={name}
            saved={field.saved}
            replayed={field.replayed}
            match={field.match}
            deltaDb={field.delta_db}
            delta={field.delta}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * Record-mode replay result view - grid of chunks plus detail panel.
 */
function RecordResult({ result }) {
  const [selectedIndex, setSelectedIndex] = useState(0)
  const { summary, per_chunk_results: chunks } = result
  const selectedChunk = chunks[selectedIndex]

  return (
    <div className="replay-result-body" data-testid="replay-record-result">
      <div className="replay-summary-line">
        {summary.matched_chunks}/{summary.total_chunks} chunks matched · {summary.mismatched_chunks} mismatched
      </div>
      <div className="replay-chunk-grid">
        {chunks.map((chunk, idx) => {
          const matched = chunk.comparison.all_match
          return (
            <button
              type="button"
              key={idx}
              className={`replay-chunk-cell ${selectedIndex === idx ? 'replay-chunk-cell-selected' : ''}`}
              data-testid={`replay-chunk-cell-${idx}`}
              onClick={() => setSelectedIndex(idx)}
              title={`Chunk ${idx + 1}: ${matched ? 'matched' : 'mismatched'}`}
              style={{
                backgroundColor: matched ? 'var(--neon-green)' : 'var(--neon-red)',
              }}
            >
              {idx + 1}
            </button>
          )
        })}
      </div>
      {selectedChunk && (
        <div className="replay-chunk-detail" data-testid="replay-chunk-detail">
          <div className="replay-chunk-detail-title">
            CHUNK {selectedIndex + 1} DETAIL
          </div>
          <div className="replay-fields">
            {Object.entries(selectedChunk.comparison.field_results).map(([name, field]) => (
              <FieldRow
                key={name}
                name={name}
                saved={field.saved}
                replayed={field.replayed}
                match={field.match}
                deltaDb={field.delta_db}
                delta={field.delta}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Results view - shows replay loading / failure / success states.
 */
function ResultsView({ replayState, onBack }) {
  return (
    <div className="replay-results">
      <button
        type="button"
        className="replay-back-link"
        data-testid="replay-back-link"
        onClick={onBack}
      >
        ← BACK
      </button>

      {replayState.status === 'loading' && (
        <div
          className="replay-state-message"
          data-testid="replay-loading"
          role="status"
          aria-live="polite"
          style={{ color: 'var(--neon-amber)' }}
        >
          REPLAYING…
        </div>
      )}

      {replayState.status === 'failure' && (
        <div
          className="replay-state-message"
          data-testid="replay-failure"
          role="alert"
          style={{ color: 'var(--neon-red)' }}
        >
          {replayState.message}
        </div>
      )}

      {replayState.status === 'ok' && (
        <>
          <div className="replay-info-line" data-testid="replay-info-line">
            {replayState.result?.band_resolution?.band_key ?? '---'} · {' '}
            {formatFreqMHz(replayState.result?.file_metadata?.core_frequency_hz)} · {' '}
            {replayState.result?.band_resolution?.match ?? '---'} · {' '}
            {replayState.result?.band_resolution?.profile_source ?? '---'}
          </div>
          {replayState.result?.file_metadata?.fingerprint_field === 'mimir:fingerprint' ? (
            <OneShotResult result={replayState.result} />
          ) : (
            <RecordResult result={replayState.result} />
          )}
        </>
      )}
    </div>
  )
}

/**
 * Standalone /replay page (Phase 71).
 *
 * Lets the operator pick a saved SigMF capture and replay it through
 * the fingerprint pipeline under today's band thresholds. Consists of a
 * picker (driven by useCaptures) and a results view (driven by useReplay),
 * switched locally by selectedFilename without a page reload.
 *
 * Passive receive display only - no TX capability.
 */
export default function ReplayPage() {
  const { state: capturesState } = useCaptures()
  const { state: replayState, replay } = useReplay()
  const [selectedFilename, setSelectedFilename] = useState(null)

  useEffect(() => {
    document.body.classList.add('replay-page')
    return () => document.body.classList.remove('replay-page')
  }, [])

  useEffect(() => {
    if (selectedFilename) {
      replay(selectedFilename)
    }
  }, [selectedFilename, replay])

  const handleSelect = (filename) => {
    setSelectedFilename(filename)
  }

  const handleBack = () => {
    setSelectedFilename(null)
  }

  return (
    <div className="replay-shell">
      <Header />
      <main className="replay-body">
        {selectedFilename === null ? (
          <PickerView capturesState={capturesState} onSelect={handleSelect} />
        ) : (
          <ResultsView replayState={replayState} onBack={handleBack} />
        )}
      </main>
    </div>
  )
}
