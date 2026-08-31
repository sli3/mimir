import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'
import SpectrometerBar from '../components/SpectrometerBar.jsx'
import { WATERFALL_LABEL_WIDTH } from '../components/WaterfallPanel.jsx'

const mockFocusFrequency = vi.fn()

vi.mock('../hooks/useCanvasSize.js', () => ({
  useCanvasSize: () => ({ width: 300, height: 64 }),
}))

describe('SpectrometerBar', () => {
  it('renders a canvas element without crashing', () => {
    const { container } = render(
      <SpectrometerBar
        spectrumUpdates={[]}
        focusedFreq={98000000}
        focusFrequency={mockFocusFrequency}
      />
    )
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
  })

  it('renders canvas when spectrum updates are provided', () => {
    const { container } = render(
      <SpectrometerBar
        spectrumUpdates={[
          { center_freq_hz: 98000000, psd_db: new Array(2048).fill(-50), ts: Date.now() },
        ]}
        focusedFreq={98000000}
        focusFrequency={mockFocusFrequency}
      />
    )
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
  })

  it('renders canvas when focusedFreq is null', () => {
    const { container } = render(
      <SpectrometerBar
        spectrumUpdates={[]}
        focusedFreq={null}
        focusFrequency={mockFocusFrequency}
      />
    )
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
  })

  it('renders left spacer div with correct width', () => {
    const { container } = render(
      <SpectrometerBar
        spectrumUpdates={[]}
        focusedFreq={98000000}
        focusFrequency={mockFocusFrequency}
      />
    )
    const wrapper = container.firstChild
    expect(wrapper).toBeInTheDocument()
    const children = wrapper.querySelectorAll('div')
    // First child should be the spacer div
    const spacer = children[0]
    expect(spacer).toBeInTheDocument()
    expect(spacer.style.width).toBe(`${WATERFALL_LABEL_WIDTH}px`)
    expect(spacer.style.flexShrink).toBe('0')
  })

  it('canvas spans full width when label width is 0', () => {
    const { container } = render(
      <SpectrometerBar
        spectrumUpdates={[]}
        focusedFreq={98000000}
        focusFrequency={mockFocusFrequency}
      />
    )
    const wrapper = container.firstChild
    const canvas = wrapper.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
    // When WATERFALL_LABEL_WIDTH is 0, the canvas fills the container
    expect(canvas.style.flex).toBe('1 1 0%')
  })

  it('click handler does NOT call focusFrequency (cursor is display-only)', () => {
    const { container } = render(
      <SpectrometerBar
        spectrumUpdates={[
          { center_freq_hz: 98000000, psd_db: new Array(2048).fill(-50), ts: Date.now() },
        ]}
        focusedFreq={98000000}
        focusFrequency={mockFocusFrequency}
      />
    )
    const wrapper = container.firstChild
    const canvas = wrapper.querySelector('canvas')
    expect(canvas).toBeInTheDocument()

    // Mock canvas dimensions
    canvas.width = 1000
    canvas.height = 64
    canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 64 })

    // Click at the center of the canvas — cursor should draw but frequency should NOT change
    mockFocusFrequency.mockClear()
    fireEvent.click(canvas, {
      clientX: 500,
      bubbles: true,
    })
    expect(mockFocusFrequency).not.toHaveBeenCalled()
  })

  it('clicking SpectrometerBar does NOT call focusFrequency', () => {
    mockFocusFrequency.mockClear()
    const { container } = render(
      <SpectrometerBar
        spectrumUpdates={[]}
        focusedFreq={98000000}
        focusFrequency={mockFocusFrequency}
      />
    )
    const wrapper = container.firstChild
    const canvas = wrapper.querySelector('canvas')
    expect(canvas).toBeInTheDocument()

    canvas.width = 300
    canvas.height = 64
    canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 300, height: 64 })

    fireEvent.click(canvas, { clientX: 75, clientY: 32, bubbles: true })
    expect(mockFocusFrequency).not.toHaveBeenCalled()
  })

  it('renders PSD stroke when spectrum update is within tolerance of focusedFreq (Phase 76 demo-mode offset)', () => {
    const mockCtx = {
      fillStyle: '',
      fillRect: vi.fn(),
      beginPath: vi.fn(),
      closePath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      strokeStyle: '',
      lineWidth: 0,
      stroke: vi.fn(),
      fill: vi.fn(),
      setLineDash: vi.fn(),
      fillText: vi.fn(),
      font: '',
      measureText: vi.fn(() => ({ width: 50 })),
    }
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mockCtx)

    render(
      <SpectrometerBar
        spectrumUpdates={[
          { center_freq_hz: 1_090_030_000, psd_db: new Array(2048).fill(-50), ts: Date.now() },
        ]}
        focusedFreq={1_090_000_000}
        focusFrequency={mockFocusFrequency}
      />
    )

    expect(mockCtx.beginPath).toHaveBeenCalled()
    expect(mockCtx.stroke).toHaveBeenCalled()
  })

  it('clicking SpectrometerBar at different positions never calls focusFrequency', () => {
    mockFocusFrequency.mockClear()
    const { container } = render(
      <SpectrometerBar
        spectrumUpdates={[]}
        focusedFreq={98000000}
        focusFrequency={mockFocusFrequency}
      />
    )
    const wrapper = container.firstChild
    const canvas = wrapper.querySelector('canvas')
    expect(canvas).toBeInTheDocument()

    canvas.width = 300
    canvas.height = 64
    canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 300, height: 64 })

    fireEvent.click(canvas, { clientX: 10, clientY: 32, bubbles: true })
    fireEvent.click(canvas, { clientX: 150, clientY: 32, bubbles: true })
    fireEvent.click(canvas, { clientX: 290, clientY: 32, bubbles: true })
    expect(mockFocusFrequency).not.toHaveBeenCalled()
  })
})
