import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'

const mockFocusFrequency = vi.fn()

vi.mock('../hooks/useSocket.js', () => ({
  useSocket: () => ({
    focusedFreq: null,
    focusFrequency: mockFocusFrequency,
    getPsdDb: () => null,
  }),
}))

vi.mock('../hooks/useCanvasSize.js', () => ({
  useCanvasSize: () => ({ width: 300, height: 200 }),
}))

vi.mock('../hooks/useWaterfall.js', () => ({
  useWaterfall: vi.fn(),
}))

import WaterfallPanel from '../components/WaterfallPanel.jsx'

describe('WaterfallPanel', () => {
  beforeEach(() => {
    mockFocusFrequency.mockClear()
  })

  it('renders 8 canvas elements (main + crosshair per band strip)', () => {
    render(<WaterfallPanel />)
    const canvases = document.querySelectorAll('canvas')
    expect(canvases.length).toBe(8)
  })

  it('renders 4 band labels with correct frequency text', () => {
    render(<WaterfallPanel />)
    expect(screen.getByText('98.0 MHz')).toBeTruthy()
    expect(screen.getByText('145.175 MHz')).toBeTruthy()
    expect(screen.getByText('915.0 MHz')).toBeTruthy()
    expect(screen.getByText('1090.0 MHz')).toBeTruthy()
  })

  it('renders 4 band names', () => {
    render(<WaterfallPanel />)
    expect(screen.getByText('FM BROADCAST')).toBeTruthy()
    expect(screen.getByText('APRS')).toBeTruthy()
    expect(screen.getByText('ISM / LoRa')).toBeTruthy()
    expect(screen.getByText('ADS-B')).toBeTruthy()
  })

  it('clicking a label calls focusFrequency with correct freq_hz', () => {
    render(<WaterfallPanel />)
    const label = screen.getByText('98.0 MHz')
    fireEvent.click(label)
    expect(mockFocusFrequency).toHaveBeenCalledWith(98000000)
  })
})
