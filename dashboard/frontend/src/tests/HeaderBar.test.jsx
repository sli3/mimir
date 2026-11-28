import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import HeaderBar from '../components/HeaderBar.jsx'

describe('HeaderBar', () => {
  it('links to the standalone radar, vector space and replay pages', () => {
    render(<HeaderBar clock="12:00:00" />)
    expect(screen.getByRole('link', { name: 'RADAR' })).toHaveAttribute('href', '/radar')
    expect(screen.getByRole('link', { name: 'VECTOR SPACE' })).toHaveAttribute('href', '/vectordb')
    expect(screen.getByRole('link', { name: 'REPLAY' })).toHaveAttribute('href', '/replay')
  })
})
