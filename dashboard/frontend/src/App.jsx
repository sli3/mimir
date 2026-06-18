import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useSocket } from './hooks/useSocket.js'
import WaterfallPanel from './components/WaterfallPanel.jsx'
import SpectrometerBar from './components/SpectrometerBar.jsx'
import AcarsMessagePanel from './components/AcarsMessagePanel.jsx'
import AisVesselPanel from './components/AisVesselPanel.jsx'
import AdsbAircraftPanel from './components/AdsbAircraftPanel.jsx'
import SignalHistoryLog from './components/SignalHistoryLog.jsx'
import AIReasoningPanel from './components/AIReasoningPanel.jsx'

const INITIAL_AI_REASONING = {
  freq_hz: null,
  signal_type: null,
  confidence: null,
  confidence_score: null,
  au_legal_status: null,
  reasoning: null,
  timestamp: null,
  peak_power_db: null,
  snr_db: null,
  bandwidth_hz: null,
  spectral_flatness: null,
  chroma_distance: null,
  signal_threshold_db: null,
  snr_margin_db: null,
}

const BAND_GROUPS = [
  {
    label: 'BROADCAST',
    bands: [
      { name: 'FM BROADCAST', freq_hz: 98000000, label: 'FM' },
    ],
  },
  {
    label: 'AVIATION BAND',
    bands: [
      { name: 'AVIATION', freq_hz: 127000000, label: 'AVIATION' },
      { name: 'ACARS', freq_hz: 129125000, label: 'ACARS' },
      { name: 'ADS-B', freq_hz: 1090000000, label: 'ADS-B' },
    ],
  },
  {
    label: 'DATA / IoT',
    bands: [
      { name: 'APRS', freq_hz: 145175000, label: 'APRS' },
      { name: 'ISM', freq_hz: 915000000, label: 'ISM' },
    ],
  },
]

const OVERVIEW_BANDS = [
  { name: 'FM BROADCAST', freq_hz: 98000000 },
  { name: 'APRS',         freq_hz: 145175000 },
  { name: 'ISM / LoRa',   freq_hz: 915000000 },
  { name: 'ADS-B',        freq_hz: 1090000000 },
]

