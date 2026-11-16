// Tuned-band helpers, moved out of App.jsx unchanged.

/** Check whether the current focus frequency is tuned to a specific band.
 *  Returns true when freq is within margin of target. Default margin is
 *  2 MHz (suitable for most bands). AIS uses a tighter 100 kHz margin
 *  because the dual-channel centre (162.000 MHz) sits between CH1
 *  (161.975 MHz) and CH2 (162.025 MHz) -- 100 kHz covers both channels
 *  while excluding nearby marine VHF allocations.
 *  @param {number|null} freq - current focus frequency in Hz
 *  @param {number} target - band centre frequency in Hz
 *  @param {number} margin - tolerance in Hz (default 2 MHz)
 *  @returns {boolean} */
export function isTuned(freq, target, margin = 2_000_000) {
  return freq != null && Math.abs(freq - target) <= margin
}

/** ACARS has two AU frequencies: 129.125 MHz and 130.025 MHz.
 *  Both use 5 kHz tolerance matching the FFSK deviation. Either match
 *  counts as "tuned" for the ACARS sub-panel display.
 *  @param {number|null} freq - current focus frequency in Hz
 *  @returns {boolean} */
export function isAcarsTuned(freq) {
  return isTuned(freq, 129125000, 5000) || isTuned(freq, 130025000, 5000)
}

/** AIS dual-channel centre is 162.000 MHz. 100 kHz tolerance covers both
 *  CH1 (161.975 MHz) and CH2 (162.025 MHz).
 *  @param {number|null} freq - current focus frequency in Hz
 *  @returns {boolean} */
export function isAisTuned(freq) {
  return isTuned(freq, 162000000, 100000)
}

/** ADS-B at 1090 MHz uses the default 2 MHz margin. Unlike ACARS/AIS, ADS-B
 *  intentionally keeps the wide default so the sub-panel stays visible across
 *  the broader tuning neighbourhood. No explicit margin argument is passed,
 *  preserving the existing isTuned() default behaviour (2_000_000 Hz).
 *  @param {number|null} freq - current focus frequency in Hz
 *  @returns {boolean} */
export function isAdsbTuned(freq) {
  return isTuned(freq, 1090000000)
}
