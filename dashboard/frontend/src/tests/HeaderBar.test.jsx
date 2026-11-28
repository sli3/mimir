import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import HeaderBar from '../components/HeaderBar.jsx'

describe('HeaderBar', () => {
  it('links to all four pages', () => {
    render(<HeaderBar current="dashboard" />)
    expect(screen.getByRole('link', { name: 'DASHBOARD' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'RADAR' })).toHaveAttribute('href', '/radar')
    expect(screen.getByRole('link', { name: 'VECTOR SPACE' })).toHaveAttribute('href', '/vectordb')
    expect(screen.getByRole('link', { name: 'REPLAY' })).toHaveAttribute('href', '/replay')
  })

  it.each([
    ['dashboard', 'DASHBOARD'],
    ['radar', 'RADAR'],
    ['vectordb', 'VECTOR SPACE'],
    ['replay', 'REPLAY'],
  ])('marks only %s as the current page', (current, label) => {
    render(<HeaderBar current={current} />)
    const currentLink = screen.getByRole('link', { name: label })
    expect(currentLink).toHaveAttribute('aria-current', 'page')
    screen.getAllByRole('link').filter((link) => link !== currentLink).forEach((link) => {
      expect(link).not.toHaveAttribute('aria-current')
    })
  })
})
