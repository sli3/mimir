import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
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
})
