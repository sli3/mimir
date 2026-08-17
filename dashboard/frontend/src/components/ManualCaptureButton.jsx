/**
 * Verdict copy and the buildCaptureVerdict helper for the manual capture
 * button + result panel pair (CaptureButton.jsx, CaptureResultPanel.jsx).
 *
 * The component pair has been split: CaptureButton is just the button,
 * and CaptureResultPanel renders all result states. This file now
 * exports only the verdict constants and the helper; the default
 * component export is gone.
 *
 * The verdict helper keys on `occupied_bins` from the fingerprint, with
 * `is_burst` as a sibling-key override. The fingerprint itself is the
 * same seven _FINGERPRINT_METADATA_KEYS measurement fields the backend
 * already persisted; `is_burst` is a top-level sibling on the /api/capture
 * response (deliberately NOT in _FINGERPRINT_METADATA_KEYS because it
 * describes the detection pipeline, not the captured spectrum).
 */

// Verdict copy. Terse, no trailing full stop, matching the existing
// cyberpunk UI copy style.
export const VERDICT_WIDE = 'Real signal — wide occupied bandwidth'
export const VERDICT_NARROW = 'Weak / narrow — likely not a real broadcast'
export const VERDICT_BURST = 'Burst detected'
export const VERDICT_FALLBACK = 'Captured — inspect fingerprint'

/**
 * Build a plain-language verdict from the capture result.
 *
 * Provisional, uncalibrated thresholds. The 2026-08-17 finding
 * established that `snr_db` alone is not a reliable signal-presence
 * detector on Pluto (a persistent narrow artefact keeps SNR elevated
 * regardless of air traffic), so this verdict keys on `occupied_bins`
 * instead. The 20-bin boundary is chosen because ADS-B squitters, FM
 * broadcasts, and LoRa signals occupy hundreds of bins, while a
 * DC-offset / LO-leakage artefact occupies ~5 bins. A 10-19 bin reading
 * is the ambiguous middle — currently labelled as the fallback.
 *
 * `is_burst` overrides the two occupied_bins rules: a genuine burst is
 * meaningful regardless of how narrow it is.
 *
 * @param {object|null} captureResult - The /api/capture ok payload's
 *   relevant fields, shaped as `{ fingerprint, is_burst }`. `fingerprint`
 *   carries the seven _FINGERPRINT_METADATA_KEYS measurement fields;
 *   `is_burst` is the top-level sibling key from the response.
 * @returns {{category: string, verdict: string}} category is one of
 *   "wide" | "narrow" | "burst" | "fallback", used for the CSS colour
 *   class; verdict is the operator-facing headline.
 */
export function buildCaptureVerdict(captureResult) {
  const fp = captureResult?.fingerprint && typeof captureResult.fingerprint === 'object'
    ? captureResult.fingerprint
    : {}
  if (captureResult?.is_burst) {
    return { category: 'burst', verdict: VERDICT_BURST }
  }
  const occupied = fp.occupied_bins
  if (typeof occupied === 'number' && Number.isFinite(occupied)) {
    if (occupied >= 20) {
      return { category: 'wide', verdict: VERDICT_WIDE }
    }
    if (occupied <= 9) {
      return { category: 'narrow', verdict: VERDICT_NARROW }
    }
  }
  return { category: 'fallback', verdict: VERDICT_FALLBACK }
}
