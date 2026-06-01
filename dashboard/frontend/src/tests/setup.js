import '@testing-library/jest-dom'
import { vi } from 'vitest'

HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
  getImageData: vi.fn((width, height) => ({
    width,
    height,
    data: new Uint8ClampedArray(width * height * 4),
  })),
  putImageData: vi.fn(),
  clearRect: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
}))

class ResizeObserverMock {
  observe() {}
  disconnect() {}
  unobserve() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverMock)
