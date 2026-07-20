import { useEffect } from 'react'
import { psdToRgb, normalisePsd } from '../utils/colourmap.js'

const NUM_PSD_BINS = 2048

// Adaptive colour-scale anchoring.
//
// The bottom of the colour scale is anchored to the row's NOISE FLOOR, not
// its absolute minimum. If we used the absolute min, the huge span of
// near-noise bins gets stretched across the low-to-mid gradient and the whole
// background lights up cyan — every tiny noise fluctuation becomes visible,
// so the waterfall looks like pure noise even when it's mostly empty band.
//
// Instead we take a high percentile of the row as the floor: most of a
// quiet band is noise, so (say) the 70th percentile lands squarely in the
// noise floor. Everything at or below it maps to the darkest stops (stays
// dark); only bins ABOVE the noise floor climb into the bright colours.
// A few dB of pad below the floor keeps the noise sitting just inside the
// dark end rather than clipping to pure black and shimmering.
//
// SCALE_FLOOR_PERCENTILE — 0..1 fraction of the sorted row used as the noise
//   anchor. 0.7 = 70th percentile. Higher = darker background (more of the
//   band treated as noise); lower = more sensitive but noisier-looking.
const SCALE_FLOOR_PERCENTILE = 0.7
const SCALE_FLOOR_PAD_DB = 2
const SCALE_CEIL_PAD_DB = 6

/**
 * Return the value at a given 0..1 percentile of a numeric array, ignoring
 * non-finite entries. Uses a sorted copy — fine for a 2048-bin row at the
 * once-per-frame rate the waterfall runs at.
 */
function percentile(arr, p) {
  const clean = []
  for (let i = 0; i < arr.length; i++) {
    if (Number.isFinite(arr[i])) clean.push(arr[i])
  }
  if (clean.length === 0) return null
  clean.sort((a, b) => a - b)
  const idx = Math.min(
    clean.length - 1,
    Math.max(0, Math.round(p * (clean.length - 1)))
  )
  return clean[idx]
}

/**
 * Waterfall hook — scrolls PSD data as a GPU-accelerated canvas waterfall.
 *
 * Receives an array of PSD power values (``psdDb``) and draws them as a
 * single new row at the top of the canvas, shifting all existing rows down
 * by one pixel via ``ctx.drawImage()``. Each PSD bin is averaged into the
 * available canvas pixel width, normalised, and colour-mapped.
 *
 * Adaptive colour scale
 * ----------------------
 * The colour scale is derived per row from the actual min and max of
 * ``psdDb`` (plus a few dB of headroom, see SCALE_*_PAD_DB), rather than a
 * fixed -80..0 dBFS window. Different devices (and the same device at
 * different gains) sit at very different absolute dBFS levels — e.g. the
 * uncalibrated ADALM-PLUTO delivers a much lower-amplitude signal than the
 * calibrated HackRF — so a fixed window rendered Pluto's whole spectrum as
 * near-black. Measuring the window from the data itself makes the waterfall
 * self-scaling for any device or gain, with no hard-coded ranges to revisit
 * (e.g. when Phase 39 calibrates Pluto). See utils/colourmap.js normalisePsd.
 *
 * The ``sampleRateHz`` parameter was removed in PHASE-TECH-DEBT-1 — the
 * hook relies solely on ``psdDb`` length for bin-to-pixel mapping.
 *
 * @param {{ canvasRef: React.RefObject<HTMLCanvasElement>, psdDb: number[] }} props
 *        ``canvasRef`` — the canvas element to draw onto.
 *        ``psdDb`` — array of 2048 PSD power values in dBFS.
 */
export function useWaterfall({ canvasRef, psdDb }) {
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !psdDb || psdDb.length === 0) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const width = canvas.width
    const height = canvas.height
    if (width === 0 || height === 0) return

    // Derive the adaptive colour window from this row's own dynamic range.
    // Floor = noise-floor percentile (keeps noise dark); ceiling = peak.
    // Single pass for the max (avoids Math.max(...psdDb) spread, which can
    // blow the call stack on large arrays); percentile() handles the floor.
    let rowMax = -Infinity
    for (let i = 0; i < psdDb.length; i++) {
      const v = psdDb[i]
      if (Number.isFinite(v) && v > rowMax) rowMax = v
    }
    const noiseFloor = percentile(psdDb, SCALE_FLOOR_PERCENTILE)
    // Fallback if the whole row was non-finite.
    if (!Number.isFinite(rowMax) || noiseFloor === null) {
      rowMax = 0
    }
    const scaleMin = (noiseFloor ?? -100) - SCALE_FLOOR_PAD_DB
    const scaleMax = rowMax + SCALE_CEIL_PAD_DB

    // GPU scroll: draw entire canvas shifted down by 1 pixel
    ctx.drawImage(canvas, 0, 1)

    // Build new top row only (1px)
    const rowData = ctx.createImageData(width, 1)
    const data = rowData.data
    const groupSize = NUM_PSD_BINS / width

    for (let x = 0; x < width; x++) {
      const startBin = Math.floor(x * groupSize)
      const endBin = Math.min(Math.floor((x + 1) * groupSize), NUM_PSD_BINS)
      let sum = 0
      let count = 0
      for (let i = startBin; i < endBin; i++) {
        sum += psdDb[i]
        count++
      }
      const avg = count > 0 ? sum / count : psdDb[startBin] ?? -100
      const norm = normalisePsd(avg, scaleMin, scaleMax)
      const [r, g, b] = psdToRgb(norm)
      const idx = x * 4
      data[idx]     = r
      data[idx + 1] = g
      data[idx + 2] = b
      data[idx + 3] = 255
    }

    // Write only the new top row
    ctx.putImageData(rowData, 0, 0)
  }, [psdDb])
}