import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import React from 'react'

vi.mock('@react-three/fiber', () => ({
  Canvas: () => <div data-testid="canvas" />,
}))

vi.mock('@react-three/drei', () => ({
  OrbitControls: () => null,
  Grid: () => null,
  Html: ({ children }) => <div>{children}</div>,
}))

import VectorSpacePage, {
  VECTOR_COLOUR_MAP,
  normaliseLabel,
  getPointColour,
} from '../pages/VectorSpacePage.jsx'

describe('VectorSpacePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    document.body.className = ''
  })

  it('renders loading state initially', () => {
    global.fetch = vi.fn(() => new Promise(() => {}))
    render(<VectorSpacePage />)
    expect(screen.getByText(/INITIALISING VECTOR STORE PROJECTION/)).toBeInTheDocument()
  })

  it('renders empty state when store has no records', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: 'empty', count: 0, method: null, points: [] }),
      })
    )
    render(<VectorSpacePage />)
    await waitFor(() => {
      expect(screen.getByText(/NOT ENOUGH DATA YET/)).toBeInTheDocument()
    })
    expect(screen.getByText(/capture_to_vectorstore.py/)).toBeInTheDocument()
  })

  it('renders header with record count and reduction method', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'ok',
            count: 3,
            method: 'pca',
            points: [
              { id: 'r1', x: 1, y: 2, z: 3, label: 'FM_broadcast' },
              { id: 'r2', x: 4, y: 5, z: 6, label: 'ADS_B' },
            ],
          }),
      })
    )
    render(<VectorSpacePage />)
    await waitFor(() => {
      expect(screen.getByText('3')).toBeInTheDocument()
    })
    expect(screen.getByText('PCA')).toBeInTheDocument()
  })

  it('renders error state when fetch fails', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ error: 'projection failed' }),
      })
    )
    render(<VectorSpacePage />)
    await waitFor(() => {
      expect(screen.getByText(/PROJECTION FAILED/)).toBeInTheDocument()
    })
    expect(screen.getByText(/projection failed/)).toBeInTheDocument()
  })

  it('adds vector-space-page class to body and removes on unmount', () => {
    global.fetch = vi.fn(() => new Promise(() => {}))
    const { unmount } = render(<VectorSpacePage />)
    expect(document.body.classList.contains('vector-space-page')).toBe(true)
    unmount()
    expect(document.body.classList.contains('vector-space-page')).toBe(false)
  })
})

describe('VECTOR_COLOUR_MAP', () => {
  it('contains all expected band keys', () => {
    expect(VECTOR_COLOUR_MAP).toHaveProperty('fm_broadcast')
    expect(VECTOR_COLOUR_MAP).toHaveProperty('adsb')
    expect(VECTOR_COLOUR_MAP).toHaveProperty('ism_915')
    expect(VECTOR_COLOUR_MAP).toHaveProperty('aviation_vhf')
    expect(VECTOR_COLOUR_MAP).toHaveProperty('aprs')
    expect(VECTOR_COLOUR_MAP).toHaveProperty('acars')
    expect(VECTOR_COLOUR_MAP).toHaveProperty('ais')
    expect(VECTOR_COLOUR_MAP).toHaveProperty('unknown')
  })

  it('uses the exact colours from the phase spec', () => {
    expect(VECTOR_COLOUR_MAP.fm_broadcast).toBe('#00f0ff')
    expect(VECTOR_COLOUR_MAP.adsb).toBe('#ff2a6d')
    expect(VECTOR_COLOUR_MAP.ism_915).toBe('#05ffa1')
    expect(VECTOR_COLOUR_MAP.aviation_vhf).toBe('#fcee0a')
    expect(VECTOR_COLOUR_MAP.aprs).toBe('#ff8a00')
    expect(VECTOR_COLOUR_MAP.acars).toBe('#b400ff')
    expect(VECTOR_COLOUR_MAP.ais).toBe('#2d7bff')
    expect(VECTOR_COLOUR_MAP.unknown).toBe('#f5f5f5')
  })
})

describe('normaliseLabel', () => {
  it('maps known store labels to colour-map keys', () => {
    expect(normaliseLabel('FM_broadcast')).toBe('fm_broadcast')
    expect(normaliseLabel('Aviation_VHF')).toBe('aviation_vhf')
    expect(normaliseLabel('ACARS')).toBe('acars')
    expect(normaliseLabel('APRS')).toBe('aprs')
    expect(normaliseLabel('AIS')).toBe('ais')
    expect(normaliseLabel('ISM_LoRa')).toBe('ism_915')
    expect(normaliseLabel('ADS_B')).toBe('adsb')
  })

  it('returns lowercased underscore key for unknown labels', () => {
    expect(normaliseLabel('Some_Other_Label')).toBe('some_other_label')
  })

  it('treats null/undefined as unknown', () => {
    expect(normaliseLabel(null)).toBe('unknown')
    expect(normaliseLabel(undefined)).toBe('unknown')
  })
})

describe('getPointColour', () => {
  it('returns the correct colour for known labels', () => {
    expect(getPointColour('FM_broadcast')).toBe('#00f0ff')
    expect(getPointColour('ADS_B')).toBe('#ff2a6d')
    expect(getPointColour('ISM_LoRa')).toBe('#05ffa1')
  })

  it('returns unknown colour for nullish labels', () => {
    expect(getPointColour(null)).toBe('#f5f5f5')
    expect(getPointColour(undefined)).toBe('#f5f5f5')
  })

  it('returns fallback grey for unrecognised labels', () => {
    expect(getPointColour('totally_unknown_band')).toBe('#888888')
  })
})
