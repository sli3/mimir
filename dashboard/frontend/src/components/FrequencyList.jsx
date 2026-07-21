import React from 'react'

/** Frequency configuration for the sidebar band list.
 *  Seven AU-legal frequencies, each with a display label, name,
 *  CSS colour variable, and BAND_PROFILES band_key.  Kept in sync
 *  with STRIP_CONFIGS (WaterfallPanel.jsx) and BAND_GROUPS (App.jsx).
 *  Ordered by frequency ascending.  AIS uses 162.000 MHz (dual-channel
 *  centre) to match BAND_PROFILES in shared_state.py (Phase 15b).
 *
 *  NOTE: If adding a new band, update FREQ_CONFIGS here (including
 *  its band_key, which must match a BAND_PROFILES key so the
 *  Phase 38 unsupported-band greying can find it), STRIP_CONFIGS in
 *  WaterfallPanel.jsx, BAND_GROUPS and OVERVIEW_BANDS in App.jsx,
 *  and FREQ_COLOUR_MAP + freqLabel() in SignalHistoryLog.jsx. */
const FREQ_CONFIGS = [
  { freq_hz: 98000000,   label: '98.0 MHz',     name: 'FM BROADCAST', colourVar: '--neon-cyan',    band_key: 'fm_broadcast' },
  { freq_hz: 127000000,  label: '127.0 MHz',    name: 'AVIATION VHF', colourVar: '--neon-cyan',    band_key: 'aviation' },
  { freq_hz: 129125000,  label: '129.125 MHz',  name: 'ACARS',        colourVar: '--neon-amber',   band_key: 'acars' },
  { freq_hz: 145175000,  label: '145.175 MHz',  name: 'APRS',         colourVar: '--neon-green',   band_key: 'aprs' },
  { freq_hz: 162000000,  label: '162.000 MHz',  name: 'AIS',          colourVar: '--neon-red',     band_key: 'ais' },
  { freq_hz: 915000000,  label: '915.0 MHz',    name: 'ISM / LoRa',   colourVar: '--neon-amber',   band_key: 'ism' },
  { freq_hz: 1090000000, label: '1090.0 MHz',   name: 'ADS-B',        colourVar: '--neon-magenta', band_key: 'adsb' },
]

function latestForFreq(scanResults, freqHz) {
  if (!scanResults || scanResults.length === 0) return null
  for (const r of scanResults) {
    if (r.center_freq_hz === freqHz) return r
  }
  return null
}

export default function FrequencyList({ scanResults, focusedFreq, focusFrequency, unsupportedBands = {} }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {FREQ_CONFIGS.map((cfg) => {
        const isActive = cfg.freq_hz === focusedFreq
        const latest = latestForFreq(scanResults, cfg.freq_hz)
        const colour = `var(${cfg.colourVar})`
        // Phase 38 — backend-supplied unsupported-band map, keyed by
        // band_key. Empty object for HackRF / pre-first-stats: every band
        // is supported, and the row renders exactly as it did before.
        const reason = unsupportedBands[cfg.band_key]
        const isUnsupported = reason != null

        // Style the row: unsupported = dimmed, no cursor, no onClick,
        // no latest scan readout. Supported = unchanged.
        const rowStyle = isUnsupported
          ? {
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 12px',
              cursor: 'not-allowed',
              borderLeft: '2px solid transparent',
              background: 'transparent',
              opacity: 0.35,
            }
          : {
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 12px',
              cursor: 'pointer',
              borderLeft: isActive ? '2px solid var(--border-active)' : '2px solid transparent',
              background: isActive ? 'rgba(0,255,255,0.05)' : 'transparent',
            }

        return (
          <div
            key={cfg.freq_hz}
            onClick={isUnsupported ? undefined : () => focusFrequency(cfg.freq_hz)}
            data-active={!isUnsupported && isActive ? 'true' : undefined}
            data-unsupported={isUnsupported ? 'true' : undefined}
            title={isUnsupported ? reason : undefined}
            style={rowStyle}
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
            {!isUnsupported && latest && (
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
