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

  it('renders 14 canvas elements (main + crosshair per band strip) in default mode', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    const canvases = document.querySelectorAll('canvas')
    expect(canvases.length).toBe(14)
  })

  it('renders 7 band labels with correct frequency text in default mode', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    expect(screen.getByText('98.0 MHz')).toBeTruthy()
    expect(screen.getByText('145.175 MHz')).toBeTruthy()
    expect(screen.getByText('127.0 MHz')).toBeTruthy()
    expect(screen.getByText('129.125 MHz')).toBeTruthy()
    expect(screen.getByText('915.0 MHz')).toBeTruthy()
    expect(screen.getByText('161.975 MHz')).toBeTruthy()
    expect(screen.getByText('1090.0 MHz')).toBeTruthy()
  })

  it('renders 7 band names in default mode', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    expect(screen.getByText('FM BROADCAST')).toBeTruthy()
    expect(screen.getByText('APRS')).toBeTruthy()
    expect(screen.getByText('AVIATION VHF')).toBeTruthy()
    expect(screen.getByText('ACARS')).toBeTruthy()
    expect(screen.getByText('ISM / LoRa')).toBeTruthy()
    expect(screen.getByText('AIS')).toBeTruthy()
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

  it('clicking Aviation label calls focusFrequency with 127000000', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    fireEvent.click(screen.getByText('127.0 MHz'))
    expect(mockFocusFrequency).toHaveBeenCalledWith(127000000)
  })

  it('clicking ACARS label calls focusFrequency with 129125000', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    fireEvent.click(screen.getByText('129.125 MHz'))
    expect(mockFocusFrequency).toHaveBeenCalledWith(129125000)
  })

  it('clicking ISM/LoRa label calls focusFrequency with 915000000', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    fireEvent.click(screen.getByText('915.0 MHz'))
    expect(mockFocusFrequency).toHaveBeenCalledWith(915000000)
  })

  it('clicking AIS label calls focusFrequency with 161975000', () => {
    render(<WaterfallPanel focusedFreq={null} focusFrequency={mockFocusFrequency} />)
    fireEvent.click(screen.getByText('161.975 MHz'))
    expect(mockFocusFrequency).toHaveBeenCalledWith(161975000)
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

  it('singleBand=true renders 2 canvases (main + crosshair, one strip only)', () => {
    render(<WaterfallPanel focusedFreq={98000000} focusFrequency={mockFocusFrequency} singleBand={true} />)
    const canvases = document.querySelectorAll('canvas')
    expect(canvases.length).toBe(2)
  })

  it('singleBand=true hides sidebar and shows only one band', () => {
    render(<WaterfallPanel focusedFreq={98000000} focusFrequency={mockFocusFrequency} singleBand={true} />)
    // hideSidebar=true: label text should NOT be present
    expect(screen.queryByText('98.0 MHz')).toBeNull()
    expect(screen.queryByText('145.175 MHz')).toBeNull()
    // Only one band's canvas area should remain
    const canvases = document.querySelectorAll('canvas')
    expect(canvases.length).toBe(2)
  })

  it('singleBand=true with no matching freq falls back to first band and hides sidebar', () => {
    render(<WaterfallPanel focusedFreq={123456789} focusFrequency={mockFocusFrequency} singleBand={true} />)
    // hideSidebar=true: label text should NOT be present even on fallback
    expect(screen.queryByText('98.0 MHz')).toBeNull()
  })

  it('singleBand=false shows label and uses default font size', () => {
    render(<WaterfallPanel focusedFreq={98000000} focusFrequency={mockFocusFrequency} singleBand={false} />)
    const label = screen.getByText('98.0 MHz')
    expect(label.style.fontSize).toBe('9px')
    // Other bands should also be visible
    expect(screen.getByText('145.175 MHz')).toBeTruthy()
  })

  it('singleBand=true does not render label sidebar (hideSidebar)', () => {
    render(<WaterfallPanel focusedFreq={98000000} focusFrequency={mockFocusFrequency} singleBand={true} />)
    // In singleBand mode, hideSidebar=true, so the label div should not be rendered
    // Only the canvas area should remain
    const canvases = document.querySelectorAll('canvas')
    expect(canvases.length).toBe(2)
    // The label text should NOT be present because hideSidebar=true
    expect(screen.queryByText('98.0 MHz')).toBeNull()
  })

  it('singleBand=true: clicking the canvas does NOT call focusFrequency', () => {
    render(
      <WaterfallPanel
        focusedFreq={98000000}
        focusFrequency={mockFocusFrequency}
        singleBand={true}
      />
    )
    const canvases = document.querySelectorAll('canvas')
    // First canvas is the waterfall canvas (not the crosshair overlay)
    fireEvent.click(canvases[0], { clientX: 123, clientY: 50 })
    expect(mockFocusFrequency).not.toHaveBeenCalled()
  })

  it('singleBand=false: clicking the canvas calls focusFrequency with a computed frequency', () => {
    render(
      <WaterfallPanel
        focusedFreq={98000000}
        focusFrequency={mockFocusFrequency}
        singleBand={false}
      />
    )
    const canvases = document.querySelectorAll('canvas')
    fireEvent.click(canvases[0], { clientX: 0, clientY: 50 })
    // focusFrequency should be called with some computed frequency
    expect(mockFocusFrequency).toHaveBeenCalled()
    const calledWith = mockFocusFrequency.mock.calls[0][0]
    expect(typeof calledWith).toBe('number')
  })
})
