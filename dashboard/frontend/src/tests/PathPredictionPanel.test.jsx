import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

import PathPredictionPanel from '../components/PathPredictionPanel.jsx'

// Mirror of the makeAircraft pattern in AircraftDetailPanel.test.jsx:
// every fixture is a valid in-range contact by default.
const makeAc = (overrides = {}) => ({
  icao: 'ABC123',
  callsign: 'QFA1',
  bearing_deg: 45,
  range_nm: 10,
  ...overrides,
})

// Build a trailsRef of the shape RadarScopePanel owns:
// { current: Map<icao, [{bearing_deg, range_nm, ts}, ...]> }.
const makeTrailsRef = (entries = {}) => ({
  current: new Map(Object.entries(entries)),
})

describe('PathPredictionPanel', () => {
  describe('no-selection state', () => {
    it('renders the placeholder with exact copy when selectedIcao is null', () => {
      render(
        <PathPredictionPanel adsbAircraft={{}} selectedIcao={null} />
      )
      // Verbatim copy match with AircraftDetailPanel's placeholder
      // (mirrors AircraftDetailPanel.test.jsx's assertion).
      const placeholder = screen.getByTestId('radar-prediction-placeholder')
      expect(placeholder).toBeInTheDocument()
      expect(placeholder.textContent).toBe('No aircraft selected')
    })
  })

  describe('gathering state', () => {
    it('renders the gathering state when the selected aircraft has no trail history', () => {
      render(
        <PathPredictionPanel
          adsbAircraft={{ ABC123: makeAc({ callsign: 'TESTCALL' }) }}
          selectedIcao="ABC123"
          trailsRef={makeTrailsRef()}
        />
      )
      const gathering = screen.getByTestId('radar-prediction-gathering')
      expect(gathering).toBeInTheDocument()
      expect(gathering.textContent).toContain('TESTCALL')
      expect(gathering.textContent).toContain('gathering position history (0 fix)')
    })

    it('falls back to the ICAO as identifier when callsign is null', () => {
      render(
        <PathPredictionPanel
          adsbAircraft={{
            ABC123: makeAc({ callsign: null, bearing_deg: 45, range_nm: 10 }),
          }}
          selectedIcao="ABC123"
          trailsRef={makeTrailsRef()}
        />
      )
      const gathering = screen.getByTestId('radar-prediction-gathering')
      expect(gathering.textContent).toContain('ABC123')
      expect(gathering.textContent).toContain('gathering position history')
    })

    it('still renders the gathering state with exactly 1 trail point', () => {
      render(
        <PathPredictionPanel
          adsbAircraft={{ ABC123: makeAc() }}
          selectedIcao="ABC123"
          trailsRef={makeTrailsRef({
            ABC123: [{ bearing_deg: 45, range_nm: 10, ts: 1000 }],
          })}
        />
      )
      const gathering = screen.getByTestId('radar-prediction-gathering')
      expect(gathering.textContent).toContain('gathering position history (1 fix)')
    })
  })

  describe('physics state (2+ trail points)', () => {
    it('does not render the orphan physics readout (replaced by scope box for selected aircraft)', () => {
      // Phase 58-FIX: the standalone θ/Δr readout was removed from this
      // panel — its data now lives in the floating scope box on the
      // selected aircraft's blip in RadarScopePanel, so a third on-screen
      // copy here was redundant. The vector is still derived (used by the
      // LLM column and the anomaly strip's high-turn-rate flag); only the
      // orphan readout text is gone.
      render(
        <PathPredictionPanel
          adsbAircraft={{ ABC123: makeAc() }}
          selectedIcao="ABC123"
          trailsRef={makeTrailsRef({
            ABC123: [
              { bearing_deg: 40, range_nm: 15, ts: 0 },
              { bearing_deg: 60, range_nm: 10, ts: 10000 },
            ],
          })}
        />
      )
      expect(screen.queryByTestId('radar-prediction-physics')).toBeNull()
    })

    it('renders the main column and anomaly strip with 3 trail points', () => {
      render(
        <PathPredictionPanel
          adsbAircraft={{ ABC123: makeAc() }}
          selectedIcao="ABC123"
          trailsRef={makeTrailsRef({
            ABC123: [
              { bearing_deg: 40, range_nm: 15, ts: 0 },
              { bearing_deg: 50, range_nm: 12, ts: 5000 },
              { bearing_deg: 60, range_nm: 10, ts: 10000 },
            ],
          })}
        />
      )
      expect(screen.getByTestId('radar-prediction-llm')).toBeInTheDocument()
      expect(screen.getByTestId('radar-anomaly-strip')).toBeInTheDocument()
      // No orphan physics readout — its content is in the scope box.
      expect(screen.queryByTestId('radar-prediction-physics')).toBeNull()
    })

    it('renders the LlmReasoningPanel child and PredictionGlyph sibling in the main column', () => {
      // Phase 58-FIX: the prediction glyph is now a SIBLING of the
      // LlmReasoningPanel inside the main column (top-left of the
      // panel), no longer nested inside the LLM result block.
      render(
        <PathPredictionPanel
          adsbAircraft={{ ABC123: makeAc() }}
          selectedIcao="ABC123"
          trailsRef={makeTrailsRef({
            ABC123: [
              { bearing_deg: 40, range_nm: 15, ts: 0 },
              { bearing_deg: 60, range_nm: 10, ts: 10000 },
            ],
          })}
        />
      )
      // LLM panel is present (idle = the manual trigger button).
      const llm = screen.getByTestId('radar-prediction-llm')
      expect(llm).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'ANALYSE PATH WITH LLM' })
      ).toBeInTheDocument()
      // Prediction glyph renders as a SIBLING of the LLM panel (top of
      // the main column), not nested inside it.
      const glyph = screen.getByTestId('prediction-glyph')
      expect(glyph).toBeInTheDocument()
      expect(llm.contains(glyph)).toBe(false)
    })
  })

  describe('defensive behaviour', () => {
    it('renders the no-selection state when the selected ICAO is absent from adsbAircraft', () => {
      expect(() => {
        render(
          <PathPredictionPanel adsbAircraft={{}} selectedIcao="ABC123" />
        )
      }).not.toThrow()
      expect(screen.getByTestId('radar-prediction-placeholder').textContent)
        .toBe('No aircraft selected')
    })

    it('renders the no-selection state when adsbAircraft is undefined (default)', () => {
      expect(() => {
        render(<PathPredictionPanel selectedIcao={null} />)
      }).not.toThrow()
      expect(screen.getByTestId('radar-prediction-placeholder')).toBeInTheDocument()
    })

    it('uses a default empty Map when trailsRef is not passed', () => {
      render(
        <PathPredictionPanel
          adsbAircraft={{ ABC123: makeAc() }}
          selectedIcao="ABC123"
        />
      )
      expect(screen.getByTestId('radar-prediction-gathering')).toBeInTheDocument()
    })

    it('does not throw on any combination of missing/null inputs', () => {
      const cases = [
        {},
        { adsbAircraft: null, selectedIcao: null },
        { adsbAircraft: undefined, selectedIcao: 'ABC123' },
        { adsbAircraft: {}, selectedIcao: 'ABC123', trailsRef: { current: new Map() } },
        { adsbAircraft: { ABC123: makeAc() }, selectedIcao: 'ABC123', trailsRef: null },
      ]
      for (const props of cases) {
        expect(() => render(<PathPredictionPanel {...props} />)).not.toThrow()
      }
    })
  })

  describe('continuous anomaly strip (Phase 58)', () => {
    const twoFixes = [
      { bearing_deg: 40, range_nm: 15, ts: 0 },
      { bearing_deg: 80, range_nm: 10, ts: 10000 },
    ]
    const renderPanel = (aircraft, history = []) => render(
      <PathPredictionPanel adsbAircraft={{ ABC123: makeAc(aircraft) }} selectedIcao="ABC123" trailsRef={makeTrailsRef({ ABC123: history })} />
    )

    it('anomaly strip renders continuously when an aircraft is selected', () => {
      const first = renderPanel({ squawk: '7700' })
      expect(screen.getByTestId('radar-anomaly-strip')).toBeInTheDocument()
      first.unmount()
      renderPanel({ squawk: '7700' }, twoFixes)
      expect(screen.getByTestId('radar-anomaly-strip')).toBeInTheDocument()
    })
    it('emergency squawk flag renders during history gathering', () => {
      renderPanel({ squawk: '7700' })
      expect(screen.getByTestId('anomaly-flag-squawk')).toHaveTextContent('7700')
    })
    it('emergency squawk flag does not render for a non-emergency squawk', () => {
      renderPanel({ squawk: '1200' }, twoFixes)
      expect(screen.queryByTestId('anomaly-flag-squawk')).toBeNull()
    })
    it('emergency squawk flag does not render when squawk is null', () => {
      renderPanel({ squawk: null }, twoFixes)
      expect(screen.queryByTestId('anomaly-flag-squawk')).toBeNull()
    })
    it('rapid altitude flag renders during history gathering', () => {
      renderPanel({ vertical_rate: 4000 })
      expect(screen.getByTestId('anomaly-flag-altitude')).toHaveTextContent('CLIMB')
    })
    it('rapid altitude flag does not render at exactly 3000 ft/min', () => {
      renderPanel({ vertical_rate: 3000 })
      expect(screen.queryByTestId('anomaly-flag-altitude')).toBeNull()
    })
    it('rapid altitude flag does not render below the 3000 ft/min threshold', () => {
      renderPanel({ vertical_rate: 2000 })
      expect(screen.queryByTestId('anomaly-flag-altitude')).toBeNull()
    })
    it('high turn rate flag renders when a motion vector is available', () => {
      renderPanel({}, [
        { bearing_deg: 40, range_nm: 15, ts: 0 },
        { bearing_deg: 90, range_nm: 10, ts: 10000 },
      ])
      expect(screen.getByTestId('anomaly-flag-turn')).toBeInTheDocument()
    })
    it('high turn rate flag does not render at exactly 3.0 deg/s', () => {
      renderPanel({}, [
        { bearing_deg: 40, range_nm: 10, ts: 0 },
        { bearing_deg: 70, range_nm: 10, ts: 10000 },
      ])
      expect(screen.queryByTestId('anomaly-flag-turn')).toBeNull()
    })
    it('high turn rate flag does not render during history gathering', () => {
      renderPanel({})
      expect(screen.queryByTestId('anomaly-flag-turn')).toBeNull()
    })
    it('all three anomaly flags can render simultaneously', () => {
      renderPanel({ squawk: '7700', vertical_rate: -4000 }, twoFixes)
      expect(screen.getByTestId('anomaly-flag-squawk')).toBeInTheDocument()
      expect(screen.getByTestId('anomaly-flag-altitude')).toHaveTextContent('DESCENT')
      expect(screen.getByTestId('anomaly-flag-turn')).toBeInTheDocument()
    })
    it('clear state renders the no-anomalies message', () => {
      renderPanel({}, [
        { bearing_deg: 40, range_nm: 10, ts: 0 },
        { bearing_deg: 70, range_nm: 10, ts: 10000 },
      ])
      expect(screen.getByTestId('anomaly-strip-clear')).toHaveTextContent('NO ANOMALIES')
    })
  })
})
