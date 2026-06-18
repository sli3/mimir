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
})