function useClock() {
  const [time, setTime] = useState(new Date())
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])
  return time.toLocaleTimeString('en-AU', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function useFrozenDisplay(aiReasoning) {
  const frozenRef = useRef(null)
  const timerRef = useRef(null)
  const [displayed, setDisplayed] = useState(INITIAL_AI_REASONING)

  useEffect(() => {
    if (!aiReasoning || aiReasoning.signal_type === null) {
      return
    }

    const shouldUpdate =
      aiReasoning.signal_type !== frozenRef.current?.signal_type ||
      timerRef.current === null

    if (shouldUpdate) {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
      frozenRef.current = aiReasoning
      setDisplayed(aiReasoning)
      timerRef.current = setTimeout(() => {
        timerRef.current = null
      }, 8000)
    }

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [aiReasoning])

  return displayed
}

function getSdrColour(status) {
  if (status === 'CONNECTED') return 'var(--neon-green)'
  if (status === 'NOT_RESPONDING') return 'var(--neon-amber)'
  return 'var(--neon-red)'
}

function isTuned(freq, target, margin = 2_000_000) {
  return freq != null && Math.abs(freq - target) <= margin
}

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

export default function App() {
  const socket = useSocket()
  const {
    scanResults,
    spectrumUpdates,
    systemStats,
    focusedFreq,
    focusFrequency,
    aiReasoning,
    acarsMessages,
    aisVessels,
    adsbAircraft,
  } = socket

  const clock = useClock()
  const displayed = useFrozenDisplay(aiReasoning)
  const [customInput, setCustomInput] = useState('')
  /** Pinned AI reasoning entry — set by clicking a row in SignalHistoryLog.
   *  Toggles on/off: clicking the same row unpins, clicking a different row
   *  replaces the pin. Composite identity uses (timestamp + center_freq_hz)
   *  because timestamps alone are not guaranteed unique across frequencies
   *  at scan rate (~4-5 Hz).
   *
   *  TODO: Pin eviction — if the pinned entry scrolls out of scanResults
   *  (capped at 200), the row becomes invisible and the user cannot unpin.
   *  Consider adding an unpin button inside AIReasoningPanel or a timeout.
   *
   *  TODO: Pin survives frequency change — FocusFrequency clears aiReasoning
   *  but not pinnedReasoning. Signal Details shows new band while AI Reasoning
   *  shows old pinned data. Intentional per spec but a UX gap — consider
   *  clearing pin on band change or adding a visual indicator.
   *  @type {{ freq_hz, signal_type, confidence, confidence_score, au_legal_status, reasoning, timestamp } | null} */
  const [pinnedReasoning, setPinnedReasoning] = useState(null)
  /** @type {string|null} — derived pin timestamp for data-pinned attribute matching */
  const pinnedTimestamp = pinnedReasoning ? pinnedReasoning.timestamp : null

  /** Click handler for SignalHistoryLog rows. Toggles pin on/off.
   *  Uses composite identity (timestamp + center_freq_hz) so the user must
   *  click the exact same row to unpin. Spreads INITIAL_AI_REASONING then
   *  overlays entry fields to ensure every display key is present.
   *  @param {{ timestamp: string, center_freq_hz: number, signal_type: string, confidence: string, confidence_score: number, au_legal_status: string, reasoning: string }} entry */
  const handlePinReasoning = useCallback((entry) => {
    setPinnedReasoning((prev) => {
      if (prev && prev.timestamp === entry.timestamp && prev.freq_hz === entry.center_freq_hz) {
        return null
      }
      return {
        ...INITIAL_AI_REASONING,
        freq_hz: entry.center_freq_hz,
        signal_type: entry.signal_type || null,
        confidence: entry.confidence || null,
        confidence_score: entry.confidence_score ?? null,
        au_legal_status: entry.au_legal_status || null,
        reasoning: entry.reasoning || null,
        timestamp: entry.timestamp || null,
      }
    })
  }, [])

  const handleTune = useCallback(() => {
    const val = parseFloat(customInput)
    if (Number.isFinite(val) && val > 0) {
      focusFrequency(val * 1e6)
    }
  }, [customInput, focusFrequency])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter') {
      handleTune()
    }
  }, [handleTune])

  const adsbAircraftList = Object.values(adsbAircraft || {})

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      width: '100vw',
      background: 'var(--bg-root)',
      gap: '2px',
      overflow: 'hidden',
    }}>
      {/* Row 1 — Header bar */}
      <div style={{
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        height: '36px',
        flexShrink: 0,
        background: 'var(--bg-header)',
        borderBottom: '1px solid rgba(0,255,255,0.2)',
        padding: '0 12px',
        gap: '16px',
      }}>
        <span style={{
          fontFamily: "'Press Start 2P', monospace",
          fontSize: '14px',
          color: 'var(--neon-cyan)',
          letterSpacing: '3px',
          fontWeight: 'bold',
        }}>
          MIMIR
        </span>
        <span style={{
          fontSize: '11px',
          color: 'var(--text-dim)',
          letterSpacing: '2px',
        }}>
          PASSIVE RF INTELLIGENCE // ADELAIDE SA
        </span>
        <div style={{
          marginLeft: 'auto',
          display: 'flex',
          flexDirection: 'row',
          alignItems: 'center',
          gap: '16px',
        }}>
          <span style={{
            fontSize: '11px',
            color: 'var(--text-dim)',
            fontFamily: 'var(--font-data)',
          }}>
            {clock}
          </span>
        </div>
      </div>

      {/* Row 2 — Top half */}
      <div style={{
        display: 'flex',
        flexDirection: 'row',
        height: '52vh',
        flexShrink: 0,
        overflow: 'hidden',
      }}>
        {/* Left column */}
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          borderRight: '1px solid var(--border)',
          overflow: 'hidden',
        }}>
          {/* Section A — Band nav bar */}
          <div style={{
            display: 'flex',
            flexDirection: 'row',
            alignItems: 'center',
            height: '48px',
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
                      const active = isTuned(focusedFreq, band.freq_hz)
                      const hasAdsb = band.label === 'ADS-B' && adsbAircraftList.length > 0
                      return (
                        <button
                          key={band.freq_hz}
                          onClick={() => focusFrequency(band.freq_hz)}
                          style={{
                            fontFamily: 'monospace',
                            fontSize: '12px',
                            padding: '3px 8px',
                            background: active ? 'rgba(0,255,255,0.07)' : 'transparent',
                            cursor: 'pointer',
                            letterSpacing: '1px',
                            border: active ? '1px solid var(--neon-cyan)' : '1px solid var(--border)',
                            color: active ? 'var(--neon-cyan)' : 'var(--text-dim)',
                          }}
                        >
                          {band.label}{hasAdsb ? ' ●' : ''}
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
            </div>
          </div>

          {/* Section B — Main waterfall */}
          <div data-testid="waterfall" style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
            <WaterfallPanel
              focusedFreq={focusedFreq}
              focusFrequency={focusFrequency}
              singleBand={true}
            />
          </div>

          {/* Section C — SpectrometerBar */}
          <SpectrometerBar
            spectrumUpdates={spectrumUpdates}
            focusedFreq={focusedFreq}
            focusFrequency={focusFrequency}
          />

          {/* Section D — Mini band overview strip */}
          <div style={{
            display: 'flex',
            flexDirection: 'row',
            height: '44px',
            flexShrink: 0,
            background: 'var(--bg-header)',
            borderTop: '1px solid var(--border)',
          }}>
            {OVERVIEW_BANDS.map((band, idx) => {
              const active = isTuned(focusedFreq, band.freq_hz)
              const now = Date.now()
              const hasRecent = scanResults.some((r) => {
                const ts = r.timestamp ? new Date(r.timestamp).getTime() : 0
                return Math.abs(r.center_freq_hz - band.freq_hz) <= 2_000_000 && (now - ts) < 10000
              })
              return (
                <div
                  key={band.freq_hz}
                  onClick={() => focusFrequency(band.freq_hz)}
                  style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'center',
                    padding: '2px 6px',
                    borderRight: idx < OVERVIEW_BANDS.length - 1 ? '1px solid var(--border)' : 'none',
                    cursor: 'pointer',
                    position: 'relative',
                    overflow: 'hidden',
                    borderTop: active ? '2px solid var(--neon-cyan)' : '2px solid transparent',
                  }}
                >
                  <span style={{
                    fontSize: '9px',
                    color: 'var(--text-dim)',
                    letterSpacing: '1px',
                    textTransform: 'uppercase',
                    fontFamily: 'var(--font-data)',
                  }}>
                    {band.name}
                  </span>
                  <span style={{
                    fontSize: '11px',
                    color: 'var(--text-dim)',
                    marginTop: '1px',
                    fontFamily: 'var(--font-data)',
                  }}>
                    {(band.freq_hz / 1e6).toFixed(3)} MHz
                  </span>
                  <div style={{
                    position: 'absolute',
                    bottom: 0,
                    left: 0,
                    right: 0,
                    height: '3px',
                    background: hasRecent ? 'var(--neon-green)' : '#1A3040',
                  }} />
                </div>
              )
            })}
          </div>
        </div>

        {/* Right column — Signal Details panel */}
        <div style={{
          width: '380px',
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--bg-panel)',
          borderLeft: '1px solid var(--border)',
          overflow: 'hidden',
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
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}>
              {displayed.signal_type != null ? (
                <div style={{
                  display: 'flex',
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: '4px',
                }}>
                  <span style={{
                    fontSize: '8px',
                    color: 'var(--neon-red)',
                    lineHeight: 1,
                    fontFamily: 'var(--font-data)',
                  }}>
                    ●
                  </span>
                  <span style={{
                    fontSize: '11px',
                    color: 'var(--neon-red)',
                    letterSpacing: '1px',
                    fontFamily: 'var(--font-display)',
                    animation: 'blink 1.2s infinite',
                  }}>
                    ACTIVE
                  </span>
                </div>
              ) : (
                <div style={{
                  display: 'flex',
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: '4px',
                }}>
                  <span style={{
                    fontSize: '8px',
                    color: 'var(--text-dim)',
                    lineHeight: 1,
                    fontFamily: 'var(--font-data)',
                  }}>
                    ●
                  </span>
                  <span style={{
                    fontSize: '11px',
                    color: 'var(--text-dim)',
                    letterSpacing: '1px',
                    fontFamily: 'var(--font-display)',
                  }}>
                    IDLE
                  </span>
                </div>
              )}
            </div>
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
            {[
              { label: 'FREQUENCY', value: displayed.freq_hz != null ? (displayed.freq_hz / 1e6).toFixed(3) + ' MHz' : (systemStats?.active_frequency_hz ? (systemStats.active_frequency_hz / 1e6).toFixed(3) + ' MHz' : '---'), color: 'var(--neon-cyan)' },
              { label: 'CLASSIFICATION', value: displayed.signal_type ? displayed.signal_type.toUpperCase() : '---', color: 'var(--neon-cyan)' },
              { label: 'CONFIDENCE', value: displayed.confidence_score != null ? (displayed.confidence_score * 100).toFixed(0) + '%' : '---', color: 'var(--neon-green)' },
              { label: 'POWER', value: displayed.peak_power_db != null ? displayed.peak_power_db.toFixed(1) + ' dBFS' : '---', color: 'var(--neon-amber)' },
              { label: 'SNR', value: displayed.snr_db != null ? displayed.snr_db.toFixed(1) + ' dB' : '---', color: 'var(--neon-green)' },
              { label: 'THRESHOLD', value: displayed.signal_threshold_db != null ? displayed.signal_threshold_db.toFixed(1) + ' dB' : '---', color: 'var(--text-dim)' },
              { label: 'SNR MARGIN', value: displayed.snr_margin_db != null ? `${displayed.snr_margin_db >= 0 ? '+' : ''}${displayed.snr_margin_db.toFixed(1)} dB` : '---', color: displayed.snr_margin_db != null && displayed.snr_margin_db >= 0 ? 'var(--neon-green)' : 'var(--neon-amber)' },
              { label: 'BANDWIDTH', value: displayed.bandwidth_hz != null && displayed.bandwidth_hz > 0 ? (displayed.bandwidth_hz / 1e6).toFixed(3) + ' MHz' : '---', color: 'var(--text-primary)' },
              { label: 'SPECTRAL FLATNESS', value: displayed.spectral_flatness != null ? displayed.spectral_flatness.toFixed(3) : '---', color: 'var(--text-primary)' },
              { label: 'CHROMA DISTANCE', value: displayed.chroma_distance != null ? displayed.chroma_distance.toFixed(3) : '---', color: 'var(--neon-magenta)' },
              { label: 'AU LEGAL', value: displayed.au_legal_status || '---', color: (displayed.au_legal_status || '').includes('LEGAL') ? 'var(--neon-green)' : 'var(--neon-red)' },
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
                      background: 'var(--neon-green)',
                    }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Row 3 — Bottom half */}
      <div style={{
        display: 'flex',
        flexDirection: 'row',
        flex: 1,
        minHeight: 0,
        overflow: 'hidden',
      }}>
        {/* Bottom-left — System & Signal */}
        <div style={{
          flex: 2,
          display: 'flex',
          flexDirection: 'column',
          borderRight: '1px solid var(--border)',
          overflow: 'hidden',
        }}>
          {/* Section A — System Status */}
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
              <div style={{
                marginTop: '8px',
                display: 'flex',
                flexDirection: 'row',
                alignItems: 'center',
                gap: '10px',
                height: '28px',
              }}>
                <div style={{
                  width: '28px',
                  height: '28px',
                  border: '1px solid var(--neon-cyan)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '9px',
                  color: 'var(--neon-cyan)',
                  letterSpacing: '1px',
                  fontFamily: 'var(--font-data)',
                }}>
                  OP
                </div>
                <span style={{
                  fontSize: '11px',
                  color: 'var(--text-dim)',
                  fontFamily: 'var(--font-data)',
                }}>
                  OPERATOR — MONITORING
                </span>
                <span style={{
                  marginLeft: 'auto',
                  fontSize: '10px',
                  color: 'var(--neon-red)',
                  letterSpacing: '1px',
                  fontFamily: 'var(--font-data)',
                  visibility: 'hidden',
                }}>
                  ⚠ ANOMALY
                </span>
              </div>
            </div>
          </div>

          {/* Section B — Signal History */}
          <div style={{
            flex: 1,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}>
            <div style={{
              height: '28px',
              flexShrink: 0,
              background: 'var(--bg-header)',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              padding: '0 10px',
              justifyContent: 'space-between',
            }}>
              <span style={{
                fontSize: '11px',
                color: 'var(--neon-green)',
                letterSpacing: '2px',
                fontFamily: 'var(--font-data)',
              }}>
                SIGNAL HISTORY
              </span>
              <span style={{
                fontSize: '11px',
                color: 'var(--text-dim)',
                fontFamily: 'var(--font-data)',
              }}>
                {scanResults.length} ENTRIES
              </span>
            </div>
            <div style={{
              flex: 1,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
            }}>
              {/* Data rows */}
              <SignalHistoryLog
                scanResults={scanResults}
                onPinReasoning={handlePinReasoning}
                pinnedTimestamp={pinnedTimestamp}
              />
            </div>
          </div>
        </div>

        {/* Bottom-right — AI Reasoning & Decoded Signals */}
        <div style={{
          flex: 3,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          {/* Section A — AI Reasoning */}
          <div style={{ height: '210px', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
            <div style={{
              height: '28px',
              flexShrink: 0,
              background: 'var(--bg-header)',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              padding: '0 10px',
              justifyContent: 'space-between',
            }}>
              <span style={{
                fontSize: '11px',
                color: 'var(--neon-magenta)',
                letterSpacing: '2px',
                fontFamily: 'var(--font-data)',
              }}>
                AI REASONING
              </span>
              <span style={{
                fontSize: '11px',
                color: 'var(--text-dim)',
                letterSpacing: '1px',
                fontFamily: 'var(--font-data)',
              }}>
                HOLDS 8s · UPDATES ON NEW SIGNAL
              </span>
            </div>
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <AIReasoningPanel
                key={pinnedTimestamp || 'live'}
                aiReasoning={pinnedReasoning || aiReasoning}
                isPinned={!!pinnedReasoning}
              />
            </div>
          </div>

          {/* Section B — Decoded Signals */}
          <div style={{
            flex: 1,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}>
            <div style={{
              height: '28px',
              flexShrink: 0,
              background: 'var(--bg-header)',
              borderBottom: '1px solid var(--border)',
              padding: '0 10px',
              display: 'flex',
              alignItems: 'center',
            }}>
              <span style={{
                fontSize: '11px',
                color: 'var(--neon-amber)',
                letterSpacing: '2px',
                fontFamily: 'var(--font-data)',
              }}>
                DECODED SIGNALS
              </span>
            </div>
            <div style={{
              flex: 1,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
            }}>
              {/* SUB-PANEL 1 — ADS-B AIRCRAFT */}
              <div style={{
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                flexDirection: 'column',
                flexShrink: 0,
              }}>
                <div style={{
                  display: 'flex',
                  flexDirection: 'row',
                  padding: '6px 10px',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}>
                  <span style={{
                    fontSize: '11px',
                    color: 'var(--neon-amber)',
                    letterSpacing: '1px',
                    fontFamily: 'var(--font-data)',
                  }}>
                    ADS-B AIRCRAFT
                  </span>
                  <span style={{
                    fontSize: '11px',
                    color: isTuned(focusedFreq, 1090000000) ? 'var(--neon-green)' : 'var(--neon-red)',
                    fontFamily: 'var(--font-data)',
                  }}>
                    {isTuned(focusedFreq, 1090000000)
                      ? '● TUNED 1090.000 MHz'
                      : '● NOT TUNED — 1090.000 MHz'}
                  </span>
                </div>
                <div style={{ padding: '0 10px 8px' }}>
                  {isTuned(focusedFreq, 1090000000) ? (
                    adsbAircraftList.length > 0 ? (
                      <div style={{ height: '100px', overflow: 'auto' }}>
                        <AdsbAircraftPanel
                          adsbAircraft={adsbAircraft}
                          focusedFreq={focusedFreq}
                        />
                      </div>
                    ) : (
                      <div style={{
                        fontSize: '12px',
                        color: 'var(--text-dim)',
                        fontFamily: 'var(--font-data)',
                        padding: '5px 8px',
                      }}>
                        Listening on 1090.000 MHz...
                      </div>
                    )
                  ) : (
                    <div
                      onClick={() => focusFrequency(1090000000)}
                      style={{
                        border: '1px solid rgba(255,68,68,0.3)',
                        background: 'rgba(255,68,68,0.05)',
                        padding: '5px 8px',
                        fontSize: '12px',
                        color: 'var(--neon-red)',
                        letterSpacing: '1px',
                        fontFamily: 'var(--font-data)',
                        cursor: 'pointer',
                      }}
                    >
                      ▸ TUNE TO 1090.000 MHz TO DECODE ADS-B
                    </div>
                  )}
                </div>
              </div>

              {/* SUB-PANEL 2 — ACARS MESSAGES */}
              <div style={{
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                flexDirection: 'column',
                flexShrink: 0,
              }}>
                <div style={{
                  display: 'flex',
                  flexDirection: 'row',
                  padding: '6px 10px',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}>
                  <span style={{
                    fontSize: '11px',
                    color: 'var(--neon-amber)',
                    letterSpacing: '1px',
                    fontFamily: 'var(--font-data)',
                  }}>
                    ACARS MESSAGES
                  </span>
                  <span style={{
                    fontSize: '11px',
                    color: isTuned(focusedFreq, 129125000, 5000) ? 'var(--neon-green)' : 'var(--neon-red)',
                    fontFamily: 'var(--font-data)',
                  }}>
                    {isTuned(focusedFreq, 129125000, 5000)
                      ? '● TUNED 129.125 MHz'
                      : '● NOT TUNED — 129.125 MHz'}
                  </span>
                </div>
                <div style={{ padding: '0 10px 8px' }}>
                  {isTuned(focusedFreq, 129125000, 5000) ? (
                    acarsMessages.length > 0 ? (
                      <div style={{ height: '100px', overflow: 'auto' }}>
                        <AcarsMessagePanel
                          acarsMessages={acarsMessages}
                          focusedFreq={focusedFreq}
                        />
                      </div>
                    ) : (
                      <div style={{
                        fontSize: '12px',
                        color: 'var(--text-dim)',
                        fontFamily: 'var(--font-data)',
                        padding: '5px 8px',
                      }}>
                        Listening on 129.125 MHz...
                      </div>
                    )
                  ) : (
                    <div
                      onClick={() => focusFrequency(129125000)}
                      style={{
                        border: '1px solid rgba(255,68,68,0.3)',
                        background: 'rgba(255,68,68,0.05)',
                        padding: '5px 8px',
                        fontSize: '12px',
                        color: 'var(--neon-red)',
                        letterSpacing: '1px',
                        fontFamily: 'var(--font-data)',
                        cursor: 'pointer',
                      }}
                    >
                      ▸ TUNE TO 129.125 MHz TO DECODE ACARS
                    </div>
                  )}
                </div>
              </div>

              {/* SUB-PANEL 3 — AIS VESSELS */}
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                flexShrink: 0,
              }}>
                <div style={{
                  display: 'flex',
                  flexDirection: 'row',
                  padding: '6px 10px',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}>
                  <span style={{
                    fontSize: '11px',
                    color: 'var(--neon-amber)',
                    letterSpacing: '1px',
                    fontFamily: 'var(--font-data)',
                  }}>
                    AIS VESSELS
                  </span>
                  <span style={{
                    fontSize: '11px',
                    color: isTuned(focusedFreq, 161975000, 100000) ? 'var(--neon-green)' : 'var(--neon-red)',
                    fontFamily: 'var(--font-data)',
                  }}>
                    {isTuned(focusedFreq, 161975000, 100000)
                      ? '● TUNED 161.975 MHz'
                      : '● NOT TUNED — 161.975 MHz'}
                  </span>
                </div>
                <div style={{ padding: '0 10px 8px' }}>
                  {isTuned(focusedFreq, 161975000, 100000) ? (
                    aisVessels.length > 0 ? (
                      <div style={{ height: '100px', overflow: 'auto' }}>
                        <AisVesselPanel
                          aisMessages={aisVessels}
                          focusedFreq={focusedFreq}
                        />
                      </div>
                    ) : (
                      <div style={{
                        fontSize: '12px',
                        color: 'var(--text-dim)',
                        fontFamily: 'var(--font-data)',
                        padding: '5px 8px',
                      }}>
                        Listening on 161.975 MHz...
                      </div>
                    )
                  ) : (
                    <div
                      onClick={() => focusFrequency(161975000)}
                      style={{
                        border: '1px solid rgba(255,68,68,0.3)',
                        background: 'rgba(255,68,68,0.05)',
                        padding: '5px 8px',
                        fontSize: '12px',
                        color: 'var(--neon-red)',
                        letterSpacing: '1px',
                        fontFamily: 'var(--font-data)',
                        cursor: 'pointer',
                      }}
                    >
                      ▸ TUNE TO 161.975 MHz TO DECODE AIS
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
