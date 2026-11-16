import AcarsMessagePanel from './AcarsMessagePanel.jsx'
import AisVesselPanel from './AisVesselPanel.jsx'
import AdsbAircraftPanel from './AdsbAircraftPanel.jsx'
import RawDecodePanel from './RawDecodePanel.jsx'
import FrameInspectorPanel from './FrameInspectorPanel.jsx'
import PanelHeader from './PanelHeader.jsx'
import { isAcarsTuned, isAisTuned, isAdsbTuned } from '../utils/tuning.js'

/** Render the notice for a band without an available decoder. */
function NoDecoderNotice() {
  return (
    <div style={{
      padding: '16px 10px',
      fontSize: '11px',
      color: 'var(--text-dim)',
      fontFamily: 'var(--font-data)',
      letterSpacing: '1px',
    }}>
      NO DECODER FOR THIS BAND
    </div>
  )
}

/**
 * Render tuned decoder panels with shared column headers and fallback notices.
 * Props: focusedFreq, anyDecoderTuned, adsbAircraft, adsbAircraftHistory,
 * acarsMessages, acarsRawLog, aisVessels, aisRawLog, adsbRawLog, rawView, setRawView,
 * pinnedFrame, setPinnedFrame, frameData.
 */
export default function DecodedSignalsRow({
  focusedFreq,
  anyDecoderTuned,
  adsbAircraft,
  adsbAircraftHistory,
  acarsMessages,
  acarsRawLog,
  aisVessels,
  aisRawLog,
  adsbRawLog,
  rawView,
  setRawView,
  pinnedFrame,
  setPinnedFrame,
  frameData,
}) {
  return (
    <div style={{
      flex: 1,
      minHeight: 0,
      display: 'flex',
      flexDirection: 'row',
      overflow: 'hidden',
      borderTop: '1px solid var(--border)',
    }}>
      {/* Column 1 — SIGNAL INTERCEPT */}
      <div style={{
        flex: 1,
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        borderRight: '1px solid var(--border)',
      }}>
        <PanelHeader title="SIGNAL INTERCEPT" colour={'var(--neon-amber)'} />
        <div style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}>
          {isAdsbTuned(focusedFreq) && (
            <div style={{
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              flexDirection: 'column',
              flex: 1,
              minHeight: 0,
            }}>
              {/* SUB-PANEL 1 — ADS-B AIRCRAFT */}
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
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  border: '1px solid var(--neon-green)',
                  background: 'rgba(0, 255, 136, 0.08)',
                  boxShadow: '0 0 6px rgba(0, 255, 136, 0.25)',
                  padding: '2px 8px',
                  fontFamily: 'var(--font-display)',
                  fontSize: 10,
                  color: 'var(--neon-green)',
                  letterSpacing: 1,
                }}>
                  ◆ <span>TUNED</span>
                </div>
              </div>
              <div style={{ padding: '0 10px 8px', display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <AdsbAircraftPanel
                    adsbAircraft={adsbAircraft}
                    adsbAircraftHistory={adsbAircraftHistory}
                    focusedFreq={focusedFreq}
                  />
                </div>
              </div>
            </div>
          )}

          {isAcarsTuned(focusedFreq) && (
            <div style={{
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              flexDirection: 'column',
              flexShrink: 0,
            }}>
              {/* SUB-PANEL 2 — ACARS MESSAGES
                  FIX (Phase 18b-hotfix): removed acarsMessages.length > 0 inner gate.
                  AcarsMessagePanel always mounts when tuned — component handles its own
                  empty state ("Listening..." / "Awaiting decodes...") internally. */}
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
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  border: '1px solid var(--neon-green)',
                  background: 'rgba(0, 255, 136, 0.08)',
                  boxShadow: '0 0 6px rgba(0, 255, 136, 0.25)',
                  padding: '2px 8px',
                  fontFamily: 'var(--font-display)',
                  fontSize: 10,
                  color: 'var(--neon-green)',
                  letterSpacing: 1,
                }}>
                  ◆ <span>TUNED</span>
                </div>
              </div>
              <div style={{ padding: '0 10px 8px' }}>
                <div style={{ height: '150px', overflow: 'auto' }}>
                  <AcarsMessagePanel
                    acarsMessages={acarsMessages}
                    focusedFreq={focusedFreq}
                    acarsRawLog={acarsRawLog}
                  />
                </div>
              </div>
            </div>
          )}

          {isAisTuned(focusedFreq) && (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              flexShrink: 0,
            }}>
              {/* SUB-PANEL 3 — AIS VESSELS
                  162.000 MHz = dual-channel centre (matches backend BAND_PROFILES).
                  100 kHz tolerance covers both CH1 (161.975 MHz) and CH2 (162.025 MHz).
                  FIX (Phase 18b-hotfix): removed aisVessels.length > 0 inner gate.
                  AisVesselPanel always mounts when tuned — component handles its own
                  empty state ("Listening..." / "Awaiting decodes...") internally. */}
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
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  border: '1px solid var(--neon-green)',
                  background: 'rgba(0, 255, 136, 0.08)',
                  boxShadow: '0 0 6px rgba(0, 255, 136, 0.25)',
                  padding: '2px 8px',
                  fontFamily: 'var(--font-display)',
                  fontSize: 10,
                  color: 'var(--neon-green)',
                  letterSpacing: 1,
                }}>
                  ◆ <span>TUNED</span>
                </div>
              </div>
              <div style={{ padding: '0 10px 8px' }}>
                <div style={{ height: '150px', overflow: 'auto' }}>
                  <AisVesselPanel
                    aisMessages={aisVessels}
                    focusedFreq={focusedFreq}
                    aisRawLog={aisRawLog}
                  />
                </div>
              </div>
            </div>
          )}

          {!anyDecoderTuned && (
            <NoDecoderNotice />
          )}
        </div>
      </div>

      {/* Column 2 — RAW DECODE (gated on ADS-B tuning) */}
      <div style={{
        flex: 1,
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        borderRight: '1px solid var(--border)',
      }}>
        {isAdsbTuned(focusedFreq) ? (
          <RawDecodePanel
            adsbRawLog={adsbRawLog}
            rawView={rawView}
            setRawView={setRawView}
            pinnedFrame={pinnedFrame}
            setPinnedFrame={setPinnedFrame}
          />
        ) : (
          <>
            <PanelHeader title="RAW DECODE" colour={'var(--neon-cyan)'} />
            <NoDecoderNotice />
          </>
        )}
      </div>

      {/* Column 3 — FRAME INSPECTOR (gated on ADS-B tuning) */}
      <div style={{
        flex: 1,
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {isAdsbTuned(focusedFreq) ? (
          <FrameInspectorPanel
            pinnedFrame={pinnedFrame}
            frameData={frameData}
            adsbRawLog={adsbRawLog}
          />
        ) : (
          <>
            <PanelHeader title="FRAME INSPECTOR" colour={'var(--neon-cyan)'} />
            <NoDecoderNotice />
          </>
        )}
      </div>
    </div>
  )
}
