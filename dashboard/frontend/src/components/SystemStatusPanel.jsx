import StatCell from './StatCell.jsx'

/** Return the display colour for the SDR connection status. */
function getSdrColour(status) {
  if (status === 'CONNECTED') return 'var(--neon-green)'
  if (status === 'NOT_RESPONDING') return 'var(--neon-amber)'
  return 'var(--neon-red)'
}

/**
 * Render system statistics in three rows of labelled stat cells.
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
            <StatCell
              label="SDR STATUS"
              value={systemStats?.hackrf_status?.replace(/_/g, ' ') || 'DISCONNECTED'}
              colour={getSdrColour(systemStats?.hackrf_status)}
            />
            <StatCell
              label="ACTIVE FREQ"
              value={systemStats?.active_frequency_hz
                  ? (systemStats.active_frequency_hz / 1e6).toFixed(3) + ' MHz'
                  : '---'}
              colour={'var(--neon-cyan)'}
            />
          </div>

          {/* Row 2 — SCAN COUNT | BACKLOG | IN QUEUE */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '4px' }}>
            <StatCell
              label="SCAN COUNT"
              value={String(systemStats?.scan_count ?? 0).padStart(5, '0')}
              colour={'var(--neon-amber)'}
            />
            <StatCell
              label="BACKLOG"
              value={String(systemStats?.last_backlog ?? 0).padStart(3, '0')}
              colour={'var(--neon-amber)'}
            />
            <StatCell
              label="IN QUEUE"
              value={String(systemStats?.queue_depth ?? 0).padStart(3, '0')}
              colour={'var(--neon-amber)'}
            />
          </div>

          {/* Row 3 — LLM INFERENCE | CLASSIFIED */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
            <StatCell
              label="LLM INFERENCE"
              value={systemStats?.llm_last_inference_ms != null
                  ? Math.round(systemStats.llm_last_inference_ms) + ' ms'
                  : '--- ms'}
              colour={'var(--neon-magenta)'}
            />
            <StatCell
              label="CLASSIFIED"
              value={String(systemStats?.llm_call_count ?? 0).padStart(5, '0')}
              colour={'var(--neon-magenta)'}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
