/**
 * Render the header with links to the radar and vector space pages.
 * Props: clock.
 */
export default function HeaderBar({ clock }) {
  return (
    <div style={{
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
        {/* Links to the standalone radar scope and vector space pages. */}
        <a
          href="/radar"
          style={{
            fontSize: '11px',
            color: 'var(--neon-cyan)',
            letterSpacing: '2px',
            fontFamily: 'var(--font-data)',
            textDecoration: 'none',
            border: '1px solid var(--border)',
            padding: '2px 8px',
          }}
        >
          RADAR
        </a>
        <a
          href="/vectordb"
          style={{
            fontSize: '11px',
            color: 'var(--neon-cyan)',
            letterSpacing: '2px',
            fontFamily: 'var(--font-data)',
            textDecoration: 'none',
            border: '1px solid var(--border)',
            padding: '2px 8px',
          }}
        >
          VECTOR SPACE
        </a>
        <span style={{
          fontSize: '11px',
          color: 'var(--text-dim)',
          fontFamily: 'var(--font-data)',
        }}>
          {clock}
        </span>
      </div>
    </div>
  )
}
