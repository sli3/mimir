/**
 * Render a labelled system statistic with its display colour.
 */
export default function StatCell({ label, value, colour }) {
  return (
    <div style={{
      border: '1px solid var(--border)',
      background: 'rgba(0,255,255,0.03)',
      borderRadius: '2px',
      padding: '2px 6px',
      display: 'flex',
      flexDirection: 'column',
      gap: '1px',
    }}>
      <span style={{
        fontFamily: 'var(--font-display)',
        fontSize: '9px',
        color: 'var(--text-dim)',
        letterSpacing: '1px',
        textTransform: 'uppercase',
      }}>
        {label}
      </span>
      <span style={{
        fontFamily: 'var(--font-data)',
        fontSize: '11px',
        color: colour,
      }}>
        {value}
      </span>
    </div>
  )
}
