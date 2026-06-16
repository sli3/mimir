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

export default function AIReasoningPanel({ aiReasoning }) {
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
          fontSize: 9,
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
          gap: 6,
          height: '100%',
        }}>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 9,
            color: 'var(--neon-cyan)',
          }}>
            {displayData.freq_hz
              ? `${(displayData.freq_hz / 1e6).toFixed(3)} MHz`
              : '—'}
          </div>

          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: 14,
            color: 'var(--neon-cyan)',
            letterSpacing: 2,
          }}>
            {displayData.signal_type === 'unavailable'
              ? 'TIMEOUT'
              : (displayData.signal_type || '').toUpperCase()}
          </div>

          {displayData.confidence && (
            <div style={{
              fontFamily: 'var(--font-data)',
              fontSize: 11,
              color: confidenceColour(displayData.confidence),
            }}>
              {displayData.confidence.toUpperCase()}{'  '}
              {displayData.confidence_score != null
                ? displayData.confidence_score.toFixed(2)
                : ''}
            </div>
          )}

          {displayData.au_legal_status && (
            <div style={{
              fontFamily: 'var(--font-data)',
              fontSize: 10,
              color: 'var(--neon-green)',
              opacity: 0.7,
            }}>
              {displayData.au_legal_status}
            </div>
          )}

          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: 9,
            color: 'var(--text-dim)',
            opacity: 0.5,
            marginBottom: 4,
          }}>
            {formatTimestamp(displayData.timestamp)}
          </div>

          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: 10,
            color: displayData.signal_type === 'unavailable'
              ? 'var(--neon-amber)'
              : 'var(--text-dim)',
            lineHeight: 1.5,
            flex: 1,
            overflowY: 'auto',
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
