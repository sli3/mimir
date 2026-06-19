import React from 'react'

const FREQ_CONFIGS = [
  { freq_hz: 98000000,   label: '98.0 MHz',    name: 'FM BROADCAST', colourVar: '--neon-cyan'    },
  { freq_hz: 145175000,  label: '145.175 MHz',  name: 'APRS',         colourVar: '--neon-green'  },
  { freq_hz: 915000000,  label: '915.0 MHz',    name: 'ISM / LoRa',   colourVar: '--neon-amber'  },
  { freq_hz: 1090000000, label: '1090.0 MHz',   name: 'ADS-B',        colourVar: '--neon-magenta'},
]

function latestForFreq(scanResults, freqHz) {
  if (!scanResults || scanResults.length === 0) return null
  for (const r of scanResults) {
    if (r.center_freq_hz === freqHz) return r
  }
  return null
}

export default function FrequencyList({ scanResults, focusedFreq, focusFrequency }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {FREQ_CONFIGS.map((cfg) => {
        const isActive = cfg.freq_hz === focusedFreq
        const latest = latestForFreq(scanResults, cfg.freq_hz)
        const colour = `var(${cfg.colourVar})`

        return (
          <div
            key={cfg.freq_hz}
            onClick={() => focusFrequency(cfg.freq_hz)}
            data-active={isActive ? 'true' : undefined}
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 12px',
              cursor: 'pointer',
              borderLeft: isActive ? '2px solid var(--border-active)' : '2px solid transparent',
              background: isActive ? 'rgba(0,255,255,0.05)' : 'transparent',
            }}
          >
            <div>
              <div style={{
                fontFamily: 'var(--font-display)',
                fontSize: 9,
                color: colour,
                marginBottom: 2,
              }}>
                {cfg.label}
              </div>
              <div style={{
                fontFamily: 'var(--font-data)',
                fontSize: 12,
                color: 'var(--text-dim)',
              }}>
                {cfg.name}
              </div>
            </div>
            {latest && (
              <div style={{
                fontFamily: 'var(--font-data)',
                fontSize: 12,
                color: colour,
                textAlign: 'right',
              }}>
                <div>{latest.signal_type}</div>
                <div>{latest.confidence_score != null ? Math.round(latest.confidence_score * 100) + '%' : '---'}</div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
