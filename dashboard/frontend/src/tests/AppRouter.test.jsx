import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'

const vectorPage = vi.hoisted(() => ({ loaded: false }))

vi.mock('../App.jsx', () => ({
  default: () => <div>APP STUB</div>,
}))
vi.mock('../pages/RadarPage.jsx', () => ({
  default: () => <div>RADAR STUB</div>,
}))
vi.mock('../pages/ReplayPage.jsx', () => ({
  default: () => <div>REPLAY STUB</div>,
}))
vi.mock('../pages/VectorSpacePage.jsx', () => {
  vectorPage.loaded = true
  return { default: () => <div>VECTOR SPACE STUB</div> }
})

describe('AppRouter', () => {
  beforeEach(() => {
    // Give each test a fresh lazy component and module-load flag.
    vi.resetModules()
    vectorPage.loaded = false
  })

  it('renders the dashboard without loading the vector page', async () => {
    const { default: AppRouter } = await import('../AppRouter.jsx')
    render(<AppRouter route="/" />)
    expect(screen.getByText('APP STUB')).toBeInTheDocument()
    expect(vectorPage.loaded).toBe(false)
  })

  it('renders radar without loading the vector page', async () => {
    const { default: AppRouter } = await import('../AppRouter.jsx')
    render(<AppRouter route="/radar" />)
    expect(screen.getByText('RADAR STUB')).toBeInTheDocument()
    expect(vectorPage.loaded).toBe(false)
  })

  it('renders replay without loading the vector page', async () => {
    const { default: AppRouter } = await import('../AppRouter.jsx')
    render(<AppRouter route="/replay" />)
    expect(screen.getByText('REPLAY STUB')).toBeInTheDocument()
    expect(vectorPage.loaded).toBe(false)
  })

  it('shows the fallback before loading the vector page', async () => {
    const { default: AppRouter } = await import('../AppRouter.jsx')
    render(<AppRouter route="/vectordb" />)
    expect(screen.getByText('LOADING VECTOR SPACE…')).toBeInTheDocument()
    expect(await screen.findByText('VECTOR SPACE STUB')).toBeInTheDocument()
    expect(vectorPage.loaded).toBe(true)
  })
})
