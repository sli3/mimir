import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'
import FrequencyList from '../components/FrequencyList.jsx'

describe('FrequencyList', () => {
  const mockFocusFrequency = vi.fn()

  beforeEach(() => {
    mockFocusFrequency.mockClear()
  })

  it('renders 4 frequency rows', () => {
    render(
      <FrequencyList
        scanResults={[]}
        focusedFreq={null}
        focusFrequency={mockFocusFrequency}
      />
    )
    expect(screen.getByText('98.0 MHz')).toBeInTheDocument()
    expect(screen.getByText('145.175 MHz')).toBeInTheDocument()
    expect(screen.getByText('915.0 MHz')).toBeInTheDocument()
    expect(screen.getByText('1090.0 MHz')).toBeInTheDocument()
  })

  it('renders 4 signal names', () => {
    render(
      <FrequencyList
        scanResults={[]}
        focusedFreq={null}
        focusFrequency={mockFocusFrequency}
      />
    )
    expect(screen.getByText('FM BROADCAST')).toBeInTheDocument()
    expect(screen.getByText('APRS')).toBeInTheDocument()
    expect(screen.getByText('ISM / LoRa')).toBeInTheDocument()
    expect(screen.getByText('ADS-B')).toBeInTheDocument()
  })

  it('clicking first row calls focusFrequency with 98000000', () => {
    render(
      <FrequencyList
        scanResults={[]}
        focusedFreq={null}
        focusFrequency={mockFocusFrequency}
      />
    )
    fireEvent.click(screen.getByText('98.0 MHz'))
    expect(mockFocusFrequency).toHaveBeenCalledWith(98000000)
  })

  it('row matching focusedFreq has data-active="true"', () => {
    render(
      <FrequencyList
        scanResults={[]}
        focusedFreq={98000000}
        focusFrequency={mockFocusFrequency}
      />
    )
    const rows = document.querySelectorAll('[data-active="true"]')
    expect(rows.length).toBe(1)
  })

  it('renders greyed, non-clickable row with title attribute when band is unsupported', () => {
    const reason = "Below Pluto's 325 MHz tuning floor (98 MHz)"
    render(
      <FrequencyList
        scanResults={[]}
        focusedFreq={null}
        focusFrequency={mockFocusFrequency}
        unsupportedBands={{ fm_broadcast: reason }}
      />
    )
    const fmRow = screen.getByText('98.0 MHz').closest('div[data-unsupported="true"]')
    expect(fmRow).toBeInTheDocument()
    expect(fmRow).toHaveAttribute('title', reason)
    // Verify cursor is not-allowed
    expect(fmRow.style.cursor).toBe('not-allowed')
    // Verify opacity is reduced
    expect(parseFloat(fmRow.style.opacity)).toBeLessThan(1)
    // Clicking the row does NOT call focusFrequency
    fireEvent.click(fmRow)
    expect(mockFocusFrequency).not.toHaveBeenCalled()
  })

  it('does not render latest scan result for an unsupported row', () => {
    const reason = "Below Pluto's 325 MHz tuning floor (98 MHz)"
    render(
      <FrequencyList
        scanResults={[{
          center_freq_hz: 98000000,
          signal_type: 'fm_broadcast',
          confidence_score: 0.95,
        }]}
        focusedFreq={null}
        focusFrequency={mockFocusFrequency}
        unsupportedBands={{ fm_broadcast: reason }}
      />
    )
    // signal_type and confidence should NOT render for the unsupported row
    expect(screen.queryByText('fm_broadcast')).toBeNull()
    expect(screen.queryByText('95%')).toBeNull()
  })

  it('renders normally and remains clickable when unsupportedBands is empty (HackRF / pre-stats)', () => {
    render(
      <FrequencyList
        scanResults={[]}
        focusedFreq={null}
        focusFrequency={mockFocusFrequency}
        unsupportedBands={{}}
      />
    )
    const fmRow = screen.getByText('98.0 MHz').closest('div[style*="cursor: pointer"]')
    expect(fmRow).not.toBeNull()
    expect(fmRow).not.toHaveAttribute('data-unsupported')
    expect(fmRow.style.cursor).toBe('pointer')
    fireEvent.click(fmRow)
    expect(mockFocusFrequency).toHaveBeenCalledWith(98000000)
  })

  it('unsupportedBands defaults to {} when prop is omitted (zero visual change for HackRF)', () => {
    // Backwards-compat: callers that don't pass unsupportedBands at all
    // get the empty-map default and zero visual change.
    render(
      <FrequencyList
        scanResults={[]}
        focusedFreq={null}
        focusFrequency={mockFocusFrequency}
      />
    )
    const fmRow = screen.getByText('98.0 MHz').closest('div[style*="cursor: pointer"]')
    expect(fmRow).not.toBeNull()
    expect(fmRow).not.toHaveAttribute('data-unsupported')
    fireEvent.click(fmRow)
    expect(mockFocusFrequency).toHaveBeenCalledWith(98000000)
  })
})
