import React from 'react'

export default function AIReasoningPanel() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      fontFamily: 'var(--font-display)',
      fontSize: 10,
      color: 'var(--text-dim)',
      textAlign: 'center',
      padding: 8,
    }}>
      <div>SELECT A FREQUENCY</div>
      <div>TO ANALYSE</div>
    </div>
  )
}
