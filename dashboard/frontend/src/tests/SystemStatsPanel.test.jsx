import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'
import SystemStatsPanel from '../components/SystemStatsPanel.jsx'

describe('SystemStatsPanel', () => {
  it('renders all --- placeholders when systemStats is null', () => {
    render(<SystemStatsPanel systemStats={null} />)
    const dashes = screen.getAllByText('---')
    expect(dashes.length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('00000')).toBeInTheDocument()
    expect(screen.getByText('--- ms')).toBeInTheDocument()
  })

  it('renders CONNECTED status when hackrf_status is CONNECTED', () => {
    render(<SystemStatsPanel systemStats={{ hackrf_status: 'CONNECTED' }} />)
    expect(screen.getByText('CONNECTED')).toBeInTheDocument()
  })

  it('renders zero-padded scan count for scan_count=42', () => {
    render(<SystemStatsPanel systemStats={{
      hackrf_status: 'CONNECTED',
      active_frequency_hz: 98000000,
      scan_count: 42,
      queue_depth: 3,
      llm_last_inference_ms: 1240,
    }} />)
    expect(screen.getByText('00042')).toBeInTheDocument()
  })

  it('renders active frequency in MHz format', () => {
    render(<SystemStatsPanel systemStats={{
      hackrf_status: 'CONNECTED',
      active_frequency_hz: 145175000,
      scan_count: 0,
      queue_depth: 0,
      llm_last_inference_ms: 0,
    }} />)
    expect(screen.getByText('145.175 MHz')).toBeInTheDocument()
  })

  it('renders queue depth zero-padded', () => {
    render(<SystemStatsPanel systemStats={{
      hackrf_status: 'CONNECTED',
      active_frequency_hz: 98000000,
      scan_count: 0,
      queue_depth: 3,
      llm_last_inference_ms: 1240,
    }} />)
    expect(screen.getByText('003')).toBeInTheDocument()
  })
})
