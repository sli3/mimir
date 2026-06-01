import React, { useRef, useState, useCallback, useEffect } from 'react'
import { useSocket } from '../hooks/useSocket.js'
import { useCanvasSize } from '../hooks/useCanvasSize.js'
import { useWaterfall } from '../hooks/useWaterfall.js'

const SAMPLE_RATE_HZ = 2_000_000

const STRIP_CONFIGS = [
  { freq_hz: 98000000,   label: '98.0 MHz',   name: 'FM BROADCAST', colour: 'var(--neon-cyan)'    },
  { freq_hz: 145175000,  label: '145.175 MHz', name: 'APRS',         colour: 'var(--neon-green)'  },
  { freq_hz: 915000000,  label: '915.0 MHz',   name: 'ISM / LoRa',   colour: 'var(--neon-amber)'  },
  { freq_hz: 1090000000, label: '1090.0 MHz',  name: 'ADS-B',        colour: 'var(--neon-magenta)'},
]

function WaterfallStrip({ config, latestPsd, focusedFreq, focusFrequency }) {
  const canvasRef = useRef(null)
  const crosshairRef = useRef(null)
  const canvasSize = useCanvasSize(canvasRef)
  useCanvasSize(crosshairRef)
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
    const freq = config.freq_hz + ((x / width) - 0.5) * SAMPLE_RATE_HZ
    setCrosshairX(x)
    focusFrequency(Math.round(freq))
  }, [config.freq_hz, focusFrequency])

  useEffect(() => {
    const canvas = crosshairRef.current
    if (!canvas) return
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
      height: '25%',
      borderBottom: '1px solid rgba(255,255,255,0.05)',
    }}>
      <div
        onClick={() => focusFrequency(config.freq_hz)}
        style={{
          width: 100,
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '0 8px',
          cursor: 'pointer',
          borderLeft: isActive ? '3px solid rgba(0,255,255,0.7)' : '3px solid transparent',
          background: isActive ? 'rgba(0,255,255,0.04)' : 'transparent',
        }}
      >
        <div style={{
          fontFamily: '"Press Start 2P", monospace',
          fontSize: 6,
          color: config.colour,
          marginBottom: 2,
        }}>
          {config.label}
        </div>
        <div style={{
          fontFamily: '"Share Tech Mono", monospace',
          fontSize: 8,
          color: 'var(--text-dim)',
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

export default function WaterfallPanel() {
  const { focusedFreq, focusFrequency, getPsdDb } = useSocket()

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      width: '100%',
      background: 'var(--panel)',
    }}>
      {STRIP_CONFIGS.map((config) => (
        <WaterfallStrip
          key={config.freq_hz}
          config={config}
          latestPsd={getPsdDb(config.freq_hz)}
          focusedFreq={focusedFreq}
          focusFrequency={focusFrequency}
        />
      ))}
    </div>
  )
}
