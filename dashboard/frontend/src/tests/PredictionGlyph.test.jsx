import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

import PredictionGlyph from '../components/PredictionGlyph.jsx'

// The glyph is a pure function of the vector prop: no sockets, no
// timers, no hooks. Every assertion is on the rendered SVG transform.

describe('PredictionGlyph (Phase 55)', () => {
  it('renders the SVG when the vector is non-null', () => {
    render(
      <PredictionGlyph vector={{ thetaDegPerSec: 0.5, deltaRNmPerSec: -0.1 }} />
    )
    expect(screen.getByTestId('prediction-glyph')).toBeInTheDocument()
  })

  it('renders nothing when the vector is null', () => {
    const { container } = render(<PredictionGlyph vector={null} />)
    expect(screen.queryByTestId('prediction-glyph')).toBeNull()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the vector is undefined', () => {
    const { container } = render(<PredictionGlyph vector={undefined} />)
    expect(screen.queryByTestId('prediction-glyph')).toBeNull()
    expect(container).toBeEmptyDOMElement()
  })

  it('rotates the dot row in opposite directions for positive vs negative theta', () => {
    const { unmount } = render(
      <PredictionGlyph vector={{ thetaDegPerSec: 5, deltaRNmPerSec: 0 }} />
    )
    const positive = screen
      .getByTestId('prediction-glyph-row')
      .getAttribute('transform')
    unmount()

    render(
      <PredictionGlyph vector={{ thetaDegPerSec: -5, deltaRNmPerSec: 0 }} />
    )
    const negative = screen
      .getByTestId('prediction-glyph-row')
      .getAttribute('transform')

    expect(positive).toBe('rotate(5 100 45)')
    expect(negative).toBe('rotate(-5 100 45)')
    expect(positive).not.toBe(negative)
  })

  it('applies no rotation transform at all for zero theta', () => {
    render(
      <PredictionGlyph vector={{ thetaDegPerSec: 0, deltaRNmPerSec: 0.2 }} />
    )
    expect(
      screen.getByTestId('prediction-glyph-row').getAttribute('transform')
    ).toBeNull()
  })

  it('clamps an extreme positive theta to the +45 degree visual maximum', () => {
    render(
      <PredictionGlyph vector={{ thetaDegPerSec: 100, deltaRNmPerSec: 0 }} />
    )
    expect(
      screen.getByTestId('prediction-glyph-row').getAttribute('transform')
    ).toBe('rotate(45 100 45)')
  })

  it('clamps an extreme negative theta to the -45 degree visual minimum', () => {
    render(
      <PredictionGlyph vector={{ thetaDegPerSec: -100, deltaRNmPerSec: 0 }} />
    )
    expect(
      screen.getByTestId('prediction-glyph-row').getAttribute('transform')
    ).toBe('rotate(-45 100 45)')
  })
})
