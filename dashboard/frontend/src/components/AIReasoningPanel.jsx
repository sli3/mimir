import { useState, useEffect, useRef } from 'react'

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
 *  The component fades out (opacity 0→1 transition) when the reasoning
 *  entry changes, unless a pin override supresses the transition.
 *
 *  @param {{ aiReasoning: object, isPinned?: boolean }} props
 *  @param {object} props.aiReasoning — the reasoning data object (keys:
 *    freq_hz, signal_type, confidence, confidence_score, au_legal_status,
 *    reasoning, timestamp)
 *  @param {boolean} [props.isPinned=false] — if true and signal_type is set,
 *    renders a boxed ◆ PINNED badge with timestamp in amber, and the component
 *    key in App.jsx forces remount on pin toggle */
export default function AIReasoningPanel({ aiReasoning, isPinned = false }) {
  const [opacity, setOpacity] = useState(1)
  const [displayData, setDisplayData] = useState(null)
  const prevReasoningRef = useRef(null)

  useEffect(() => {
    if (!aiReasoning || aiReasoning.signal_type === null) {
      setDisplayData(null)
      setOpacity(1)
      prevReasoningRef.current = null
      return
    }

    if (prevReasoningRef.current === null) {
      setDisplayData(aiReasoning)
      setOpacity(1)
      prevReasoningRef.current = aiReasoning
      return
    }

    if (aiReasoning.timestamp === prevReasoningRef.current.timestamp) return

    setOpacity(0)
    const timer = setTimeout(() => {
      setDisplayData(aiReasoning)
      setOpacity(1)
    }, 200)
    prevReasoningRef.current = aiReasoning

    return () => clearTimeout(timer)
  }, [aiReasoning])

  const placeholder = !displayData || !displayData.signal_type

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
              <div style={{
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
              }}>
                ◆ PINNED
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
                fontSize: 10,
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
              {displayData.signal_type === 'unavailable'
                ? 'TIMEOUT'
                : (displayData.signal_type || '').toUpperCase()}
            </span>
            <span style={{ color: 'var(--text-dim)' }}> : </span>
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
              <span style={{ color: 'var(--text-dim)' }}>CONFIDENCE: </span>
              <span style={{
                color: confidenceColour(displayData.confidence),
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
            fontSize: 11,
            color: 'var(--text-dim)',
            marginBottom: 4,
          }}>
            CLASSIFICATION LOG
          </div>

          {/* Reasoning body */}
          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: 13,
            color: displayData.signal_type === 'unavailable'
              ? 'var(--neon-amber)'
              : 'var(--text-dim)',
            lineHeight: 1.5,
            flex: 1,
            overflowY: 'auto',
            marginTop: 8,
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
