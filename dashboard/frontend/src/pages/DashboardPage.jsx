import { useState, useCallback } from 'react'
import { useSocket } from '../hooks/useSocket.js'
import useFrameInspector from '../hooks/useFrameInspector.js'
import useCaptureControls from '../hooks/useCaptureControls.js'
import WaterfallPanel from '../components/WaterfallPanel.jsx'
import SpectrometerBar from '../components/SpectrometerBar.jsx'
import SignalHistoryLog from '../components/SignalHistoryLog.jsx'
import AIReasoningPanel from '../components/AIReasoningPanel.jsx'
import CaptureResultPanel from '../components/CaptureResultPanel.jsx'
import { INITIAL_AI_REASONING } from '../constants/aiReasoning.js'
import { isAcarsTuned, isAisTuned, isAdsbTuned } from '../utils/tuning.js'
import { OPERATOR_STATE_CONFIG, getOperatorState } from '../utils/operatorState.js'
import useClock from '../hooks/useClock.js'
import useFrozenDisplay from '../hooks/useFrozenDisplay.js'
import HeaderBar from '../components/HeaderBar.jsx'
import BandNavBar from '../components/BandNavBar.jsx'
import DecodedSignalsRow from '../components/DecodedSignalsRow.jsx'
import SignalDetailsPanel from '../components/SignalDetailsPanel.jsx'
import SystemStatusPanel from '../components/SystemStatusPanel.jsx'

