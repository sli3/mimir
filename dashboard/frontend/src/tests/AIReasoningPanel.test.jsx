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

const OFFLINE_REASONING = {
  freq_hz: 98000000,
  signal_type: 'llm_offline',
  confidence: 'low',
  confidence_score: 0.0,
  au_legal_status: 'UNKNOWN',
  reasoning: 'LLM server offline at http://192.168.0.66:8080/v1. Cooldown active — next retry in 42 s.',
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

  it('shows amber LLM OFFLINE text when signal_type is llm_offline', () => {
    render(
      <AIReasoningPanel
        aiReasoning={OFFLINE_REASONING}
        focusedFreq={98000000}
      />
    )
    expect(screen.getByText('LLM OFFLINE')).toBeInTheDocument()
    expect(screen.getByText(/Cooldown active/)).toBeInTheDocument()
  })

  it('renders PINNED badge when isPinned=true and signal_type is set', () => {
    render(<AIReasoningPanel aiReasoning={SAMPLE_REASONING} isPinned={true} />)
    expect(screen.getByText(/PINNED/)).toBeInTheDocument()
  })

  it('does not render PINNED badge when isPinned=false', () => {
    render(<AIReasoningPanel aiReasoning={SAMPLE_REASONING} isPinned={false} />)
    expect(screen.queryByText(/PINNED/)).not.toBeInTheDocument()
  })

  it('does not render PINNED badge when isPinned=true but signal_type is null', () => {
    render(<AIReasoningPanel aiReasoning={EMPTY_REASONING} isPinned={true} />)
    expect(screen.queryByText(/PINNED/)).not.toBeInTheDocument()
  })

  describe('confidence provenance gate (Phase 32)', () => {
    it('dims confidence value when source=fingerprint and no measurement', () => {
      render(
        <AIReasoningPanel
          aiReasoning={{
            ...SAMPLE_REASONING,
            snr_db: null,
            bandwidth_hz: null,
            source: 'fingerprint',
          }}
        />
      )
      const valueSpan = screen.getByText('HIGH 0.95')
      expect(valueSpan.style.color).toBe('var(--text-dim)')
    })

    it('keeps confidence value bright when source=decode (no measurement but provenance overrides)', () => {
      render(
        <AIReasoningPanel
          aiReasoning={{
            ...SAMPLE_REASONING,
            snr_db: null,
            bandwidth_hz: null,
            source: 'decode',
            confidence_score: 1.0,
          }}
        />
      )
      const valueSpan = screen.getByText('HIGH 1.00')
      expect(valueSpan.style.color).toBe('var(--neon-cyan)')
    })

    it('keeps confidence value bright when source=fingerprint with measurement', () => {
      render(
        <AIReasoningPanel
          aiReasoning={{
            ...SAMPLE_REASONING,
            snr_db: 12.0,
            bandwidth_hz: 200000,
            source: 'fingerprint',
          }}
        />
      )
      const valueSpan = screen.getByText('HIGH 0.95')
      expect(valueSpan.style.color).toBe('var(--neon-cyan)')
    })
  })
})
