import { describe, it, expect } from 'vitest'
import { getOperatorState } from '../App.jsx'

describe('getOperatorState', () => {
  it('returns MONITORING when freq_hz is null', () => {
    expect(getOperatorState({ freq_hz: null, novel: null, au_legal_status: null })).toBe('MONITORING')
  })

  it('returns ANOMALY when novel is true', () => {
    expect(getOperatorState({ freq_hz: 98000000, novel: true, au_legal_status: 'legal_rx' })).toBe('ANOMALY')
  })

  it('returns VERIFY when novel is false and au_legal_status is verify_before_use', () => {
    expect(getOperatorState({ freq_hz: 98000000, novel: false, au_legal_status: 'verify_before_use' })).toBe('VERIFY')
  })

  it('returns NORMAL when novel is false and au_legal_status is legal_rx', () => {
    expect(getOperatorState({ freq_hz: 98000000, novel: false, au_legal_status: 'legal_rx' })).toBe('NORMAL')
  })

  it('returns VERIFY for LLM-offline fallback (novel=false, verify_before_use)', () => {
    expect(getOperatorState({ freq_hz: 98000000, novel: false, au_legal_status: 'verify_before_use', reasoning: 'LLM offline — using ChromaDB match only' })).toBe('VERIFY')
  })

  it('returns NORMAL for ADS-B confirmed decode (novel=false, legal_rx)', () => {
    expect(getOperatorState({ freq_hz: 1090000000, novel: false, au_legal_status: 'legal_rx', reasoning: 'Confirmed ADS-B Mode S frame' })).toBe('NORMAL')
  })

  it('does NOT default to NORMAL when novel is null (incomplete data)', () => {
    expect(getOperatorState({ freq_hz: 98000000, novel: null, au_legal_status: 'legal_rx' })).not.toBe('NORMAL')
  })

  it('falls through to VERIFY for an unrecognised au_legal_status value', () => {
    expect(getOperatorState({ freq_hz: 98000000, novel: false, au_legal_status: 'something_unexpected' })).toBe('VERIFY')
  })
})
