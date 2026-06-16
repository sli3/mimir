import React, { useRef, useEffect, useCallback, useState } from 'react'
import { useCanvasSize } from '../hooks/useCanvasSize.js'
import { WATERFALL_LABEL_WIDTH } from './WaterfallPanel.jsx'

const SAMPLE_RATE_HZ = 2_000_000

function findLatestSpectrum(spectrumUpdates, focusedFreq) {
  if (!spectrumUpdates || spectrumUpdates.length === 0 || focusedFreq == null) {
    return null
  }
  for (let i = 0; i < spectrumUpdates.length; i++) {
    if (spectrumUpdates[i].center_freq_hz === focusedFreq) {
      return spectrumUpdates[i]
    }
  }
  return null
}

export default function SpectrometerBar({ spectrumUpdates, focusedFreq, focusFrequency }) {
  const containerRef = useRef(null)
  const canvasRef = useRef(null)
  const crosshairXRef = useRef(null)
  const crosshairFreqRef = useRef(null)
  const [crosshairVersion, setCrosshairVersion] = useState(0)
  const canvasSize = useCanvasSize(canvasRef)

  /**
   * Handle a click on the spectrometer canvas.
   *
   * The click computes the raw frequency at the clicked pixel position and
   * draws a crosshair + frequency label as a display-only cursor.  Clicking
   * NEVER changes the focus frequency — the crosshair is a read tool only.
   */
  const handleClick = useCallback((e) => {
    const canvas = canvasRef.current
    if (!canvas || focusedFreq == null) return
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const width = canvas.width
    if (x < 0 || x > width) return
    // Compute frequency at clicked pixel without snapping or tuning.
    // This is a display-only frequency cursor — no focusFrequency() call.
    const relativeX = x / width
    const rawFreq = focusedFreq + (relativeX - 0.5) * SAMPLE_RATE_HZ
    crosshairXRef.current = x
    crosshairFreqRef.current = rawFreq
    setCrosshairVersion((v) => v + 1)   // force immediate canvas redraw
  }, [focusedFreq])

  // Clear the crosshair cursor when the band changes.
  useEffect(() => {
    crosshairXRef.current = null
    crosshairFreqRef.current = null
    setCrosshairVersion((v) => v + 1)
  }, [focusedFreq])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const width = canvas.width
    const height = canvas.height
    if (width === 0 || height === 0) return

    ctx.fillStyle = '#030810'
    ctx.fillRect(0, 0, width, height)

    const latest = findLatestSpectrum(spectrumUpdates, focusedFreq)
    const psd = latest ? latest.psd_db : null

    if (psd && psd.length > 0) {
      const minVal = Math.min(...psd)
      const maxVal = Math.max(...psd)
      const range = maxVal - minVal || 1

      ctx.beginPath()
      for (let i = 0; i < psd.length; i++) {
        const x = (i / (psd.length - 1)) * width
        const norm = (psd[i] - minVal) / range
        const y = height - (norm * (height - 4)) - 2
        if (i === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      }

      ctx.strokeStyle = 'var(--neon-cyan)'
      ctx.lineWidth = 1
      ctx.stroke()

      ctx.lineTo(width, height)
      ctx.lineTo(0, height)
      ctx.closePath()
      ctx.fillStyle = 'rgba(0,255,255,0.15)'
      ctx.fill()
    } else {
      const y = height / 2
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(width, y)
      ctx.strokeStyle = 'rgba(0,255,255,0.3)'
      ctx.lineWidth = 1
      ctx.stroke()
    }

    if (crosshairXRef.current !== null) {
      const cx = crosshairXRef.current
      ctx.beginPath()
      ctx.setLineDash([3, 3])
      ctx.moveTo(cx, 0)
      ctx.lineTo(cx, height)
      ctx.strokeStyle = 'rgba(0,255,255,0.5)'
      ctx.lineWidth = 1
      ctx.stroke()
      ctx.setLineDash([])
      // Frequency label
      if (crosshairFreqRef.current !== null) {
        const freqLabel = (crosshairFreqRef.current / 1e6).toFixed(3) + ' MHz'
        ctx.font = '11px monospace'
        const labelWidth = ctx.measureText(freqLabel).width
        // Keep label inside canvas: right of line unless too close to right edge,
        // clamped so it never clips at the left edge either.
        const labelX = Math.max(4, cx + labelWidth + 8 < width ? cx + 4 : cx - labelWidth - 4)
        ctx.fillStyle = 'rgba(0,255,255,0.9)'
        ctx.fillText(freqLabel, labelX, 24)
      }
    }

    const bandStart = focusedFreq != null ? (focusedFreq - SAMPLE_RATE_HZ / 2) / 1e6 : null
    const bandEnd = focusedFreq != null ? (focusedFreq + SAMPLE_RATE_HZ / 2) / 1e6 : null
    const center = focusedFreq != null ? (focusedFreq / 1e6).toFixed(3) + ' MHz' : ''

    ctx.fillStyle = 'var(--text-dim)'
    ctx.font = '9px var(--font-data)'
    if (bandStart != null) {
      ctx.fillText(bandStart.toFixed(3) + ' MHz', 4, height - 4)
    }
    if (bandEnd != null) {
      const text = bandEnd.toFixed(3) + ' MHz'
      const textWidth = ctx.measureText(text).width
      ctx.fillText(text, width - textWidth - 4, height - 4)
    }
    if (center) {
      ctx.fillStyle = 'var(--neon-cyan)'
      ctx.font = '11px var(--font-data)'
      const centerWidth = ctx.measureText(center).width
      ctx.fillText(center, (width - centerWidth) / 2, 14)
    }
  }, [spectrumUpdates, focusedFreq, canvasSize, crosshairVersion])

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '64px',
        flexShrink: 0,
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'row',
      }}
    >
      <div style={{ width: WATERFALL_LABEL_WIDTH, flexShrink: 0 }} />
      <canvas
        ref={canvasRef}
        style={{
          flex: 1,
          height: '100%',
        }}
        onClick={handleClick}
      />
    </div>
  )
}
