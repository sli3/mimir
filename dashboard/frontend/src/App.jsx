import React from 'react'
import { useSocket } from './hooks/useSocket.js'
import FrequencyList from './components/FrequencyList.jsx'
import SignalHistoryLog from './components/SignalHistoryLog.jsx'
import SystemStatsPanel from './components/SystemStatsPanel.jsx'
import AIReasoningPanel from './components/AIReasoningPanel.jsx'
import CharacterPanel from './components/CharacterPanel.jsx'
import WaterfallPanel from './components/WaterfallPanel.jsx'
import AcarsMessagePanel from './components/AcarsMessagePanel.jsx'
import AisVesselPanel from './components/AisVesselPanel.jsx'
import AdsbAircraftPanel from './components/AdsbAircraftPanel.jsx'
const panelStyle = {
  background: 'var(--panel)',
  border: '1px solid var(--border)',
  overflow: 'hidden',
}

export default function App() {
  const socket = useSocket()

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 320px',
      gridTemplateRows: '48px 1fr 200px 160px 140px 120px 120px 120px',
      gridTemplateAreas: `
        "header    header"
        "waterfall ai"
        "waterfall character"
        "history   history"
        "acars     acars"
        "ais       ais"
        "adsb      adsb"
        "freqlist  stats"
      `,
      height: '100vh',
      gap: '2px',
      padding: '4px',
    }}>
      <div style={{
        ...panelStyle,
        gridArea: 'header',
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        padding: '0 12px',
      }}>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: 12,
          color: 'var(--neon-cyan)',
          textShadow: '0 0 10px var(--neon-cyan)',
        }}>
          MIMIR
        </span>
        <span style={{
          fontFamily: 'var(--font-data)',
          fontSize: 10,
          color: 'var(--text-dim)',
        }}>
          PASSIVE RF INTELLIGENCE // ADELAIDE SA
        </span>
      </div>

      <div id="waterfall-slot" style={{
        ...panelStyle,
        gridArea: 'waterfall',
        border: '2px solid var(--neon-cyan)',
        boxShadow: '0 0 8px rgba(0,255,255,0.3), inset 0 0 8px rgba(0,255,255,0.05)',
        overflow: 'visible',
        padding: 0,
      }}>
        <WaterfallPanel
          focusedFreq={socket.focusedFreq}
          focusFrequency={socket.focusFrequency}
        />
      </div>

      <div style={{
        ...panelStyle,
        gridArea: 'ai',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <AIReasoningPanel
          aiReasoning={socket.aiReasoning}
        />
      </div>

      <div style={{
        ...panelStyle,
        gridArea: 'character',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <CharacterPanel />
      </div>

      <div style={{
        ...panelStyle,
        gridArea: 'history',
      }}>
        <SignalHistoryLog scanResults={socket.scanResults} />
      </div>

      <div style={{
        ...panelStyle,
        gridArea: 'acars',
      }}>
        <AcarsMessagePanel
          acarsMessages={socket.acarsMessages}
          focusedFreq={socket.focusedFreq}
        />
      </div>

      <div style={{
        ...panelStyle,
        gridArea: 'ais',
      }}>
        <AisVesselPanel
          aisMessages={socket.aisMessages}
          focusedFreq={socket.focusedFreq}
        />
      </div>

      <div style={{
        ...panelStyle,
        gridArea: 'adsb',
      }}>
        <AdsbAircraftPanel
          adsbAircraft={socket.adsbAircraft}
          focusedFreq={socket.focusedFreq}
        />
      </div>

      <div style={{
        ...panelStyle,
        gridArea: 'freqlist',
      }}>
        <FrequencyList
          scanResults={socket.scanResults}
          focusedFreq={socket.focusedFreq}
          focusFrequency={socket.focusFrequency}
        />
      </div>

      <div style={{
        ...panelStyle,
        gridArea: 'stats',
      }}>
        <SystemStatsPanel systemStats={socket.systemStats} />
      </div>
    </div>
  )
}
