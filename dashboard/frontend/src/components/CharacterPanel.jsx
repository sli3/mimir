import React from 'react'

export default function CharacterPanel() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
    }}>
      <div style={{
        width: 80,
        height: 120,
        border: '2px solid var(--border-active)',
        boxShadow: '0 0 8px var(--neon-cyan), inset 0 0 8px rgba(0,255,255,0.05)',
      }} />
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: 6,
        color: 'var(--text-dim)',
        marginTop: 4,
      }}>
        OPERATOR
      </div>
    </div>
  )
}
