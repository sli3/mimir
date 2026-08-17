import React from 'react'

/**
 * Capture button for the main spectrum view.
 *
 * Pressing the button hands off to the parent's state machine, which
 * performs the POST /api/capture request and renders the result panel
 * separately. This component is intentionally just the button — verdict
 * rendering lives in CaptureResultPanel so the two can be mounted in
 * different parts of the dashboard (the button sits next to TUNE in the
 * top control row; the result panel lives in the right sidebar).
 *
 * Passive receive display only: the parent endpoint performs a file
 * write of already-received samples and has no TX capability.
 *
 * @param {object} props
 * @param {() => void} props.onClick - click handler (no args). Parent
 *   owns all state machine logic.
 * @param {boolean} props.pending - when true, the button is disabled
 *   and the label switches to "CAPTURING…".
 */
export default function CaptureButton({ onClick, pending }) {
  return (
    <button
      type="button"
      className="manual-capture-button"
      data-testid="manual-capture-button"
      onClick={onClick}
      disabled={pending}
    >
      {pending ? 'CAPTURING…' : 'CAPTURE NOW'}
    </button>
  )
}
