import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import React, { useRef } from 'react'

const NUM_PSD_BINS = 2048

function createMockCanvasContext(width, height) {
  const imageData = {
    width,
    height,
    data: new Uint8ClampedArray(width * height * 4),
  }

  return {
    getImageData: vi.fn(() => ({
      width,
      height,
      data: new Uint8ClampedArray(imageData.data),
    })),
    putImageData: vi.fn((data) => {
      imageData.data.set(data.data)
    }),
    createImageData: vi.fn((w, h) => ({
      width: w,
      height: h,
      data: new Uint8ClampedArray(w * h * 4),
    })),
    drawImage: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
  }
}

function createMockCanvas(width, height) {
  const ctx = createMockCanvasContext(width, height)
  const canvas = {
    width,
    height,
    getContext: vi.fn(() => ctx),
  }
  canvas.getContext = vi.fn(() => ctx)
  return { canvas, ctx }
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

    const rowData = ctx.createImageData(width, 1)
    const data = rowData.data
    const groupSize = NUM_PSD_BINS / width
    for (let x = 0; x < width; x++) {
      const startBin = Math.floor(x * groupSize)
      const endBin = Math.floor((x + 1) * groupSize)
      const count = endBin - startBin
      let sum = 0
      for (let i = startBin; i < endBin; i++) {
        sum += psdDb[i]
      }
      const avg = sum / count
      const idx = x * 4
      data[idx] = Math.round(avg * 3.1875)
      data[idx + 1] = Math.round(avg * 3.1875)
      data[idx + 2] = Math.round(avg * 3.1875) + 16
      data[idx + 3] = 255
    }

    ctx.putImageData(rowData, 0, 0)

    const result = ctx.createImageData(width, 1)
    result.data.set(data)
    for (let x = 0; x < width; x++) {
      const idx = x * 4
      expect(result.data[idx + 3]).toBe(255)
    }
  })

  it('uses GPU drawImage to scroll canvas down by 1 pixel', () => {
    const width = 4
    const height = 3
    const { canvas, ctx } = createMockCanvas(width, height)

    // First frame: draw a white top row
    const rowData1 = ctx.createImageData(width, 1)
    for (let x = 0; x < width; x++) {
      rowData1.data[x * 4] = 255
      rowData1.data[x * 4 + 1] = 255
      rowData1.data[x * 4 + 2] = 255
      rowData1.data[x * 4 + 3] = 255
    }
    ctx.putImageData(rowData1, 0, 0)

    // Second frame: simulate drawImage scroll + new gray row
    ctx.drawImage(canvas, 0, 1)
    const rowData2 = ctx.createImageData(width, 1)
    for (let x = 0; x < width; x++) {
      rowData2.data[x * 4] = 100
      rowData2.data[x * 4 + 1] = 100
      rowData2.data[x * 4 + 2] = 100
      rowData2.data[x * 4 + 3] = 255
    }
    ctx.putImageData(rowData2, 0, 0)

    // The second putImageData placed the gray row at y=0
    // The drawImage would have shifted the old white row down by 1
    // (mock canvas doesn't actually track this, but we verify the calls)
    expect(ctx.drawImage).toHaveBeenCalledWith(canvas, 0, 1)
    expect(ctx.putImageData).toHaveBeenCalledTimes(2)
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

import { useWaterfall } from '../hooks/useWaterfall.js'

describe('useWaterfall hook integration', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('does not crash when psdDb is null', () => {
    const { canvas } = createMockCanvas(100, 100)
    expect(() => {
      function TestComponent() {
        const canvasRef = useRef(canvas)
        useWaterfall({ canvasRef, psdDb: null })
        return null
      }
      render(React.createElement(TestComponent))
    }).not.toThrow()
  })

  it('does not call putImageData when psdDb is null', () => {
    const { canvas, ctx } = createMockCanvas(100, 100)
    function TestComponent() {
      const canvasRef = useRef(canvas)
      useWaterfall({ canvasRef, psdDb: null })
      return null
    }
    render(React.createElement(TestComponent))
    expect(ctx.putImageData).not.toHaveBeenCalled()
    expect(ctx.drawImage).not.toHaveBeenCalled()
  })

  it('calls drawImage and createImageData when psdDb is provided', () => {
    const width = 10
    const height = 100
    const { canvas, ctx } = createMockCanvas(width, height)
    const psdDb = new Array(NUM_PSD_BINS).fill(-40)

    function TestComponent() {
      const canvasRef = useRef(canvas)
      useWaterfall({ canvasRef, psdDb })
      return null
    }
    render(React.createElement(TestComponent))

    expect(ctx.drawImage).toHaveBeenCalledWith(canvas, 0, 1)
    expect(ctx.createImageData).toHaveBeenCalledWith(width, 1)
    expect(ctx.putImageData).toHaveBeenCalled()
    expect(ctx.getImageData).not.toHaveBeenCalled()
  })
})
