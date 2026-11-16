/** Return the display colour for the SDR connection status. */
function getSdrColour(status) {
  if (status === 'CONNECTED') return 'var(--neon-green)'
  if (status === 'NOT_RESPONDING') return 'var(--neon-amber)'
  return 'var(--neon-red)'
}

/**
 * Render the SystemStatusPanel section.
 * Props: systemStats.
 */
export default function SystemStatusPanel({ systemStats }) {
  return (
    <div style={{ flexShrink: 0 }}>
      <div style={{
        height: '28px',
        background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border)',
        padding: '0 10px',
        display: 'flex',
        alignItems: 'center',
      }}>
        <span style={{
          fontSize: '11px',
          color: 'var(--neon-cyan)',
          letterSpacing: '2px',
          fontFamily: 'var(--font-data)',
        }}>
          SYSTEM STATUS
        </span>
      </div>
      <div style={{ padding: '4px' }}>
        <div style={{
          display: 'grid',
          gridTemplateRows: 'auto auto auto',
          gap: '2px',
          alignContent: 'start',
          overflow: 'hidden',
          height: '115px',
        }}>
          {/* Row 1 — SDR STATUS | ACTIVE FREQ */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
            <div style={{
              border: '1px solid var(--border)',
              background: 'rgba(0,255,255,0.03)',
              borderRadius: '2px',
              padding: '2px 6px',
              display: 'flex',
              flexDirection: 'column',
              gap: '1px',
            }}>
              <span style={{
                fontFamily: 'var(--font-display)',
                fontSize: '9px',
                color: 'var(--text-dim)',
                letterSpacing: '1px',
                textTransform: 'uppercase',
              }}>
                SDR STATUS
              </span>
              <span style={{
                fontFamily: 'var(--font-data)',
                fontSize: '11px',
                color: getSdrColour(systemStats?.hackrf_status),
              }}>
                {systemStats?.hackrf_status?.replace(/_/g, ' ') || 'DISCONNECTED'}
              </span>
            </div>
            <div style={{
              border: '1px solid var(--border)',
              background: 'rgba(0,255,255,0.03)',
              borderRadius: '2px',
              padding: '2px 6px',
              display: 'flex',
              flexDirection: 'column',
              gap: '1px',
            }}>
              <span style={{
                fontFamily: 'var(--font-display)',
                fontSize: '9px',
                color: 'var(--text-dim)',
                letterSpacing: '1px',
                textTransform: 'uppercase',
              }}>
                ACTIVE FREQ
              </span>
              <span style={{
                fontFamily: 'var(--font-data)',
                fontSize: '11px',
                color: 'var(--neon-cyan)',
              }}>
                {systemStats?.active_frequency_hz
                  ? (systemStats.active_frequency_hz / 1e6).toFixed(3) + ' MHz'
                  : '---'}
              </span>
            </div>
          </div>

          {/* Row 2 — SCAN COUNT | BACKLOG | IN QUEUE */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '4px' }}>
            <div style={{
              border: '1px solid var(--border)',
              background: 'rgba(0,255,255,0.03)',
              borderRadius: '2px',
              padding: '2px 6px',
              display: 'flex',
              flexDirection: 'column',
              gap: '1px',
            }}>
              <span style={{
                fontFamily: 'var(--font-display)',
                fontSize: '9px',
                color: 'var(--text-dim)',
                letterSpacing: '1px',
                textTransform: 'uppercase',
              }}>
                SCAN COUNT
              </span>
              <span style={{
                fontFamily: 'var(--font-data)',
                fontSize: '11px',
                color: 'var(--neon-amber)',
              }}>
                {String(systemStats?.scan_count ?? 0).padStart(5, '0')}
              </span>
            </div>
            <div style={{
              border: '1px solid var(--border)',
              background: 'rgba(0,255,255,0.03)',
              borderRadius: '2px',
              padding: '2px 6px',
              display: 'flex',
              flexDirection: 'column',
              gap: '1px',
            }}>
              <span style={{
                fontFamily: 'var(--font-display)',
                fontSize: '9px',
                color: 'var(--text-dim)',
                letterSpacing: '1px',
                textTransform: 'uppercase',
              }}>
                BACKLOG
              </span>
              <span style={{
                fontFamily: 'var(--font-data)',
                fontSize: '11px',
                color: 'var(--neon-amber)',
              }}>
                {String(systemStats?.last_backlog ?? 0).padStart(3, '0')}
              </span>
            </div>
            <div style={{
              border: '1px solid var(--border)',
              background: 'rgba(0,255,255,0.03)',
              borderRadius: '2px',
              padding: '2px 6px',
              display: 'flex',
              flexDirection: 'column',
              gap: '1px',
            }}>
              <span style={{
                fontFamily: 'var(--font-display)',
                fontSize: '9px',
                color: 'var(--text-dim)',
                letterSpacing: '1px',
                textTransform: 'uppercase',
              }}>
                IN QUEUE
              </span>
              <span style={{
                fontFamily: 'var(--font-data)',
                fontSize: '11px',
                color: 'var(--neon-amber)',
              }}>
                {String(systemStats?.queue_depth ?? 0).padStart(3, '0')}
              </span>
            </div>
          </div>

          {/* Row 3 — LLM INFERENCE | CLASSIFIED */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
            <div style={{
              border: '1px solid var(--border)',
              background: 'rgba(0,255,255,0.03)',
              borderRadius: '2px',
              padding: '2px 6px',
              display: 'flex',
              flexDirection: 'column',
              gap: '1px',
            }}>
              <span style={{
                fontFamily: 'var(--font-display)',
                fontSize: '9px',
                color: 'var(--text-dim)',
                letterSpacing: '1px',
                textTransform: 'uppercase',
              }}>
                LLM INFERENCE
              </span>
              <span style={{
                fontFamily: 'var(--font-data)',
                fontSize: '11px',
                color: 'var(--neon-magenta)',
              }}>
                {systemStats?.llm_last_inference_ms != null
                  ? Math.round(systemStats.llm_last_inference_ms) + ' ms'
                  : '--- ms'}
              </span>
            </div>
            <div style={{
              border: '1px solid var(--border)',
              background: 'rgba(0,255,255,0.03)',
              borderRadius: '2px',
              padding: '2px 6px',
              display: 'flex',
              flexDirection: 'column',
              gap: '1px',
            }}>
              <span style={{
                fontFamily: 'var(--font-display)',
                fontSize: '9px',
                color: 'var(--text-dim)',
                letterSpacing: '1px',
                textTransform: 'uppercase',
              }}>
                CLASSIFIED
              </span>
              <span style={{
                fontFamily: 'var(--font-data)',
                fontSize: '11px',
                color: 'var(--neon-magenta)',
              }}>
                {String(systemStats?.llm_call_count ?? 0).padStart(5, '0')}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
