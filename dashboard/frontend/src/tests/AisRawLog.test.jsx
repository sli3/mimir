import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, renderHook, act } from '@testing-library/react'
import React from 'react'

vi.mock('socket.io-client', () => ({
  io: vi.fn(),
}))

import { useSocket } from '../hooks/useSocket.js'
import { io } from 'socket.io-client'
import AisVesselPanel from '../components/AisVesselPanel.jsx'

describe('AisRawLog', () => {
  describe('useSocket hook', () => {
    let mockSocket
    let eventHandlers

    beforeEach(() => {
      eventHandlers = {}
      mockSocket = {
        on: vi.fn((event, cb) => {
          if (!eventHandlers[event]) eventHandlers[event] = []
          eventHandlers[event].push(cb)
          return mockSocket
        }),
        off: vi.fn(),
        emit: vi.fn(),
        disconnect: vi.fn(),
      }
      io.mockReturnValue(mockSocket)
    })

    it('populates aisRawLog from ais_message event', () => {
      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['ais_message'][0]

      act(() => {
        handler({
          mmsi: '503000001',
          raw: '!AIVDM,1,1,,A,15Mj23P000G?q7fK>g,0*1B',
          timestamp: '2025-01-01T00:00:00Z',
        })
      })

      expect(result.current.aisRawLog.length).toBe(1)
      expect(result.current.aisRawLog[0].raw).toMatch(/^!AIVDM/)
      expect(result.current.aisRawLog[0].mmsi).toBe('503000001')
    })

    it('ignores ais_message events with no raw field', () => {
      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['ais_message'][0]

      act(() => {
        handler({
          mmsi: '503000001',
          timestamp: '2025-01-01T00:00:00Z',
        })
      })

      expect(result.current.aisRawLog).toEqual([])
    })
  })

  describe('AisVesselPanel RAW DECODE section', () => {
    it('renders RAW DECODE section when tuned and aisRawLog is populated', () => {
      render(
        <AisVesselPanel
          aisMessages={[]}
          focusedFreq={162000000}
          aisRawLog={[{
            mmsi: '503000001',
            raw: '!AIVDM,1,1,,A,test,0*00',
            timestamp: '2025-01-01T00:00:00Z',
          }]}
        />
      )

      expect(screen.getByText('RAW DECODE')).toBeInTheDocument()
      expect(screen.getByText('503000001')).toBeInTheDocument()
    })

    it('shows "Awaiting decodes..." when tuned but aisRawLog is empty', () => {
      render(
        <AisVesselPanel
          aisMessages={[]}
          focusedFreq={162000000}
          aisRawLog={[]}
        />
      )

      const awaiting = screen.queryAllByText('Awaiting decodes...')
      expect(awaiting.length).toBeGreaterThanOrEqual(1)
    })
  })
})
