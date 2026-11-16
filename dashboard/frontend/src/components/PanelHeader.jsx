/**
 * Render a panel column title with its display colour.
 */
export default function PanelHeader({ title, colour }) {
  return (
    <div style={{
      height: '28px',
      flexShrink: 0,
      background: 'var(--bg-header)',
      borderBottom: '1px solid var(--border)',
      padding: '0 10px',
      display: 'flex',
      alignItems: 'center',
    }}>
      <span style={{
        fontSize: '11px',
        color: colour,
        letterSpacing: '2px',
        fontFamily: 'var(--font-data)',
      }}>
        {title}
      </span>
    </div>
  )
}
