// Operator state configuration and helper, moved out of App.jsx unchanged.

/** Colour and label configuration for the OPERATOR status badge.
 *  Each state maps to a display colour and a tooltip label shown in the
 *  body of the SIGNAL DETAILS panel. The `color` is used for the
 *  badge text; `opColor` outlines the OP icon.
 *  @type {{ MONITORING: {...}, NORMAL: {...}, VERIFY: {...}, ANOMALY: {...} }} */
export const OPERATOR_STATE_CONFIG = {
  MONITORING: {
    label: 'OPERATOR — MONITORING',
    color: 'var(--text-dim)',
    opColor: 'var(--neon-cyan)',
  },
  NORMAL: {
    label: 'OPERATOR — NORMAL',
    color: '#00D9FF',
    opColor: '#00D9FF',
  },
  VERIFY: {
    label: 'OPERATOR — VERIFY',
    color: '#FFB020',
    opColor: '#FFB020',
  },
  ANOMALY: {
    label: 'OPERATOR — ANOMALY',
    color: '#FF2840',
    opColor: '#FF2840',
  },
}

/** Derive the OPERATOR status from the current AI reasoning slot.
 *  The state machine is evaluated in order: no signal (MONITORING), then
 *  novel/unseen (ANOMALY), then explicitly legal (NORMAL), otherwise
 *  VERIFY. Used by the OPERATOR badge in the SIGNAL DETAILS panel and
 *  the ANOMALY warning indicator.
 *  @param {object|null} aiReasoning - current AI reasoning slot from useSocket
 *  @returns {'MONITORING'|'NORMAL'|'VERIFY'|'ANOMALY'} */
export function getOperatorState(aiReasoning) {
  if (aiReasoning?.freq_hz === null) return 'MONITORING'
  if (aiReasoning?.novel === true) return 'ANOMALY'
  if (aiReasoning?.novel === false && aiReasoning?.au_legal_status === 'legal_rx') return 'NORMAL'
  return 'VERIFY'
}
