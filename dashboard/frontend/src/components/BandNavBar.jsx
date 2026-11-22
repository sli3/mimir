import React from 'react'
import { BAND_GROUPS } from '../constants/bands.js'
import CaptureButton from './CaptureButton.jsx'
import RecordButton from './RecordButton.jsx'

/**
 * Render the BandNavBar section.
 * Props: focusedFreq, focusFrequency, unsupportedBands, adsbAircraftList,
 * adsbAircraftHistory, customInput, setCustomInput, handleKeyDown, handleTune,
 * handleCaptureClick, capturePending, recording, handleRecordClick, recordElapsedSec,
 * recordWarning, recordResult (successful saves include a cap_reached flag).
 */
export default function BandNavBar({
  focusedFreq,
  focusFrequency,
  unsupportedBands,
  adsbAircraftList,
  adsbAircraftHistory,
  customInput,
  setCustomInput,
  handleKeyDown,
  handleTune,
  handleCaptureClick,
  capturePending,
  recording,
  handleRecordClick,
  recordElapsedSec,
  recordWarning,
  recordResult,
}) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'row',
      alignItems: 'center',
      height: '56px',
      flexShrink: 0,
      background: 'var(--bg-header)',
      borderBottom: '1px solid var(--border)',
      padding: '0 8px',
      gap: '0px',
    }}>
      {BAND_GROUPS.map((group, groupIdx) => (
        <React.Fragment key={group.label}>
          {groupIdx > 0 && (
            <div style={{
              width: '1px',
              background: 'var(--border)',
              alignSelf: 'stretch',
              margin: '4px 8px',
            }} />
          )}
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
          }}>
            <span style={{
              fontFamily: 'var(--font-data)',
              fontSize: '9px',
              color: 'var(--text-dim)',
              letterSpacing: '1px',
              textTransform: 'uppercase',
              marginBottom: '2px',
              whiteSpace: 'nowrap',
            }}>
              {group.label}
            </span>
            <div style={{
              display: 'flex',
              flexDirection: 'row',
              gap: '4px',
            }}>
              {group.bands.map((band) => {
                // Exact match only — custom frequencies must not highlight named band buttons.
                // isTuned() with its 2 MHz default margin causes adjacent bands (e.g. AVIATION
                // at 127 MHz and ACARS at 129.125 MHz) to both light up for a custom input.
                const active = focusedFreq === band.freq_hz
                const hasAdsb = band.label === 'ADS-B' && (adsbAircraftList.length > 0 || (adsbAircraftHistory && adsbAircraftHistory.length > 0))
                // Phase 38 — grey out bands the active device cannot
                // physically receive. Empty map (HackRF / pre-first-stats)
                // means everything renders exactly as before.
                const unsupportedReason = unsupportedBands[band.band_key]
                const isUnsupported = unsupportedReason != null
                // Phase 38-Hotfix-1: no `disabled` attribute here on
                // purpose. Native `title` tooltips do not fire on
                // HTML disabled controls (the browser removes them
                // from hit-testing, so mouseover never fires). The
                // tooltip IS the reason this row is greyed, so it
                // must be visible on hover. Click is blocked by
                // the onClick omission above; do not re-add
                // `disabled` here.
                return (
                  <button
                    key={band.freq_hz}
                    onClick={isUnsupported ? undefined : () => focusFrequency(band.freq_hz)}
                    title={isUnsupported ? unsupportedReason : undefined}
                    data-unsupported={isUnsupported ? 'true' : undefined}
                    style={{
                      fontFamily: 'monospace',
                      fontSize: '12px',
                      padding: '2px 6px',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      background: isUnsupported ? 'transparent' : (active ? 'rgba(0,255,255,0.07)' : 'transparent'),
                      cursor: isUnsupported ? 'not-allowed' : 'pointer',
                      letterSpacing: '1px',
                      border: isUnsupported ? '1px solid var(--border)' : (active ? '1px solid var(--neon-cyan)' : '1px solid var(--border)'),
                      color: isUnsupported ? 'var(--text-dim)' : (active ? 'var(--neon-cyan)' : 'var(--text-dim)'),
                      opacity: isUnsupported ? 0.35 : 1,
                    }}
                  >
                    <span>{band.label}{hasAdsb ? ' ●' : ''}</span>
                    <span style={{
                      fontSize: '11px',
                      color: 'var(--text-dim)',
                      fontFamily: 'var(--font-data)',
                    }}>
                      {(band.freq_hz / 1e6).toFixed(3) + ' MHz'}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        </React.Fragment>
      ))}
      <div style={{
        marginLeft: 'auto',
        display: 'flex',
        flexDirection: 'row',
        gap: '6px',
        alignItems: 'center',
      }}>
        <span style={{
          fontSize: '11px',
          color: 'var(--text-dim)',
          letterSpacing: '1px',
          fontFamily: 'var(--font-data)',
        }}>
          CUSTOM MHz
        </span>
        <input
          type="text"
          placeholder="e.g. 162.025"
          value={customInput}
          onChange={(e) => setCustomInput(e.target.value)}
          onKeyDown={handleKeyDown}
          style={{
            background: 'var(--bg-header)',
            border: '1px solid rgba(0,255,255,0.3)',
            color: 'var(--neon-cyan)',
            fontFamily: 'monospace',
            fontSize: '12px',
            padding: '3px 8px',
            width: '100px',
            outline: 'none',
          }}
        />
        <button
          onClick={handleTune}
          style={{
            border: '1px solid var(--neon-cyan)',
            color: 'var(--neon-cyan)',
            background: 'rgba(0,255,255,0.1)',
            fontFamily: 'monospace',
            fontSize: '12px',
            padding: '3px 8px',
            cursor: 'pointer',
          }}
        >
          TUNE ▶
        </button>
        <CaptureButton onClick={handleCaptureClick} pending={capturePending} />
        <RecordButton
          recording={recording}
          onClick={handleRecordClick}
          elapsedSec={recordElapsedSec}
          warning={recordWarning}
        />
        {recordResult && !recording && (
          <span
            data-testid="record-result"
            style={{
              fontFamily: 'var(--font-data)',
              fontSize: '11px',
              letterSpacing: '1px',
              color: recordResult.status === 'ok'
                ? 'var(--neon-cyan)'
                : 'var(--neon-red)',
              whiteSpace: 'nowrap',
            }}
          >
            {recordResult.status === 'ok'
              ? `Recorded ${recordResult.duration_sec.toFixed(1)}s / ${recordResult.cycle_count} cycles${recordResult.cap_reached ? ' (stopped at memory cap)' : ''}`
              : `Recording failed: ${recordResult.cause}`}
          </span>
        )}
      </div>
    </div>
  )
}
