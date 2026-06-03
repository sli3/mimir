import React from 'react'

const rowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '2px 12px',
}

const labelStyle = {
  fontFamily: 'var(--font-display)',
  fontSize: 9,
  color: 'var(--text-dim)',
}

const valueStyle = {
  fontFamily: 'var(--font-data)',
  fontSize: 13,
}

export default function SystemStatsPanel({ systemStats }) {
  const sdrStatus = systemStats?.hackrf_status
  const sdrColour = sdrStatus === 'CONNECTED'
    ? '#00ffff'
    : sdrStatus === 'NOT_RESPONDING'
      ? '#ffff00'
      : sdrStatus === 'DISCONNECTED'
        ? '#ff4444'
        : '#ff4444'

  const activeFreq = systemStats?.active_frequency_hz
    ? `${(systemStats.active_frequency_hz / 1e6).toFixed(3)} MHz`
    : '---'

  const scanCount = systemStats?.scan_count != null
    ? String(systemStats.scan_count).padStart(5, '0')
    : '00000'

  const queueDepth = systemStats?.queue_depth != null
    ? `${String(systemStats.queue_depth).padStart(3, '0')} / 020`
    : '--- / ---'

  const llmInference = systemStats?.llm_last_inference_ms != null
    ? `${systemStats.llm_last_inference_ms} ms`
    : '--- ms'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
      <div style={rowStyle}>
        <span style={labelStyle}>SDR STATUS</span>
        <span style={{ ...valueStyle, color: sdrColour }}>
          {sdrStatus ? sdrStatus.replace(/_/g, ' ') : 'DISCONNECTED'}
        </span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>ACTIVE FREQ</span>
        <span style={{ ...valueStyle, color: 'var(--neon-cyan)' }}>{activeFreq}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>SCAN COUNT</span>
        <span style={{ ...valueStyle, color: 'var(--neon-green)' }}>{scanCount}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>QUEUE DEPTH</span>
        <span style={{ ...valueStyle, color: 'var(--neon-amber)' }}>{queueDepth}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>LLM INFERENCE</span>
        <span style={{ ...valueStyle, color: 'var(--neon-magenta)' }}>{llmInference}</span>
      </div>
    </div>
  )
}
