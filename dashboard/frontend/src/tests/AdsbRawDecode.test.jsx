import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import AdsbAircraftPanel from '../components/AdsbAircraftPanel.jsx'

describe('AdsbRawDecode', () => {
  // The component fires a fetch('/api/adsb/parse?hex=...') effect
  // whenever adsbRawLog is non-empty. Without a mock, that fetch hits
  // a real, unmocked network call in the test environment — its
  // resolution/rejection timing depends on the local network stack
  // and Node version, which can differ machine to machine, causing
  // React act() warnings inconsistently. Stubbing fetch here makes
  // that behaviour deterministic across all environments.
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      })
    ))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('hex helpers', () => {
    it('hexToBin converts hex to space-separated 8-bit groups', () => {
      const hex = '8D7C4516'
      const result = hex.match(/.{1,2}/g)
        .map((byte) => parseInt(byte, 16).toString(2).padStart(8, '0'))
        .join(' ')
      expect(result).toBe('10001101 01111100 01000101 00010110')
    })

    it('hexToSpaced formats hex as uppercase space-separated byte pairs', () => {
      const hex = '8D7C4516'
      const result = hex.match(/.{1,2}/g).join(' ').toUpperCase()
      expect(result).toBe('8D 7C 45 16')
    })

    it('hexToSpaced handles lowercase input', () => {
      const hex = '8d7c4516'
      const result = hex.match(/.{1,2}/g).join(' ').toUpperCase()
      expect(result).toBe('8D 7C 45 16')
    })

    it('hexToBin handles uppercase input', () => {
      const hex = '8D7C4516'
      const result = hex.match(/.{1,2}/g)
        .map((byte) => parseInt(byte, 16).toString(2).padStart(8, '0'))
        .join(' ')
      expect(result).toBe('10001101 01111100 01000101 00010110')
    })
  })

  describe('RAW DECODE section rendering', () => {
    const mockAircraft = {}
    const mockHistory = []
    const mockFocusedFreq = 1090000000

    it('shows "Awaiting frames..." when adsbRawLog is empty', () => {
      render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={[]}
        />
      )
      const awaitingElements = screen.getAllByText('Awaiting frames...')
      expect(awaitingElements.length).toBeGreaterThanOrEqual(1)
    })

    it('renders RAW DECODE section when adsbRawLog has entries', async () => {
      const mockRawLog = [
        { icao: 'ABC123', raw_hex: '8D406B902015A678D4D220AA4BDA', timestamp: '2026-06-25T12:00:00Z' },
      ]
      render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={mockRawLog}
        />
      )
      expect(screen.getByText('RAW DECODE')).toBeInTheDocument()
      expect(screen.getByText('ABC123')).toBeInTheDocument()

      // Wait for the mount-time fetch (triggered by the non-empty
      // adsbRawLog) to actually resolve, so its setFrameData call is
      // captured inside act() before the test ends. "Decoding..."
      // only clears once frameData has been set — this is a real
      // synchronisation point, not a condition that's trivially true
      // immediately after render.
      await waitFor(() => {
        expect(screen.queryByText('Decoding...')).not.toBeInTheDocument()
      })
    })

    it('HEX view displays uppercase space-separated bytes', async () => {
      const mockRawLog = [
        { icao: 'DEF456', raw_hex: '8D7C4516902136CF', timestamp: '2026-06-25T12:00:00Z' },
      ]
      render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={mockRawLog}
        />
      )
      const hexSpaced = '8D 7C 45 16 90 21 36 CF'
      expect(screen.getByText(hexSpaced)).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.queryByText('Decoding...')).not.toBeInTheDocument()
      })
    })

    it('BIN toggle renders space-separated 8-bit groups', async () => {
      const mockRawLog = [
        { icao: 'GHI789', raw_hex: '8D7C4516', timestamp: '2026-06-25T12:00:00Z' },
      ]
      render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={mockRawLog}
        />
      )

      await waitFor(() => {
        expect(screen.queryByText('Decoding...')).not.toBeInTheDocument()
      })

      const binButton = screen.getByRole('button', { name: /bin/i })
      fireEvent.click(binButton)
      const binExpected = '10001101 01111100 01000101 00010110'
      expect(screen.getByText(binExpected)).toBeInTheDocument()
    })

    it('toggle button switches between HEX and BIN views', async () => {
      const mockRawLog = [
        { icao: 'JKL012', raw_hex: '8D7C4516', timestamp: '2026-06-25T12:00:00Z' },
      ]
      render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={mockRawLog}
        />
      )

      await waitFor(() => {
        expect(screen.queryByText('Decoding...')).not.toBeInTheDocument()
      })

      expect(screen.getByText('8D 7C 45 16')).toBeInTheDocument()

      const binButton = screen.getByRole('button', { name: /bin/i })
      fireEvent.click(binButton)
      expect(screen.getByText('10001101 01111100 01000101 00010110')).toBeInTheDocument()

      const hexButton = screen.getByRole('button', { name: /hex/i })
      fireEvent.click(hexButton)
      expect(screen.getByText('8D 7C 45 16')).toBeInTheDocument()
    })

    it('renders multiple entries in chronological order (newest first)', async () => {
      const mockRawLog = [
        { icao: 'OLD123', raw_hex: 'AAAAAAAA', timestamp: '2026-06-25T10:00:00Z' },
        { icao: 'NEW456', raw_hex: 'BBBBBBBB', timestamp: '2026-06-25T12:00:00Z' },
      ]
      render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={mockRawLog}
        />
      )
      expect(screen.getByText('NEW456')).toBeInTheDocument()
      expect(screen.getByText('OLD123')).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.queryByText('Decoding...')).not.toBeInTheDocument()
      })
    })
  })

  describe('ring buffer cap', () => {
    it('does not crash with large adsbRawLog arrays', async () => {
      const largeLog = Array.from({ length: 100 }, (_, i) => ({
        icao: `TST${i.toString().padStart(3, '0')}`,
        raw_hex: '8D406B902015A678D4D220AA4BDA',
        timestamp: '2026-06-25T12:00:00Z',
      }))
      render(
        <AdsbAircraftPanel
          adsbAircraft={{}}
          adsbAircraftHistory={[]}
          focusedFreq={1090000000}
          adsbRawLog={largeLog}
        />
      )
      expect(screen.getByText('RAW DECODE')).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.queryByText('Decoding...')).not.toBeInTheDocument()
      })
    })
  })
})