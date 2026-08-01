import React from 'react'

/**
 * FRAME INSPECTOR column panel (UI-OVERHAUL Change 6b).
 *
 * Extracted from AdsbAircraftPanel so the parsed Mode S frame view lives in
 * its own independently scrolling dashboard column. Rendering logic is
 * preserved verbatim from the original AdsbAircraftPanel FRAME INSPECTOR
 * block; the pinnedFrame / frameData state is now lifted to App.jsx and
 * passed in as props so RawDecodePanel can share it.
 *
 * The adsbRawLog prop is required (beyond the original spec's prop list)
 * because the preserved placeholder logic distinguishes "no frames yet"
 * (Awaiting frames...) from "frames present but parse pending" (Decoding...).
 *
 * Passive receive display only — no TX capability.
 *
 * @param {Object|null} pinnedFrame - Currently pinned frame entry, or null
 * @param {Object|null} frameData - Parsed frame data from /api/adsb/parse, or null
 * @param {Array} adsbRawLog - Recent raw Mode S frames {icao, raw_hex}
 */
export default function FrameInspectorPanel({
  pinnedFrame,
  frameData,
  adsbRawLog = [],
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header bar — FRAME INSPECTOR label + PINNED badge */}
      <div style={{
        height: '28px',
        flexShrink: 0,
        background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        padding: '0 10px',
        gap: '8px',
      }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 12,
                      color: 'var(--neon-cyan)', letterSpacing: '1px' }}>
          FRAME INSPECTOR
        </div>
        {pinnedFrame && (
          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: 10,
            color: 'var(--neon-amber)',
            border: '1px solid var(--neon-amber)',
            padding: '1px 5px',
          }}>
            (PINNED)
          </div>
        )}
      </div>
      {/* Scrollable decoded field list */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '8px' }}>
        {adsbRawLog.length === 0 ? (
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                        color: 'var(--text-dim)' }}>
            Awaiting frames...
          </div>
        ) : frameData === null ? (
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                        color: 'var(--text-dim)' }}>
            Decoding...
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
            <div style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                             color: 'var(--text-dim)', letterSpacing: '1px',
                             flexShrink: 0 }}>
                DOWNLINK FORMAT
              </span>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 13,
                             color: 'var(--text)', textAlign: 'right',
                             marginLeft: 'auto' }}>
                {frameData.df !== null && frameData.df !== undefined ? String(frameData.df) : '—'}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                             color: 'var(--text-dim)', letterSpacing: '1px',
                             flexShrink: 0 }}>
                ICAO ADDRESS
              </span>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 13,
                             color: 'var(--neon-cyan)', textAlign: 'right',
                             marginLeft: 'auto' }}>
                {frameData.icao ?? '—'}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                             color: 'var(--text-dim)', letterSpacing: '1px',
                             flexShrink: 0 }}>
                TYPECODE
              </span>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 13,
                             color: 'var(--text)', textAlign: 'right',
                             marginLeft: 'auto' }}>
                {frameData.typecode !== null && frameData.typecode !== undefined ? String(frameData.typecode) : '—'}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                             color: 'var(--text-dim)', letterSpacing: '1px',
                             flexShrink: 0 }}>
                MESSAGE TYPE
              </span>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 13,
                             color: 'var(--text)', textAlign: 'right',
                             marginLeft: 'auto' }}>
                {frameData.message_type ?? '—'}
              </span>
            </div>
            {frameData.fields && Object.entries(frameData.fields).map(([k, v]) => (
              <div key={k} style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
                <span style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                               color: 'var(--text-dim)', letterSpacing: '1px',
                               flexShrink: 0 }}>
                  {k.toUpperCase()}
                </span>
                <span style={{ fontFamily: 'var(--font-data)', fontSize: 13,
                               color: 'var(--text)', textAlign: 'right',
                               marginLeft: 'auto' }}>
                  {v}
                </span>
              </div>
            ))}
            <div style={{ display: 'flex', flexDirection: 'row', borderBottom: '1px solid #0F2030', padding: '4px 0' }}>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 12,
                             color: 'var(--text-dim)', letterSpacing: '1px',
                             flexShrink: 0 }}>
                CRC
              </span>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 13,
                             textAlign: 'right',
                             marginLeft: 'auto',
                             color: frameData.crc_ok === true ? 'var(--neon-green)' : frameData.crc_ok === false ? 'var(--neon-red)' : 'var(--text-dim)' }}>
                {frameData.crc_ok === true ? 'OK ✓' : frameData.crc_ok === false ? 'FAIL ✗' : '—'}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
