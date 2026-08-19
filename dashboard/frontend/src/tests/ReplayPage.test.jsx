import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import React from 'react'

import ReplayPage from '../pages/ReplayPage.jsx'

const BASE_REPLAY_RESULT = {
  file_metadata: {
    path: '/tmp/capture_98000000hz_20260819_120000.sigmf-meta',
    core_frequency_hz: 98_000_000,
    core_sample_rate_hz: 2_000_000,
    core_datatype: 'cf32_le',
    mimir_device_profile: 'hackrf',
    fingerprint_field: 'mimir:fingerprint',
  },
  band_resolution: {
    band_key: 'fm_broadcast',
    match: 'exact',
    band_center_freq_hz: 98_000_000,
    profile_source: 'hackrf_base',
  },
  summary: {
    total_chunks: 1,
    matched_chunks: 1,
    mismatched_chunks: 0,
  },
}

function buildFieldResults(overrides = {}) {
  return {
    peak_freq_hz: { saved: 98_000_000, replayed: 98_000_000, match: true },
    peak_power_db: { saved: -20.0, replayed: -20.1, match: true, delta_db: -0.1 },
    noise_floor_db: { saved: -45.0, replayed: -45.0, match: true, delta_db: 0.0 },
    snr_db: { saved: 25.0, replayed: 24.9, match: true, delta_db: -0.1 },
    bandwidth_hz: { saved: 100_000, replayed: 100_000, match: true },
    occupied_bins: { saved: 102, replayed: 102, match: true },
    spectral_flatness: { saved: 0.123, replayed: 0.123, match: true, delta: 0.0 },
    ...overrides,
  }
}

function buildOneShotResult(overrides = {}) {
  return {
    ...BASE_REPLAY_RESULT,
    summary: { total_chunks: 1, matched_chunks: 1, mismatched_chunks: 0 },
    per_chunk_results: [
      {
        replayed_fingerprint: {},
        saved_fingerprint: {},
        comparison: {
          tolerance_db: 0.1,
          all_match: true,
          field_results: buildFieldResults(),
        },
      },
    ],
    ...overrides,
  }
}

function buildRecordResult(chunks = 5, mismatchIndex = -1) {
  const perChunkResults = Array.from({ length: chunks }, (_, idx) => {
    const allMatch = idx !== mismatchIndex
    return {
      replayed_fingerprint: {},
      saved_fingerprint: {},
      sample_start: idx * 16384,
      sample_count: 16384,
      timestamp_sec: idx,
      comparison: {
        tolerance_db: 0.1,
        all_match: allMatch,
        field_results: buildFieldResults(
          allMatch
            ? {}
            : {
                snr_db: { saved: 25.0, replayed: 30.5, match: false, delta_db: 5.5 },
              }
        ),
      },
    }
  })
  return {
    ...BASE_REPLAY_RESULT,
    file_metadata: {
      ...BASE_REPLAY_RESULT.file_metadata,
      fingerprint_field: 'mimir:fingerprint_sequence',
    },
    summary: {
      total_chunks: chunks,
      matched_chunks: chunks - (mismatchIndex >= 0 ? 1 : 0),
      mismatched_chunks: mismatchIndex >= 0 ? 1 : 0,
    },
    per_chunk_results: perChunkResults,
  }
}

function mockFetchCaptures(captures = []) {
  return vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ captures }),
    })
  )
}

function mockFetchReplay(result, status = 200) {
  return vi.fn((_, opts) =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(result),
    })
  )
}

async function selectFirstCapture() {
  const firstRow = screen.getByTestId(/^capture-row-/)
  await act(async () => {
    fireEvent.click(firstRow)
  })
}

