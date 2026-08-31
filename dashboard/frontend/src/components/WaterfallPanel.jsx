import React, { useRef, useState, useCallback, useEffect } from 'react'
import { useSocket } from '../hooks/useSocket.js'
import { useCanvasSize } from '../hooks/useCanvasSize.js'
import { useWaterfall } from '../hooks/useWaterfall.js'
import { freqMatches } from '../utils/frequency.js'

export const WATERFALL_LABEL_WIDTH = 0

const SAMPLE_RATE_HZ = 2_000_000

// Phase 69 — waterfall event markers.
const MARKER_STROKE_COLOURS = {
  capture: 'rgba(0, 217, 255, 0.85)',     // cyan, matches CaptureButton / crosshair
  record_start: 'rgba(0, 255, 136, 0.85)', // green, matches APRS band colour
  record_stop: 'rgba(255, 68, 68, 0.85)',  // red, matches AIS band colour
}
const MARKER_LABEL_PREFIXES = {
  capture: 'CAPTURE',
  record_start: 'REC START',
  record_stop: 'REC STOP',
}

/** Format a marker label timestamp. Matches the frontend convention in
 *  SignalHistoryLog.jsx (toLocaleTimeString en-AU, hour12 false) so the
 *  operator sees the same time format everywhere. Takes the marker's
 *  createdAt (Date.now() at add time) so the label shows WHEN the event
 *  happened, not the wall-clock time at redraw. */
function formatMarkerTime(createdAt) {
  return new Date(createdAt).toLocaleTimeString('en-AU', { hour12: false })
}

/** Draw a single waterfall event marker onto a 2D canvas context.
 *  No-ops for off-canvas markers (rowOffset < 0 or >= canvasHeight).
 *  Uses ctx.save()/restore() to leave the caller's canvas state untouched. */
function drawMarker(ctx, marker, canvasWidth, canvasHeight) {
  const y = marker.rowOffset
  if (y < 0 || y >= canvasHeight) return
  ctx.save()
  ctx.strokeStyle = MARKER_STROKE_COLOURS[marker.type]
  ctx.lineWidth = 1
  if (marker.type === 'capture') {
    ctx.setLineDash([])
  } else {
    ctx.setLineDash([6, 4])
  }
  ctx.beginPath()
  ctx.moveTo(0, y + 0.5)
  ctx.lineTo(canvasWidth, y + 0.5)
  ctx.stroke()
  ctx.setLineDash([])

  const label = `${MARKER_LABEL_PREFIXES[marker.type]} ${formatMarkerTime(marker.createdAt)}`
  ctx.font = '11px monospace'
  const textWidth = ctx.measureText(label).width
  const textX = 4
  const textY = Math.min(y + 14, canvasHeight - 2)
  ctx.fillStyle = 'rgba(0, 0, 0, 0.6)'
  ctx.fillRect(textX - 2, textY - 11, textWidth + 4, 13)
  ctx.fillStyle = MARKER_STROKE_COLOURS[marker.type]
  ctx.fillText(label, textX, textY)
  ctx.restore()
}

/** Waterfall strip configuration for each monitored band.
 *  Seven AU-legal frequencies, each with a display label, name,
 *  and CSS colour variable.  Used by WaterfallStrip to render
 *  the per-band waterfall canvas and by SpectrometerBar for
 *  frequency snapping.  Ordered by frequency ascending.
 *
 *  NOTE: STRIP_CONFIGS, BAND_GROUPS in App.jsx, OVERVIEW_BANDS
 *  in App.jsx, FREQ_COLOUR_MAP in SignalHistoryLog.jsx, and
 *  FREQ_CONFIGS in FrequencyList.jsx are all in sync at 162.000 MHz
 *  for AIS (Phase 15b — dual-channel centre). */
export const STRIP_CONFIGS = [
  { freq_hz: 98000000,   label: '98.0 MHz',    name: 'FM BROADCAST', colourVar: '--neon-cyan'    },
  { freq_hz: 145175000,  label: '145.175 MHz',  name: 'APRS',         colourVar: '--neon-green'  },
  { freq_hz: 127000000,  label: '127.0 MHz',   name: 'AVIATION VHF', colourVar: '--neon-cyan'   },
  { freq_hz: 129125000,  label: '129.125 MHz',  name: 'ACARS',        colourVar: '--neon-amber'  },
  { freq_hz: 915000000,  label: '915.0 MHz',    name: 'ISM / LoRa',   colourVar: '--neon-amber'  },
  { freq_hz: 162000000,  label: '162.000 MHz',  name: 'AIS',          colourVar: '--neon-red'    },
  { freq_hz: 1090000000, label: '1090.0 MHz',   name: 'ADS-B',        colourVar: '--neon-magenta'},
]

