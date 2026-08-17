import React from 'react'
import {
  buildCaptureVerdict,
  VERDICT_WIDE,
  VERDICT_NARROW,
  VERDICT_BURST,
  VERDICT_FALLBACK,
} from './ManualCaptureButton.jsx'

export { VERDICT_WIDE, VERDICT_NARROW, VERDICT_BURST, VERDICT_FALLBACK }

/**
 * Capture result panel.
 *
 * Header style mirrors the SIGNAL DETAILS header at App.jsx:952-1002
 * (height 28px, var(--bg-header) bg, border-bottom 1px solid var(--border),
 * padding 0 10px, fontSize 11px, letterSpacing 2px, var(--font-data), title
 * color var(--neon-cyan)) so the panel reads as part of the same
 * consolidated right-sidebar stack.
 *
 * Body handles the four states:
 *   - idle                → "NO CAPTURE YET"
 *   - pending             → "CAPTURING…"
 *   - ok                  → verdict headline + supporting numbers + saved
 *                            file path. ARIA role="status" aria-live="polite"
 *                            so the result is announced at the next polite
 *                            opportunity.
 *   - failure (error | timeout | scanner_unavailable | transport_error |
 *     unexpected) → the failure message. ARIA role="alert" so the failure
 *     is announced immediately.
 *
 * The component owns no state — it receives `state` from the parent and
 * renders deterministically. The state machine itself lives in App so the
 * button and panel can be mounted in different sections.
 *
 * @param {object} props
 * @param {object} props.state - the parent-owned state object:
 *   { status: 'idle' }
 *   { status: 'pending' }
 *   { status: 'ok', file, fingerprint, is_burst }
 *   { status: 'error' | 'timeout' | 'scanner_unavailable' |
 *     'transport_error' | 'unexpected', message }
 */
export default function CaptureResultPanel({ state }) {
  const status = state?.status ?? 'idle'
  const okState = status === 'ok'
  const pendingState = status === 'pending'
  const failureState = status === 'error'
    || status === 'timeout'
    || status === 'scanner_unavailable'
    || status === 'transport_error'
    || status === 'unexpected'

  const captureResult = okState
    ? {
        fingerprint: state.fingerprint ?? null,
        is_burst: state.is_burst ?? false,
      }
    : null
  const verdict = okState ? buildCaptureVerdict(captureResult) : null
  const fp = okState && state.fingerprint ? state.fingerprint : null

  return (
    <div style={{
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      borderBottom: '1px solid var(--border)',
    }}>
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
          color: 'var(--neon-cyan)',
          letterSpacing: '2px',
          fontFamily: 'var(--font-data)',
        }}>
          CAPTURE RESULT
        </span>
      </div>
      <div style={{
        padding: '8px 10px',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {status === 'idle' && (
          <div
            style={{
              fontSize: '11px',
              color: 'var(--text-dim)',
              fontFamily: 'var(--font-data)',
              letterSpacing: '1px',
            }}
          >
            NO CAPTURE YET
          </div>
        )}
        {pendingState && (
          <div
            style={{
              fontSize: '11px',
              color: 'var(--neon-amber)',
              fontFamily: 'var(--font-data)',
              letterSpacing: '1px',
            }}
          >
            CAPTURING…
          </div>
        )}
        {okState && (
          <div
            className="manual-capture-result"
            data-testid="manual-capture-result"
            role="status"
            aria-live="polite"
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              fontFamily: 'var(--font-data)',
            }}
          >
            <div className={`manual-capture-verdict manual-capture-verdict-${verdict.category}`}>
              {verdict.verdict}
            </div>
            <div className="manual-capture-numbers">
              {typeof fp?.occupied_bins === 'number' && (
                <span style={{ fontSize: '11px', color: 'var(--text-primary)' }}>
                  occupied bins: {fp.occupied_bins}
                </span>
              )}
              {typeof fp?.snr_db === 'number' && (
                <span style={{ fontSize: '11px', color: 'var(--text-primary)' }}>
                  {' '}SNR: {fp.snr_db.toFixed(1)} dB
                </span>
              )}
              {typeof fp?.peak_freq_hz === 'number' && (
                <span style={{ fontSize: '11px', color: 'var(--text-primary)' }}>
                  {' '}peak: {(fp.peak_freq_hz / 1e6).toFixed(3)} MHz
                </span>
              )}
            </div>
            {state.file && (
              <div
                className="manual-capture-file"
                style={{
                  fontSize: '10px',
                  color: 'var(--text-dim)',
                  fontFamily: 'var(--font-data)',
                  wordBreak: 'break-all',
                }}
              >
                {state.file}
              </div>
            )}
          </div>
        )}
        {failureState && (
          <div
            className="manual-capture-result manual-capture-result-error"
            data-testid="manual-capture-result"
            role="alert"
            style={{
              fontSize: '11px',
              color: 'var(--neon-red)',
              fontFamily: 'var(--font-data)',
            }}
          >
            {state.message}
          </div>
        )}
      </div>
    </div>
  )
}
