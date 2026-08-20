import React, { useEffect, useMemo, useState } from 'react'
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

// BURST_MARGIN_DB mirrors core/pipeline/features.py:BURST_MARGIN_DB
// (paired via tests/dashboard/test_replay_burst_thresholds.py).
// MAX_OBSERVED_EXCESS_DB is empirical — observed 11.27 dB ceiling across
// two independent ADS-B captures in Phase 72 (-2.6 to 11.3 dB range).
// Recalibrate after field sessions that move the ceiling.
const BURST_MARGIN_DB = 6.0
const MAX_OBSERVED_EXCESS_DB = 11.27

// RGB tuples mirror --neon-green / --neon-amber in theme/cyberpunk.css:15-16.
// Used for sRGB interpolation between t=0 and t=1.
const NEON_GREEN_RGB = [0, 255, 136]
const NEON_AMBER_RGB = [255, 204, 0]

/**
 * Map a burst_excess_db value to a 0-1 intensity for the visual overlay.
 *
 * 0 means "at or below the backend burst threshold" (no visual change).
 * 1 means "at the empirical ceiling observed across ADS-B captures".
 * Non-finite or negative values clamp to 0 so the UI never renders NaN.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function burstIntensity(burstExcessDb) {
  if (!Number.isFinite(burstExcessDb) || burstExcessDb < 0) return 0
  const t = (burstExcessDb - BURST_MARGIN_DB) / (MAX_OBSERVED_EXCESS_DB - BURST_MARGIN_DB)
  return Math.max(0, Math.min(1, t))
}

/**
 * Interpolate between neon-green and neon-amber based on burst intensity t.
 * At t=0 the exact CSS variable is returned so regression tests and the
 * rendered colour both match today's pure-green cells byte-for-byte.
 */
function interpolateBurstColour(t) {
  if (t <= 0) return 'var(--neon-green)'
  if (t >= 1) return 'var(--neon-amber)'
  const r = Math.round(NEON_GREEN_RGB[0] * (1 - t) + NEON_AMBER_RGB[0] * t)
  const g = Math.round(NEON_GREEN_RGB[1] * (1 - t) + NEON_AMBER_RGB[1] * t)
  const b = Math.round(NEON_GREEN_RGB[2] * (1 - t) + NEON_AMBER_RGB[2] * t)
  return `rgb(${r}, ${g}, ${b})`
}

/**
 * Build a box-shadow ring for mismatched cells that intensifies with t.
 * At t=0 no shadow is emitted, preserving the pre-feature red fill exactly.
 */
