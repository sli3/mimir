/** Return the earliest matching signal time from scanResults for signalType. */
function getFirstSeen(signalType, scanResults) {
  if (!signalType || !scanResults) return '---'
  for (let i = scanResults.length - 1; i >= 0; i--) {
    if (scanResults[i].signal_type === signalType) {
      const ts = scanResults[i].timestamp
      if (ts) {
        return new Date(ts).toLocaleTimeString('en-AU', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
      }
    }
  }
  return '---'
}

/** Return whether the status starts with legal, regardless of case. */
function isLegalStatus(status) {
  return /^legal/i.test(status || '')
}

/**
 * Render the SignalDetailsPanel section with legal statuses coloured green.
 * Props: displayed, systemStats, scanResults, operatorState, operatorConfig,
 * aiReasoning, operatorTooltipVisible, setOperatorTooltipVisible, operatorFocused,
 * setOperatorFocused.
 */
export default function SignalDetailsPanel({
  displayed,
  systemStats,
  scanResults,
  operatorState,
  operatorConfig,
  aiReasoning,
  operatorTooltipVisible,
  setOperatorTooltipVisible,
  operatorFocused,
  setOperatorFocused,
}) {
  return (
    <div style={{
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      borderBottom: '1px solid var(--border)',
    }}>
      {/* Header */}
      <div style={{
        height: '28px',
        flexShrink: 0,
        background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border)',
        padding: '0 10px',
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <span style={{
          fontSize: '11px',
          color: 'var(--text-dim)',
          letterSpacing: '2px',
          fontFamily: 'var(--font-data)',
        }}>
          SIGNAL DETAILS
        </span>
          {displayed.signal_type != null ? (
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              border: '1px solid #ff4444',
              background: 'rgba(255, 68, 68, 0.14)',
              boxShadow: '0 0 6px rgba(255, 68, 68, 0.35)',
              padding: '2px 8px',
              fontFamily: 'var(--font-display)',
              fontSize: 10,
              color: '#ff4444',
              letterSpacing: 1,
              animation: 'blink 1.2s infinite',
            }}>
              ◆ <span>ACTIVE</span>
            </div>
          ) : (
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              border: '1px solid var(--text-dim)',
              background: 'transparent',
              padding: '2px 8px',
              fontFamily: 'var(--font-display)',
              fontSize: 10,
              color: 'var(--text-dim)',
              letterSpacing: 1,
            }}>
              ◆ <span>IDLE</span>
            </div>
          )}
      </div>

      {/* Body */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '8px 10px',
        display: 'flex',
        flexDirection: 'column',
        gap: '0',
      }}>
        {(() => {
          const isConfirmedDecode = displayed.source === 'decode'
          const hasRealMeasurement =
            displayed.snr_db != null &&
            displayed.bandwidth_hz != null &&
            displayed.bandwidth_hz > 0
          const dimConfidence = !isConfirmedDecode && !hasRealMeasurement
          return [
          { label: 'DEVICE', value: systemStats?.current_device_display || '---', color: 'var(--neon-cyan)' },
          { label: 'FREQUENCY', value: displayed.freq_hz != null ? (displayed.freq_hz / 1e6).toFixed(3) + ' MHz' : (systemStats?.active_frequency_hz ? (systemStats.active_frequency_hz / 1e6).toFixed(3) + ' MHz' : '---'), color: 'var(--neon-cyan)' },
          { label: 'CLASSIFICATION', value: displayed.signal_type ? displayed.signal_type.toUpperCase() : '---', color: 'var(--neon-cyan)' },
          { label: 'CONFIDENCE', value: displayed.confidence_score != null ? (displayed.confidence_score * 100).toFixed(0) + '%' : '---', color: dimConfidence ? 'var(--text-dim)' : 'var(--neon-green)' },
          { label: 'POWER', value: displayed.peak_power_db != null ? displayed.peak_power_db.toFixed(1) + ' dBFS' : '---', color: 'var(--neon-amber)' },
          { label: 'SNR', value: displayed.snr_db != null ? displayed.snr_db.toFixed(1) + ' dB' : '---', color: 'var(--neon-green)' },
          { label: 'THRESHOLD', value: displayed.signal_threshold_db != null ? displayed.signal_threshold_db.toFixed(1) + ' dB' : '---', color: 'var(--text-dim)' },
          { label: 'SNR MARGIN', value: displayed.snr_margin_db != null ? `${displayed.snr_margin_db >= 0 ? '+' : ''}${displayed.snr_margin_db.toFixed(1)} dB` : '---', color: displayed.snr_margin_db != null && displayed.snr_margin_db >= 0 ? 'var(--neon-green)' : 'var(--neon-amber)' },
          { label: 'BANDWIDTH', value: displayed.bandwidth_hz != null && displayed.bandwidth_hz > 0 ? (displayed.bandwidth_hz / 1e6).toFixed(3) + ' MHz' : '---', color: 'var(--text-primary)' },
          { label: 'SPECTRAL FLATNESS', value: displayed.spectral_flatness != null ? displayed.spectral_flatness.toFixed(3) : '---', color: 'var(--text-primary)' },
          { label: 'CHROMA DISTANCE', value: displayed.chroma_distance != null ? displayed.chroma_distance.toFixed(3) : '---', color: 'var(--neon-magenta)' },
          { label: 'AU LEGAL', value: displayed.au_legal_status || '---', color: isLegalStatus(displayed.au_legal_status) ? 'var(--neon-green)' : 'var(--neon-red)' },
          { label: 'FIRST SEEN', value: getFirstSeen(displayed.signal_type, scanResults), color: 'var(--text-dim)' },
          { label: 'LAST SEEN', value: displayed.timestamp ? new Date(displayed.timestamp).toLocaleTimeString('en-AU', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '---', color: 'var(--neon-green)' },
        ].map((row, i) => (
          <div key={i}>
            <div style={{
              display: 'flex',
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              borderBottom: '1px solid #0F2030',
              padding: '5px 0',
            }}>
              <span style={{
                fontSize: '10px',
                color: 'var(--text-dim)',
                letterSpacing: '1px',
                textTransform: 'uppercase',
                fontFamily: 'var(--font-data)',
                flexShrink: 0,
              }}>
                {row.label}
              </span>
              <span style={{
                fontSize: '13px',
                fontWeight: 'bold',
                color: row.color,
                fontFamily: 'var(--font-data)',
                flexShrink: 0,
                textAlign: 'right',
              }}>
                {row.value}
              </span>
            </div>
            {row.label === 'CONFIDENCE' && displayed.confidence_score != null && (
              <div style={{
                width: '100%',
                height: '3px',
                background: '#0F2030',
                marginTop: '2px',
              }}>
                <div style={{
                  width: (displayed.confidence_score * 100) + '%',
                  height: '100%',
                  background: dimConfidence ? 'var(--text-dim)' : 'var(--neon-green)',
                }} />
              </div>
            )}
          </div>
        ))
        })()}
        <div style={{
        borderTop: '1px solid #0F2030',
          marginTop: '8px',
          paddingTop: '8px',
          display: 'flex',
          flexDirection: 'row',
          alignItems: 'center',
          gap: '10px',
          height: '28px',
        }}>
          <div
            tabIndex={0}
            aria-label={`OPERATOR status: ${operatorState.toLowerCase()}${aiReasoning?.reasoning ? `. ${aiReasoning.reasoning}` : ''}`}
            onMouseEnter={() => setOperatorTooltipVisible(true)}
            onMouseLeave={() => setOperatorTooltipVisible(false)}
            onFocus={() => {
              setOperatorFocused(true)
              setOperatorTooltipVisible(true)
            }}
            onBlur={() => {
              setOperatorFocused(false)
              setOperatorTooltipVisible(false)
            }}
            style={{
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              gap: '10px',
              position: 'relative',
              outline: operatorFocused ? '1px solid var(--neon-cyan)' : 'none',
              outlineOffset: '2px',
              cursor: operatorState !== 'MONITORING' ? 'help' : 'default',
            }}
          >
            <div style={{
              width: '28px',
              height: '28px',
              border: `1px solid ${operatorConfig.opColor}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '9px',
              color: operatorConfig.opColor,
              letterSpacing: '1px',
              fontFamily: 'var(--font-data)',
            }}>
              OP
            </div>
            <span style={{
              fontSize: '11px',
              color: operatorConfig.color,
              fontFamily: 'var(--font-data)',
            }}>
              {operatorConfig.label}
            </span>
            {operatorTooltipVisible && operatorState !== 'MONITORING' && aiReasoning?.reasoning && (
              <div style={{
                position: 'absolute',
                bottom: '100%',
                left: 0,
                marginBottom: '8px',
                width: '320px',
                padding: '8px 10px',
                background: 'var(--bg-header)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontSize: '11px',
                fontFamily: 'var(--font-data)',
                lineHeight: '1.4',
                zIndex: 10,
                pointerEvents: 'none',
                boxShadow: '0 0 8px rgba(0,0,0,0.5)',
              }}>
                {aiReasoning.reasoning}
              </div>
            )}
          </div>
          <span style={{
            marginLeft: 'auto',
            fontSize: '10px',
            color: 'var(--neon-red)',
            letterSpacing: '1px',
            fontFamily: 'var(--font-data)',
            visibility: operatorState === 'ANOMALY' ? 'visible' : 'hidden',
          }}>
            ⚠ ANOMALY
          </span>
        </div>
      </div>
    </div>
  )
}
