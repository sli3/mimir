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

export function normalisePsd(psdDbValue, minDb = -80, maxDb = 0) {
  const norm = (psdDbValue - minDb) / (maxDb - minDb)
  return Math.max(0, Math.min(1, norm))
}
