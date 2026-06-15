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
      const norm = normalisePsd(avg)
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
