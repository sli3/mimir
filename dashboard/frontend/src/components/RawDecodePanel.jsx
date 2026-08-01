import React from 'react'

/**
 * Convert a hex string to space-separated 8-bit binary groups.
 * Example: "A3D4" -> "10100011 11010100"
 * Used in the RAW DECODE view's binary mode to show the Mode S
 * frame bits at a glance.
 * @param {string} hex - Hex string (e.g. "A3D4F0")
 * @returns {string} Space-separated 8-bit binary groups
 */
function hexToBin(hex) {
  return hex.match(/.{1,2}/g)
    .map((byte) => parseInt(byte, 16).toString(2).padStart(8, '0'))
    .join(' ')
}

/**
 * Format a hex string as uppercase space-separated byte pairs.
 * Example: "a3d4" -> "A3 D4"
 * Used in the RAW DECODE view's hex mode to make the Mode S frame
 * readable at a glance.
 * @param {string} hex - Hex string (e.g. "A3D4F0")
 * @returns {string} Uppercase space-separated byte pairs
 */
function hexToSpaced(hex) {
  return hex.match(/.{1,2}/g).join(' ').toUpperCase()
}

/**
 * RAW DECODE column panel (UI-OVERHAUL Change 6a).
 *
 * Extracted from AdsbAircraftPanel so the raw Mode S frame list lives in
 * its own independently scrolling dashboard column. Rendering logic is
 * preserved verbatim from the original AdsbAircraftPanel RAW DECODE block;
 * the rawView / pinnedFrame state is now lifted to App.jsx and passed in
 * as props so FrameInspectorPanel can share it.
 *
 * Passive receive display only — no TX capability.
 *
 * @param {Array} adsbRawLog - Recent raw Mode S frames {icao, raw_hex}
 * @param {string} rawView - Current view mode ('hex' or 'bin')
 * @param {Function} setRawView - Function to set raw view mode
 * @param {Object|null} pinnedFrame - Currently pinned frame entry, or null
 * @param {Function} setPinnedFrame - Function to set/clear the pinned frame
 */
export default function RawDecodePanel({
  adsbRawLog = [],
  rawView,
  setRawView,
  pinnedFrame,
  setPinnedFrame,
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header bar — RAW DECODE label + HEX/BIN toggle */}
      <div style={{
        height: '28px',
        flexShrink: 0,
        background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        padding: '0 10px',
        justifyContent: 'space-between',
      }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 12,
                      color: 'var(--neon-cyan)', letterSpacing: '1px' }}>
          RAW DECODE
        </div>
        <div style={{ display: 'flex', flexDirection: 'row', gap: '0px' }}>
          {['hex', 'bin'].map((mode) => (
            <button
              key={mode}
              onClick={() => setRawView(mode)}
              style={{
                fontFamily: 'var(--font-data)',
                fontSize: 12,
                padding: '1px 6px',
                background: rawView === mode ? 'rgba(0,255,255,0.1)' : 'transparent',
                border: '1px solid var(--border)',
                borderColor: rawView === mode ? 'var(--neon-cyan)' : 'var(--border)',
                color: rawView === mode ? 'var(--neon-cyan)' : 'var(--text-dim)',
                cursor: 'pointer',
                letterSpacing: '1px',
                textTransform: 'uppercase',
              }}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>
      {/* Scrollable frame list */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '8px' }}>
        {adsbRawLog.length === 0 ? (
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                        color: 'var(--text-dim)' }}>
            Awaiting frames...
          </div>
        ) : (
          <div style={{ overflow: 'auto' }}>
            {adsbRawLog.map((entry, idx) => {
              const isPinned = pinnedFrame && entry.icao === pinnedFrame.icao && entry.raw_hex === pinnedFrame.raw_hex
              const isNewest = !pinnedFrame && idx === 0
              return (
                <div
                  key={idx}
                  onClick={() => {
                    if (isPinned) {
                      setPinnedFrame(null)
                    } else {
                      setPinnedFrame(entry)
                    }
                  }}
                  style={{
                    display: 'flex',
                    flexDirection: 'row',
                    gap: '8px',
                    marginBottom: '2px',
                    alignItems: 'flex-start',
                    cursor: 'pointer',
                    background: isPinned ? 'rgba(0,255,255,0.07)' : isNewest ? 'rgba(0,255,255,0.03)' : 'transparent',
                    borderLeft: isPinned ? '2px solid var(--neon-cyan)' : 'none',
                    paddingLeft: isPinned ? '6px' : '8px',
                  }}
                >
                  <span style={{ fontFamily: 'monospace', fontSize: 13,
                                 color: 'var(--neon-cyan)', whiteSpace: 'nowrap',
                                 flexShrink: 0 }}>
                    {entry.icao}
                  </span>
                  <span style={{ fontFamily: 'monospace', fontSize: 12,
                                 color: 'var(--text-dim)', wordBreak: 'break-all',
                                 lineHeight: '1.4' }}>
                    {rawView === 'hex'
                      ? hexToSpaced(entry.raw_hex)
                      : hexToBin(entry.raw_hex)}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
