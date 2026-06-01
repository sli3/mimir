import { useEffect } from 'react'
import { psdToRgb, normalisePsd } from '../utils/colourmap.js'

const NUM_PSD_BINS = 2048

export function useWaterfall({ canvasRef, psdDb, sampleRateHz }) {
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !psdDb || psdDb.length === 0) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const width = canvas.width
    const height = canvas.height
    if (width === 0 || height === 0) return

    const imageData = ctx.getImageData(0, 0, width, height)
    const data = imageData.data

    for (let y = height - 2; y >= 0; y--) {
      const srcStart = y * width * 4
      const dstStart = (y + 1) * width * 4
      data.set(data.subarray(srcStart, srcStart + width * 4), dstStart)
    }

    const groupSize = NUM_PSD_BINS / width

    for (let x = 0; x < width; x++) {
      let sum = 0
      const startBin = Math.floor(x * groupSize)
      const endBin = Math.floor((x + 1) * groupSize)
      const count = endBin - startBin
      for (let i = startBin; i < endBin; i++) {
        sum += psdDb[i]
      }
      const avg = sum / count
      const norm = normalisePsd(avg)
      const [r, g, b] = psdToRgb(norm)
      const idx = x * 4
      data[idx] = r
      data[idx + 1] = g
      data[idx + 2] = b
      data[idx + 3] = 255
    }

    ctx.putImageData(imageData, 0, 0)
  }, [canvasRef, psdDb, sampleRateHz])
}
