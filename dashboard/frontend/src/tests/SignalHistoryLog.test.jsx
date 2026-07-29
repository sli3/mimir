import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'
import SignalHistoryLog from '../components/SignalHistoryLog.jsx'

describe('SignalHistoryLog', () => {
  it('renders container without crash when scanResults is empty', () => {
    const { container } = render(<SignalHistoryLog scanResults={[]} />)
    expect(container).toBeTruthy()
  })

  it('shows placeholder text when scanResults is empty', () => {
    render(<SignalHistoryLog scanResults={[]} />)
    expect(screen.getByText('No signals recorded')).toBeInTheDocument()
  })

  it('renders two entries when two scan results provided', () => {
    const results = [
      { timestamp: 1000000000, center_freq_hz: 98000000, label: 'FM', confidence_score: 0.95 },
      { timestamp: 1000000001, center_freq_hz: 145175000, label: 'APRS', confidence_score: 0.88 },
    ]
    render(<SignalHistoryLog scanResults={results} />)
    expect(screen.getByText('FM')).toBeInTheDocument()
    expect(screen.getByText('APRS')).toBeInTheDocument()
  })

  it('first entry text appears before second in DOM order', () => {
    const results = [
      { timestamp: 1000000000, center_freq_hz: 98000000, label: 'ALPHA', confidence_score: 0.95 },
      { timestamp: 1000000001, center_freq_hz: 145175000, label: 'BRAVO', confidence_score: 0.88 },
    ]
    render(<SignalHistoryLog scanResults={results} />)
    const entries = screen.getAllByText(/ALPHA|BRAVO/)
    expect(entries[0]).toHaveTextContent('ALPHA')
    expect(entries[1]).toHaveTextContent('BRAVO')
  })

  it('calls onPinReasoning with the entry when a row is clicked', () => {
    const onPin = vi.fn()
    const results = [
      { timestamp: 1000000000, center_freq_hz: 98000000, signal_type: 'fm_broadcast', label: 'FM', confidence_score: 0.95, confidence: 'high', au_legal_status: 'LEGAL RX', reasoning: 'Test reasoning' },
    ]
    render(<SignalHistoryLog scanResults={results} onPinReasoning={onPin} pinnedTimestamp={null} />)
    fireEvent.click(screen.getByText('fm_broadcast'))
    expect(onPin).toHaveBeenCalledWith(results[0])
  })

  it('applies data-pinned="true" to the row whose timestamp matches pinnedTimestamp', () => {
    const results = [
      { timestamp: 111, center_freq_hz: 98000000, label: 'FM', confidence_score: 0.9 },
      { timestamp: 222, center_freq_hz: 145175000, label: 'APRS', confidence_score: 0.8 },
    ]
    const { container } = render(
      <SignalHistoryLog scanResults={results} onPinReasoning={vi.fn()} pinnedTimestamp={111} />
    )
    const pinned = container.querySelectorAll('[data-pinned="true"]')
    expect(pinned.length).toBe(1)
  })

  it('does not throw when onPinReasoning is not provided and a row exists', () => {
    const results = [
      { timestamp: 1000000000, center_freq_hz: 98000000, label: 'FM', confidence_score: 0.95 },
    ]
    expect(() => {
      render(<SignalHistoryLog scanResults={results} />)
    }).not.toThrow()
  })

  it('calls onPinReasoning each time a row is clicked (toggle behaviour in parent)', () => {
    const onPin = vi.fn()
    const results = [
      { timestamp: 1000000000, center_freq_hz: 98000000, signal_type: 'fm_broadcast', confidence_score: 0.95 },
    ]
    render(<SignalHistoryLog scanResults={results} onPinReasoning={onPin} pinnedTimestamp={null} />)
    fireEvent.click(screen.getByText('fm_broadcast'))
    fireEvent.click(screen.getByText('fm_broadcast'))
    expect(onPin).toHaveBeenCalledTimes(2)
    expect(onPin).toHaveBeenCalledWith(results[0])
  })

  it('F1: renders [PEAK] when is_burst is true', () => {
    const results = [
      {
        timestamp: 1000000000,
        center_freq_hz: 1090000000,
        signal_type: 'adsb',
        confidence_score: 0.95,
        is_burst: true,
      },
    ]
    const { container } = render(<SignalHistoryLog scanResults={results} />)
    expect(container.textContent).toContain('[PEAK]')
  })

  it('F2: does NOT render [PEAK] when is_burst is false', () => {
    const results = [
      {
        timestamp: 1000000000,
        center_freq_hz: 98000000,
        signal_type: 'fm_broadcast',
        confidence_score: 0.95,
        is_burst: false,
      },
    ]
    const { container } = render(<SignalHistoryLog scanResults={results} />)
    expect(container.textContent).not.toContain('[PEAK]')
  })

  it('F3: does NOT render [PEAK] when is_burst is absent entirely', () => {
    const results = [
      {
        timestamp: 1000000000,
        center_freq_hz: 98000000,
        signal_type: 'fm_broadcast',
        confidence_score: 0.95,
      },
    ]
    const { container } = render(<SignalHistoryLog scanResults={results} />)
    expect(container.textContent).not.toContain('[PEAK]')
  })

  it('F4: does NOT render [PEAK] when is_burst is null', () => {
    const results = [
      {
        timestamp: 1000000000,
        center_freq_hz: 98000000,
        signal_type: 'fm_broadcast',
        confidence_score: 0.95,
        is_burst: null,
      },
    ]
    const { container } = render(<SignalHistoryLog scanResults={results} />)
    expect(container.textContent).not.toContain('[PEAK]')
  })

  it('F5 regression guard: old gap formula would fire, new check does not', () => {
    // Old formula: (peak_bin_power_db - peak_power_db) >= 10
    // Gap here is 20 dB — would have rendered [PEAK] under the old code.
    // is_burst is false (backend's decision) — must NOT render [PEAK].
    // This test fails if anyone re-introduces the local gap computation.
    const results = [
      {
        timestamp: 1000000000,
        center_freq_hz: 98000000,
        signal_type: 'fm_broadcast',
        confidence_score: 0.95,
        peak_bin_power_db: -50.0,
        peak_power_db: -70.0,
        is_burst: false,
      },
    ]
    const { container } = render(<SignalHistoryLog scanResults={results} />)
    expect(container.textContent).not.toContain('[PEAK]')
  })

  it('F6: mixed list renders [PEAK] only on bursting subset', () => {
    const results = [
      { timestamp: 1000000004, center_freq_hz: 1090000000, signal_type: 'adsb', confidence_score: 0.95, is_burst: true },
      { timestamp: 1000000003, center_freq_hz: 98000000, signal_type: 'fm_broadcast', confidence_score: 0.95, is_burst: false },
      { timestamp: 1000000002, center_freq_hz: 145175000, signal_type: 'aprs', confidence_score: 0.95, is_burst: true },
      { timestamp: 1000000001, center_freq_hz: 129125000, signal_type: 'acars', confidence_score: 0.95 },
      { timestamp: 1000000000, center_freq_hz: 162000000, signal_type: 'ais', confidence_score: 0.95, is_burst: null },
    ]
    const { container } = render(<SignalHistoryLog scanResults={results} />)
    // Count [PEAK] occurrences in the rendered text. Expect exactly 2:
    // the ADS-B entry (is_burst: true) and the APRS entry (is_burst: true).
    const text = container.textContent
    const matches = text.match(/\[PEAK\]/g) || []
    expect(matches.length).toBe(2)
    // Sanity: every entry's other fields still render.
    expect(text).toContain('adsb')
    expect(text).toContain('fm_broadcast')
    expect(text).toContain('aprs')
    expect(text).toContain('acars')
    expect(text).toContain('ais')
  })
})