function WaterfallStrip({ config, latestPsd, focusedFreq, focusFrequency, singleBand, hideSidebar, device, markers, onStripScroll }) {
  const canvasRef = useRef(null)
  const crosshairRef = useRef(null)
  const canvasSize = useCanvasSize(canvasRef)
  const [crosshairX, setCrosshairX] = useState(null)

  useWaterfall({
    canvasRef,
    psdDb: latestPsd,
    device,
  })

  // Phase 69: per-strip marker view. Mirrors the spectrumUpdates
  // filtering pattern (line 214-216 below) — each strip only sees
  // markers belonging to its own frequency.
  const stripMarkers = markers.filter((m) => m.freqHz === config.freq_hz)

  // Phase 69: marker rowOffset increment must fire on the SAME trigger
  // useWaterfall uses (a new PSD row arriving = one scroll tick), so
  // markers scroll at exactly the same rate as the underlying signal
  // data. A separate setInterval would drift out of sync — do NOT use one.
  useEffect(() => {
    if (!latestPsd) return
    onStripScroll(config.freq_hz, canvasSize.height)
  }, [latestPsd])

  /**
   * Handle a click on the waterfall canvas.
   *
   * The crosshair is drawn in every mode.  In multi-band overview mode
   * (singleBand=false) the click position is mapped to a frequency and
   * emitted via focusFrequency.  In singleBand mode the mapping is
   * suppressed because an off-centre click would compute a non-STRIP_CONFIG
   * value (e.g. 1089753124 instead of 1090000000).  config.freq_hz is the
   * exact focusedFreq for named bands, so a click outside the band would
   * target a different freq and break the latestUpdate lookup against the
   * strip's data (now matched within 100 kHz tolerance by freqMatches()).
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
    // instead of 1090000000). config.freq_hz is the exact focusedFreq for
    // named bands, so a click outside the band would target a different
    // freq and break the latestUpdate lookup against the strip's data.
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

    // Phase 69: draw markers FIRST so the crosshair (drawn next)
    // renders on top. The drawMarker helper no-ops off-canvas rows.
    for (const marker of stripMarkers) {
      drawMarker(ctx, marker, canvas.width, canvas.height)
    }

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
  }, [crosshairX, canvasSize, stripMarkers])

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

export default function WaterfallPanel({ focusedFreq, focusFrequency, singleBand = false, markers = [], onStripScroll = () => {} }) {
  // device is the raw SoapySDR driver string ("hackrf" / "plutosdr") from
  // system_stats — threaded into useWaterfall for per-device colour scaling
  // (Phase 42). null until the first system_stats arrives, which selects
  // the _default profile (pre-Phase-42 behaviour).
  // Phase 76 third fix: opt out of focus control. WaterfallPanel's own useSocket()
  // instance opens its own socket and holds its own focusedFreqRef, but it has no
  // legitimate opinion about which frequency the dashboard should be focused on.
  // Without skipInitialRetune, this hook's stale 98MHz default would emit
  // set_focus_frequency on every socket connect and silently overwrite the
  // server's single global focus state whenever its resync fires last after
  // App.jsx's real focus-control instance. Most visibly broken in --demo mode
  // where it caused ALL classification results to be filtered out of the
  // dashboard because the server's focus kept getting reset to FM.
  const { spectrumUpdates, device } = useSocket({ skipInitialRetune: true })

  const configs = singleBand
    ? (() => {
        // Exact match — user clicked a named band button.
        const exact = STRIP_CONFIGS.find((c) => c.freq_hz === focusedFreq)
        if (exact) return [exact]
        // Custom frequency — synthesise a temporary strip config so the
        // latestPsd lookup matches the actual center_freq_hz the backend
        // emits. Borrow the colour from the nearest named band.
        const nearest = STRIP_CONFIGS.reduce((a, b) =>
          Math.abs(a.freq_hz - focusedFreq) <= Math.abs(b.freq_hz - focusedFreq) ? a : b
        )
        return [{
          freq_hz: focusedFreq,
          label: `${(focusedFreq / 1e6).toFixed(3)} MHz`,
          name: 'CUSTOM',
          colourVar: nearest.colourVar,
        }]
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
          (u) => freqMatches(u.center_freq_hz, config.freq_hz)
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
            device={device}
            markers={markers}
            onStripScroll={onStripScroll}
          />
        )
      })}
    </div>
  )
}