describe('ReplayPage picker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.className = ''
  })

  it('renders the loading state while captures are loading', async () => {
    const deferred = {}
    const jsonPromise = new Promise((resolve) => { deferred.resolveJson = resolve })
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => jsonPromise,
      })
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    expect(screen.getByTestId('captures-loading')).toHaveTextContent('LOADING CAPTURES…')
    await act(async () => {
      deferred.resolveJson({ captures: [] })
    })
    await waitFor(() => expect(screen.getByTestId('captures-empty')).toBeInTheDocument())
  })

  it('renders the empty state when no captures exist', async () => {
    vi.stubGlobal('fetch', mockFetchCaptures())
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-empty')).toBeInTheDocument())
    expect(screen.getByTestId('captures-empty')).toHaveTextContent('NO CAPTURES RECORDED YET')
  })

  it('renders the failure state when /api/captures fails', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ error: 'internal_error', detail: 'disk unreadable' }),
      })
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-failure')).toBeInTheDocument())
    expect(screen.getByTestId('captures-failure')).toHaveTextContent('disk unreadable')
  })

  it('renders a capture row with frequency, device, timestamp, chunks, and mode badge', async () => {
    const captures = [
      {
        filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
        mode: 'oneshot',
        chunk_count: 1,
        core_frequency_hz: 98_000_000,
        device: 'hackrf',
        timestamp: '2026-08-19T12:00:00',
      },
      {
        filename: 'capture_915000000hz_20260819_130000.sigmf-meta',
        mode: 'record',
        chunk_count: 5,
        core_frequency_hz: 915_000_000,
        device: 'plutosdr',
        timestamp: '2026-08-19T13:00:00',
      },
    ]
    vi.stubGlobal('fetch', mockFetchCaptures(captures))
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    const oneshotRow = screen.getByTestId('capture-row-capture_98000000hz_20260819_120000.sigmf-meta')
    expect(oneshotRow).toHaveTextContent('98.0 MHz')
    expect(oneshotRow).toHaveTextContent('hackrf')
    expect(oneshotRow).toHaveTextContent('19 Aug 2026')
    expect(oneshotRow).toHaveTextContent('1 chunk')
    expect(oneshotRow).toHaveTextContent('[oneshot]')
    const recordRow = screen.getByTestId('capture-row-capture_915000000hz_20260819_130000.sigmf-meta')
    expect(recordRow).toHaveTextContent('915.0 MHz')
    expect(recordRow).toHaveTextContent('plutosdr')
    expect(recordRow).toHaveTextContent('5 chunks')
    expect(recordRow).toHaveTextContent('[record]')
  })

  it('does not allow clicking rows with mode unknown', async () => {
    const captures = [
      {
        filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
        mode: 'unknown',
        chunk_count: 0,
        core_frequency_hz: null,
        device: null,
        timestamp: '2026-08-19T12:00:00',
        error: 'metadata parse error',
      },
    ]
    vi.stubGlobal('fetch', mockFetchCaptures(captures))
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    const row = screen.getByTestId('capture-row-capture_98000000hz_20260819_120000.sigmf-meta')
    expect(row).toBeDisabled()
  })
})

describe('ReplayPage results view — one-shot', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.className = ''
  })

  it('renders the info line, status dot, label, and all seven field rows', async () => {
    const fetchMock = vi.fn((url) => {
      if (url === '/api/captures') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            captures: [{
              filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
              mode: 'oneshot',
              chunk_count: 1,
              core_frequency_hz: 98_000_000,
              device: 'hackrf',
              timestamp: '2026-08-19T12:00:00',
            }],
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(buildOneShotResult()),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    await selectFirstCapture()
    await waitFor(() => expect(screen.getByTestId('replay-info-line')).toBeInTheDocument())
    expect(screen.getByTestId('replay-info-line')).toHaveTextContent('fm_broadcast · 98.0 MHz · exact · hackrf_base')
    expect(screen.getByText('EXACT MATCH')).toBeInTheDocument()
    const expectedFields = [
      'peak_freq_hz',
      'peak_power_db',
      'noise_floor_db',
      'snr_db',
      'bandwidth_hz',
      'occupied_bins',
      'spectral_flatness',
    ]
    for (const field of expectedFields) {
      expect(screen.getByTestId(`replay-field-row-${field}`)).toBeInTheDocument()
    }
  })
})

