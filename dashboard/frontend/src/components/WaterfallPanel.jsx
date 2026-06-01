import React, { useRef, useState, useCallback, useEffect } from 'react'
import { useSocket } from '../hooks/useSocket.js'
import { useCanvasSize } from '../hooks/useCanvasSize.js'
import { useWaterfall } from '../hooks/useWaterfall.js'

const SAMPLE_RATE_HZ = 2_000_000

const STRIP_CONFIGS = [
  { freq_hz: 98000000,   label: '98.0 MHz',    name: 'FM BROADCAST', colourVar: '--neon-cyan'    },
  { freq_hz: 145175000,  label: '145.175 MHz',  name: 'APRS',         colourVar: '--neon-green'  },
  { freq_hz: 915000000,  label: '915.0 MHz',    name: 'ISM / LoRa',   colourVar: '--neon-amber'  },
  { freq_hz: 1090000000, label: '1090.0 MHz',   name: 'ADS-B',        colourVar: '--neon-magenta'},
]

function WaterfallStrip({ config, latestPsd, focusedFreq, focusFrequency }) {
  const canvasRef = useRef(null)
  const crosshairRef = useRef(null)
  const canvasSize = useCanvasSize(canvasRef)
  const [crosshairX, setCrosshairX] = useState(null)

  useWaterfall({
    canvasRef,
    psdDb: latestPsd,
    sampleRateHz: SAMPLE_RATE_HZ,
  })

  const handleCanvasClick = useCallback((e) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const width = canvas.width
    const relativeX = x / width
    const freq = config.freq_hz + (relativeX - 0.5) * SAMPLE_RATE_HZ
    setCrosshairX(x)
    focusFrequency(Math.round(freq))
  }, [config.freq_hz, focusFrequency])

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
      <div
        onClick={() => focusFrequency(config.freq_hz)}
        style={{
          width: 90,
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
          fontSize: 9,
          color: `var(${config.colourVar})`,
        }}>
          {config.label}
        </div>
        <div style={{
          fontFamily: 'var(--font-data)',
          fontSize: 12,
          color: 'var(--text-dim)',
          marginTop: 4,
        }}>
          {config.name}
        </div>
      </div>
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

export default function WaterfallPanel({ focusedFreq, focusFrequency }) {
  const { spectrumUpdates } = useSocket()

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      width: '100%',
    }}>
      {STRIP_CONFIGS.map((config) => {
        const latestUpdate = [...spectrumUpdates].reverse().find(
          (u) => u.center_freq_hz === config.freq_hz
        )
        return (
          <WaterfallStrip
            key={config.freq_hz}
            config={config}
            latestPsd={latestUpdate ? latestUpdate.psd_db : null}
            focusedFreq={focusedFreq}
            focusFrequency={focusFrequency}
          />
        )
      })}
    </div>
  )
}
