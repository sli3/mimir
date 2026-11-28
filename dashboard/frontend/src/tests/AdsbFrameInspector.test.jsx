import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, renderHook } from '@testing-library/react'
import React from 'react'
import RawDecodePanel from '../components/RawDecodePanel.jsx'
import FrameInspectorPanel from '../components/FrameInspectorPanel.jsx'
import useFrameInspector from '../hooks/useFrameInspector.js'

// UI-OVERHAUL (Change 6): the FRAME INSPECTOR block was extracted from
// AdsbAircraftPanel into FrameInspectorPanel, and the pinnedFrame /
// frameData state plus the /api/adsb/parse effect live in
// hooks/useFrameInspector.js, used by pages/DashboardPage.jsx.
// The harness uses the production hook so pin/unpin, auto-fetch and clearing
// behaviour follow the same state flow as the dashboard.

/** Wire both decode panels to the production frame-inspector hook. */
function Harness({ adsbRawLog }) {
  const { rawView, setRawView, pinnedFrame, setPinnedFrame, frameData } = useFrameInspector(adsbRawLog)

  return (
    <>
      <RawDecodePanel
        adsbRawLog={adsbRawLog}
        rawView={rawView}
        setRawView={setRawView}
        pinnedFrame={pinnedFrame}
        setPinnedFrame={setPinnedFrame}
      />
      <FrameInspectorPanel
        pinnedFrame={pinnedFrame}
        frameData={frameData}
        adsbRawLog={adsbRawLog}
      />
    </>
  )
}

describe('AdsbFrameInspector', () => {
  describe('FRAME INSPECTOR header', () => {
    it('test_frame_inspector_header_always_rendered_when_tuned', () => {
      render(
        <FrameInspectorPanel
          pinnedFrame={null}
          frameData={null}
          adsbRawLog={[]}
        />
      )
      expect(screen.getByText('FRAME INSPECTOR')).toBeInTheDocument()
    })

    it('does not call fetch when adsbRawLog is empty', () => {
      const fetchMock = vi.fn()
      vi.stubGlobal('fetch', fetchMock)

      render(<Harness adsbRawLog={[]} />)

      expect(fetchMock).not.toHaveBeenCalled()
      vi.unstubAllGlobals()
    })
  })

  describe('frame fetching', () => {
    it('clears parsed data immediately when the target hex becomes null', async () => {
      const data = { df: 17, icao: '7C1CA5', fields: { Altitude: '35000 ft' } }
      const fetchMock = vi.fn(() => Promise.resolve({ json: async () => data }))
      vi.stubGlobal('fetch', fetchMock)
      try {
        const { result, rerender } = renderHook(
          ({ log }) => useFrameInspector(log),
          { initialProps: { log: [{ raw_hex: '8D7C1CA5902136CF' }] } }
        )
        await waitFor(() => expect(result.current.frameData).toEqual(data))

        rerender({ log: [] })
        expect(result.current.frameData).toBeNull()
        expect(fetchMock).toHaveBeenCalledTimes(1)
      } finally {
        vi.unstubAllGlobals()
      }
    })

    it('hides the previous parsed frame while a different target is loading', async () => {
      const data = { df: 17, icao: '7C1CA5', fields: {} }
      const fetchMock = vi.fn()
        .mockResolvedValueOnce({ json: async () => data })
        .mockImplementationOnce(() => new Promise(() => {}))
      vi.stubGlobal('fetch', fetchMock)
      try {
        const { result, rerender } = renderHook(
          ({ log }) => useFrameInspector(log),
          { initialProps: { log: [{ raw_hex: '8D7C1CA5902136CF' }] } }
        )
        await waitFor(() => expect(result.current.frameData).toEqual(data))

        rerender({ log: [{ raw_hex: '8D406B902015A678D4D220AA4BDA' }] })
        expect(result.current.frameData).toBeNull()
        expect(fetchMock).toHaveBeenCalledTimes(2)
      } finally {
        vi.unstubAllGlobals()
      }
    })

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

      render(<Harness adsbRawLog={mockRawLog} />)

      expect(fetchMock).toHaveBeenCalled()
      const fetchCallArgs = fetchMock.mock.calls[0][0]
      expect(fetchCallArgs).toContain('/api/adsb/parse?hex=')
      expect(fetchCallArgs).toContain('8D7C1CA5902136CF')

      // Wait for the resolved frame data to actually render. This is the
      // real synchronisation point: it only becomes true after
      // the parsed result has been stored inside the promise chain, so it correctly
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

      const { container } = render(<Harness adsbRawLog={[entry1, entry2]} />)

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
        <FrameInspectorPanel
          pinnedFrame={null}
          frameData={null}
          adsbRawLog={mockRawLog}
        />
      )

      expect(screen.getByText('Decoding...')).toBeInTheDocument()

      vi.unstubAllGlobals()
    })

    it('shows "Awaiting frames..." when adsbRawLog is empty', () => {
      render(
        <FrameInspectorPanel
          pinnedFrame={null}
          frameData={null}
          adsbRawLog={[]}
        />
      )

      const awaitingText = screen.getAllByText('Awaiting frames...')
      expect(awaitingText.length).toBeGreaterThanOrEqual(1)
    })
  })
})
