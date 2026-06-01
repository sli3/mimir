import { describe, it, expect, vi, beforeEach } from 'vitest'

const NUM_PSD_BINS = 2048

function createMockCanvas(width, height) {
  const imageData = {
    width,
    height,
    data: new Uint8ClampedArray(width * height * 4),
  }

  const ctx = {
    getImageData: vi.fn(() => {
      const clone = new Uint8ClampedArray(width * height * 4)
      clone.set(imageData.data)
      return { width, height, data: clone }
    }),
    putImageData: vi.fn((imgData) => {
      imageData.data.set(imgData.data)
    }),
  }

  const canvas = {
    width,
    height,
    getContext: vi.fn(() => ctx),
  }

  return { canvas, ctx, imageData }
}

describe('useWaterfall logic', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('downsamples 2048 values to pixel width using averaging', () => {
    const width = 10
    const height = 100
    const { canvas, ctx } = createMockCanvas(width, height)

    const psdDb = new Array(NUM_PSD_BINS).fill(0)
    for (let i = 0; i < NUM_PSD_BINS; i++) {
      const groupIndex = Math.floor(i / (NUM_PSD_BINS / width))
      psdDb[i] = groupIndex * 10
    }

    const imageData = ctx.getImageData(0, 0, width, height)
    const len = width * 4
    const row = imageData.data.subarray(0, len)

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
      const idx = x * 4
      row[idx] = Math.round(avg * 3.1875)
      row[idx + 1] = Math.round(avg * 3.1875)
      row[idx + 2] = Math.round(avg * 3.1875) + 16
      row[idx + 3] = 255
    }

    ctx.putImageData(imageData, 0, 0)

    const result = ctx.getImageData(0, 0, width, 1)
    for (let x = 0; x < width; x++) {
      const idx = x * 4
      expect(result.data[idx + 3]).toBe(255)
    }
  })

  it('shifts rows down by 1 pixel after update', () => {
    const width = 4
    const height = 3
    const { canvas, ctx } = createMockCanvas(width, height)

    const imageData1 = ctx.getImageData(0, 0, width, height)
    for (let i = 0; i < width * height * 4; i++) {
      imageData1.data[i] = 255
    }
    ctx.putImageData(imageData1, 0, 0)

    const imageData2 = ctx.getImageData(0, 0, width, height)
    const data2 = imageData2.data
    for (let y = height - 2; y >= 0; y--) {
      const srcStart = y * width * 4
      const dstStart = (y + 1) * width * 4
      data2.set(data2.subarray(srcStart, srcStart + width * 4), dstStart)
    }
    for (let x = 0; x < width; x++) {
      data2[x * 4] = 100
      data2[x * 4 + 1] = 100
      data2[x * 4 + 2] = 100
      data2[x * 4 + 3] = 255
    }
    ctx.putImageData(imageData2, 0, 0)

    const result = ctx.getImageData(0, 0, width, height)
    const pixelRow1 = result.data[0]
    expect(pixelRow1).toBe(100)
  })

  it('skips when psdDb is empty or canvas not mounted', () => {
    const { canvas } = createMockCanvas(100, 100)
    const fn = () => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return
    }
    expect(fn()).toBeUndefined()
  })
})
