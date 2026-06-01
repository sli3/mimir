import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

vi.mock('../hooks/useSocket.js', () => ({
  useSocket: () => ({
    scanResults: [],
    spectrumUpdates: [],
    systemStats: null,
    focusedFreq: null,
    focusFrequency: vi.fn(),
    getPsdDb: vi.fn(() => null),
    isConnected: false,
  }),
}))

import App from '../App.jsx'

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without crashing', () => {
    render(<App />)
  })

  it('renders MIMIR header', () => {
    render(<App />)
    expect(screen.getByText('MIMIR')).toBeInTheDocument()
  })

  it('renders AWAITING SIGNAL DATA', () => {
    render(<App />)
    expect(screen.getByText('AWAITING SIGNAL DATA')).toBeInTheDocument()
  })

  it('renders SELECT A FREQUENCY', () => {
    render(<App />)
    expect(screen.getByText('SELECT A FREQUENCY')).toBeInTheDocument()
  })

  it('renders TO ANALYSE', () => {
    render(<App />)
    expect(screen.getByText('TO ANALYSE')).toBeInTheDocument()
  })

  it('renders OPERATOR', () => {
    render(<App />)
    expect(screen.getByText('OPERATOR')).toBeInTheDocument()
  })

  it('renders SDR STATUS', () => {
    render(<App />)
    expect(screen.getByText('SDR STATUS')).toBeInTheDocument()
  })
})
