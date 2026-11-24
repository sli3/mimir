import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

import HeaderBar from '../components/HeaderBar.jsx'

describe('HeaderBar', () => {
  it('links to the standalone radar and vector space pages', () => {
    render(<HeaderBar clock="12:00:00" />)
    expect(screen.getByRole('link', { name: 'RADAR' })).toHaveAttribute('href', '/radar')
    expect(screen.getByRole('link', { name: 'VECTOR SPACE' })).toHaveAttribute('href', '/vectordb')
  })
})
