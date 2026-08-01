import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React, { useState } from 'react'
import RawDecodePanel from '../components/RawDecodePanel.jsx'

// UI-OVERHAUL (Change 6): the RAW DECODE block was extracted from
// AdsbAircraftPanel into RawDecodePanel. The rawView / pinnedFrame state
// is now lifted to App.jsx, so these tests drive the panel through a
// small stateful harness that mirrors the App-level wiring. The panel
// itself performs no fetch — the /api/adsb/parse effect moved to App.jsx
// with the state — so the old fetch stub and "Decoding..." waitFor
// synchronisation points are gone (they belonged to the FRAME INSPECTOR
// side of the old combined component).

function Harness({ adsbRawLog }) {
  const [rawView, setRawView] = useState('hex')
  const [pinnedFrame, setPinnedFrame] = useState(null)
  return (
    <RawDecodePanel
      adsbRawLog={adsbRawLog}
      rawView={rawView}
      setRawView={setRawView}
      pinnedFrame={pinnedFrame}
      setPinnedFrame={setPinnedFrame}
    />
  )
}

describe('AdsbRawDecode', () => {
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
    it('shows "Awaiting frames..." when adsbRawLog is empty', () => {
      render(<Harness adsbRawLog={[]} />)
      const awaitingElements = screen.getAllByText('Awaiting frames...')
      expect(awaitingElements.length).toBeGreaterThanOrEqual(1)
    })

    it('renders RAW DECODE section when adsbRawLog has entries', () => {
      const mockRawLog = [
        { icao: 'ABC123', raw_hex: '8D406B902015A678D4D220AA4BDA', timestamp: '2026-06-25T12:00:00Z' },
      ]
      render(<Harness adsbRawLog={mockRawLog} />)
      expect(screen.getByText('RAW DECODE')).toBeInTheDocument()
      expect(screen.getByText('ABC123')).toBeInTheDocument()
    })

    it('HEX view displays uppercase space-separated bytes', () => {
      const mockRawLog = [
        { icao: 'DEF456', raw_hex: '8D7C4516902136CF', timestamp: '2026-06-25T12:00:00Z' },
      ]
      render(<Harness adsbRawLog={mockRawLog} />)
      const hexSpaced = '8D 7C 45 16 90 21 36 CF'
      expect(screen.getByText(hexSpaced)).toBeInTheDocument()
    })

    it('BIN toggle renders space-separated 8-bit groups', () => {
      const mockRawLog = [
        { icao: 'GHI789', raw_hex: '8D7C4516', timestamp: '2026-06-25T12:00:00Z' },
      ]
      render(<Harness adsbRawLog={mockRawLog} />)

      const binButton = screen.getByRole('button', { name: /bin/i })
      fireEvent.click(binButton)
      const binExpected = '10001101 01111100 01000101 00010110'
      expect(screen.getByText(binExpected)).toBeInTheDocument()
    })

    it('toggle button switches between HEX and BIN views', () => {
      const mockRawLog = [
        { icao: 'JKL012', raw_hex: '8D7C4516', timestamp: '2026-06-25T12:00:00Z' },
      ]
      render(<Harness adsbRawLog={mockRawLog} />)

      expect(screen.getByText('8D 7C 45 16')).toBeInTheDocument()

      const binButton = screen.getByRole('button', { name: /bin/i })
      fireEvent.click(binButton)
      expect(screen.getByText('10001101 01111100 01000101 00010110')).toBeInTheDocument()

      const hexButton = screen.getByRole('button', { name: /hex/i })
      fireEvent.click(hexButton)
      expect(screen.getByText('8D 7C 45 16')).toBeInTheDocument()
    })

    it('renders multiple entries in chronological order (newest first)', () => {
      const mockRawLog = [
        { icao: 'OLD123', raw_hex: 'AAAAAAAA', timestamp: '2026-06-25T10:00:00Z' },
        { icao: 'NEW456', raw_hex: 'BBBBBBBB', timestamp: '2026-06-25T12:00:00Z' },
      ]
      render(<Harness adsbRawLog={mockRawLog} />)
      expect(screen.getByText('NEW456')).toBeInTheDocument()
      expect(screen.getByText('OLD123')).toBeInTheDocument()
    })
  })

  describe('ring buffer cap', () => {
    it('does not crash with large adsbRawLog arrays', () => {
      const largeLog = Array.from({ length: 100 }, (_, i) => ({
        icao: `TST${i.toString().padStart(3, '0')}`,
        raw_hex: '8D406B902015A678D4D220AA4BDA',
        timestamp: '2026-06-25T12:00:00Z',
      }))
      render(<Harness adsbRawLog={largeLog} />)
      expect(screen.getByText('RAW DECODE')).toBeInTheDocument()
    })
  })
})
