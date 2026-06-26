import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, renderHook, act } from '@testing-library/react'
import React from 'react'

vi.mock('socket.io-client', () => ({
  io: vi.fn(),
}))

import { useSocket } from '../hooks/useSocket.js'
import { io } from 'socket.io-client'
import AcarsMessagePanel from '../components/AcarsMessagePanel.jsx'

describe('AcarsRawLog', () => {
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

    it('populates acarsRawLog from acars_message event', () => {
      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['acars_message'][0]

      act(() => {
        handler({
          registration: 'VH-OGE',
          text: 'HELLO',
          raw: 'HELLO',
          timestamp: '2025-01-01T00:00:00Z',
        })
      })

      expect(result.current.acarsRawLog.length).toBe(1)
      expect(result.current.acarsRawLog[0].raw).toBe('HELLO')
      expect(result.current.acarsRawLog[0].registration).toBe('VH-OGE')
    })

    it('ignores acars_message events with no raw field', () => {
      const { result } = renderHook(() => useSocket())
      const handler = eventHandlers['acars_message'][0]

      act(() => {
        handler({
          registration: 'VH-OGE',
          text: 'HELLO',
          timestamp: '2025-01-01T00:00:00Z',
        })
      })

      expect(result.current.acarsRawLog).toEqual([])
    })
  })

  describe('AcarsMessagePanel RAW DECODE section', () => {
    it('renders RAW DECODE section when tuned and acarsRawLog is populated', () => {
      render(
        <AcarsMessagePanel
          acarsMessages={[]}
          focusedFreq={129125000}
          acarsRawLog={[{
            registration: 'VH-OGE',
            raw: 'HELLO',
            timestamp: '2025-01-01T00:00:00Z',
          }]}
        />
      )

      expect(screen.getByText('RAW DECODE')).toBeInTheDocument()
      expect(screen.getByText('HELLO')).toBeInTheDocument()
    })

    it('shows "Awaiting decodes..." when tuned but acarsRawLog is empty', () => {
      render(
        <AcarsMessagePanel
          acarsMessages={[]}
          focusedFreq={129125000}
          acarsRawLog={[]}
        />
      )

      const awaiting = screen.queryAllByText('Awaiting decodes...')
      expect(awaiting.length).toBeGreaterThanOrEqual(1)
    })
  })
})