function burstRingStyle(t) {
  if (t <= 0) return {}
  return {
    boxShadow: `0 0 0 ${2 + 3 * t}px var(--neon-amber), 0 0 ${6 + 8 * t}px ${1 + 2 * t}px var(--neon-amber)`,
  }
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
        <span className="replay-field-label">[SAVED]</span> {String(saved ?? '---')}
        {' → '}
        <span className="replay-field-label">[REPLAYED]</span> {String(replayed ?? '---')}
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
  const fp = chunk.replayed_fingerprint ?? {}
  const isBurst = fp.is_burst === true
  const burstExcessDb = fp.burst_excess_db
  const burstText = Number.isFinite(burstExcessDb) && burstExcessDb >= 0
    ? `${Number(burstExcessDb).toFixed(1)}dB`
    : '---dB'

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
        {isBurst && (
          <span className="replay-burst-badge" data-testid="replay-burst-badge">
            BURST {burstText}
          </span>
        )}
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
  const [analysisOpen, setAnalysisOpen] = useState(true)
  const { summary, per_chunk_results: chunks } = result
  const selectedChunk = chunks[selectedIndex]

  // burstStats: compute once from chunks array. Returns stats object with:
  // - total: chunk count, burstCount: chunks where is_burst=true, burstRate: burstCount/total
  // - burstMin/burstMax: range among bursty chunks only (null if none)
  // - strongestIdx/strongestVal: chunk index with max burst_excess_db among bursty
  // - fullMin/fullMax: range across ALL chunks with finite burst_excess_db (null if none)
  // - hasAnyFiniteBurst: true if any chunk has a finite burst_excess_db value
  // Empty state semantics: burstMin/burstMax/strongestVal are null when burstCount=0;
  // fullMin/fullMax are null when no finite values exist. Guarded against division-by-zero.
  const burstStats = useMemo(() => {
    const total = chunks.length
    let burstCount = 0
    let burstMin = Infinity
    let burstMax = -Infinity
    let fullMin = Infinity
    let fullMax = -Infinity
    let strongestIdx = -1
    let strongestVal = -Infinity
    for (let i = 0; i < total; i += 1) {
      const fp = chunks[i].replayed_fingerprint ?? {}
      const v = fp.burst_excess_db
      if (Number.isFinite(v)) {
        if (v < fullMin) fullMin = v
        if (v > fullMax) fullMax = v
        if (fp.is_burst === true) {
          burstCount += 1
          if (v < burstMin) burstMin = v
          if (v > burstMax) burstMax = v
          if (v > strongestVal) {
            strongestVal = v
            strongestIdx = i
          }
        }
      }
    }
    return {
      total,
      burstCount,
      burstRate: total > 0 ? burstCount / total : 0,
      burstMin: burstCount > 0 ? burstMin : null,
      burstMax: burstCount > 0 ? burstMax : null,
      strongestIdx,
      strongestVal: burstCount > 0 ? strongestVal : null,
      fullMin: Number.isFinite(fullMin) ? fullMin : null,
      fullMax: Number.isFinite(fullMax) ? fullMax : null,
      hasAnyFiniteBurst: Number.isFinite(fullMin) && Number.isFinite(fullMax),
    }
  }, [chunks])

  return (
    <div className="replay-result-body" data-testid="replay-record-result">
      <div className="replay-summary-line">
        {summary.matched_chunks}/{summary.total_chunks} chunks matched · {summary.mismatched_chunks} mismatched
      </div>
      {/* Collapsible burst analysis panel - positioned after summary line, before chunk grid.
          Shares selectedIndex state with the chunk grid (not a duplicate state). */}
      <div className="replay-burst-panel" data-testid="replay-burst-panel">
        <button
          type="button"
          className="replay-burst-panel-header"
          data-testid="replay-burst-panel-toggle"
          onClick={() => setAnalysisOpen((prev) => !prev)}
          aria-expanded={analysisOpen}
        >
          <span className="replay-burst-panel-chevron">{analysisOpen ? '▾' : '▸'}</span>
          <span>BURST ANALYSIS</span>
        </button>
        {analysisOpen && (
          <div className="replay-burst-panel-body" data-testid="replay-burst-panel-body">
            {/* 4-column desktop stat grid: burst count, burst range, strongest burst, full range (secondary) */}
            <div className="replay-burst-stat-grid" data-testid="replay-burst-stat-grid">
              {/* bursting count card */}
              <div className="replay-burst-stat-card" data-testid="burst-stat-count">
                <div className="replay-burst-stat-label">BURSTS DETECTED</div>
                <div className="replay-burst-stat-value">
                  <strong>{burstStats.burstCount}</strong>
                  <span className="replay-burst-stat-rate"> / {burstStats.total} ({burstStats.total > 0 ? (burstStats.burstRate * 100).toFixed(1) : '0.0'}%)</span>
                </div>
              </div>

              {/* burst range card */}
              <div className="replay-burst-stat-card" data-testid="burst-stat-burst-range">
                <div className="replay-burst-stat-label">BURST EXCESS RANGE</div>
                <div className="replay-burst-stat-value">
                  {burstStats.burstCount > 0 && Number.isFinite(burstStats.burstMin) && Number.isFinite(burstStats.burstMax)
                    ? `${burstStats.burstMin.toFixed(1)} – ${burstStats.burstMax.toFixed(1)} dB`
                    : <span style={{ color: 'var(--text-dim)' }}>no bursts detected in this capture</span>}
                </div>
              </div>

              {/* strongest burst card */}
              <div className="replay-burst-stat-card" data-testid="burst-stat-strongest">
                <div className="replay-burst-stat-label">STRONGEST BURST</div>
                <div className="replay-burst-stat-value">
                  {burstStats.burstCount > 0
                    ? `chunk ${burstStats.strongestIdx + 1} @ ${burstStats.strongestVal.toFixed(1)} dB`
                    : <span style={{ color: 'var(--text-dim)' }}>—</span>}
                </div>
              </div>

              {/* full range card — label is dimmed (see .replay-burst-stat-card-secondary
                  .replay-burst-stat-label in ReplayPage.css); value colour matches the
                  other three cards, per live-review: a value fade with no attached
                  meaning read as an unexplained inconsistency rather than a signal. */}
              <div className="replay-burst-stat-card replay-burst-stat-card-secondary" data-testid="burst-stat-full-range">
                <div className="replay-burst-stat-label">FULL RANGE</div>
                <div className="replay-burst-stat-value">
                  {burstStats.hasAnyFiniteBurst
                    ? `${burstStats.fullMin.toFixed(1)} – ${burstStats.fullMax.toFixed(1)} dB`
                    : '—'}
                </div>
              </div>
            </div>
            {/* Legend swatches - colours mirror the grid colour logic:
                green (matched, no burst), amber (matched, burst), red (mismatch),
                red+amber ring (mismatch, burst). Uses same helpers as Phase 73. */}
            <div className="replay-burst-legend" data-testid="replay-burst-legend">
              <div className="replay-burst-legend-item">
                <span className="replay-burst-legend-swatch" style={{ backgroundColor: 'var(--neon-green)' }} />
                <span>matched, no burst</span>
              </div>
              <div className="replay-burst-legend-item">
                <span className="replay-burst-legend-swatch" style={{ backgroundColor: 'var(--neon-amber)' }} />
                <span>matched, burst</span>
              </div>
              <div className="replay-burst-legend-item">
                <span className="replay-burst-legend-swatch" style={{ backgroundColor: 'var(--neon-red)' }} />
                <span>mismatch</span>
              </div>
              <div className="replay-burst-legend-item">
                <span
                  className="replay-burst-legend-swatch"
                  style={{
                    backgroundColor: 'var(--neon-red)',
                    boxShadow: '0 0 0 2px var(--neon-amber)',
                  }}
                />
                <span>mismatch, burst</span>
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="replay-chunk-grid">
        {chunks.map((chunk, idx) => {
          const matched = chunk.comparison.all_match
          const fp = chunk.replayed_fingerprint ?? {}
          const t = burstIntensity(fp.burst_excess_db)
          const cellStyle = {
            backgroundColor: matched ? interpolateBurstColour(t) : 'var(--neon-red)',
          }
          const ringStyle = !matched ? burstRingStyle(t) : {}
          return (
            <button
              type="button"
              key={idx}
              className={`replay-chunk-cell ${selectedIndex === idx ? 'replay-chunk-cell-selected' : ''}`}
              data-testid={`replay-chunk-cell-${idx}`}
              onClick={() => setSelectedIndex(idx)}
              title={`Chunk ${idx + 1}: ${matched ? 'matched' : 'mismatched'}`}
              style={{ ...cellStyle, ...ringStyle }}
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
          {/* Burst-excess row - shown after the seven compared fields in chunk detail.
              Has [REPLAYED] label but no [SAVED] because BURST_EXCESS_DB was never in
              the seven saved/compared fingerprint keys (it's replay-only). */}
          <div
            className="replay-field-row replay-burst-row"
            data-testid={`replay-burst-row-${selectedIndex}`}
          >
            <span className="replay-field-name">BURST_EXCESS_DB</span>
            <span className="replay-burst-row-value">
              {Number.isFinite(selectedChunk.replayed_fingerprint?.burst_excess_db) && selectedChunk.replayed_fingerprint?.burst_excess_db >= 0 ? (
                <>
                  <span className="replay-field-label">[REPLAYED]</span>{' '}
                  {Number(selectedChunk.replayed_fingerprint.burst_excess_db).toFixed(1)} dB
                  {selectedChunk.replayed_fingerprint?.is_burst === true ? (
                    <span
                      className="replay-burst-badge"
                      data-testid={`replay-burst-row-badge-${selectedIndex}`}
                      style={{ marginLeft: '8px' }}
                    >
                      BURST
                    </span>
                  ) : (
                    <span
                      className="replay-burst-row-note"
                      data-testid={`replay-burst-row-note-${selectedIndex}`}
                      style={{ marginLeft: '8px', color: 'var(--text-dim)' }}
                    >
                      below {BURST_MARGIN_DB.toFixed(1)} dB threshold
                    </span>
                  )}
                </>
              ) : (
                <>
                  <span className="replay-field-label">[REPLAYED]</span>{' '}
                  <span style={{ color: 'var(--text-dim)' }}>--- dB</span>
                </>
              )}
            </span>
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
  const { state: capturesState, refetch: refetchCaptures } = useCaptures()
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
    refetchCaptures()
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