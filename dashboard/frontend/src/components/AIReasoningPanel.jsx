import { useState, useEffect } from 'react'

function formatTimestamp(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('en-GB', { hour12: false })
}

function confidenceColour(confidence) {
  if (confidence === 'high') return 'var(--neon-cyan)'
  if (confidence === 'medium') return 'var(--neon-amber)'
  return 'var(--neon-magenta)'
}

/** Displays the current (or pinned) AI reasoning: frequency, signal type,
 *  confidence, AU legal status, timestamp, and the LLM's reasoning text.
 *  When `isPinned` is true and a valid signal_type is present, renders a
 *  boxed ◆ PINNED badge (amber border + glow) beside the timestamp at the
 *  top of the panel. A "CLASSIFICATION LOG" heading sits above the reasoning body.
 *
 *  Shows "AWAITING SIGNAL..." when no reasoning data is available (placeholder).
 *
 *  The first entry displays immediately. A new timestamp fades the old entry
 *  out, waits 200 ms, then replaces it and fades back in (opacity 0 to 1).
 *  Equal timestamps leave the display and any pending fade unchanged.
 *
 *  @param {{ aiReasoning: object, isPinned?: boolean }} props
 *  @param {object} props.aiReasoning — the reasoning data object (keys:
 *    freq_hz, signal_type, confidence, confidence_score, au_legal_status,
 *    reasoning, timestamp, source, plus fingerprint fields such as snr_db,
 *    bandwidth_hz, spectral_flatness, chroma_distance, and per-band thresholds)
 *  @param {boolean} [props.isPinned=false] — if true and signal_type is set,
 *    renders a boxed ◆ PINNED badge with timestamp in amber.
 *    pages/DashboardPage.jsx renders the panel without a key, so a pin toggle
 *    updates the same instance. */
export default function AIReasoningPanel({ aiReasoning, isPinned = false, onUnpin }) {
  const [opacity, setOpacity] = useState(1)
  const [displayData, setDisplayData] = useState(null)
  const [prevReasoning, setPrevReasoning] = useState(null)
  const reasoning = !aiReasoning || aiReasoning.signal_type === null ? null : aiReasoning

  // Adjust this component's state before committing a changed entry. Keeping
  // the previous reasoning in state avoids reading or writing refs in render.
  if (reasoning === null && prevReasoning !== null) {
    setPrevReasoning(null)
    setDisplayData(null)
    setOpacity(1)
  } else if (reasoning !== null && (
    prevReasoning === null || reasoning.timestamp !== prevReasoning.timestamp
  )) {
    setPrevReasoning(reasoning)
    if (prevReasoning === null) {
      setDisplayData(reasoning)
      setOpacity(1)
    } else {
      setOpacity(0)
    }
  }

  // Only the timeout callback updates state here. Stable previous reasoning
  // keeps equal-timestamp prop objects from cancelling or restarting a fade.
  useEffect(() => {
    if (opacity !== 0 || prevReasoning === null) return
    const timer = setTimeout(() => {
      setDisplayData(prevReasoning)
      setOpacity(1)
    }, 200)

    return () => clearTimeout(timer)
  }, [prevReasoning, opacity])

  const placeholder = !displayData || !displayData.signal_type
  const isConfirmedDecode = displayData?.source === 'decode'
  const hasRealMeasurement =
    displayData?.snr_db != null &&
    displayData?.bandwidth_hz != null &&
    displayData?.bandwidth_hz > 0
  const dimConfidence = !isConfirmedDecode && !hasRealMeasurement

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      fontFamily: 'var(--font-data)',
      padding: 10,
      overflow: 'hidden',
    }}>
      {placeholder ? (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          fontFamily: 'var(--font-display)',
          fontSize: 11,
          color: 'var(--text-dim)',
          textAlign: 'center',
        }}>
          AWAITING SIGNAL...
        </div>
      ) : (
        <div style={{
          opacity,
          transition: 'opacity 300ms ease-in-out',
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
        }}>
          {/* Line 1 — Status / timestamp row */}
          {isPinned && displayData.signal_type ? (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 4,
            }}>
              <div
                onClick={onUnpin}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  border: '1px solid var(--neon-amber)',
                  background: 'rgba(255, 170, 0, 0.14)',
                  boxShadow: '0 0 6px rgba(255, 170, 0, 0.35)',
                  padding: '2px 8px',
                  fontFamily: 'var(--font-display)',
                  fontSize: 10,
                  color: 'var(--neon-amber)',
                  letterSpacing: 1,
                  cursor: 'pointer',
                }}>
                ◆ PINNED — CLICK TO UNPIN
              </div>
              <span style={{
                fontFamily: 'var(--font-display)',
                fontSize: 10,
                color: 'var(--neon-amber)',
              }}>
                {formatTimestamp(displayData.timestamp)}
              </span>
            </div>
          ) : (
            <div style={{ marginBottom: 4 }}>
              <span style={{
                fontFamily: 'var(--font-display)',
                fontSize: 13,
                color: 'var(--text-bright)',
              }}>
                {formatTimestamp(displayData.timestamp)}
              </span>
            </div>
          )}

          {/* Line 2 — Identity row */}
          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: 13,
            marginTop: 4,
          }}>
            <span style={{ color: 'var(--neon-cyan)' }}>
              {displayData.signal_type === 'llm_offline'
                ? 'LLM OFFLINE'
                : displayData.signal_type === 'unavailable'
                  ? 'TIMEOUT'
                  : (displayData.signal_type || '').toUpperCase()}
            </span>
            <span style={{ color: 'var(--text-dim)' }}>: </span>
            <span style={{ color: 'var(--neon-cyan)' }}>
              {displayData.freq_hz
                ? `${(displayData.freq_hz / 1e6).toFixed(3)} MHz`
                : '—'}
            </span>
            {displayData.au_legal_status && (
              <>
                <span style={{ color: 'var(--text-dim)' }}> | </span>
                <span style={{ color: 'var(--neon-green)' }}>
                  {displayData.au_legal_status}
                </span>
              </>
            )}
          </div>

          {/* Line 3 — Confidence row (conditional) */}
          {displayData.confidence && (
            <div style={{
              fontFamily: 'var(--font-data)',
              fontSize: 13,
              marginTop: 4,
            }}>
              <span style={{ color: 'var(--neon-cyan)' }}>CONFIDENCE: </span>
              <span style={{
                color: dimConfidence ? 'var(--text-dim)' : confidenceColour(displayData.confidence),
              }}>
                {displayData.confidence.toUpperCase()}{' '}
                {displayData.confidence_score != null
                  ? displayData.confidence_score.toFixed(2)
                  : ''}
              </span>
            </div>
          )}

          {/* CLASSIFICATION LOG heading */}
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 13,
            color: 'var(--neon-cyan)',
            marginTop: 12,
          }}>
            CLASSIFICATION LOG:
          </div>

          {/* Reasoning body */}
          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: 13,
            color: (displayData.signal_type === 'unavailable' || displayData.signal_type === 'llm_offline')
              ? 'var(--neon-amber)'
              : 'var(--text-dim)',
            lineHeight: 1.5,
            flex: 1,
            overflowY: 'auto',
            marginTop: 4,
          }}>
            {displayData.signal_type === 'unavailable'
              ? 'LLM TIMEOUT — ChromaDB match only'
              : (displayData.reasoning || '')}
          </div>
        </div>
      )}
    </div>
  )
}
