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
// Per-device colour-scale profiles (Phase 42).
//
// Each profile controls how the adaptive colour window is derived from a
// PSD row:
//
//   floorPercentile — 0..1 fraction of the sorted row used as the noise
//     anchor. 0.7 = 70th percentile. Higher = darker background (more of the
//     band treated as noise); lower = more sensitive but noisier-looking.
//   floorPadDb — dB of pad below the noise floor, keeping noise just inside
//     the dark end rather than clipping to pure black and shimmering.
//   ceilPadDb — dB of headroom above the row peak.
//   minSpanDb — minimum colour-window span in dB. On a dead band the
//     natural (floor..peak) span can shrink to a few dB, which stretches
//     tiny noise fluctuations across the whole palette and makes the
//     waterfall look grainy. Enforcing a floor on the span keeps a dead
//     band's noise pinned to the dark end.
//
// minSpanDb values are VISUAL-TUNING PLACEHOLDERS — sensible defaults to be
// tuned on hardware, same status as other Mimir calibration constants. They
// are NOT calibrated measurements.
//
// Keyed on the RAW SoapySDR driver strings emitted by system_stats.device
// ("hackrf" / "plutosdr" — DEVICE_PROFILES keys), NOT the friendly display
// names from display_name_for_device(). Unknown or missing devices fall
// back to _default, which reproduces the pre-Phase-42 behaviour exactly
// (minSpanDb: 0 = no floor).
const DEVICE_SCALE_PROFILES = {
  hackrf:   { floorPercentile: 0.70, floorPadDb: 2, ceilPadDb: 6, minSpanDb: 30 },
  plutosdr: { floorPercentile: 0.70, floorPadDb: 2, ceilPadDb: 6, minSpanDb: 15 },
  _default: { floorPercentile: 0.70, floorPadDb: 2, ceilPadDb: 6, minSpanDb: 0  }, // 0 = no floor = today's behaviour
}

/**
 * Resolve the colour-scale profile for a raw device driver string.
 * Unknown, null, or undefined devices fall back to the _default profile,
 * preserving pre-Phase-42 behaviour for any device without an entry.
 */
export function selectDeviceProfile(device) {
  return DEVICE_SCALE_PROFILES[device] ?? DEVICE_SCALE_PROFILES._default
}

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
 * Compute the adaptive colour window for one PSD row.
 *
 * Pure function — no React, no DOM — so the scale maths is testable
 * directly. Encapsulates the row-max scan, the noise-floor percentile, the
 * floor/ceiling pads, and the per-device minimum-span floor.
 *
 * @param {number[]} psdDb - array of PSD power values in dBFS.
 * @param {{ floorPercentile: number, floorPadDb: number, ceilPadDb: number, minSpanDb: number }} profile
 *        a DEVICE_SCALE_PROFILES entry (see selectDeviceProfile).
 * @returns {{ scaleMin: number, scaleMax: number }} the colour window in dB.
 */
export function computeScaleWindow(psdDb, profile) {
  // Single pass for the max (avoids Math.max(...psdDb) spread, which can
  // blow the call stack on large arrays); percentile() handles the floor.
  let rowMax = -Infinity
  for (let i = 0; i < psdDb.length; i++) {
    const v = psdDb[i]
    if (Number.isFinite(v) && v > rowMax) rowMax = v
  }
  const noiseFloor = percentile(psdDb, profile.floorPercentile)
  // Fallback if the whole row was non-finite.
  if (!Number.isFinite(rowMax) || noiseFloor === null) {
    rowMax = 0
  }
  const scaleMin = (noiseFloor ?? -100) - profile.floorPadDb
  let scaleMax = rowMax + profile.ceilPadDb
  // Enforce per-device minimum span so a dead band's tiny range does not
  // stretch noise across the palette (Phase 42 graininess fix).
  scaleMax = Math.max(scaleMax, scaleMin + profile.minSpanDb)
  return { scaleMin, scaleMax }
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
 * ``psdDb`` (plus a few dB of headroom, see DEVICE_SCALE_PROFILES), rather than a
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
 * Phase 42 added the ``device`` parameter: the colour window is computed
 * per device via DEVICE_SCALE_PROFILES (see computeScaleWindow), so each
 * SDR gets a minimum-span floor matched to how grainy its dead-band noise
 * looks. Unknown devices use the _default profile, which reproduces the
 * pre-Phase-42 behaviour exactly.
 *
 * @param {{ canvasRef: React.RefObject<HTMLCanvasElement>, psdDb: number[], device: string|null }} props
 *        ``canvasRef`` — the canvas element to draw onto.
 *        ``psdDb`` — array of 2048 PSD power values in dBFS.
 *        ``device`` — raw SoapySDR driver string from system_stats
 *        ("hackrf" / "plutosdr"), or null before the first system_stats
 *        arrives. Selects the DEVICE_SCALE_PROFILES entry.
 */
export function useWaterfall({ canvasRef, psdDb, device }) {
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !psdDb || psdDb.length === 0) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const width = canvas.width
    const height = canvas.height
    if (width === 0 || height === 0) return

    // Derive the adaptive colour window from this row's own dynamic range,
    // using the profile for the connected device (Phase 42). Floor =
    // noise-floor percentile (keeps noise dark); ceiling = peak; per-device
    // minimum span stops dead-band noise stretching across the palette.
    const profile = selectDeviceProfile(device)
    const { scaleMin, scaleMax } = computeScaleWindow(psdDb, profile)

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
  }, [psdDb, device])
}