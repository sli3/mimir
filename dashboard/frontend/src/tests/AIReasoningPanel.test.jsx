import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'
import AIReasoningPanel from '../components/AIReasoningPanel.jsx'

const EMPTY_REASONING = {
  freq_hz: null,
  signal_type: null,
  confidence: null,
  confidence_score: null,
  au_legal_status: null,
  reasoning: null,
  timestamp: null,
}

const SAMPLE_REASONING = {
  freq_hz: 915000000,
  signal_type: 'ism_lora',
  confidence: 'high',
  confidence_score: 0.95,
  au_legal_status: 'LEGAL RX',
  reasoning: 'Signal matches ISM band LoRa characteristics with strong correlation to known chirp spread spectrum patterns.',
  timestamp: '2026-06-03T12:30:00.000Z',
}

const UNAVAILABLE_REASONING = {
  freq_hz: 98000000,
  signal_type: 'unavailable',
  confidence: 'low',
  confidence_score: 0.4,
  au_legal_status: 'UNKNOWN',
  reasoning: null,
  timestamp: '2026-06-03T12:30:00.000Z',
}

describe('AIReasoningPanel', () => {
  it('renders placeholder when aiReasoning signal_type is null', () => {
    render(
      <AIReasoningPanel
        aiReasoning={EMPTY_REASONING}
        focusedFreq={null}
      />
    )
    expect(screen.getByText('AWAITING SIGNAL...')).toBeInTheDocument()
  })

  it('renders signal_type, confidence, reasoning when populated', () => {
    render(
      <AIReasoningPanel
        aiReasoning={SAMPLE_REASONING}
        focusedFreq={915000000}
      />
    )
    expect(screen.getByText('ISM_LORA')).toBeInTheDocument()
    expect(screen.getByText((content) => content.includes('HIGH'))).toBeInTheDocument()
    expect(screen.getByText((content) => content.includes('0.95'))).toBeInTheDocument()
    expect(screen.getByText(/LoRa characteristics/)).toBeInTheDocument()
    expect(screen.getByText(/915\.000 MHz/)).toBeInTheDocument()
    expect(screen.getByText('LEGAL RX')).toBeInTheDocument()
  })

  it('shows yellow LLM TIMEOUT text when signal_type is unavailable', () => {
    render(
      <AIReasoningPanel
        aiReasoning={UNAVAILABLE_REASONING}
        focusedFreq={98000000}
      />
    )
    expect(screen.getByText('TIMEOUT')).toBeInTheDocument()
    expect(screen.getByText('LLM TIMEOUT — ChromaDB match only')).toBeInTheDocument()
  })
})
