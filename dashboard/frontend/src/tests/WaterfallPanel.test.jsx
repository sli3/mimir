import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'

const mockFocusFrequency = vi.fn()

vi.mock('../hooks/useSocket.js', () => ({
  useSocket: () => ({
    spectrumUpdates: [],
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
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    const canvases = document.querySelectorAll('canvas')
    expect(canvases.length).toBe(8)
  })

  it('renders 4 band labels with correct frequency text', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    expect(screen.getByText('98.0 MHz')).toBeTruthy()
    expect(screen.getByText('145.175 MHz')).toBeTruthy()
    expect(screen.getByText('915.0 MHz')).toBeTruthy()
    expect(screen.getByText('1090.0 MHz')).toBeTruthy()
  })

  it('renders 4 band names', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    expect(screen.getByText('FM BROADCAST')).toBeTruthy()
    expect(screen.getByText('APRS')).toBeTruthy()
    expect(screen.getByText('ISM / LoRa')).toBeTruthy()
    expect(screen.getByText('ADS-B')).toBeTruthy()
  })

  it('clicking a label calls focusFrequency with correct freq_hz', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    const label = screen.getByText('98.0 MHz')
    fireEvent.click(label)
    expect(mockFocusFrequency).toHaveBeenCalledWith(98000000)
  })

  it('clicking on APRS label calls focusFrequency with 145175000', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    fireEvent.click(screen.getByText('145.175 MHz'))
    expect(mockFocusFrequency).toHaveBeenCalledWith(145175000)
  })

  it('clicking ISM/LoRa label calls focusFrequency with 915000000', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    fireEvent.click(screen.getByText('915.0 MHz'))
    expect(mockFocusFrequency).toHaveBeenCalledWith(915000000)
  })

  it('clicking ADS-B label calls focusFrequency with 1090000000', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    fireEvent.click(screen.getByText('1090.0 MHz'))
    expect(mockFocusFrequency).toHaveBeenCalledWith(1090000000)
  })

  it('renders without crashing when focusedFreq is set', () => {
    render(<WaterfallPanel focusedFreq={98000000} focusFrequency={mockFocusFrequency} />)
    expect(screen.getByText('98.0 MHz')).toBeTruthy()
    expect(screen.getByText('APRS')).toBeTruthy()
  })
})
