import React, { useRef, useState, useCallback, useEffect } from 'react'
import { useSocket } from '../hooks/useSocket.js'
import { useCanvasSize } from '../hooks/useCanvasSize.js'
import { useWaterfall } from '../hooks/useWaterfall.js'

export const WATERFALL_LABEL_WIDTH = 0

const SAMPLE_RATE_HZ = 2_000_000

/** Waterfall strip configuration for each monitored band.
 *  Seven AU-legal frequencies, each with a display label, name,
 *  and CSS colour variable.  Used by WaterfallStrip to render
 *  the per-band waterfall canvas and by SpectrometerBar for
 *  frequency snapping.  Ordered by frequency ascending.
 *
 *  NOTE: OVERVIEW_BANDS and BAND_GROUPS in App.jsx still have
 *  only 6 entries (AIS at 161.975 MHz is missing from both).
 *  If adding a new band here, add it to those lists too. */
export const STRIP_CONFIGS = [
  { freq_hz: 98000000,   label: '98.0 MHz',    name: 'FM BROADCAST', colourVar: '--neon-cyan'    },
  { freq_hz: 145175000,  label: '145.175 MHz',  name: 'APRS',         colourVar: '--neon-green'  },
  { freq_hz: 127000000,  label: '127.0 MHz',   name: 'AVIATION VHF', colourVar: '--neon-cyan'   },
  { freq_hz: 129125000,  label: '129.125 MHz',  name: 'ACARS',        colourVar: '--neon-amber'  },
  { freq_hz: 915000000,  label: '915.0 MHz',    name: 'ISM / LoRa',   colourVar: '--neon-amber'  },
  { freq_hz: 161975000,  label: '161.975 MHz',  name: 'AIS',          colourVar: '--neon-red'    },
  { freq_hz: 1090000000, label: '1090.0 MHz',   name: 'ADS-B',        colourVar: '--neon-magenta'},
]

function WaterfallStrip({ config, latestPsd, focusedFreq, focusFrequency, singleBand, hideSidebar }) {
  const canvasRef = useRef(null)
  const crosshairRef = useRef(null)
  const canvasSize = useCanvasSize(canvasRef)
  const [crosshairX, setCrosshairX] = useState(null)

  useWaterfall({
    canvasRef,
    psdDb: latestPsd,
  })

  /**
   * Handle a click on the waterfall canvas.
   *
   * The crosshair is drawn in every mode.  In multi-band overview mode
   * (singleBand=false) the click position is mapped to a frequency and
   * emitted via focusFrequency.  In singleBand mode the mapping is
   * suppressed because an off-centre click would compute a non-STRIP_CONFIG
   * value (e.g. 1089753124 instead of 1090000000).  The latestUpdate lookup
   * in WaterfallPanel uses strict equality against config.freq_hz, so any
   * deviation freezes the waterfall.
   */
  const handleCanvasClick = useCallback((e) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    // Draw the crosshair cursor regardless of mode.
    setCrosshairX(x)
    // In singleBand mode, do NOT change the focus frequency.
    // An off-centre click computes a non-STRIP_CONFIG value (e.g. 1089753124
    // instead of 1090000000). The latestUpdate lookup uses strict equality
    // against config.freq_hz, so any deviation freezes the waterfall.
    // In multi-band overview mode (singleBand=false), preserve original behaviour.
    if (!singleBand) {
      const width = canvas.width
      const relativeX = x / width
      const freq = config.freq_hz + (relativeX - 0.5) * SAMPLE_RATE_HZ
      focusFrequency(Math.round(freq))
    }
  }, [config.freq_hz, focusFrequency, singleBand])

  useEffect(() => {
    const canvas = crosshairRef.current
    if (!canvas) return
    if (canvasSize.width === 0 || canvasSize.height === 0) return
    canvas.width = canvasSize.width
    canvas.height = canvasSize.height
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    if (crosshairX !== null) {
      ctx.strokeStyle = 'rgba(0,255,255,0.75)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(crosshairX, 0)
      ctx.lineTo(crosshairX, canvas.height)
      ctx.stroke()
      // Frequency label at crosshair
      const relativeX = crosshairX / canvas.width
      const freq = config.freq_hz + (relativeX - 0.5) * SAMPLE_RATE_HZ
      const label = (freq / 1e6).toFixed(3) + ' MHz'
      ctx.font = '11px monospace'
      const labelWidth = ctx.measureText(label).width
      const labelX = Math.max(
        4,
        crosshairX + labelWidth + 8 < canvas.width
          ? crosshairX + 4
          : crosshairX - labelWidth - 4
      )
      ctx.fillStyle = 'rgba(0,255,255,0.9)'
      ctx.fillText(label, labelX, 24)
    }
  }, [crosshairX, canvasSize])

  const isActive = config.freq_hz === focusedFreq

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'row',
      flex: 1,
      borderBottom: '1px solid var(--border)',
      borderLeft: isActive ? '3px solid var(--border-active)' : '3px solid transparent',
      background: isActive ? 'rgba(0,255,255,0.03)' : 'transparent',
    }}>
      {!hideSidebar && (
        <div
          onClick={() => focusFrequency(config.freq_hz)}
          style={{
            width: singleBand ? 110 : 90,
            flexShrink: 0,
            padding: 4,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            cursor: 'pointer',
          }}
        >
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: singleBand ? 14 : 9,
            color: `var(${config.colourVar})`,
          }}>
            {config.label}
          </div>
          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: singleBand ? 13 : 12,
            color: 'var(--text-dim)',
            marginTop: 4,
          }}>
            {config.name}
          </div>
        </div>
      )}
      <div style={{
        flex: 1,
        position: 'relative',
        overflow: 'hidden',
      }}>
        <canvas
          ref={canvasRef}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
          }}
          onClick={handleCanvasClick}
        />
        <canvas
          ref={crosshairRef}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            pointerEvents: 'none',
          }}
        />
      </div>
    </div>
  )
}

export default function WaterfallPanel({ focusedFreq, focusFrequency, singleBand = false }) {
  const { spectrumUpdates } = useSocket()

  const configs = singleBand
    ? (() => {
        const match = STRIP_CONFIGS.find(
          (c) => Math.abs(c.freq_hz - focusedFreq) <= 2_000_000
        )
        return match ? [match] : [STRIP_CONFIGS[0]]
      })()
    : STRIP_CONFIGS

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      width: '100%',
    }}>
      {configs.map((config) => {
        const latestUpdate = spectrumUpdates.find(
          (u) => u.center_freq_hz === config.freq_hz
        )
        return (
          <WaterfallStrip
            key={config.freq_hz}
            config={config}
            latestPsd={latestUpdate ? latestUpdate.psd_db : null}
            focusedFreq={focusedFreq}
            focusFrequency={focusFrequency}
            singleBand={singleBand}
            hideSidebar={singleBand}
          />
        )
      })}
    </div>
  )
}
