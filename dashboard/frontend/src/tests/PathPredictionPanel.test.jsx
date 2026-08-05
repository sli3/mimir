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
    it('renders theta, deltaR and the horizon with 2 trail points', () => {
      // Oldest->newest: bearing 40 -> 60 over 10 s (10000 ms) = +2.0 deg/s;
      // range 15 -> 10 over 10 s = -0.5 nm/s (closing).
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
      const physics = screen.getByTestId('radar-prediction-physics')
      expect(physics).toBeInTheDocument()
      expect(physics.textContent).toContain('+2.0°/s')
      expect(physics.textContent).toContain('-0.5nm/s')
      expect(physics.textContent).toContain('projecting 45s ahead')
    })

    it('renders the physics state with 3 trail points (extra points do not break it)', () => {
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
      expect(screen.getByTestId('radar-prediction-physics')).toBeInTheDocument()
    })

    it('renders the LlmReasoningPanel child in the right column', () => {
      // Phase 53: the static "LLM REASONING — PENDING" placeholder was
      // replaced by the live LlmReasoningPanel child (idle state = the
      // manual trigger button). This is the only Phase 52 test whose
      // testid changed as a result.
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
      const llm = screen.getByTestId('radar-prediction-llm')
      expect(llm).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'ANALYSE PATH WITH LLM' })
      ).toBeInTheDocument()
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
})