/** Render the dashboard, owning its display state and interaction callbacks. */
export default function DashboardPage() {
  const socket = useSocket()
  const {
    scanResults,
    spectrumUpdates,
    systemStats,
    unsupportedBands,           // Phase 38 — device-aware band UI
    focusedFreq,
    focusFrequency,
    aiReasoning,
    acarsMessages,
    aisVessels,
    adsbAircraft,
    adsbAircraftHistory,
    adsbRawLog,
    acarsRawLog,
    aisRawLog,
  } = socket

  const clock = useClock()
  const displayed = useFrozenDisplay(aiReasoning)
  const [customInput, setCustomInput] = useState('')
  const [pinnedReasoning, setPinnedReasoning] = useState(null)
  const [operatorTooltipVisible, setOperatorTooltipVisible] = useState(false)
  const [operatorFocused, setOperatorFocused] = useState(false)
  const operatorState = getOperatorState(aiReasoning)
  const operatorConfig = OPERATOR_STATE_CONFIG[operatorState]
  const pinnedTimestamp = pinnedReasoning ? pinnedReasoning.timestamp : null

  const { rawView, setRawView, pinnedFrame, setPinnedFrame, frameData } = useFrameInspector(adsbRawLog)

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
        source: entry.source ?? null,
        snr_db: entry.snr_db ?? null,
        bandwidth_hz: entry.bandwidth_hz ?? null,
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

  const {
    captureState,
    capturePending,
    handleCaptureClick,
    recording,
    recordElapsedSec,
    recordWarning,
    recordResult,
    handleRecordClick,
    markers,
    tickAndPrune,
  } = useCaptureControls(focusedFreq)

  const adsbAircraftList = Object.values(adsbAircraft || {})
  const anyDecoderTuned = isAdsbTuned(focusedFreq)
    || isAcarsTuned(focusedFreq)
    || isAisTuned(focusedFreq)

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
      <HeaderBar clock={clock} />

      {/* Main content row — left stack + consolidated right column
          (UI-OVERHAUL Change 4: the old Row 2 / Row 3 split is gone) */}
      <div style={{
        display: 'flex',
        flexDirection: 'row',
        flex: 1,
        minHeight: 0,
        overflow: 'hidden',
      }}>
        {/* Left column */}
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          {/* Top block — band nav + waterfall + spectrometer
              (UI-OVERHAUL Change 1: was 52vh, now 42vh) */}
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            height: '42vh',
            flexShrink: 0,
            overflow: 'hidden',
          }}>
            {/* Section A — Band nav bar
                (UI-OVERHAUL Change 3: two-line buttons forced a height
                bump from 48px to 56px) */}
            <BandNavBar
              focusedFreq={focusedFreq}
              focusFrequency={focusFrequency}
              unsupportedBands={unsupportedBands}
              adsbAircraftList={adsbAircraftList}
              adsbAircraftHistory={adsbAircraftHistory}
              customInput={customInput}
              setCustomInput={setCustomInput}
              handleKeyDown={handleKeyDown}
              handleTune={handleTune}
              handleCaptureClick={handleCaptureClick}
              capturePending={capturePending}
              recording={recording}
              handleRecordClick={handleRecordClick}
              recordElapsedSec={recordElapsedSec}
              recordWarning={recordWarning}
              recordResult={recordResult}
            />

            {/* Section B — Main waterfall */}
            <div data-testid="waterfall" style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
              <WaterfallPanel
                focusedFreq={focusedFreq}
                focusFrequency={focusFrequency}
                singleBand={true}
                markers={markers}
                onStripScroll={tickAndPrune}
              />
            </div>

            {/* Section C — SpectrometerBar */}
            <SpectrometerBar
              spectrumUpdates={spectrumUpdates}
              focusedFreq={focusedFreq}
              focusFrequency={focusFrequency}
            />
          </div>

          {/* AI Reasoning — UI-OVERHAUL Change 5: moved from the old
              bottom-right slot into the vacated bottom-left area */}
          <div style={{
            minHeight: '220px',
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            borderTop: '1px solid var(--border)',
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
            <div style={{ flex: 1, overflowY: 'auto' }}>
              <AIReasoningPanel
                aiReasoning={pinnedReasoning || aiReasoning}
                isPinned={!!pinnedReasoning}
                onUnpin={() => setPinnedReasoning(null)}
              />
            </div>
          </div>

          {/* Decoded Signals — UI-OVERHAUL Change 6: three independently
              scrolling equal-width columns */}
          <DecodedSignalsRow
            focusedFreq={focusedFreq}
            anyDecoderTuned={anyDecoderTuned}
            adsbAircraft={adsbAircraft}
            adsbAircraftHistory={adsbAircraftHistory}
            acarsMessages={acarsMessages}
            acarsRawLog={acarsRawLog}
            aisVessels={aisVessels}
            aisRawLog={aisRawLog}
            adsbRawLog={adsbRawLog}
            rawView={rawView}
            setRawView={setRawView}
            pinnedFrame={pinnedFrame}
            setPinnedFrame={setPinnedFrame}
            frameData={frameData}
          />
        </div>

        {/* Right column — consolidated full-height panel stack
            (UI-OVERHAUL Change 4): Signal Details + System Status +
            Signal History. Pure JSX move; all internals unchanged. */}
        <div style={{
          width: '380px',
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--bg-panel)',
          borderLeft: '1px solid var(--border)',
          overflow: 'hidden',
        }}>
          {/* Section 1 — Signal Details */}
          <SignalDetailsPanel
            displayed={displayed}
            systemStats={systemStats}
            scanResults={scanResults}
            operatorState={operatorState}
            operatorConfig={operatorConfig}
            aiReasoning={aiReasoning}
            operatorTooltipVisible={operatorTooltipVisible}
            setOperatorTooltipVisible={setOperatorTooltipVisible}
            operatorFocused={operatorFocused}
            setOperatorFocused={setOperatorFocused}
          />

          {/* Section 1b — Capture Result (Phase 67). Header mirrors the
              SIGNAL DETAILS header above (height 28px, var(--bg-header)
              bg, border-bottom 1px solid var(--border), var(--neon-cyan)
              title). Body hosts the manual-capture state machine's render
              — idle → "NO CAPTURE YET", pending → "CAPTURING…", ok →
              verdict + numbers + file path with role="status", failure →
              message with role="alert". */}
          <CaptureResultPanel state={captureState} />

          {/* Section 2 — System Status */}
          <SystemStatusPanel systemStats={systemStats} />

          {/* Section 3 — Signal History */}
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
              <SignalHistoryLog
                scanResults={scanResults}
                onPinReasoning={handlePinReasoning}
                pinnedTimestamp={pinnedTimestamp}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
