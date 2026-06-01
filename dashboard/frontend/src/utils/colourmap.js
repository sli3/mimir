const STOPS = [
  { t: 0.00, r: 3,   g: 3,   b: 16  },
  { t: 0.25, r: 0,   g: 50,  b: 80  },
  { t: 0.50, r: 0,   g: 200, b: 200 },
  { t: 0.75, r: 180, g: 0,   b: 200 },
  { t: 1.00, r: 255, g: 255, b: 255 },
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
