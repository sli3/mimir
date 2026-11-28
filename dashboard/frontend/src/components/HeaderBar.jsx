import useClock from '../hooks/useClock.js'

const PAGE_LINKS = [
  { current: 'dashboard', label: 'DASHBOARD', href: '/' },
  { current: 'radar', label: 'RADAR', href: '/radar' },
  { current: 'vectordb', label: 'VECTOR SPACE', href: '/vectordb' },
  { current: 'replay', label: 'REPLAY', href: '/replay' },
]

const LINK_STYLE = {
  fontSize: '11px',
  color: 'var(--neon-cyan)',
  letterSpacing: '2px',
  fontFamily: 'var(--font-data)',
  textDecoration: 'none',
  border: '1px solid var(--border)',
  padding: '2px 8px',
}

const CURRENT_LINK_STYLE = {
  ...LINK_STYLE,
  border: '1px solid var(--neon-cyan)',
  background: 'rgba(0, 255, 255, 0.08)',
  color: 'var(--text-bright)',
}

/** Render shared page navigation, highlighting current, with a live clock. */
export default function HeaderBar({ current }) {
  const clock = useClock()

  return (
    <nav aria-label="Main navigation" style={{
      display: 'flex',
      flexDirection: 'row',
      alignItems: 'center',
      height: '36px',
      flexShrink: 0,
      background: 'var(--bg-header)',
      borderBottom: '1px solid rgba(0,255,255,0.2)',
      padding: '0 12px',
      gap: '16px',
    }}>
      <span style={{
        fontFamily: "'Press Start 2P', monospace",
        fontSize: '14px',
        color: 'var(--neon-cyan)',
        letterSpacing: '3px',
        fontWeight: 'bold',
      }}>
        MIMIR
      </span>
      <span style={{
        fontSize: '11px',
        color: 'var(--text-dim)',
        letterSpacing: '2px',
      }}>
        PASSIVE RF INTELLIGENCE // ADELAIDE SA
      </span>
      <div style={{
        marginLeft: 'auto',
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        gap: '16px',
      }}>
        {PAGE_LINKS.map((link) => (
          <a
            key={link.current}
            href={link.href}
            aria-current={current === link.current ? 'page' : undefined}
            style={current === link.current ? CURRENT_LINK_STYLE : LINK_STYLE}
          >
            {link.label}
          </a>
        ))}
        <span style={{
          fontSize: '11px',
          color: 'var(--text-dim)',
          fontFamily: 'var(--font-data)',
        }}>
          {clock}
        </span>
      </div>
    </nav>
  )
}
