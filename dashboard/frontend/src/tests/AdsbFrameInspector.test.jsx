import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import AdsbAircraftPanel from '../components/AdsbAircraftPanel.jsx'

describe('AdsbFrameInspector', () => {
  const mockAircraft = {}
  const mockHistory = []
  const mockFocusedFreq = 1090000000

  describe('FRAME INSPECTOR header', () => {
    it('test_frame_inspector_header_always_rendered_when_tuned', () => {
      render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={[]}
        />
      )
      expect(screen.getByText('FRAME INSPECTOR')).toBeInTheDocument()
    })

    it('does not call fetch when adsbRawLog is empty', () => {
      const fetchMock = vi.fn()
      vi.stubGlobal('fetch', fetchMock)

      render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={[]}
        />
      )

      expect(fetchMock).not.toHaveBeenCalled()
      vi.unstubAllGlobals()
    })
  })

  describe('frame fetching', () => {
    it('test_frame_inspector_fetches_newest_frame_automatically', async () => {
      const mockFrameData = {
        df: 17,
        icao: '7C1CA5',
        crc_ok: true,
        typecode: 11,
        message_type: 'Airborne position',
        fields: {
          Altitude: '35000 ft',
        },
      }
      const fetchMock = vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockFrameData),
        })
      )
      vi.stubGlobal('fetch', fetchMock)

      const mockRawLog = [
        { icao: '7C1CA5', raw_hex: '8D7C1CA5902136CF', timestamp: '2026-06-25T12:00:00Z' },
      ]

      render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={mockRawLog}
        />
      )

      expect(fetchMock).toHaveBeenCalled()
      const fetchCallArgs = fetchMock.mock.calls[0][0]
      expect(fetchCallArgs).toContain('/api/adsb/parse?hex=')
      expect(fetchCallArgs).toContain('8D7C1CA5902136CF')

      // Wait for the resolved frame data to actually render. This is the
      // real synchronisation point: it only becomes true after
      // setFrameData has run inside the promise chain, so it correctly
      // captures that state update inside act() via RTL's waitFor
      // (NOT vi.waitFor, which is React/act-unaware and does not help
      // here — see https://github.com/vitest-dev/vitest/discussions/7062).
      await waitFor(() => {
        expect(screen.getByText('35000 ft')).toBeInTheDocument()
      })

      vi.unstubAllGlobals()
    })
  })

  describe('pin/unpin functionality', () => {
    it('test_frame_inspector_pin_unpin_on_click', async () => {
      const mockFrameData = {
        df: 17,
        icao: 'ENTRY2',
        crc_ok: true,
        typecode: 11,
        message_type: 'Airborne position',
        fields: {},
      }
      const fetchMock = vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockFrameData),
        })
      )
      vi.stubGlobal('fetch', fetchMock)

      const entry1 = { icao: 'ENTRY1', raw_hex: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA', timestamp: '2026-06-25T12:00:00Z' }
      const entry2 = { icao: 'ENTRY2', raw_hex: 'BBBBBBBBBBBBBBBBBBBBBBBBBBBB', timestamp: '2026-06-25T12:01:00Z' }

      const { container } = render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={[entry1, entry2]}
        />
      )

      // Wait for the automatic mount-time fetch (targetHex defaults to
      // entry1, the newest entry, before any pin exists) to actually
      // resolve and clear the "Decoding..." placeholder, before we start
      // clicking around. "Decoding..." only disappears once frameData
      // has been set, so this is a real synchronisation point rather
      // than a condition that's trivially true immediately after render.
      await waitFor(() => {
        expect(screen.queryByText('Decoding...')).not.toBeInTheDocument()
      })

      const allText = container.textContent
      expect(allText).toContain('ENTRY1')
      expect(allText).toContain('ENTRY2')

      const clickTargets = Array.from(container.querySelectorAll('div[style*="cursor"]'))
      const entry2Target = clickTargets.find(el => el.textContent.includes('ENTRY2'))
      expect(entry2Target).toBeDefined()

      fireEvent.click(entry2Target)

      await waitFor(() => {
        expect(screen.getByText('(PINNED)')).toBeInTheDocument()
      })

      fireEvent.click(entry2Target)

      await waitFor(() => {
        expect(screen.queryByText('(PINNED)')).toBeNull()
      })

      vi.unstubAllGlobals()
    })
  })

  describe('decoding state', () => {
    it('shows "Decoding..." when frameData is null and frames exist', () => {
      const fetchMock = vi.fn(() => new Promise(() => {}))
      vi.stubGlobal('fetch', fetchMock)

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

      expect(screen.getByText('Decoding...')).toBeInTheDocument()

      vi.unstubAllGlobals()
    })

    it('shows "Awaiting frames..." when adsbRawLog is empty', () => {
      const fetchMock = vi.fn()
      vi.stubGlobal('fetch', fetchMock)

      render(
        <AdsbAircraftPanel
          adsbAircraft={mockAircraft}
          adsbAircraftHistory={mockHistory}
          focusedFreq={mockFocusedFreq}
          adsbRawLog={[]}
        />
      )

      const awaitingText = screen.getAllByText('Awaiting frames...')
      expect(awaitingText.length).toBeGreaterThanOrEqual(1)

      vi.unstubAllGlobals()
    })
  })
})