describe('ReplayPage results view — record-mode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.className = ''
  })

  it('renders a grid of five cells and the summary line', async () => {
    const fetchMock = vi.fn((url) => {
      if (url === '/api/captures') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            captures: [{
              filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
              mode: 'record',
              chunk_count: 5,
              core_frequency_hz: 98_000_000,
              device: 'hackrf',
              timestamp: '2026-08-19T12:00:00',
            }],
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(buildRecordResult(5)),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    await selectFirstCapture()
    await waitFor(() => expect(screen.getByTestId('replay-record-result')).toBeInTheDocument())
    expect(screen.getByTestId('replay-record-result')).toHaveTextContent('5/5 chunks matched · 0 mismatched')
    for (let i = 0; i < 5; i += 1) {
      expect(screen.getByTestId(`replay-chunk-cell-${i}`)).toBeInTheDocument()
    }
  })

  it('renders record-mode grid for a single-entry sequence capture', async () => {
    const fetchMock = vi.fn((url) => {
      if (url === '/api/captures') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            captures: [{
              filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
              mode: 'record',
              chunk_count: 1,
              core_frequency_hz: 98_000_000,
              device: 'hackrf',
              timestamp: '2026-08-19T12:00:00',
            }],
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(buildRecordResult(1)),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    await selectFirstCapture()
    await waitFor(() => expect(screen.getByTestId('replay-record-result')).toBeInTheDocument())
    expect(screen.getByTestId('replay-record-result')).toHaveTextContent('1/1 chunks matched · 0 mismatched')
    expect(screen.getByTestId('replay-chunk-cell-0')).toBeInTheDocument()
    expect(screen.queryByTestId('replay-oneshot-result')).not.toBeInTheDocument()
  })

  it('clicking a matched cell shows that chunk detail with all seven fields', async () => {
    const result = buildRecordResult(5)
    const fetchMock = vi.fn((url) => {
      if (url === '/api/captures') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            captures: [{
              filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
              mode: 'record',
              chunk_count: 5,
              core_frequency_hz: 98_000_000,
              device: 'hackrf',
              timestamp: '2026-08-19T12:00:00',
            }],
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(result),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    await selectFirstCapture()
    await waitFor(() => expect(screen.getByTestId('replay-chunk-cell-2')).toBeInTheDocument())
    await act(async () => {
      fireEvent.click(screen.getByTestId('replay-chunk-cell-2'))
    })
    await waitFor(() => expect(screen.getByTestId('replay-chunk-detail')).toBeInTheDocument())
    expect(screen.getByText('CHUNK 3 DETAIL')).toBeInTheDocument()
    const expectedFields = [
      'peak_freq_hz',
      'peak_power_db',
      'noise_floor_db',
      'snr_db',
      'bandwidth_hz',
      'occupied_bins',
      'spectral_flatness',
    ]
    for (const field of expectedFields) {
      expect(screen.getByTestId(`replay-field-row-${field}`)).toBeInTheDocument()
    }
  })

  it('clicking a mismatched cell shows mismatched fields in danger colour', async () => {
    const result = buildRecordResult(5, 3)
    const fetchMock = vi.fn((url) => {
      if (url === '/api/captures') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            captures: [{
              filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
              mode: 'record',
              chunk_count: 5,
              core_frequency_hz: 98_000_000,
              device: 'hackrf',
              timestamp: '2026-08-19T12:00:00',
            }],
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(result),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    await selectFirstCapture()
    await waitFor(() => expect(screen.getByTestId('replay-chunk-cell-3')).toBeInTheDocument())
    await act(async () => {
      fireEvent.click(screen.getByTestId('replay-chunk-cell-3'))
    })
    await waitFor(() => expect(screen.getByTestId('replay-chunk-detail')).toBeInTheDocument())
    const snrRow = screen.getByTestId('replay-field-row-snr_db')
    expect(snrRow).toHaveTextContent('25 → 30.5 (+5.50 dB)')
    expect(snrRow.style.color).toBe('var(--neon-red)')
  })
})

describe('ReplayPage back navigation and failures', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.className = ''
  })

  it('clicking BACK returns to the picker without a page reload', async () => {
    const fetchMock = vi.fn((url) => {
      if (url === '/api/captures') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            captures: [{
              filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
              mode: 'oneshot',
              chunk_count: 1,
              core_frequency_hz: 98_000_000,
              device: 'hackrf',
              timestamp: '2026-08-19T12:00:00',
            }],
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(buildOneShotResult()),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    await selectFirstCapture()
    await waitFor(() => expect(screen.getByTestId('replay-oneshot-result')).toBeInTheDocument())
    await act(async () => {
      fireEvent.click(screen.getByTestId('replay-back-link'))
    })
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledTimes(2) // captures + replay, not a page reload
  })

  it('maps busy (503) to the specific retry message', async () => {
    const fetchMock = vi.fn((url) => {
      if (url === '/api/captures') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            captures: [{
              filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
              mode: 'oneshot',
              chunk_count: 1,
              core_frequency_hz: 98_000_000,
              device: 'hackrf',
              timestamp: '2026-08-19T12:00:00',
            }],
          }),
        })
      }
      return Promise.resolve({
        ok: false,
        status: 503,
        json: () => Promise.resolve({ error: 'busy', detail: 'another replay is in progress' }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    await selectFirstCapture()
    await waitFor(() => expect(screen.getByTestId('replay-failure')).toBeInTheDocument())
    expect(screen.getByTestId('replay-failure')).toHaveTextContent(
      'Another replay is in progress; try again in a moment'
    )
  })

  it('maps replay_failed and other error codes to the generic failure message', async () => {
    const fetchMock = vi.fn((url) => {
      if (url === '/api/captures') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            captures: [{
              filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
              mode: 'oneshot',
              chunk_count: 1,
              core_frequency_hz: 98_000_000,
              device: 'hackrf',
              timestamp: '2026-08-19T12:00:00',
            }],
          }),
        })
      }
      return Promise.resolve({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ error: 'replay_failed', detail: 'no fingerprint field' }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    await selectFirstCapture()
    await waitFor(() => expect(screen.getByTestId('replay-failure')).toBeInTheDocument())
    expect(screen.getByTestId('replay-failure')).toHaveTextContent(
      'Replay failed: no fingerprint field'
    )
  })

  it('maps network/transport errors to the transport message', async () => {
    const fetchMock = vi.fn((url) => {
      if (url === '/api/captures') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            captures: [{
              filename: 'capture_98000000hz_20260819_120000.sigmf-meta',
              mode: 'oneshot',
              chunk_count: 1,
              core_frequency_hz: 98_000_000,
              device: 'hackrf',
              timestamp: '2026-08-19T12:00:00',
            }],
          }),
        })
      }
      return Promise.reject(new Error('net down'))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ReplayPage />)
    await waitFor(() => expect(screen.getByTestId('captures-list')).toBeInTheDocument())
    await selectFirstCapture()
    await waitFor(() => expect(screen.getByTestId('replay-failure')).toBeInTheDocument())
    expect(screen.getByTestId('replay-failure')).toHaveTextContent(
      'Could not reach replay server'
    )
  })
})
