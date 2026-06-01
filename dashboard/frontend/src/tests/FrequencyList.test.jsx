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
})
