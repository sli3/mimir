const STOPS = [
  { t: 0.00, r: 3,   g: 8,   b: 16  },   /* --wf-noise  #030810 */
  { t: 0.10, r: 0,   g: 48,  b: 80  },   /* --wf-weak   #003050 */
  { t: 0.20, r: 0,   g: 96,  b: 128 },   /* --wf-low    #006080 */
  { t: 0.35, r: 0,   g: 160, b: 192 },   /* --wf-mid    #00A0C0 */
  { t: 0.50, r: 0,   g: 224, b: 224 },   /* --wf-signal #00E0E0 */
  { t: 0.65, r: 255, g: 204, b: 0   },   /* --wf-strong #FFCC00 */
  { t: 0.80, r: 255, g: 68,  b: 0   },   /* --wf-peak   #FF4400 */
  { t: 0.92, r: 255, g: 255, b: 255 },   /* --wf-hot    #FFFFFF */
  { t: 1.00, r: 255, g: 255, b: 255 },   /* --wf-hot    #FFFFFF */
]

export function psdToRgb(normalisedValue) {
  const v = Math.max(0, Math.min(1, normalisedValue))

  for (let i = 0; i < STOPS.length - 1; i++) {
    const lo = STOPS[i]
    const hi = STOPS[i + 1]
    if (v >= lo.t && v <= hi.t) {
      const span = hi.t - lo.t
      const t = span === 0 ? 0 : (v - lo.t) / span
      return [
        Math.round(lo.r + (hi.r - lo.r) * t),
        Math.round(lo.g + (hi.g - lo.g) * t),
        Math.round(lo.b + (hi.b - lo.b) * t),
      ]
    }
  }

  return [255, 255, 255]
}

/**
 * Normalise a PSD value in dBFS to a 0-1 position on the STOPS gradient,
 * using an explicit min/max window supplied by the caller.
 *
 * Why explicit min/max instead of a fixed -80..0 range?
 * -----------------------------------------------------
 * Different devices sit at very different absolute dBFS levels for a signal
 * of the same quality. HackRF uses per-band calibrated gain; the ADALM-PLUTO
 * currently runs at a fixed, uncalibrated 30 dB default (Phase 39 will
 * calibrate it), and delivers a much lower-amplitude signal into the same
 * FFT — so its whole PSD curve sits far below HackRF's. A single fixed
 * -80..0 window mapped every Pluto bin to ~0 (near-black), rendering the
 * waterfall invisible even though the signal decoded perfectly.
 *
 * The fix is adaptive: the waterfall hook (useWaterfall.js) measures the
 * min and max of each incoming PSD row and passes them here, so the colour
 * scale always spans exactly the data present — for any device, any gain,
 * with no hard-coded numbers to revisit when Phase 39 lands.
 *
 * @param {number} psdDbValue - the PSD value to map, in dBFS.
 * @param {number} minDb - the value that maps to 0.0 (bottom of the gradient).
 * @param {number} maxDb - the value that maps to 1.0 (top of the gradient).
 * @returns {number} normalised value in [0, 1].
 */
export function normalisePsd(psdDbValue, minDb, maxDb) {
  // Degenerate/invalid window (flat row, or NaN): fall back to a neutral
  // low value so the row renders as noise-floor colour rather than NaN.
  const span = maxDb - minDb
  if (!Number.isFinite(span) || span <= 0) return 0
  const norm = (psdDbValue - minDb) / span
  return Math.max(0, Math.min(1, norm))
}