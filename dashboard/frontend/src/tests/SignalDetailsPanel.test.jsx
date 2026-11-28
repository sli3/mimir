import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import SignalDetailsPanel from '../components/SignalDetailsPanel.jsx'

describe('SignalDetailsPanel AU LEGAL colour', () => {
  it.each([
    ['legal_rx', 'var(--neon-green)'],
    ['LEGAL RX', 'var(--neon-green)'],
    ['verify_before_use', 'var(--neon-red)'],
  ])('renders %s with colour %s', (status, colour) => {
    render(
      <SignalDetailsPanel
        displayed={{ au_legal_status: status }}
        systemStats={null}
        scanResults={null}
        operatorState="MONITORING"
        operatorConfig={{
          opColor: 'var(--neon-cyan)',
          color: 'var(--neon-cyan)',
          label: 'MONITORING',
        }}
        aiReasoning={null}
        operatorTooltipVisible={false}
        setOperatorTooltipVisible={vi.fn()}
        operatorFocused={false}
        setOperatorFocused={vi.fn()}
      />
    )

    // Read the value beside the AU LEGAL label to check this row's colour.
    const value = screen.getByText('AU LEGAL').nextElementSibling
    expect(value).toHaveTextContent(status)
    expect(value.style.color).toBe(colour)
  })
})
