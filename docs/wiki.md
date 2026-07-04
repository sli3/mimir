---
description: "Mimir project wiki — pipeline reference, phase log, acronym glossary, and frontend stack. Updated by @doc-writer at the end of each build."
status: live
last_updated_phase: "BUG-03"
---

# Mimir Wiki

Knowledge base for the Mimir project. Written in plain English for an RF beginner.
Updated automatically by `@doc-writer` at the end of each build cycle.

---

## Contents

1. [What Mimir Is](#what-mimir-is)
2. [Signal Pipeline — The Full Flow](#signal-pipeline)
3. [Phase Log](#phase-log)
4. [Frontend Stack](#frontend-stack)
5. [Hardware Concepts](#hardware-concepts)
6. [Acronym Glossary](#acronym-glossary)

---

## What Mimir Is

Mimir is a passive RF spectrum scanner. It uses a HackRF software-defined radio to
listen to the air, processes what it hears through a Python pipeline, classifies
signals using a local LLM running on a machine called yubaba, and displays everything
live in a browser-based waterfall dashboard.

It is passive receive-only. It never transmits. All frequencies are Australian
ACMA-compliant under the Radiocommunications Act 1992.

---

## Signal Pipeline

Every scan flows through these steps in order. Each function does one job and passes
its output to the next.

**Exception: Decoder-driven paths.** ACARS, AIS, and ADS-B decoders run as subscribers
on the shared IQ bus. When a decoder successfully decodes a frame, it emits an
`adsb_aircraft` / `acars_message` / `ais_message` event directly. ADS-B additionally
emits a `scan_result` event (confidence = 1.0) that bypasses steps 3-6 entirely — a
CRC-validated decode is ground truth, no LLM classification needed.

```
Step  Function / Component          What it does
────  ────────────────────────────  ──────────────────────────────────────────────
  1   HackRF hardware               Physical USB device. Converts radio waves to
                                    digital samples.

  2   capture_iq()                  Tunes to a frequency, collects the requested
      core/pipeline/capture.py      number of IQ samples, returns a NumPy array.

  3   compute_psd()                 Runs an FFT on the IQ samples. Returns a PSD —
      core/pipeline/fft.py          a list of power values (dB) per frequency bin.

  4   fingerprint_spectrum()        Measures the PSD: bandwidth, occupied bins,
      core/pipeline/features.py     peak power. Returns a fingerprint dict.

  5   detect_signals()              Decides whether something real is present or
      core/detection/detector.py    just noise.

  6   classify_signal()             Sends the fingerprint to the LLM on yubaba.
      core/classification/          Returns: signal type + confidence score.
      classifier.py

  7   Dashboard / Waterfall         FastAPI server streams PSD data over WebSocket.
      dashboard/                    Browser draws one row of pixels per frame.
```

---

## Phase Log

Phases are listed newest-first so the current phase is always at the top.

---

### Phase 22 Hotfix — LLM Offline Emit Rate-Limit ▶ ACTIVE

**What:** Added offline resilience to the LLM classifier. The classifier now:

1. **Health check at startup** — `scan.py` calls `classifier.check_connection()` before
   starting the scan loop. This probes the LLM server at `/models` and sets a cooldown
   if unreachable.

2. **Cooldown protection** — After a connection failure, the classifier enters a
   configurable cooldown period (default 60 seconds). During cooldown, `classify()`
   fast-fails and returns an offline result without making network calls.

3. **Graceful offline results** — When offline, the classifier returns a
   `ClassificationResult` with `signal_type="llm_offline"`, confidence "low", and
   a human-readable reasoning message explaining the offline status and suggesting
   checks.

4. **Configurable timeouts** — Added `llm_cooldown_sec` and `llm_connect_timeout_sec`
   configuration fields in `config/mimir.yaml` and `MimirConfig` dataclass.

**Changes:**

1. **`config/mimir.yaml`** — Added `llm_cooldown_sec: 60` and `llm_connect_timeout_sec: 5`
    under the `scanner:` section.

2. **`core/config/loader.py`** — Updated `MimirConfig` dataclass with
    `llm_cooldown_sec: float = 60.0` and `llm_connect_timeout_sec: float = 5.0`.
    Updated `load_config()` to parse these fields with defaults.

3. **`llm/classifier.py`** — Added `import time`. Added `_OFFLINE_SIGNAL_TYPE = "llm_offline"`
    class constant. Updated `SignalClassifier.__init__()` with `cooldown_sec` and
    `connect_timeout_sec` parameters. Added `check_connection()` public method
    (probes `/models`, never raises, returns bool). Added `_offline_result()` private
    method returning offline `ClassificationResult`. Modified `classify()` to fast-fail
    during cooldown and set cooldown on `ConnectionError`. Updated
    `ClassificationResult.signal_type` docstring to distinguish "unavailable" from
    "llm_offline".

4. **`scan.py`** — Passes `cooldown_sec` and `connect_timeout_sec` to `SignalClassifier`.
    Calls `classifier.check_connection()` at startup before creating `ScanRunner`.
    Does not exit/raise on failure.

5. **`dashboard/frontend/src/components/AIReasoningPanel.jsx`** — Added `llm_offline`
    display case: amber colour, "LLM OFFLINE" label, renders backend reasoning.

6. **`dashboard/frontend/src/components/SignalHistoryLog.jsx`** — Added amber colour for
    `llm_offline` signal_type in history rows.

7. **`tests/llm/test_classifier_offline.py`** — New file with 9 pytest tests covering
    `check_connection()` and classify() offline/cooldown behaviour.

8. **`tests/llm/test_phase4_classifier.py`** — Renamed `test_llm_unavailable_returns_fallback`
    to `test_llm_connection_error_returns_offline` and updated assertion.

9. **`dashboard/frontend/src/tests/AIReasoningPanel.test.jsx`** — Added 1 Vitest test for
    `llm_offline` display state.

**Why:** The LLM server on yubaba can be temporarily unavailable (network issues,
maintenance, or startup delays). Previously, connection failures would cause the
entire scanner to fail. Now the classifier gracefully handles offline periods,
allowing the pipeline to continue operating with informative offline results.

**Key functions:**

`SignalClassifier.check_connection()` — Probes the LLM server at `/models` and sets
an offline cooldown if unreachable. Never raises. Returns True if reachable, False
otherwise. Used by `scan.py` at startup to pre-warm connection state.

`SignalClassifier._offline_result()` — Returns a `ClassificationResult` indicating
LLM server is offline. Used when server is unreachable or classifier is in cooldown.
Provides graceful fallback that allows pipeline to continue without crashing.

**Functions:**

- `check_connection()` — Public method that probes the LLM server at startup and sets cooldown if unreachable. Never raises. Returns True if the server is reachable, False otherwise. An HTTP error (e.g. 404 from /models) is treated as reachable because not every build exposes that endpoint. This is called by scan.py at startup to pre-warm the connection state. If the server is unreachable, the classifier enters a cooldown period and will return offline results for any classification requests until the cooldown expires.

- `_offline_result()` — Private method that returns a ClassificationResult indicating the LLM server is offline. Used when the LLM server is unreachable (ConnectionError) or when the classifier is in cooldown after a recent connection failure. This provides a graceful fallback that allows the pipeline to continue operating without crashing. The result includes a human-readable reasoning message that explains the offline status and suggests checks.

**Deferred items:**

1. **`scanner.py` `_llm_call_count` inflation during offline/cooldown** — Pre-existing
    metric issue. The AI loop increments `_llm_call_count` even when `classify()`
    fast-fails during cooldown, which can inflate the count. Consider fixing in a
    future phase.

2. **Timeout in `classify()` does not trigger cooldown** — Per the explicit Phase 22
    spec, only `ConnectionError` in `classify()` sets cooldown; `Timeout` still returns
    `unavailable`. `check_connection()` does treat Timeout as offline. This asymmetry
    could be addressed in a future robustness pass.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are passive receive-only classifier resilience
  improvements. No RF interaction.

**Test counts:** 548 passing (399 pytest + 149 Vitest). New: 9 pytest tests for
classifier offline handling, 1 updated pytest test, 1 new Vitest test.

---

### BUG-03 — Tooling: Gains/Thresholds Sourced from BAND_PROFILES ✓ DONE

**What:** Updated four diagnostic tools to source gain and threshold values from
`dashboard.shared_state.BAND_PROFILES` instead of hardcoded values, ensuring
consistency across the toolchain. This is a maintenance bugfix that aligns the
tools with the live dashboard configuration.

**Changes:**

1. **`tools/capture_to_vectorstore.py`** — Added `BAND_PROFILES` import. `CAPTURE_TARGETS`
     now reads `lna_gain_db`, `vga_gain_db`, `signal_threshold_db` from
     `dashboard.shared_state.BAND_PROFILES`.

2. **`tools/calibrate_thresholds.py`** — `CALIBRATION_TARGETS` gains now read from
     `BAND_PROFILES` (thresholds already live).

3. **`tools/diagnose_fingerprints.py`** — `TARGETS` gains now read from
     `BAND_PROFILES` except `noise_floor`, which remains intentionally hardcoded
     (16,20) with a clarified comment.

4. **`tools/diagnose_threshold.py`** — Added `BAND_PROFILES` import. `BAND_SWEEP` gains
     now read from `BAND_PROFILES`. Added note about missing AIS entry (pre-existing).

5. **`tests/tools/test_capture_to_vectorstore.py`** — Updated `test_build_metadata`;
     added `test_capture_targets_match_band_profiles`.

6. **`tests/tools/test_diagnose_threshold.py`** — Added `test_band_sweep_gains_match_band_profiles`.

7. **`tests/tools/test_calibrate_thresholds.py`** (new) — Guard test for `CALIBRATION_TARGETS`.

8. **`tests/tools/test_diagnose_fingerprints.py`** (new) — Guard tests for `TARGETS`,
     including intentional `noise_floor` divergence.

**Why:** Hardcoded gain and threshold values in diagnostic tools could drift from
the live dashboard configuration, leading to inconsistent behavior. Sourcing from
`BAND_PROFILES` ensures all tools use the same per-band settings as the dashboard.

**Key functions:**

- `CAPTURE_TARGETS` in `capture_to_vectorstore.py` — Now reads gains and thresholds from
  `BAND_PROFILES`. Ensures live capture vectors match dashboard configuration.

- `CALIBRATION_TARGETS` in `calibrate_thresholds.py` — Now reads gains from `BAND_PROFILES`.
  Ensures calibration vectors match dashboard configuration.

- `TARGETS` in `diagnose_fingerprints.py` — Now reads gains from `BAND_PROFILES` except
  `noise_floor` (intentionally divergent for diagnostic visibility). Ensures diagnostic
  captures reflect live settings.

- `BAND_SWEEP` in `diagnose_threshold.py` — Now reads gains from `BAND_PROFILES`.
  Ensures threshold sweep uses live gain settings.

**Deferred items:**

1. **`diagnose_fingerprints.py` top-level loop** — Pre-existing issue: the module executes
   its capture loop at import time (no `main()` guard). This was worked around in tests
   by mocking hardware before import. Future refactor: wrap the top-level loop in
   `if __name__ == "__main__":`.

2. **`diagnose_threshold.py` missing AIS entry** — Pre-existing: `BAND_SWEEP` has no AIS
   entry, unlike the other three tools. This is out of scope for BUG-03. Future enhancement:
   add AIS to `BAND_SWEEP` if threshold-sweeping AIS is desired.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are passive receive-only tooling improvements.
  No RF interaction.

**Test counts:** 408 passed, 1 warning (was 402). No failures.

---

### Phase 20 — Live Capture → Vector Store Ingestion Tool ✓ DONE

**What:** New standalone tool `tools/capture_to_vectorstore.py` that captures live IQ
samples from the HackRF across AU-legal receive bands, computes spectral fingerprints,
converts them to embeddings, and stores them in the production ChromaDB vector store at
`data/vectorstore/`. This fills a gap in the toolchain: previously, live vectors could
only enter the store indirectly via `scan.py` running over time. The new tool lets the
operator deliberately seed the production vector store with fresh captures in a single
run, which is faster and more controlled than waiting for organic traffic.

The tool reuses the antenna-selection UX from `calibrate_thresholds.py` (Phase 19b):
the operator picks their connected antenna, and only bands within that antenna's
usable range are captured. Per-band warnings fire for ADS-B, ACARS, and AIS because
those bands require live aircraft or vessel signals to produce meaningful vectors.

A new test file `tests/tools/test_capture_to_vectorstore.py` (9 tests) covers
structure, antenna coverage, metadata correctness, 5-record capture, RuntimeError
recovery, --wipe flag, Ctrl+C skip, and signal_threshold passthrough. An existing
test file `tests/tools/test_seed_chromadb.py` was updated to fix stale ISM label
assertions (previously referenced 433 MHz, now correctly asserts ISM_915 / 915 MHz).

**Changes:**

1. **`tools/capture_to_vectorstore.py` (new file)** -- complete capture-to-vectorstore
   workflow: antenna selection, per-band IQ capture, FFT, fingerprint, embedding,
   ChromaDB storage. Supports `--wipe` flag to delete the existing collection before
   capture.

2. **`ANTENNA_PROFILES` dict** (module-level) -- three antenna profiles mapping antenna
   name to usable frequency bands: telescopic whip (5 bands), V-dipole (3 bands),
   spiral discone (2 bands). Labels match `CAPTURE_TARGETS` entries exactly.

3. **`CAPTURE_TARGETS` list** (module-level) -- seven band configurations with per-band
   frequency, sample rate, gain settings, signal threshold, and capture count. Gain
   values match `dashboard/shared_state.py` `BAND_PROFILES`.

4. **`_colour(text, code)`** -- wraps text in ANSI colour codes for terminal output.

5. **`_print_band_warning(label)`** -- prints a one-time warning for bands that need
   live signals (ADS-B, ACARS, AIS). Same pattern as `calibrate_thresholds.py`.

6. **`build_metadata(label, antenna_name, target, fingerprint, cap_idx)`** -- builds
   the ChromaDB metadata dict for a stored capture record. Includes label, source,
   antenna, frequency, gain, threshold, timestamp, peak power, SNR, and capture index.

7. **`_parse_args()`** -- parses CLI arguments. Currently supports `--wipe` only.

8. **`_select_antenna()`** -- prompts the user to select an antenna profile. Returns
   `(choice_key, profile_dict)`. Handles Ctrl+C gracefully.

9. **`run_capture_loop(store, embedder, selected_targets, antenna_name, ...)`** --
   main capture loop. For each target band, captures IQ, computes PSD, fingerprints
   the spectrum, embeds the fingerprint, and stores the vector in ChromaDB. Prints
   per-capture results with colour-coded SNR margin. Accepts `input_func` and
   `sleep_func` parameters for testability. Returns the count of records stored.

10. **`main()`** -- orchestrates the full workflow: parse args, select antenna, filter
    bands, initialise store (optionally wiping), run capture loop, print summary.

11. **`tests/tools/test_capture_to_vectorstore.py` (new file)** -- 9 pytest tests:
    structure validation, antenna coverage completeness, metadata correctness,
    5-record capture loop, RuntimeError recovery, --wipe flag, Ctrl+C skip, and
    signal_threshold passthrough.

12. **`tests/tools/test_seed_chromadb.py` (updated)** -- `TestIsmLabelIs915Variant`
    class assertions updated from stale 433 MHz to ISM_915 / 915 MHz to match
    current `CLASS_META` constants.

**Why:** The production vector store at `data/vectorstore/` accumulates vectors
organically as `scan.py` runs, but this is slow and depends on traffic presence.
A deliberate capture tool lets the operator seed the store quickly after a reseed,
hardware change, or initial setup. It is the missing piece between
`calibrate_thresholds.py` (which writes to a separate calibration store) and the
live scanner (which writes to the production store opportunistically).

**Key functions:**

`run_capture_loop(store, embedder, selected_targets, antenna_name, ...)` -- runs the
capture, fingerprint, embed, store loop for each target band. Returns the number of
records stored. The `input_func` and `sleep_func` parameters allow tests to inject
mocks without touching real hardware. Analogy: a controlled photo shoot where each
band gets its portrait taken, one at a time, rather than waiting for subjects to walk
past a security camera.

`build_metadata(label, antenna_name, target, fingerprint, cap_idx)` -- assembles the
metadata dictionary that ChromaDB stores alongside each embedding. This metadata is
what the LLM classifier and diagnostic tools use to understand where a vector came
from. Analogy: a label on a filing cabinet drawer that tells you who filed it, when,
and with what equipment.

`_select_antenna()` -- interactive prompt that maps the physical antenna to the
correct subset of frequency bands. Prevents the operator from wasting time capturing
bands the antenna cannot receive. Analogy: choosing the right lens before a
photography shoot -- a wide-angle lens for many bands, a telephoto for a narrow range.

`main()` -- top-level orchestrator. Parses CLI args, prompts for antenna, initialises
the store (wiping if requested), runs the capture loop, and prints a summary with a
reminder to re-run `calibrate_thresholds.py`. Analogy: the stage manager who calls
the shots in order -- lights, camera, action, wrap.

**Deferred items:**

1. **`tools/diagnose_fingerprints.py` ADS-B gain divergence** -- still uses legacy
   gain (32/38). Deferred from Phase 19a; out of scope for this build.

2. **ChromaDB distance reference stale (Phase 13)** -- thresholds in
   `llm/classifier.py` calibrated for 6D L2 distances. After 7D reseed,
   thresholds over-classify known signals as "novel." The capture tool prints a
   reminder to re-run `calibrate_thresholds.py` after capture. Track under
   9C-Threshold (open).

3. **`--wipe` no interactive confirmation** -- the `--wipe` flag deletes the
   collection without a Y/N prompt. Accepted per security review; the warning
   message is sufficient.

4. **Concurrent ChromaDB writes** -- if `scan.py` is running at the same time as
   this tool, both write to `data/vectorstore/` and SQLite lock errors may occur.
   Documented in README usage notes.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None -- tool performs receive-only IQ capture on ACMA-compliant
  frequencies. All bands are legal to receive passively under the Radiocommunications
  Act 1992 (Cth).

**Test counts:** 526 (384 pytest + 142 Vitest). New: 9 pytest tests for the capture
tool, 2 updated pytest tests in seed_chromadb.

---

### Phase 19b — calibrate_thresholds.py Antenna Selection + UX Improvements ✓ DONE

**What:** Interactive UX overhaul of `tools/calibrate_thresholds.py`. At startup the
operator now selects their connected antenna from a menu; only frequency bands within
that antenna's usable range are captured. Per-band warnings are shown before the first
capture of ADS-B, ACARS, and AIS because those bands require live aircraft or vessel
signals to produce meaningful vectors. The pairwise distance matrix is split into two
halves when there are more than 8 capture entries so the output fits a normal terminal
width. The SUGGESTED THRESHOLDS output now references both `_DISTANCE_SCALE_REFERENCE`
and `_build_user_prompt()` in `llm/classifier.py` so the operator knows exactly where
to apply the printed values.

**Changes:**

1. **`ANTENNA_PROFILES` dict** (module-level) -- three antenna profiles mapping antenna
   name to usable frequency bands: telescopic whip (75 MHz -- 700 MHz, 6 bands),
   V-dipole 533mm (130 MHz -- 145 MHz, 4 bands), spiral discone (800 MHz -- 8500 MHz,
   3 bands). Labels match CALIBRATION_TARGETS entries exactly.

2. **`MATRIX_SPLIT_THRESHOLD = 8`** (module-level) -- when the total number of captured
   entries exceeds this value, the pairwise distance matrix is printed in two halves
   (columns split at the midpoint) so the output does not overflow a standard 80-column
   terminal.

3. **`_print_band_warning(label: str)`** -- prints a one-time warning block before the
   first capture of ADS-B, ACARS, or AIS. Explains why live signals are needed and
   provides a link to a live traffic checker (Flightradar24 for ADS-B/ACARS,
   MarineTraffic for AIS). Operator can press ENTER to continue or Ctrl+C to skip
   the band.

4. **`_print_matrix(row_entries, col_entries, distance_pairs, ...)`** -- prints a
   pairwise distance matrix subset. All rows are printed but only the requested columns
   are shown, enabling the split-half display. Uses ANSI colour coding: green for
   strong matches, yellow for possible matches, red for different types. Same-type
   pairs are marked with an asterisk.

5. **Antenna selection prompt** (Step A) -- replaces the old ADS-B-only warning. The
   operator picks their antenna by number (1/2/3). The script filters CALIBRATION_TARGETS
   to only those bands within the selected antenna's range, prints the band list and
   any skipped bands.

6. **Per-band warnings in capture loop** -- fires `_print_band_warning` before the first
   capture of ADS-B, ACARS, or AIS. Operator can skip the band entirely via Ctrl+C.

7. **SUGGESTED THRESHOLDS output** -- now explicitly references both
   `_DISTANCE_SCALE_REFERENCE` (module-level constant, ~line 155) and
   `_build_user_prompt()` threshold block (~lines 424-431) in `llm/classifier.py`.

8. **Module and `main()` docstrings** -- updated to reflect antenna selection, per-band
   warnings, and matrix splitting.

**Why:** The previous version always captured all 8 bands regardless of antenna, wasting
time on bands the antenna could not receive. ADS-B, ACARS, and AIS need live traffic --
capturing them without aircraft or vessels in range produces noise-floor vectors that
corrupt the distance matrix and threshold suggestions. The matrix overflow was a
cosmetic problem that made the output unreadable on standard terminals.

**Key functions:**

`_print_band_warning(label: str)` -- prints a one-time warning for bands that need live
signals. ADS-B, ACARS, and AIS only produce real fingerprints when aircraft or vessels
are within range. Without them the tool captures noise-floor vectors, which corrupts
the distance matrix and threshold suggestions. Analogy: a weather station warning that
"no rain detected" might just mean the gauge is broken, not that it is dry.

`_print_matrix(row_entries, col_entries, distance_pairs, ...)` -- prints a pairwise
distance matrix subset. All rows are printed but only the requested columns are shown.
This lets the full matrix be split into two halves when it would otherwise overflow a
terminal width. Analogy: a spreadsheet that shows all rows but only half the columns at
a time, with a note to scroll right for the rest.

**Deferred items:**

1. **`tools/diagnose_fingerprints.py` ADS-B gain divergence** -- documented as
   provisional in inline TODOs. The file was aligned to 24/24 in Phase 19a but the
   AGENTS.md tech debt row is stale. Not addressed in this build (doc changes only).

2. **ChromaDB distance reference stale (Phase 13)** -- `_DISTANCE_SCALE_REFERENCE`
   thresholds in `llm/classifier.py` were calibrated for 6D L2 distances. After 7D
   reseed, thresholds over-classify known signals as "novel." This tool is part of
   the recalibration workflow. Track under 9C-Threshold (open).

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None -- all changes are calibration tool UX and display. No RF
  interaction beyond receive-only IQ capture.

**Test counts:** 517 (375 pytest + 142 Vitest). No new tests -- calibration tool
changes are not covered by the test suite.

---

### Phase 17 — Focused Decode Panel (Feature A) ✓ DONE

**What:** The DECODED SIGNALS section now shows only the decoder sub-panel relevant
to the currently focused band. Previously, all three sub-panels (ADS-B, ACARS, AIS)
were always rendered regardless of which band was tuned. This created visual clutter
when monitoring non-decoder bands (e.g. FM, APRS) and misleading "NOT TUNED" badges
on panels that were irrelevant to the current view.

The fix wraps each sub-panel in an outer conditional renderer: ADS-B renders only when
`isTuned(focusedFreq, 1090000000)`, ACARS only when `isAcarsTuned(focusedFreq)`, and
AIS only when `isAisTuned(focusedFreq)`. When no decoder band is focused, a
"NO DECODER FOR THIS BAND" placeholder is shown.

**Changes:**

1. **`isAisTuned(freq)` helper** — New top-level function in `App.jsx` (after
   `isAcarsTuned`). Checks `isTuned(freq, 162000000, 100000)`. The 100 kHz tolerance
   covers both AIS Channel 1 (161.975 MHz) and Channel 2 (162.025 MHz). Replaces
   inline `isTuned(focusedFreq, 162000000, 100000)` calls with a named function for
   consistency with `isAcarsTuned`.

2. **`anyDecoderTuned` derivation** — New boolean in `App()` body. True when
   `focusedFreq` matches ADS-B, ACARS, or AIS. Controls the "NO DECODER FOR THIS
   BAND" placeholder visibility.

3. **Outer conditional wrappers** — Each sub-panel's root `<div>` is now guarded by
   its tuned-state check (e.g. `{isTuned(focusedFreq, 1090000000) && (...)}`).
   When the guard is false, the entire sub-panel is removed from the DOM. The inner
   three-state logic (TUNED / NOT TUNED / Listening) is preserved unchanged per spec.

4. **"NO DECODER FOR THIS BAND" placeholder** — New element rendered when
   `!anyDecoderTuned`. Uses `--text-dim` colour and 11px data font to match the
   dashboard's visual language.

5. **Malformed JSDoc fix** — `isTuned()` JSDoc had `*  *` (double asterisk); fixed to
   single `*`.

6. **Test updates** — NOT TUNED tests in `AdsbTunedState.test.jsx`,
   `AcarsTunedState.test.jsx`, and `AisTunedState.test.jsx` updated to assert the
   sub-panel is hidden when `focusedFreq` is null. New `DecodedSignalsVisibility.test.jsx`
   (6 tests) covers visibility for all decoder bands, FM, and null focus. Existing
   `App.test.jsx` sub-panel presence tests updated for the behaviour change.

**Why:** When monitoring FM broadcast (98 MHz) or APRS (145.175 MHz), the ADS-B,
ACARS, and AIS sub-panels were visible but showed "NOT TUNED" badges and "TUNE TO..."
prompts. This was visual noise with no actionable value. The user already knows which
band they are on from the nav bar. Hiding irrelevant sub-panels declutters the
dashboard and makes the decoded signals section more focused.

**Key functions:**

`isAisTuned(freq)` — returns true when `freq` is within 100 kHz of the AIS
dual-channel centre (162.000 MHz). The tolerance covers both Channel 1 (161.975 MHz)
and Channel 2 (162.025 MHz). Analogy: a bouncer at the door who lets in anyone
wearing an AIS badge, regardless of which channel they arrived on.

`anyDecoderTuned` — derived boolean, true when focused on any band with a decoder
(ADS-B, ACARS, or AIS). Used solely to toggle the "NO DECODER FOR THIS BAND"
placeholder. Analogy: an "open for business" sign that flips to "closed" when no
decoder is relevant.

**Deferred items:**

1. **Dead inner NOT TUNED branches** — The inner three-state conditional (TUNED /
   NOT TUNED / "TUNE TO...") inside each sub-panel is now unreachable when the
   outer guard is false. The NOT TUNED badge and "TUNE TO..." prompt inside each
   sub-panel are dead code because the outer conditional only renders the panel when
   tuned. The spec explicitly forbade altering internal sub-panel JSX, so this dead
   code was intentionally left in place. Clean up in a future phase.

2. **Optional: `isAdsbTuned()` helper** — ADS-B uses inline `isTuned(focusedFreq,
   1090000000)` while ACARS and AIS have named helpers. Consider adding
   `isAdsbTuned(freq)` for consistency.

3. **Optional: boundary-frequency tests** — `DecodedSignalsVisibility.test.jsx`
   covers AIS CH1 (161.975 MHz) and CH2 (162.025 MHz) boundary frequencies but
   could be extended to cover ACARS 130.025 MHz (already tested via AcarsTunedState)
   and ADS-B boundary frequencies.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None -- all changes are frontend conditional rendering, no RF
  interaction

**Test counts:** 496 (373 pytest + 123 Vitest).

---

### Phase 15b — AIS Waterfall Frequency Migration Completion ✓ DONE

**What:** Completed the AIS frequency migration from 161.975 MHz (AIS Channel 1
only) to 162.000 MHz (AIS dual-channel centre) across all frontend components.
This resolves the frontend/backend AIS frequency mismatch deferred from Phase 14:
the backend `BAND_PROFILES` already centred AIS at 162.000 MHz, but the frontend
still referenced 161.975 MHz in four separate locations.

**Changes:**

1. **`WaterfallPanel.jsx` STRIP_CONFIGS** — AIS entry updated from 161.975 MHz
   to 162.000 MHz. The JSDoc comment was already updated in Phase 15 to reference
   the sync between STRIP_CONFIGS, BAND_GROUPS, and OVERVIEW_BANDS.

2. **`SignalHistoryLog.jsx` FREQ_COLOUR_MAP + freqLabel()** — The colour map key
   changed from `161975000` to `162000000` and the `freqLabel()` return value
   changed from `'161.975 MHz'` to `'162.000 MHz'`. Without this, signals
   arriving at 162.000 MHz fell through to the generic white colour and a
   computed label.

3. **`AisVesselPanel.jsx` isAisFreq + display text** — The centre frequency
   comparison changed from `161_975_000` to `162_000_000` and the "Listening
   on..." display text changed from `161.975 MHz` to `162.000 MHz`. Without
   this, the AIS vessel panel showed "Not tuned to AIS frequency" when focused
   on 162.000 MHz.

4. **`FrequencyList.jsx` FREQ_CONFIGS** — AIS entry updated from 161.975 MHz to
   162.000 MHz. Discovered during the sweep — this file was not in the original
   Phase 15 plan but contained the same stale frequency. A JSDoc comment was
   added documenting the sync requirement and the 162.000 MHz rationale.

5. **`WaterfallPanel.test.jsx`** — AIS frequency assertions updated from
   `161.975 MHz` to `162.000 MHz`.

**Why:** The AIS dual-channel centre is 162.000 MHz (midpoint between Channel 1
at 161.975 MHz and Channel 2 at 162.025 MHz). The backend `BAND_PROFILES` was
corrected to 162.000 MHz in Phase 14, but the frontend still sent 161.975 MHz
when the user clicked the AIS band button. This meant `get_band_for_freq(161975000)`
returned None (no profile matched), so AIS threshold and gains were never applied
when the user tuned to AIS. Aligning all frontend references to 162.000 MHz
ensures the band profile is correctly matched.

**Key constants affected:**

`STRIP_CONFIGS` in `WaterfallPanel.jsx` — AIS entry now `freq_hz: 162000000`.
Used by WaterfallStrip for per-band waterfall rendering and by SpectrometerBar
for frequency snapping.

`FREQ_COLOUR_MAP` in `SignalHistoryLog.jsx` — AIS key now `162000000`. Maps the
centre frequency to `--neon-red` CSS variable for consistent row colouring.

`freqLabel(freqHz)` in `SignalHistoryLog.jsx` — returns `'162.000 MHz'` for
`162000000`. Provides a human-readable label in the signal history log.

`isAisFreq` in `AisVesselPanel.jsx` — checks `Math.abs(focusedFreq - 162_000_000) <= 100_000`.
Determines whether the AIS vessel panel shows data or a "not tuned" message.

`FREQ_CONFIGS` in `FrequencyList.jsx` — AIS entry now `freq_hz: 162000000`.
Drives the sidebar band list.

**Deferred items:**
- None new. This phase resolves the "Frontend/backend AIS frequency mismatch"
  deferred item from Phase 14.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are frontend display constants, no RF
  interaction

**Test counts:** 493 (371 pytest + 122 Vitest). No new tests — existing
WaterfallPanel.test.jsx assertions updated to match new constant.

---

### PHASE-14 — AIS Band Profile Fix + CHECKPOINT Parser Fix ✓ DONE

**What:** Two targeted fixes:

1. **AIS band profile centre frequency corrected** — The `ais` entry in
   `BAND_PROFILES` (`dashboard/shared_state.py`) had its `center_freq_hz`
   changed from 161_975_000 (AIS Channel 1 only) to 162_000_000 (AIS
   dual-channel centre). The AIS demodulator in `modules/ais/constants.py`
   expects a centre of 162.000 MHz to capture both AIS channels
   (161.975 MHz and 162.025 MHz). With the old centre at 161.975 MHz,
   the demodulator's dual-channel capture was misaligned — the upper
   channel (162.025 MHz) fell outside the tuned bandwidth. The gains
   were also adjusted: lna 24→16, vga 26→20, consistent with other VHF
   bands (aviation, ACARS) that operate at similar signal strengths.

2. **CHECKPOINT_MODE parsing in build.md** — The governance doc
   `.opencode/command/build.md` now supports dual-entry checkpoint mode:
   via the `$2` flag (`CHECKPOINT`) or embedded in the task body
   (`CHECKPOINT_MODE: ON`). The PHASE-TRACKER GATE was updated to accept
   either form. This resolves the CHECKPOINT arg parser failure that
   silently dropped the `$2` positional arg when `$1` was a long
   multi-line string.

**Why:** The AIS centre frequency mismatch meant that when the dashboard
tuned to the AIS band, the backend band profile (gains, threshold) was
not applied — `get_band_for_freq(161_975_000)` returned None because the
profile centre was 162_000_000. Aligning the profile centre to
162.000 MHz ensures the AIS band profile is correctly matched when the
HackRF tunes to the AIS frequency. The gain reduction (24/26→16/20)
aligns AIS with other VHF maritime peers (aviation and ACARS both use
16/20).

**Files changed:**
- `dashboard/shared_state.py` — `BAND_PROFILES["ais"]`: centre moved from
  161_975_000 to 162_000_000, gains changed from 24/26 to 16/20, inline
  comment added documenting gain rationale and provisional threshold
- `tests/dashboard/test_shared_state.py` — 3 new tests:
  `test_ais_centre_freq_matches_constants` (asserts AU_AIS_CENTRE_FREQ_HZ
  equality), `test_ais_gains_match_aviation_acars` (asserts lna=16, vga=20),
  `test_ais_ch1_freq_no_longer_matches` (documents that
  `get_band_for_freq(161_975_000)` returns None after centre change);
  existing tests updated to match new centre
- `.opencode/command/build.md` — PHASE-TRACKER GATE updated with
  dual-entry CHECKPOINT_MODE support; usage line and TASK block comment
  expanded

**Key functions:**

`BAND_PROFILES` — per-band gain, threshold, and centre frequency
configuration for the dashboard waterfall. The `ais` entry now centres at
162.000 MHz (dual-channel) instead of 161.975 MHz (Channel 1 only). This
aligns the profile with the AIS demodulator's expected centre frequency.
Analogy: tuning a radio to the midpoint between two stations so both
come in clearly, rather than tuning to one station and losing the other.

`get_band_for_freq(freq_hz)` — looks up a BAND_PROFILES entry by exact
centre frequency match. After this change, `get_band_for_freq(161_975_000)`
returns None (CH1 is no longer a profile centre). The function's behaviour
is unchanged — it still iterates in definition order and returns the first
match. The AIS profile is now matched at 162_000_000.

**Deferred items:**

1. **Frontend/backend AIS frequency mismatch (RESOLVED — Phase 15b):** The
   frontend AIS references (STRIP_CONFIGS, FREQ_COLOUR_MAP, freqLabel(),
   isAisFreq, FREQ_CONFIGS) were updated from 161975000 to 162000000 in
   Phase 15b. All frontend components now use the dual-channel centre
   frequency, matching BAND_PROFILES.

2. **AGENTS.md AIS tech debt row stale (RESOLVED — Phase 15b):** The row
   "AIS BAND_PROFILES centre vs demodulator centre mismatch" described the
   old problem (frontend at 161.975 MHz, BAND_PROFILES at 162.000 MHz).
   Both backend and frontend are now aligned at 162.000 MHz. The AGENTS.md
   row should be updated to reflect the resolution.

3. **capture_loop.py dead code (pre-existing):** `run_shared_capture_loop()`
   is never imported or called. `band_change_event.set()` is never called
   anywhere. `BAND_PROFILES` gains are consumed only by this dead code
   path — the production scanner uses `config/mimir.yaml` gains.
   Not introduced by this build.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are band profile configuration and
  governance doc update. All RX-only.

**Test counts:** 492 (371 pytest + 121 Vitest). 3 new tests in
`tests/dashboard/test_shared_state.py`.

---

### PHASE-13 — Spectral Flatness Embedding Expansion ✓ DONE

**What:** Expanded the embedding vector from 6 dimensions to 7 by adding
`spectral_flatness` (Wiener entropy) as the 7th feature. Previously,
`spectral_flatness` was computed in `fingerprint_spectrum()` (Phase 10-Fix4)
and included in the LLM classifier's user prompt, but was not part of the
ChromaDB embedding vector — meaning ChromaDB similarity search could not
use spectral flatness when finding nearest neighbours. A narrowband FM carrier
(flatness ~0.05) and a wideband noise signal (flatness ~0.9) could appear
similar to ChromaDB if their other 6 features were close, even though their
spectral shapes are fundamentally different.

**Changes:**

1. **`embeddings/embedder.py`** — Added `"spectral_flatness"` to
   `EMBEDDING_FEATURES` at index 6 (now 7 features). Added
   `"spectral_flatness": [0.0, 1.0]` to `NORMALISATION_RANGES`. Updated
   module docstring ("6 features" to "7 features"), `embed()` Args and
   Returns docstrings ("6 keys/floats" to "7 keys/floats"). `VECTOR_DIM`
   auto-updates to 7 via `len(EMBEDDING_FEATURES)`.

2. **`llm/classifier.py`** — Added a NOTE comment block above
   `_DISTANCE_SCALE_REFERENCE` explaining that the hardcoded distance
   thresholds (0.010/0.022/0.031) were calibrated against 6D embeddings
   and will shift after a 7D reseed (L2 distance scales with
   sqrt(dimension)). Tracked under 9C-Threshold.

**Why:** Spectral flatness (Wiener entropy) measures the shape of the
spectrum: a pure tone has flatness near 0.0 (very narrow/tonal), while
white noise has flatness near 1.0 (spread uniformly across all frequencies).
This is a powerful discriminator for the vector store — two signals with
similar peak power and SNR but different spectral shapes will now produce
different embeddings, giving ChromaDB better nearest-neighbour results and
the LLM richer context for classification.

**Key functions:**

`SpectrumEmbedder.embed(fingerprint)` — converts a fingerprint dict into
a normalised 7D embedding vector. Each feature is min-max normalised to
[0, 1] using predefined ranges. The 7th feature (`spectral_flatness`) is
normalised from [0.0, 1.0] (its natural range) to [0.0, 1.0] (identity
mapping). The resulting vector is used for ChromaDB storage and similarity
search. Analogy: a blood test panel that now includes one additional marker
— the test is more informative without changing how it works.

`VECTOR_DIM` — auto-derived constant, now 7 (was 6). Used by
`SpectrumEmbedder.__init__()` to set `self.dim`. Any downstream code that
checks embedding length will pick up the new dimension automatically.

**Deferred items:**

1. **ChromaDB distance thresholds stale for 7D** — The `_DISTANCE_SCALE_REFERENCE`
   thresholds in `llm/classifier.py` (0.010/0.022/0.031) were calibrated
   against 6D L2 embeddings. After 7D reseed, these thresholds will
   over-classify known signal types as "novel" because L2 distances scale
   with sqrt(dimension). Requires recalibration via
   `tools/calibrate_thresholds.py` when live captures are available.
   Track under 9C-Threshold (open).

2. **NaN propagation** (pre-existing, LOW) — `embed()` does not guard
   against NaN values in any feature. A NaN in `spectral_flatness` (from
   a corrupt FFT) would propagate through to ChromaDB and produce
   unpredictable similarity distances. Consider adding `math.isfinite()`
   guard before normalisation. Not addressed in this build.

3. **ChromaDB re-seed required** — Existing embeddings in `data/vectorstore/`
   were computed under 6D. After this build, new captures produce 7D
   vectors. The vector store must be re-seeded (via `tools/seed_chromadb.py`)
   to ensure all stored embeddings are 7D. Running the scanner with a mix
   of 6D and 7D vectors will produce incorrect similarity results.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are embedding dimension expansion
  and comment additions. No RF interaction.

**Test counts:** 489 (368 pytest + 121 Vitest).

---

### PHASE-12 — Decoder-Driven ADS-B Classification ✓ DONE

**What:** Added a decoder-driven `scan_result` emission path for confirmed ADS-B
decodes. When `AdsbDecoder` successfully decodes an ADS-B frame (CRC valid,
DF17/DF18, valid ICAO), the decoder now emits a `scan_result` event directly —
bypassing the LLM pipeline entirely. The decode is ground truth, so confidence = 1.0.

Previously, ADS-B frames went through the same LLM classification path as raw
spectrum captures: fingerprint → embedding → ChromaDB similarity → LLM prompt →
classification. This was redundant for ADS-B because a CRC-validated, DF17-mode-S
decode is already a confirmed signal type — no AI guessing needed. The decoder path
also produces structured fields (ICAO, callsign, altitude) that the LLM prompt
could not extract from a raw PSD fingerprint.

**Changes:**

1. **`modules/adsb/subscriber.py`** — Added `scan_result_fn: Callable | None = None`
   parameter to `AdsbSubscriber.__init__()`. The callback is called after
   `broadcast_fn` in both `_decode_loop()` (real-time decodes) and `stop()`
   (harvested CPR positions). Uses `collections.abc.Callable` for the type
   annotation (PEP 604 union operator works on types, not the builtin
   `callable` function). Defaults to None for backward compatibility.

2. **`dashboard/server.py`** — Added `emit_adsb_scan_result()` top-level function.
   Builds a `scan_result` event payload with `confidence=1.0`, `signal_type='adsb'`,
   and a reasoning string constructed from ICAO, callsign, and altitude. All
   fingerprint fields (`peak_power_db`, `snr_db`, etc.) are emitted as `None`
   because the decoder path does not go through the FFT/features pipeline.
   Applies the same focused-frequency filter as `broadcast()`: only emits if the
   focused frequency is None or within `FREQ_TOLERANCE_HZ` of
   `AU_ADSB_FREQUENCY_HZ` (1090 MHz). Lock is released before `socketio.emit()`
   to avoid deadlock (matches `broadcast()` pattern).

3. **`scan.py`** — Imported `emit_adsb_scan_result` and wired it as
   `scan_result_fn` in the `AdsbSubscriber` construction.

**Why:** ADS-B at 1090 MHz is one of the strongest and most structured signals
Mimir receives. A CRC-validated Mode S decode is unambiguous ground truth —
there is nothing for the LLM to guess. The decoder also provides ICAO, callsign,
altitude, and position that a PSD fingerprint cannot. Bypassing the LLM for ADS-B
saves inference time (no ChromaDB lookup, no prompt construction, no LLM call) and
produces higher-quality classification output (confidence 1.0 vs LLM's typical
0.7-0.9 for ADS-B).

**Key functions:**

`emit_adsb_scan_result(msg: AdsbMessage)` — top-level function in `server.py`.
Acquires `_focused_freq_lock`, reads focused frequency, releases lock, then
emits a `scan_result` event with `confidence=1.0` and all fingerprint fields
as `None`. The reasoning string reads: "Confirmed ADS-B decode - ICAO {icao},
callsign {callsign}, altitude {alt} ft". Analogy: a barcode scanner that
already knows what it scanned — no need to ask the AI to guess.

`AdsbSubscriber.__init__(broadcast_fn, scan_result_fn=None)` — now accepts an
optional `scan_result_fn` callback. When provided, called alongside
`broadcast_fn` after every successful decode. When None (default), the
subscriber behaves exactly as before. Analogy: a second output port on a
radio — you can plug in an additional listener if you want, but the radio
works fine without one.

**Deferred items:**
- **scan_result flooding** — In busy airspace, ADS-B traffic can produce dozens
  of decoded frames per second. Each emits a separate `scan_result` event.
  If this floods Signal History or the AI Reasoning panel, rate-limiting or
  batching may be needed. Not addressed in this build (no busy airspace
  available for testing).

**Pre-existing issues surfaced (not new in this build):**
- `au_legal_status` casing mismatch: backend emits lowercase `'legal_rx'`,
  frontend checks for uppercase `'LEGAL'` (App.jsx:567). Pre-existing.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are passive receive-only decode path
  additions. ADS-B decoding is legal under ACMA regulations.

**Test counts:** 489 (368 pytest + 121 Vitest). 10 new tests total:
3 subscriber tests (`scan_result_fn` called, not required, called on harvest)
and 7 server tests (`TestEmitAdsbScanResult`: emit behaviour, signal type,
confidence, reasoning, focus filter).

---

### PHASE-CLASSIFIER-SCHEMA-FIX — Classifier Schema: ACARS + AIS Added to LLM Prompt ✓ DONE

**What:** Added `acars` and `ais` to the LLM classifier's schema and band reference
so the 4B LLM can output these signal types and frequency bands consistently.

Previously (PHASE-CLASSIFIER-ACCURACY-FIX), ACMA reference entries were added to
`frequency_reference.json` to give the LLM contextual hints ("Classify as acars,
not aviation_vhf"). However, the system prompt's `_JSON_SCHEMA` and
`_AU_BAND_REFERENCE` constants still did not list `acars` or `ais` as valid
`signal_type` or `frequency_band` values. The 4B LLM could not reliably output
labels that were absent from its output schema.

**Changes:**
1. **`_AU_BAND_REFERENCE`** — Added ACARS (129.0–130.1 MHz, aircraft digital messaging,
   129.125 MHz primary) and AIS (161.9–162.1 MHz, maritime vessel tracking,
   161.975/162.025 MHz) entries. These complement the ACMA reference lookup by
   giving the LLM direct band knowledge in its system prompt.

2. **`_JSON_SCHEMA`** — Added `acars` and `ais` to the `signal_type` enum list,
   and `acars_band` and `ais_band` to the `frequency_band` enum list. The LLM
   now sees these as valid output values.

3. **`ClassificationResult` docstring** — Updated `signal_type` and
   `frequency_band` field examples to include `acars`, `ais`, `acars_band`,
   and `ais_band`.

4. **`tests/test_classifier.py`** — New file with 6 static schema-inspection
   tests that verify `acars` and `ais` appear in `_AU_BAND_REFERENCE`,
   `_JSON_SCHEMA` signal_type list, and `_JSON_SCHEMA` frequency_band list.

5. **`tests/llm/test_phase4_classifier.py`** — Added `acars` and `ais` to
   `_ALL_MIMIR_BANDS` set so existing band-coverage tests include the new types.

**Why:** The 4B LLM on yubaba is a small model that follows its schema
closely. If a label is absent from the output schema, the model will
substitute a similar-sounding alternative (e.g. `aviation_vhf` for ACARS,
`marine_satellite` for AIS). Adding the labels to both the band reference
and the JSON schema eliminates this ambiguity at the prompt level.

**Files changed:**
- `llm/classifier.py` — `_AU_BAND_REFERENCE`, `_JSON_SCHEMA`,
  `ClassificationResult` docstring
- `tests/test_classifier.py` — new file, 6 static schema tests
- `tests/llm/test_phase4_classifier.py` — `_ALL_MIMIR_BANDS` expanded

**Deferred items:**
- **[RESOLVED]** "Classifier schema missing acars/ais" Known Tech Debt entry
  from PHASE-CLASSIFIER-ACCURACY-FIX is now resolved. The schema, band
  reference, and docstrings all include ACARS and AIS.
- **[OPEN]** AIS BAND_PROFILES centre vs demodulator centre mismatch —
  `BAND_PROFILES` centre_freq_hz (161.975 MHz = CH1) differs from AIS
  demodulator expected centre (162.000 MHz for dual-channel). If dashboard
  tunes to 161.975 MHz, dual-channel decode may misbehave. Not addressed
  in this build.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are prompt/schema text additions,
  no RF interaction

**Test counts:** 462 (350 pytest + 112 Vitest).

---

### PHASE-CLASSIFIER-ACCURACY-FIX — ACMA Reference Entries for ACARS and AIS + AIS Band Profile ✓ DONE

**What:** Three changes to correct LLM misclassification of ACARS and AIS signals:

1. **ACARS entry in frequency_reference.json** — Added a new reference entry
   (129.0–130.1 MHz, `mimir_band: "acars"`) so the LLM receives the context
   "Classify as acars, not aviation_vhf" when looking up 129.125 MHz.
   Previously, the LLM saw 129.125 MHz as "AERONAUTICAL MOBILE (R)" with no
   specific acars annotation and frequently classified ACARS signals as
   aviation_vhf.

2. **AIS entry in frequency_reference.json** — Added a new reference entry
   (161.9–162.1 MHz, `mimir_band: "ais"`) so the LLM receives the context
   "This is NOT marine satellite or general marine VHF... Classify as ais"
   when looking up 161.975 MHz. Previously, the LLM saw 161.975 MHz under a
   generic maritime allocation and classified AIS signals as marine_satellite.

3. **AIS entry in BAND_PROFILES** — Added the `ais` band profile to
   `dashboard/shared_state.py` BAND_PROFILES dict (between acars and aprs).
   Configuration: centre_freq_hz=161_975_000, lna_gain_db=24, vga_gain_db=26,
   signal_threshold_db=5.0 (provisional, similar to APRS VHF). This completes
   the AIS band coverage — previously AIS was missing from BAND_PROFILES even
   though the AIS decoder module existed.

**Why:** Without specific ACMA reference entries, the small 4B LLM had no way
to distinguish ACARS from ordinary aviation voice, or AIS from marine satellite
transmissions. Both misclassifications were confirmed during live testing. The
BAND_PROFILES entry was a gap: AIS had a decoder module (Phase 9E) and a
waterfall entry (Phase 10-Fix3), but no band profile for threshold/gain
configuration.

**Files changed:**
- `data/frequency_reference.json` — added ACARS entry
  (129.0–130.1 MHz, mimir_band: "acars") and AIS entry
  (161.9–162.1 MHz, mimir_band: "ais")
- `dashboard/shared_state.py` — added `ais` entry to BAND_PROFILES
  (161.975 MHz, lna=24/vga=26, threshold=5.0 dB); updated block comment
- `tests/dashboard/test_shared_state.py` — 2 new tests: test_ais_in_band_profiles,
  test_ais_band_profile_lookup
- `tests/llm/test_acma_reference.py` — 2 new tests: test_acars, test_ais
  in TestRangeMatch

**Deferred items:**
- **[RESOLVED — PHASE-CLASSIFIER-SCHEMA-FIX]** `llm/classifier.py`
  schema/examples don't list "acars" or "ais" as valid signal_type values.
  The system prompt's _JSON_SCHEMA and _AU_BAND_REFERENCE now include these
  types. Resolved in PHASE-CLASSIFIER-SCHEMA-FIX.
- **[LOW]** `get_band_for_freq()` relies on exact Hz match. The AIS
  BAND_PROFILES entry uses 161_975_000 (AIS CH1), but the AIS demodulator in
  `modules/ais/constants.py` expects centre 162_000_000 to capture both AIS
  channels. If the dashboard tunes to 161.975 MHz, the AIS subscriber may not
  centre correctly for dual-channel decode. Not addressed in this build.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are data additions (ACMA reference
  entries and band profile config)

**Test counts:** 456 (344 pytest + 112 Vitest).

---

### PHASE-BUILD-3 — AIS Waterfall Config, Tuned-State Test Coverage, SignalHistoryLog Memoisation ✓ DONE

**What:** Three changes across the frontend:

1. **AIS added to STRIP_CONFIGS** — Added AIS (161.975 MHz, `--neon-red`) as the 7th
   entry in `WaterfallPanel.jsx` STRIP_CONFIGS. The waterfall now shows all 7
   AU-legal bands: FM, APRS, Aviation VHF, ACARS, AIS, ISM/LoRa, ADS-B. Previously
   AIS was missing from the waterfall display even though AIS messages were decoded
   and displayed in the AIS panel.

2. **SignalHistoryLog React.memo** — Wrapped `SignalHistoryLog` in `React.memo` with
   a custom comparison function. Checks `pinnedTimestamp` first (fast exit on pin
   toggle), then `scanResults` array length and head entry timestamp. Prevents
   re-render on every `spectrum_update` (~4-5 Hz) while still re-rendering when
   pin state changes or new scan results arrive.
   **Resolves deferred item #3 from the Pin-to-Reasoning section** ("SignalHistoryLog
   not memoised — Re-renders on every spectrum_update (~4-5 Hz). React.memo
   recommended as optimisation.").

3. **Tuned-state test coverage expanded** — Refactored `AdsbTunedState.test.jsx` with
   `makeMock` helper, added ADS-B NOT TUNED test. Created `AcarsTunedState.test.jsx`
   (2 tests) and `AisTunedState.test.jsx` (2 tests) — both cover the three-state
   tuned-state logic (tuned+data, tuned+no data, not tuned). Updated
   `WaterfallPanel.test.jsx` canvas count (12→14), band label/name count (6→7),
   and added AIS-specific label click test.

**Why:** AIS is a monitored band (161.975 MHz, maritime vessel identification) but
was missing from the waterfall display — maritime users could not see AIS spectrum
activity while decoder messages were flowing. The memoisation reduces unnecessary
re-renders and improves dashboard responsiveness. The tuned-state tests ensure the
three-state sub-panel logic is tested for all three decoder modules (ADS-B, ACARS,
AIS), not just ADS-B.

**Key functions affected:**

`STRIP_CONFIGS` in `WaterfallPanel.jsx` — now 7 entries (added AIS at 161.975 MHz
with `--neon-red` CSS colour variable). Ordered by frequency ascending. Used by
`WaterfallStrip` for per-band waterfall rendering, by `SpectrometerBar` for
frequency snapping, and by `FrequencyList` for band enumeration.

`SignalHistoryLog` — wrapped in `React.memo` with a custom comparison function.
The comparison checks `pinnedTimestamp` first (reference equality — fast exit on
pin toggle), then `scanResults` identity (`===`), length, and head entry timestamp.
Without this, the component re-rendered on every `spectrum_update` broadcast
(~4-5 Hz) even when no new scan result had arrived.

**Deferred items:**
- OVERVIEW_BANDS in `App.jsx` has 6 entries while STRIP_CONFIGS has 7 — AIS
  (161.975 MHz) is missing from the overview band strip at the bottom of the
  waterfall. When tuned to AIS, the overview waterfall may fall back to FM
  Broadcast (STRIP_CONFIGS[0]).
- BAND_GROUPS in `App.jsx` also lacks an AIS entry — the navigation bar has no
  AIS button. Currently users must enter 161.975 via the custom frequency input
  to focus AIS.
- ACARS 130.025 MHz dual-frequency check — RESOLVED (commit 7c6ff15). Added
  `isAcarsTuned(freq)` helper in `App.jsx` that matches either 129.125 MHz or
  130.025 MHz (5000 Hz margin each). Both ACARS sub-panel call sites now use
  the helper, so the outer header correctly shows TUNED when focused on either
  ACARS frequency.
- Resolved deferred item from Pin-to-Reasoning: **SignalHistoryLog not memoised**
  resolved — `React.memo` with custom comparison implemented in this build.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are frontend display code, memoisation,
  and test coverage

**Test counts:** 445 (334 pytest + 111 Vitest).

---

### PHASE-TECH-DEBT-2 — Frontend Small Fixes: ??, null guard, colour map, overview bands, test mock ✓ DONE

**What:** Five small frontend fixes across the dashboard — no new features,
no backend changes:

1. **`||` to `??` in `useSocket.js`** — The `scan_result` handler used `||`
   for `confidence_score`, which treated `0` (a valid 0% confidence result
   from the LLM) as falsy and silently replaced it with `null`. The nullish
   coalescing operator `??` only replaces `null` or `undefined`, preserving
   `0` as a legitimate confidence value.

2. **Null guard in `FrequencyList.jsx`** — Added `!= null` guard before
   `Math.round(latest.confidence_score * 100) + '%'`. Without it, a null
   or undefined `confidence_score` produced `NaN%` in the UI.

3. **FREQ_COLOUR_MAP and `freqLabel()` expansion in `SignalHistoryLog.jsx`**
   — Added 3 missing AU frequencies: 127 MHz (Aviation VHF → --neon-cyan),
   129.125 MHz (ACARS → --neon-amber), 161.975 MHz (AIS → --neon-red).
   Previously these fell through to generic white colour and a computed
   label format. The colour map now covers all 7 AU bands Mimir monitors.
   **Resolves deferred item 4 from the Pin-to-Reasoning section**
   ("FREQ_COLOUR_MAP / freqLabel incomplete — Only 4 of 6 AU frequencies
   have dedicated colours and labels").

4. **OVERVIEW_BANDS expansion in `App.jsx`** — Added Aviation VHF (127 MHz)
   and ACARS (129.125 MHz) to the overview strip at the bottom of the
   waterfall. Previously the overview showed only 4 bands (FM, APRS, ISM,
   ADS-B), omitting two bands that were already present in the waterfall's
   STRIP_CONFIGS. The overview strip now matches the waterfall band set.

5. **`createImageData` mock in `tests/setup.js`** — Added a mock for
   `CanvasRenderingContext2D.createImageData()` to the global canvas
   `getContext` mock. Previously, tests that called `ctx.createImageData()`
   (e.g. useWaterfall tests) would fail with a runtime error because the
   method was not mocked. This fixes broken test execution in the Vitest
   suite.

**Why:** Fix 1 prevents a valid 0% confidence (the LLM genuinely has no idea)
from being silently discarded. Fix 2 prevents `NaN%` display in the frequency
list. Fix 3 makes the signal history log visually consistent across all 7 AU
bands — new contributors no longer see white text for three of the bands they
are monitoring. Fix 4 makes the overview strip complete — previously a user
could toggle between Aviation and ACARS without seeing either in the strip.
Fix 5 removes a test infrastructure gap that caused false failures.

**Key functions affected:**

`useSocket` `scan_result` handler (line 59) — `confidence_score` now uses `??`
instead of `||`. The `||` operator treats `0` as falsy because it is falsy in
JavaScript, so a 0% confidence from the LLM was replaced with `null`.
`??` only replaces `null` or `undefined`, preserving `0` as a valid numeric
confidence value. Analogy: a camera flash that correctly captures a black
object as black instead of pretending it isn't there.

`FrequencyList` render (line 67) — now guards against null/undefined
`confidence_score` with `!= null` before computing the percentage string.
Without the guard, `Math.round(null * 100)` produces `NaN`, rendering as
`NaN%` in the UI. Analogy: a fuel gauge that shows `---` instead of `NaN%`
when the sensor is disconnected.

`freqLabel(freqHz)` in `SignalHistoryLog.jsx` — handles 7 AU frequencies
with exact labels: 98.0, 127.0, 129.125, 145.175, 161.975, 915.0, 1090.0
MHz. Previously only 4 frequencies had dedicated labels — the 3 additions
(127.0, 129.125, 161.975) had fallen through to a generic `toFixed(3)`
computed label. Analogy: a map legend that now has entries for every trail
instead of leaving hikers to guess.

`FREQ_COLOUR_MAP` in `SignalHistoryLog.jsx` — maps 7 centre frequencies to
CSS colour variables. New entries: 127 MHz → --neon-cyan (same as FM, both
are aviation/voice), 129.125 MHz → --neon-amber (ACARS data link), 161.975
MHz → --neon-red (AIS maritime).

`OVERVIEW_BANDS` in `App.jsx` — expanded from 4 to 6 entries. The new
entries (AVIATION VHF at 127 MHz, ACARS at 129.125 MHz) were already present
in the waterfall's STRIP_CONFIGS but absent from the overview strip. Now
both lists are consistent, so the user sees every monitored band in the
bottom strip.

**Deferred items:**
- The `NaN` edge case in `FrequencyList.jsx`: `NaN != null` is `true` in
  JavaScript, so if `confidence_score` were somehow `NaN`, the `!= null`
  guard would pass and `Math.round(NaN * 100)` would produce `NaN`. This
  is practically impossible — SocketIO messages are serialised JSON, and
  `NaN` cannot be serialised — but is noted here as a theoretical edge
  case for anyone auditing null-safety.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are frontend display code and test mocks

**Test counts:** 439 (334 pytest + 105 Vitest).

---

### PHASE-TECH-DEBT-1 — Housekeeping: Startup Message, Stale Comments, Test Coverage ✓ DONE

**What:** Six small housekeeping fixes across the codebase — no new features:

1. **Startup message** (`scan.py:94`) — Changed ``"Scanning N frequencies"`` to
   ``"Focus mode: cycling through N band(s) one at a time"`` to better describe
   the single-frequency focus mode introduced in Phase 8C. The old message
   implied a multi-frequency parallel scan that no longer matches reality.

2. **Fatal error exit path test** (`tests/test_scan.py`) — Added
   `test_fatal_error_exits_with_code_1` covering the ``except Exception`` path
   in ``main()`` that sets ``fatal_error = True``. Resolves MED-01 from the
   PHASE-TOOLS-CLEANUP deferred items list.

3. **Strict dict equality refactor** (`tests/dashboard/test_server_stats.py`) —
   Replaced ``payload["key"]`` bare access with ``payload.get("key")`` and
   subset dict iteration so future broadcast field additions no longer break
   the test. Resolves the pre-existing Known Tech Debt entry "test_server_stats.py
   strict dict equality fragility".

4. **ADS-B message stale comments** (`modules/adsb/message.py`) — Updated
   ``latitude``/``longitude`` field docstrings from "from position_with_ref()"
   to "from PipeDecoder global CPR pair resolution (no fixed reference)".
   The old reference was stale since Phase 9F-CPR replaced the stateless
   ``position_with_ref`` with PipeDecoder pair accumulation.

5. **Unused ``sampleRateHz`` parameter** (`useWaterfall.js`) — Removed the
   dead ``sampleRateHz`` parameter from the hook destructuring and all call
   sites (``WaterfallPanel.jsx`` + 3 test call sites). The hook never used
   this value — bin-to-pixel mapping derives solely from the PSD array length.

6. **ADS-B subscriber flush on stop** (`modules/adsb/subscriber.py`) — Added
   ``self._decoder.flush()`` before ``self._running = False`` in ``stop()`` to
   release bootstrap-held CPR positions before shutdown. Previously, aircraft
   with fewer than ``BOOTSTRAP_K=5`` CPR pairs silently lost their positions.
   A full harvest-and-emit pattern would be needed for complete recovery.

**Why:** The startup message was misleading, the fatal error exit path had no
test coverage (MED-01), the test_server_stats.py refactor was a pre-existing
debt item, the ADS-B message comments were stale since 9F-CPR, the dead
``sampleRateHz`` param was confusing to future developers, and the subscriber
shutdown path was silently discarding held ADS-B positions.

**Key functions affected:**

`main()` in `scan.py` — the startup print line now reads "Focus mode: cycling
through N band(s) one at a time" instead of "Scanning N frequencies". The
docstring already documented the ``fatal_error`` flag and exit code semantics
(added in PHASE-TOOLS-CLEANUP).

`useWaterfall({ canvasRef, psdDb })` — the hook signature lost its unused
``sampleRateHz`` parameter. The mapping from 2048 PSD bins to canvas pixels
uses only the PSD array length and canvas width. Added a JSDoc block
describing the parameter change.

`AdsbSubscriber.stop()` — now calls ``self._decoder.flush()`` before setting
``_running = False``, releasing bootstrap-held CPR pairs. A full harvest
and emit of flushed positions is not implemented — they are silently released
rather than discarded without attempt.

**Deferred items:**
- ``AdsbSubscriber.stop()`` flush does not emit flushed positions to the
  dashboard — they are silently released. A harvest-and-emit pattern would
  need a pre-shutdown callback that collects released positions and broadcasts
  them before the thread dies.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are housekeeping (startup text, test
  coverage, dead param removal, comment fixes, shutdown flush).

**Test counts:** 437 (332 pytest + 105 Vitest).

---

**Why:** The 4.0 dB value was set during Phase 11 as a provisional placeholder.
Live threshold sweeps showed that 3.0 dB produces an occupied bandwidth closest
to the expected ADS-B signal width. This calibration completes the ADS-B
threshold tuning that was deferred from Phase 11, moving ADS-B from "needs
revalidation" to "calibrated" status alongside `fm_broadcast`.

**Files changed:**
- `dashboard/shared_state.py` — `BAND_PROFILES["adsb"]["signal_threshold_db"]`
  changed from `4.0` to `3.0`; inline comment updated to document calibration
  basis (`diagnose_threshold.py x3 runs`); BAND_PROFILES block comment now
  lists both `fm_broadcast` and `adsb` as calibrated bands

**Deferred items:**
1. `tools/diagnose_threshold.py` line 25: `THRESHOLD_CANDIDATES` begins at 3 dB.
   The tool recommended 3 dB — the lowest candidate in the sweep range. A future
   calibration run should extend candidates downward (e.g. `[1, 2, 3, ...]`) to
   confirm 3 dB is the true optimum and not a range-floor artefact.
2. When the existing ChromaDB re-seed (open deferred item) is performed, ensure
   ADS-B embeddings are generated under the new 3.0 dB threshold so fingerprint
   distances remain consistent with live captures.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are threshold value tuning, RX-only

**Test counts:** (see AGENTS.md for latest totals)

---

### TEST-SERVER-STATS-REFACTOR — Strict Dict Equality Fix ✓ DONE

**What:** Test-quality refactor of `tests/dashboard/test_server_stats.py` to
eliminate the fragile strict-dict-equality assertions that broke whenever a new
field was added to the broadcast payload.

**Changes:**
1. **`test_filter_passes_matching`** — Replaced the old
   `assert_called_once_with("scan_result", {full_dict_literal})` with individual
   `assert payload[key] == value` assertions for semantically important fields.
   Now asserts only the routing fields (`center_freq_hz`, `timestamp`),
   classification identity (`signal_type`, `confidence`, `confidence_score`,
   `novel`, `au_legal_status`), and explicitly-provided fingerprint fields
   (`peak_power_db`, `snr_db`, `signal_threshold_db`, `snr_margin_db`,
   `bandwidth_hz`, `spectral_flatness`, `chroma_distance`). Uses
   `pytest.approx` for float fingerprint fields to tolerate minor precision
   differences.

2. **`test_passes_all_when_focus_is_none`** — Added loose key assertions
   (`event_name`, `center_freq_hz`, `signal_type`) to complement the existing
   `assert_called_once()`. Previously the test verified only that `emit()` was
   called, not *what* was emitted.

**Why:** The strict dict equality pattern was a pre-existing tech debt item in
AGENTS.md (Known Tech Debt table: "test_server_stats.py strict dict equality
fragility"). Every prior build that added a broadcast field (chroma_distance in
Phase 10-Fix4, signal_threshold_db/snr_margin_db in Phase 11-Hotfix) had to
update this test's literal dict. The new assertions verify the fields that
matter without coupling to the full payload shape — adding a new broadcast
field will not break this test.

**Files changed:**
- `tests/dashboard/test_server_stats.py` — `test_filter_passes_matching` and
  `test_passes_all_when_focus_is_none` refactored with individual field
  assertions

**Test counts:** (see AGENTS.md for latest totals)

**Deferred items:**
- None new surfaced. This build resolves the AGENTS.md Known Tech Debt entry
  "test_server_stats.py strict dict equality fragility".

---

### AI-PANEL-BADGE-REDESIGN — Boxed Pin/Status Badges + Classification Log Heading ✓ DONE

**What:** Three cosmetic badge changes to the frontend dashboard:

1. **AIReasoningPanel CLASSIFICATION LOG heading** — Added a "CLASSIFICATION LOG"
   heading div at the top of the non-placeholder content, above the status/timestamp
   row. Uses `var(--font-display)`, 10px, `var(--text-dim)` colour to match the
   dashboard's data-panel header conventions.

2. **Boxed ◆ PINNED badge** — Replaced the previous inline PINNED badge (rendered
   between the frequency and signal type lines) with a styled boxed badge at the top
   of the panel, beside the timestamp. The badge uses an amber border
   (`1px solid var(--neon-amber)`), amber-tinted background (`rgba(255,170,0,0.14)`),
   a glow `box-shadow`, and `2px 8px` padding. When `isPinned` is false, only the
   timestamp (in `var(--text-bright)`) is displayed.

3. **App.jsx ACTIVE/IDLE badges redesigned** — Replaced the wrapping flex div with
   dot/text spans (● ACTIVE / ● IDLE) with direct boxed badges using the `◆` prefix:
   - ACTIVE: inline-flex badge, red border (`1px solid #ff4444`), red-tinted
     background (`rgba(255,68,68,0.14)`), glow box-shadow, ◆ ACTIVE text
   - IDLE: inline-flex badge, dim border (`1px solid var(--text-dim)`), transparent
     background, ◆ IDLE text

**Why:** The original inline badge styling (plain text between frequency and signal
type lines) was visually subtle and easily overlooked. The boxed badge design gives
the pinned state more visual weight — the amber border and glow make it immediately
obvious that the displayed reasoning is frozen. Similarly, the ACTIVE/IDLE badges
were previously plain text with a coloured dot that blended into the surrounding UI;
the boxed red badge makes the scanning state unmistakable at a glance.

**Files changed:**
- `dashboard/frontend/src/components/AIReasoningPanel.jsx` — added CLASSIFICATION
  LOG heading div; conditional render for isPinned: boxed ◆ PINNED badge + amber
  timestamp vs timestamp only in var(--text-bright)
- `dashboard/frontend/src/App.jsx` — replaced dot/text ACTIVE/IDLE indicators with
  boxed ◆ ACTIVE / ◆ IDLE badges using inline-flex layout, coloured borders,
  tinted backgrounds, and glow box-shadow

**Key functions:**

`AIReasoningPanel` — now renders a CLASSIFICATION LOG heading above the
status/timestamp row when showing live or pinned reasoning data. The `isPinned`
prop controls whether the row shows a boxed ◆ PINNED badge + amber timestamp
(pinned) or a plain timestamp in bright text (live). The badge design uses the
dashboard's `--neon-amber` colour tokens and a subtle glow effect to signal
"this is frozen — not updating". Analogy: a yellow sticky note you can pin to
a corkboard, now with a thick border so you cannot miss it.

**Deferred items:**
- LOW-01 (advisory): App.jsx ACTIVE badge uses hardcoded `#ff4444` instead of
  `var(--neon-red)`. Both reviewers flagged this during dual review. Spec
  explicitly required `#ff4444`. Consider switching to `var(--neon-red)` for
  theme consistency if the colour value is ever revisited.
- LOW-02 (advisory): App.jsx ACTIVE/IDLE badge conditional indentation is off by
  2 spaces from the surrounding JSX. Cosmetic only — the code compiles and
  renders correctly. Fix when touching the surrounding lines next.

### 2026-06-18 update — CLASSIFICATION LOG heading repositioned

The CLASSIFICATION LOG heading was moved from between the status/timestamp row
and the identity row (Line 1 position) to immediately above the reasoning body
(Line 4 position). The heading now sits between the conditional confidence row
and the reasoning text. Font size increased from `10` to `11`.

**Why:** The heading was originally placed at the top of the non-placeholder
content, which looked correct but cluttered the status area. Moving it directly
above the reasoning body puts the heading closer to the content it labels,
matching the visual convention of data-panel headers elsewhere in the dashboard.

**JSDoc updated:** Line 19 now reads "A 'CLASSIFICATION LOG' heading sits above
the reasoning body" (was "above the badge row").

**New deferred item:**
- LOW-03 (advisory): CLASSIFICATION LOG heading has `marginBottom: 4` but no
  `marginTop`. When the conditional confidence row is present (Line 3), the gap
  between the confidence text and the heading is 0px, creating a tight visual
  stack. Cosmetic only — the confidence row appears only when `displayData.confidence`
  is set, which is the common case. Add `marginTop: 4` or `marginTop: 8` to the
  heading's style object if breathing room is desired.

**Files changed:**
- `dashboard/frontend/src/components/AIReasoningPanel.jsx` — CLASSIFICATION LOG
  heading moved from above Line 1 to above Line 5; fontSize 10→11; JSDoc updated

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are frontend React/CSS only, no RF interaction

**Test counts:** (see AGENTS.md for latest totals)

---

### UI-READABILITY-FIX — AI Reasoning Panel Font Size + Container Height + Signal History Opacity ✓ DONE

**What:** Frontend-only UX improvement making the dashboard text easier to read
at desktop resolutions.

**Why:** During live testing, the AI reasoning text was too small to read
comfortably at 1920×1080. All font sizes in `AIReasoningPanel.jsx` were 2-6
pixels too small, and the container height (154px) clipped the enlarged text.
Signal history rows had a dimming effect from a stale opacity conditional that
made older entries harder to read than newer ones.

**Changes:**
1. **AIReasoningPanel font sizes increased** — Seven font-size values bumped up
   (9→11, 8→10, 14→20, 11→14, 10→13, 10→13, 9→11 pixels). The gap between
   elements increased from 6px to 8px for breathing room. The reasoning text
   (previously 9px) is now 11px and the signal_type heading (previously 14px)
   is now 20px — doubling the visual emphasis on the classification result.
2. **AIReasoningPanel container height increased** — The parent container in
   `App.jsx` grew from 154px to 210px (+54 pixels) to accommodate the larger
   font sizes without clipping.
3. **SignalHistoryLog opacity conditional removed** — The row `<div>` had a
   `style={{ opacity: index === scanResults.length - 1 ? 1 : 0.15 }}` that
   made all but the newest entry dim. Removing this conditional means every
   entry in the log renders at full opacity, making earlier entries as readable
   as the latest one.

**Files changed:**
- `dashboard/frontend/src/App.jsx` — AI reasoning container height 154px → 210px
- `dashboard/frontend/src/components/AIReasoningPanel.jsx` — 7 font-size values
  and gap increased across signal_type, freq_hz, confidence badge, timestamp,
  reasoning text, and detailed stats rows
- `dashboard/frontend/src/components/SignalHistoryLog.jsx` — removed opacity
  conditional from row div style

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are frontend CSS/sizing only, no RF interaction

**Test counts:** 105 Vitest (unchanged — no new tests required).

**What:** Frontend-only feature. Clicking a row in the Signal History Log pins
that entry's AI reasoning to the AI Reasoning panel, freezing it so it does
not get overwritten by subsequent scans. Clicking the same row again unpins.
The pin uses composite identity (timestamp + center_freq_hz) so the user must
click the exact same row to unpin.

**Why:** When the LLM classifies a signal, the AI Reasoning panel shows the
result for 8 seconds (via `useFrozenDisplay`), then updates on the next new
signal type. Users wanted to keep a particular classification visible for
longer reference — comparing it against newly arriving signals, or reading
the LLM's reasoning text at leisure. The pin feature provides a manual
hold-to-freeze override.

**How it works:**
- `App.jsx` owns a `pinnedReasoning` state. `handlePinReasoning(entry)` toggles
  it by comparing `prev.timestamp + prev.freq_hz` against `entry.timestamp +
  entry.center_freq_hz`.
- `SignalHistoryLog` receives `onPinReasoning` and `pinnedTimestamp` props.
  Each row calls `onPinReasoning(entry)` on click. A `data-pinned` attribute
  marks the pinned row, and amber styling (left border + tinted background)
  visually identifies it.
- `AIReasoningPanel` receives `isPinned` prop and displays a ◆ PINNED badge
  between the frequency and signal type lines when active.
- `App.jsx` uses `key={pinnedTimestamp || 'live'}` on `AIReasoningPanel` to
  force a React remount, clearing any stale fade/transition state.

**Files changed:**
- `dashboard/frontend/src/App.jsx` — `pinnedReasoning` state,
  `handlePinReasoning` callback, replaced inline Signal History and AI Reasoning
  rendering with `<SignalHistoryLog>` and `<AIReasoningPanel>` components,
  `key` prop on `AIReasoningPanel`, AI reasoning section height 154px
- `dashboard/frontend/src/components/SignalHistoryLog.jsx` — new `onPinReasoning`
  and `pinnedTimestamp` props, `data-pinned` attribute, amber pin styling,
  `onClick` handler on each row
- `dashboard/frontend/src/components/AIReasoningPanel.jsx` — new `isPinned` prop
  (default false), ◆ PINNED badge conditional rendering

**Key functions:**

`handlePinReasoning(entry)` in `App.jsx` — toggles the pinned reasoning entry.
Uses composite identity (timestamp + center_freq_hz) to distinguish rows.
Returns `null` (unpin) when the same entry is clicked again. Spreads
`INITIAL_AI_REASONING` then overlays entry fields so all display keys are
present. Analogy: a sticky note you can stick to a whiteboard by clicking,
and peel off by clicking again.

`<SignalHistoryLog onClick>` — each row in the log is clickable. The `onClick`
handler passes the entry up to `App.jsx`, which toggles the pin. The row sets
`data-pinned` to true when its timestamp matches `pinnedTimestamp`, and gets
amber left border + amber-tinted background styling.

`<AIReasoningPanel isPinned>` — when `isPinned` is true and `displayData.signal_type`
is set, renders ◆ PINNED badge. The `key` prop in `App.jsx` remounts the component
on pin toggle, resetting any fade transition.

**Deferred items:**
1. **Pin eviction** — Pin state persists after the pinned entry scrolls out of
   scanResults (capped at 200). The row becomes invisible and the user cannot
   unpin. An unpin button inside AIReasoningPanel or a pin timeout would fix
   this. Scope decision: not implemented.
2. **Pin survives frequency change** — FocusFrequency clears aiReasoning but not
   pinnedReasoning. Signal Details shows new band while AI Reasoning shows old
   pinned data. Intentional per spec but a UX gap. Consider clearing the pin on
   band change or adding a visual indicator.
3. **SignalHistoryLog not memoised** *(RESOLVED — PHASE-BUILD-3)* — Wrapped in
   `React.memo` with custom comparison (checks `pinnedTimestamp`, then
   `scanResults` length + head timestamp). No longer re-renders on every
   `spectrum_update` (~4-5 Hz).
4. **FREQ_COLOUR_MAP / freqLabel incomplete** — Only 4 of 6 AU frequencies have
   dedicated colours and labels. Aviation, ACARS, AIS fall through to generic
   white text and computed labels. Pre-existing, not introduced by this build.
5. **confidence_score || vs ?? inconsistency** — `useSocket.js` uses `||` (corrupts
   0.0 to null) while pin handler correctly uses `??`. Pre-existing bug.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are frontend React only, no RF interaction

**Test counts:** (see AGENTS.md for latest totals)

---

### PHASE-TOOLS-CLEANUP — Gain Value Consistency + Exit Code Fix ✓ DONE

**What:** Housekeeping and cleanup across four files to fix stale gain
comments, correct a misleading band profile comment, and distinguish
intentional stops from unexpected failures in the scan exit code.

1. **`tools/calibrate_thresholds.py`** — Updated the `CALIBRATION_TARGETS`
   header comment block (lines 48–52) to explain the current gain state for
   each target band: FM_broadcast (24/26) calibrated to telescopic whip
   (Phase 9C-Threshold), Aviation_VHF (16/20) matches production defaults
   but not yet validated, ADS_B (32/38) uses provisional stock-stub values
   requiring recalibration, noise_floor (0/0) zero-gain baseline. The ADS_B
   inline TODO was updated from "revalidate with telescopic whip antenna"
   to "recalibrate with telescopic whip — provisional stock-stub values"
   to be more precise about the scope of work.

2. **`tools/diagnose_fingerprints.py`** — Added a multi-line header comment
   explaining the TARGETS gain rationale: why FM_broadcast uses calibrated
   gains, why Aviation_VHF matches production defaults, why ADS_B uses
   provisional stock-stub values, and crucially why noise_floor uses
   moderate gain (16/20) for diagnostic visibility instead of the production
   zero-gain baseline from `calibrate_thresholds.py` and `shared_state.py`.
   All four inline comments were updated to reflect the current calibration
   status.

3. **`dashboard/shared_state.py`** — Updated the `noise_floor` entry in
   `BAND_PROFILES` (line 152). The comment changed from `# reference — same
   as FM` to `# noise floor baseline dB — not a signal threshold`. The old
   comment was stale (FM is now 12.0 dB, noise_floor remains 10.0 dB) and
   incorrectly implied a relationship between the two values. The new
   comment correctly describes noise_floor as an independent baseline
   measurement.

4. **`scan.py`** — Added a `fatal_error` tracking flag in `main()`. On
   `KeyboardInterrupt` the process exits with code 0 (clean stop). On any
   other `Exception` from `scanner.run()`, the flag is set to `True` and
   the `finally` block exits with code 1. Previously, only the HackRF
   startup guard exited with code 1 — unexpected scan-loop failures
   silently exited 0, making it impossible to distinguish "user stopped
   cleanly" from "something broke".

**Why:** The gain comments in both calibration tools had not been updated
since Phase 9C-Threshold, which replaced the old zero-gain defaults with
production values (24/26 for FM). Developers reading the stale comments
would be confused about which gains are settled and which are provisional.
The `noise_floor` comment was misleading because it claimed "same as FM"
when FM's `signal_threshold_db` had already diverged. The exit code fix
addresses a pre-existing monitoring gap — scripts and supervisors that
check exit codes could not distinguish a clean stop from a crash.

**Files changed:**
- `tools/calibrate_thresholds.py` — CALIBRATION_TARGETS header comment block
  rewritten; ADS_B inline TODO updated
- `tools/diagnose_fingerprints.py` — TARGETS header comment added; all four
  inline comments updated
- `dashboard/shared_state.py` — noise_floor BAND_PROFILES comment updated
- `scan.py` — `fatal_error` flag added; `finally` block exits code 1 on
  unhandled Exception; docstring updated

**Key functions:**

`main()` in `scan.py` — the CLI entry point. Now tracks `fatal_error` to
distinguish `KeyboardInterrupt` (exit 0, clean stop) from unhandled
`Exception` (exit 1, unexpected failure). Previously all non-startup paths
exited 0. Analogy: a server that sends a different error code when it
crashes vs when you press the off button.

**Deferred items:**
- MED-01: `scan.py` `except Exception → fatal_error=True` path has no test
  coverage. Adding a test would require a test file change. Deferred to a
  future build.
- ADS-B gain divergence: `calibrate_thresholds.py` / `diagnose_fingerprints.py`
  use (32/38) for ADS-B while `shared_state.py BAND_PROFILES` uses (24/24).
  Both are intentional — the tools use provisional stock-stub values until
  recalibrated with the telescopic whip. Documented in inline TODOs.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are comments, gain documentation, and
  exit code logic. No RF interaction.

**Test counts:** 422/428 (325 pytest + 97 Vitest). 6 pre-existing pytest
failures (not caused by this build).

---

### Phase 11 Hotfix — Startup Guard + Broadcast Field Order + FM Threshold ✓ DONE

**What:** Three fixes discovered during live testing of Phase 11:

1. **Clean startup failure** — `scan.py` `main()` now catches `RuntimeError` and
   `OSError` from `HackRFReceiver()` construction and `device.open()`. If the HackRF
   is not connected or USB fails, the user sees a clear ERROR log message
   (`"Startup failed: %s. Is the HackRF connected?"`) and the process exits with
   code 1. Previously, a missing HackRF produced an unhandled exception traceback.
   `load_config()` was also moved outside the try/except block so config errors
   are reported separately from hardware errors.

2. **Broadcast field ordering** — In `dashboard/server.py` `broadcast()`,
   `signal_threshold_db` and `snr_margin_db` were moved to immediately after
   `snr_db` in the SocketIO emit dict. Both fields now default to `0.0` via
   `fp.get(..., 0.0)` instead of `fp.get(...)` (which returned `None` when
   the fingerprint dict was missing the key). This is a defensive change — the
   pipeline always populates these fields, but the `0.0` default prevents
   `null` reaching the frontend if a scan result arrives without a fingerprint.

3. **FM broadcast threshold recalibrated** — The `fm_broadcast` entry in
   `BAND_PROFILES` (`dashboard/shared_state.py`) had its `signal_threshold_db`
   changed from `10.0` to `12.0`. The new value is calibrated from live FM
   reception in Adelaide with the telescopic whip antenna at lna=24/vga=26.
   The inline comment was updated to note the calibration basis.

**Why:** Fix 1 prevents confusing tracebacks when starting Mimir without the
HackRF plugged in — a common scenario during development. Fix 2 ensures the
frontend never receives `null` for threshold fields. Fix 3 corrects the FM
threshold after live testing showed 10.0 dB was slightly too permissive.

**Files changed:**
- `scan.py` — `main()` docstring updated with startup guard description;
  `load_config()` moved before try/except; `HackRFReceiver` + `device.open()`
  wrapped in `try/except (RuntimeError, OSError)` with ERROR log and `sys.exit(1)`
- `dashboard/server.py` — `broadcast()` emit dict reordered: `signal_threshold_db`
  and `snr_margin_db` moved after `snr_db`; both default to `0.0`
- `dashboard/shared_state.py` — `BAND_PROFILES["fm_broadcast"]["signal_threshold_db"]`
  changed from `10.0` to `12.0`; inline comment updated
- `tests/dashboard/test_server_stats.py` — expected broadcast payload key ordering
  updated to match the reorder
- `tests/test_scan.py` — new file with 3 tests: RuntimeError exit, OSError exit,
  successful startup with KeyboardInterrupt

**Key functions:**

`main()` — the CLI entry point. Now documents the full startup sequence and
the HackRF availability guard. Analogy: a car that checks the engine is
connected before turning the key, rather than dumping a error code on the
dashboard.

`broadcast()` inside `start_server()` — the SocketIO `scan_result` emitter.
The `fp.get(..., 0.0)` defaults mean the frontend always receives a number,
never null, for `signal_threshold_db` and `snr_margin_db`. Analogy: a safety
net that catches missing values before they reach the display.

**Deferred items:**
- `noise_floor` profile `signal_threshold_db` is still `10.0` while FM is now
  `12.0`. The comment says "reference -- same as FM" which is stale. Cosmetic.
- `except Exception` in `scanner.run()` exits with code 0 (pre-existing, no
  test coverage).
- `test_server_stats.py` strict dict equality is fragile -- future field
  additions will break it (pre-existing).

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None -- all changes are startup guard, field defaults, and
  threshold tuning. All RX-only.

**Test counts:** (see AGENTS.md for latest totals)

---

### Phase 11 — Per-Band Signal Thresholds + All-Bands Sweep ✓ DONE

**What:** Replaced the single global `SIGNAL_THRESHOLD_DB` (24.0 dB fallback) with
per-band thresholds stored in `BAND_PROFILES` and read live by the scan loop. Each
band now has its own threshold tuned to its typical signal strength in Adelaide.
The `diagnose_threshold.py` tool was rewritten from a single-FM-band script into a
permanent all-bands sweep tool with a `--band` flag for targeted runs.

**Why:** A single threshold cannot work well across all bands. FM broadcast at 98 MHz
is extremely strong (SNR 40+ dB), while ADS-B at 1090 MHz with a telescopic whip
antenna may only produce SNR 4-6 dB. A 24 dB threshold calibrated for FM misses
ADS-B entirely. Per-band thresholds ensure every band detects signals at its own
noise floor level.

The scan loop now reads `signal_threshold_db` from `shared_state.current_band`
before each fingerprint call, so switching bands via the dashboard automatically
applies the correct threshold -- no restart needed.

**Files changed:**
- `dashboard/shared_state.py` -- added `signal_threshold_db` key to every entry in
  `BAND_PROFILES`: fm_broadcast 10.0, aviation 6.0, acars 6.0, aprs 5.0, ism 5.0,
  adsb 4.0, noise_floor 10.0. Comments explain per-band rationale.
- `core/pipeline/features.py` -- `fingerprint_spectrum()` gains optional
  `signal_threshold_db: float | None = None` parameter; falls back to module-level
  `SIGNAL_THRESHOLD_DB` (24.0 dB) when not provided; returns two new keys:
  `signal_threshold_db` (the effective threshold used) and `snr_margin_db`
  (snr_db minus effective threshold).
- `core/pipeline/scanner.py` -- `_scan_loop()` reads `signal_threshold_db` from
  `shared_state.current_band` and passes it to `fingerprint_spectrum()`.
- `dashboard/server.py` -- `broadcast()` includes `signal_threshold_db` and
  `snr_margin_db` in the `scan_result` payload.
- `dashboard/frontend/src/hooks/useSocket.js` -- added `signal_threshold_db` and
  `snr_margin_db` to `INITIAL_AI_REASONING` and `scan_result` handler.
- `dashboard/frontend/src/App.jsx` -- Signal Details panel shows two new rows:
  THRESHOLD (effective threshold in dB) and SNR MARGIN (green when >= 0 dB,
  amber when < 0 dB).
- `tools/diagnose_threshold.py` -- complete rewrite: now sweeps all 6 AU-legal
  bands with `BAND_SWEEP` list; `--band` flag for single-band sweep; prints
  per-band recommendations and a summary table; no longer a "delete after use"
  tool.
- `tests/core/test_fft_features.py` -- 4 new tests for optional threshold param
  (fallback, override, positive margin, negative margin).
- `tests/dashboard/test_shared_state.py` -- 1 new test asserting
  `signal_threshold_db` presence in every BAND_PROFILES entry.
- `tests/tools/test_diagnose_threshold.py` -- new file with 2 smoke tests
  (sweep_band recommendation, BAND_KEYS coverage).
- `dashboard/frontend/src/tests/useSocket.test.js` -- updated for new fields.

**Key functions:**

`fingerprint_spectrum(psd_result, signal_threshold_db=None)` -- extracts spectral
features from a PSD. The optional `signal_threshold_db` override lets the scan loop
pass a per-band threshold; when omitted, the module-level 24.0 dB fallback applies.
Returns `signal_threshold_db` (effective threshold) and `snr_margin_db` (SNR minus
threshold -- positive means the peak SNR exceeds the detection threshold).
Analogy: a hearing test where each ear is tested at its own comfortable volume,
rather than blasting both ears at the same level.

`ScanRunner._scan_loop()` -- now reads `signal_threshold_db` from
`shared_state.current_band` before each fingerprint call. The threshold is
snapshot-locked (via `current_band_lock`) to avoid races with band-switch commands.
Analogy: the scanner adjusts its sensitivity dial automatically when you switch
bands on the dashboard.

`diagnose_threshold.sweep_band(band)` -- captures IQ samples at a band's frequency
and gain settings, then sweeps 10 threshold candidates (3-27 dB). For each
candidate it computes `fingerprint_spectrum()` and records the resulting bandwidth.
Returns the threshold whose bandwidth is closest to the band's expected signal
width. Analogy: a TV repairman adjusting the contrast dial until the picture
is clearest -- but doing it systematically across every channel.

**Deferred items:**
- Per-band thresholds are provisional values from the `diagnose_threshold.py` sweep.
  Live testing with `--band` on each frequency is needed to confirm they produce
  correct occupied_bins and bandwidth_hz readings.
- `SIGNAL_THRESHOLD_DB` (24.0 dB) module-level fallback is retained for any
  code path that calls `fingerprint_spectrum()` without a threshold override.
  This fallback is intentionally conservative (high) -- it prevents false positives
  in edge cases but may miss weak signals.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None -- all changes are RX-only threshold tuning and display

**Test counts:** (see AGENTS.md for latest totals)

---

### Stream Reset Retry + Crosshair Labels (standalone bug-fix) ✓ DONE

**What:** Three fixes discovered during live testing:

1. **HackRF readSamples stream reset on timeout** -- When `readStream()` returns
   SoapySDR error code -4 (timeout), the previous code performed a bare `time.sleep`
   retry with no stream reset. This left the SoapySDR stream in a stale state, and
   the retry would hit the same timeout again. The fix deactivates and reactivates
   the stream (`deactivateStream` + `activateStream`) before retrying, which resets
   the USB transfer pipeline. A `logger.warning` with the current frequency is
   emitted so operators can see when the hardware is struggling. The retry is
   limited to one attempt -- if the reset also fails, a `RuntimeError` is raised.

   **Why:** SoapySDR timeout (-4) means the HackRF did not deliver samples within
   the 10-second deadline. This can happen when switching bands, when USB bandwidth
   is saturated, or when the HackRF firmware is temporarily unresponsive. A stream
   reset clears the stale transfer state. A bare sleep retry does not.

2. **WaterfallPanel crosshair frequency label** -- The waterfall canvas crosshair
   (drawn by `WaterfallStrip` when `singleBand` is true) now renders a frequency
   label (e.g. "1090.125 MHz") next to the dashed line. Previously the crosshair
   was a plain dashed line with no indication of what frequency it pointed at.

   **Why:** Users clicking the waterfall canvas in singleBand mode see a crosshair
   but had no way to read the exact frequency without looking at the spectrometer
   bar. The label provides at-a-glance frequency context.

3. **SpectrometerBar frequency label left-edge clamp** -- The `labelX` calculation
   in the SpectrometerBar canvas `useEffect` now uses `Math.max(4, ...)` to clamp
   the horizontal position of the frequency label. Previously, labels at the far
   left edge of the canvas could clip off the left side of the visible area.

   **Why:** When the crosshair is within a few pixels of the left edge, the label
   text extends past `x = 0` and becomes partially invisible. Clamping to a minimum
   of 4 pixels keeps the label readable.

**Files changed:**
- `core/device/hackrf_rx.py` -- `read_samples()` stream-reset retry: deactivate,
  50 ms sleep, reactivate, 100 ms settle; `logger.warning` with frequency; retry
  limited to one attempt; docstring updated with timeout retry paragraph
- `dashboard/frontend/src/components/WaterfallPanel.jsx` -- added frequency label
  rendering in the crosshair `useEffect` (format: `{freq.toFixed(3)} MHz`)
- `dashboard/frontend/src/components/SpectrometerBar.jsx` -- `Math.max(4, ...)`
  clamp on `labelX` in canvas drawing `useEffect`
- `tests/core/test_hackrf_rx.py` -- new test file with 2 tests: stream-reset on
  timeout, RuntimeError after failed retry

**Key functions:**

`HackRFReceiver.read_samples(num_samples)` -- captures IQ samples from the HackRF.
If SoapySDR returns a timeout (-4), it resets the stream (deactivate + reactivate)
and retries once. Analogy: unplugging and replugging a USB device that stopped
responding, rather than just waiting longer.

`WaterfallStrip` crosshair `useEffect` -- draws a dashed vertical line and a
frequency label on the waterfall canvas when `singleBand` is true. The label is
formatted to 3 decimal places (e.g. "1090.125 MHz").

**Deferred items:**
- LOW-01: Crosshair label can still overlap the crosshair line at extreme left
  edge when `labelX` is clamped to 4. Cosmetic only, both WaterfallPanel and
  SpectrometerBar affected.
- Advisory: `config.freq_hz` is not in the WaterfallPanel useEffect dependency
  array. React remounts the component on band change via `key` prop, so this is
  correct but implicit.
- Advisory: `time.sleep` in `test_hackrf_rx.py` is not mocked (0.15 s per test).
  Acceptable for CI; could slow the suite if more stream-reset tests are added.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None -- stream reset and crosshair labels are RX-only / display-only

**Test counts:** (see AGENTS.md for latest totals)

---

### SpectrometerBar Cursor + SDR Status Fix (standalone bug-fix) ✓ DONE

**What:** Two fixes discovered during live testing:

1. **SpectrometerBar frequency cursor** — The spectrometer bar (thin frequency
   readout below the waterfall) previously called `focusFrequency()` on click,
   which retuned the HackRF to the clicked frequency. This was removed. Clicking
   the spectrometer bar now computes the raw frequency at the click position,
   stores it in a ref, and draws a dashed crosshair with a frequency label as
   a display-only cursor. No `focusFrequency()` call is made. The crosshair
   clears automatically when the band changes (via `focusedFreq` dependency).
   The `STRIP_CONFIGS` import was removed from SpectrometerBar since snapping
   logic is no longer needed.

   **Why:** The spectrometer bar click was redundant with the waterfall canvas
   click (which already has the singleBand guard from BUG-WATERFALL-CLICK).
   Making the spectrometer bar display-only avoids accidental retunes from
   users who just want to read a frequency value. The crosshair provides
   visual feedback (frequency label at cursor position) without side effects.

2. **SDR NOT RESPONDING window** — Changed the `_compute_hackrf_status()`
   timeout in `dashboard/server.py` from 30.0 seconds to 5.0 seconds. The
   previous 30-second window meant the dashboard showed "NOT RESPONDING" for
   up to 30 seconds after the last hardware error, even if the device had
   recovered. The 5-second window provides a more responsive status indicator
   while still masking transient glitches.

**Files changed:**
- `dashboard/frontend/src/components/SpectrometerBar.jsx` — replaced `handleClick`
  to be display-only (computes raw frequency, stores in `crosshairFreqRef`,
  increments `crosshairVersion` state); removed `STRIP_CONFIGS` import; added
  `useEffect` to clear crosshair on `focusedFreq` change; added frequency label
  drawing in canvas `useEffect`; added `crosshairVersion` to canvas `useEffect` deps
- `dashboard/server.py` — changed `_compute_hackrf_status()` NOT RESPONDING window
  from 30.0 to 5.0 seconds

**Key functions:**

`SpectrometerBar.handleClick(event)` — computes the raw frequency at the clicked
pixel position and draws a crosshair + frequency label. This is display-only; it
never calls `focusFrequency()`. Analogy: a ruler you place on a map to read a
coordinate -- it shows you where you are looking but does not move anything.

`_compute_hackrf_status()` — returns "NOT_RESPONDING" only within 5 seconds of
the last hardware error (previously 30 seconds). Analogy: a fire alarm that
stops wailing 5 seconds after the fire is out, not 30.

**Test counts:** (see AGENTS.md for latest totals)

---

### UI Cosmetic Fixes (standalone bug-fix) ✓ DONE

**What:** Two cosmetic fixes to the dashboard UI discovered during live testing:

1. **System Status grid — merged scan count and queue depth** — In `App.jsx`, the
   SYSTEM STATUS grid previously had SCAN COUNT and QUEUE DEPTH as separate grid
   cells. They have been merged into a single grid cell with two sub-columns displayed
   side by side. The queue depth value was also previously missing from the live UI
   (the data was emitted by the server but never rendered). Both values are now visible.
   The orphan `SystemStatsPanel.jsx` component was updated in parallel to stay in sync.

2. **AI Reasoning — timestamp repositioned** — The timestamp in the AI REASONING
   section was previously positioned via absolute positioning in the top-right corner
   of the panel, which could overlap with reasoning text on short messages. It has
   been moved above the reasoning text (left-aligned) with a 4px bottom margin gap.
   Both `AIReasoningPanel.jsx` (orphan component) and the inline code in `App.jsx`
   were updated so the fix is visible in the live UI.

3. **LLM inference time — Math.round()** — `llm_last_inference_ms` is now rounded
   via `Math.round()` before display, eliminating fractional millisecond display
   in the SYSTEM STATUS panel.

**Why:** The orphan components (`SystemStatsPanel.jsx`, `AIReasoningPanel.jsx`) were
already out of sync with the live `App.jsx` inline code. Both were updated so they
stay consistent for future integration, but the actual visible fix is in `App.jsx`.

**Files changed:**
- `dashboard/frontend/src/App.jsx` — merged scan count + queue depth into one grid
  cell with side-by-side sub-columns; added queue depth display (was missing);
  `Math.round()` on LLM INFERENCE; moved AI reasoning timestamp above text with
  `marginBottom: 4`
- `dashboard/frontend/src/components/SystemStatsPanel.jsx` — merged scan count +
  queue depth row; `Math.round()` on `llm_last_inference_ms` (kept in sync with
  App.jsx for future integration)
- `dashboard/frontend/src/components/AIReasoningPanel.jsx` — moved timestamp div
  above reasoning text with `marginBottom: 4` (kept in sync with App.jsx)

**Test counts:** 404/404 (313 pytest + 91 Vitest).

**Note:** No new tests were required — these are layout-only changes with no
behavioural logic.

---

### BUG-SPECTROMETER-CLICK: Spectrometer Bar Click Frequency Snap ✓ DONE

**What:** When clicking the spectrometer bar (the thin frequency readout below
the waterfall), the computed frequency did not always land on a canonical
`STRIP_CONFIGS` value. For example, clicking near 1090 MHz might produce
`1089998750` instead of `1090000000`. This caused the waterfall to freeze
because the `latestUpdate` lookup uses strict equality against `STRIP_CONFIGs`
canonical frequencies.

The fix exports `STRIP_CONFIGS` from `WaterfallPanel.jsx` (it was previously a
module-private `const`) and adds a snap-to-nearest-canonical step in
`SpectrometerBar.handleClick`. After computing the raw frequency from the click
position, the handler runs `STRIP_CONFIGS.reduce()` to find the closest canonical
value within the current band's config and uses that instead. The snap only fires
when the click is within 1 MHz of a known STRIP_CONFIG frequency — clicks far
from any band produce the raw value unchanged.

**Why:** The spectrometer bar and waterfall canvas share the same click-target
area. Without frequency snapping, any click that was even a few kHz off a
canonical value would retune the HackRF to a non-STRIP_CONFIG frequency, breaking
the strict-equality PSD lookup that the waterfall relies on. Snapping ensures
spectrometer clicks always land on a valid, recognised frequency.

**Files changed:**
- `dashboard/frontend/src/components/WaterfallPanel.jsx` — exported `STRIP_CONFIGS`
  (was `const`, now `export const`)
- `dashboard/frontend/src/components/SpectrometerBar.jsx` — imported `STRIP_CONFIGS`;
  added snap logic in `handleClick` using `STRIP_CONFIGS.reduce()` to find nearest
  canonical value; added JSDoc comment explaining the snap behaviour
- `dashboard/frontend/src/tests/SpectrometerBar.test.jsx` — 2 new tests for
  frequency snapping (snap within band, no snap outside band)

**Key functions:**

`SpectrometerBar.handleClick(event)` — reads the click's x position relative to
the canvas, computes a raw frequency, then snaps it to the nearest canonical
`STRIP_CONFIGS` value within 1 MHz. Prevents non-canonical frequencies from
reaching the waterfall's strict-equality lookup. Analogy: a dropdown autocomplete
that rounds your typed text to the nearest valid option.

**Test counts:** 416/416 (318 pytest + 98 Vitest).

---

### BUG-WATERFALL-SPEED: Redundant HackRF Retune Eliminated ✓ DONE

**What:** The ADS-B waterfall (1090 MHz) was updating at ~1 Hz instead of the
expected ~3 Hz. Root cause: every scan cycle called `device.set_center_frequency()`
regardless of whether the frequency had changed. At 1090 MHz, each retune round-trips
through libhackrf / SoapySDR and costs ~500 ms — nearly half the scan cycle budget.
Because the focus frequency does not change between cycles when monitoring a single
band, these retunes are pure overhead.

The fix adds a method-local `_last_tuned_hz` cache inside `_scan_loop()`. On each
iteration, the current `freq_hz` is compared against `_last_tuned_hz`. If they
match, `set_center_frequency()` is skipped entirely. The cache is reset
automatically when `set_focus_frequency()` changes the frequency (the scan loop
reads the new value on the next iteration and retunes once).

**Why:** At 1090 MHz the HackRF retune round-trip takes ~500 ms per call. The scan
cycle at that frequency is roughly 260 ms of sample acquisition + FFT, so a 500 ms
retune doubles the cycle time. Skipping the redundant retune restores the scan rate
from ~1 Hz to ~3 Hz — a threefold improvement in waterfall smoothness. The fix is
harmless at other frequencies too (FM broadcast, aviation VHF) where retune is
cheaper but still unnecessary when the frequency has not changed.

**Files changed:**
- `core/pipeline/scanner.py` — added `_last_tuned_hz: float | None = None` local
  variable in `_scan_loop()`; added `if freq_hz != _last_tuned_hz` guard around
  `device.set_center_frequency()`; updated docstring to document the frequency cache
- `tests/core/test_scanner.py` — added `test_scan_loop_skips_redundant_retune`
  (verifies `set_center_frequency` called once on first cycle, skipped on second
  when frequency unchanged)

**Key functions:**

`ScanRunner._scan_loop()` — now maintains a `_last_tuned_hz` local cache. The
retune guard is a simple inequality check: if the focus frequency has not changed
since the last iteration, the expensive `set_center_frequency()` call is skipped.
Analogy: you only retune the car radio when you change stations — not on every
rotation of the wheel.

**Test counts:** 416/416 (318 pytest + 98 Vitest).

---

### BUG-WATERFALL-CLICK: Waterfall Canvas Click Freeze ✓ DONE

**What:** In `singleBand={true}` mode, clicking the waterfall canvas computed a
focus frequency from the click pixel position:

```
const freq = config.freq_hz + (relativeX - 0.5) * SAMPLE_RATE_HZ
focusFrequency(Math.round(freq))
```

Any click except the exact pixel-centre produced a value like `1089753124` rather
than the STRIP_CONFIG canonical value `1090000000`. Two things broke simultaneously:

1. **Backend:** `focusFrequency()` emitted `set_focus_frequency` to the server, which
called `scanner.set_focus_frequency(1089753124)`. The HackRF retuned to that offset.
All subsequent `spectrum_update` events arrived with `center_freq_hz = 1089753124`.

2. **Frontend:** `WaterfallPanel`'s `latestUpdate` lookup uses strict equality:
```js
spectrumUpdates.find((u) => u.center_freq_hz === config.freq_hz)
```
`config.freq_hz` is `1090000000` (from `STRIP_CONFIGS`). The backend was sending
`1089753124`. The lookup never matched. `latestPsd` stayed `null`. `useWaterfall`
never fired. The waterfall froze.

**Fix:** Guarded the `focusFrequency()` call inside `handleCanvasClick` behind
`!singleBand`. The crosshair still draws in singleBand mode so users get visual
feedback, but the frequency is never retuned from the canvas. The only way to
change band in singleBand mode is via the band nav buttons, which always emit
exact `STRIP_CONFIGS` canonical frequencies.

**Files changed:**
- `dashboard/frontend/src/components/WaterfallPanel.jsx` — added `if (!singleBand)`
  guard around `focusFrequency()` in `handleCanvasClick`; added `singleBand` to the
  `useCallback` dependency array; added JSDoc comment explaining the guard
- `dashboard/frontend/src/tests/WaterfallPanel.test.jsx` — added two regression tests:
  `singleBand=true: clicking the canvas does NOT call focusFrequency` and
  `singleBand=false: clicking the canvas calls focusFrequency with a computed frequency`

**Test counts:** 413/413 (318 pytest + 95 Vitest).
- Note: 4 pytest failures in `test_ais_decoder.py` are pre-existing (missing `pyais`
  module in environment), not caused by this change.

**Deferred:**
- **BUG-WATERFALL-SPEED:** Suspected downstream symptom of BUG-WATERFALL-CLICK. The ADS-B
  band button and the waterfall canvas are visually adjacent, making an accidental
  canvas click easy immediately after switching bands. Needs live verification after
  this fix — if the ADS-B waterfall is still slow after deploying, investigate further.

---

### Spectrum Broadcast Decoupling ✓ DONE

**What:** Decoupled the `spectrum_update` SocketIO event from the AI classification
loop. Previously, `spectrum_update` was emitted inside `_emit_result()`, which only
ran after the LLM classifier finished — meaning the waterfall was gated by LLM
inference time (typically 1-2 seconds per scan). The waterfall update rate was
effectively bottlenecked at ~0.4 Hz instead of the full scan rate (~0.125 Hz per
frequency dwell, but without LLM stall it now updates every cycle).

The fix moves `_broadcast_spectrum_fn()` from `_emit_result()` (AI loop) into
`_scan_loop()`, immediately after `compute_psd()`. This means the waterfall
receives a new row as soon as the FFT completes, completely independent of the
AI pipeline. The LLM can take as long as it needs without affecting the waterfall.

A secondary fix: frequency bounds passed to `_broadcast_spectrum_fn` are now
derived from `psd["frequencies_hz"]` (the actual FFT frequency axis) instead of
a hardcoded `freq_hz +/- 1_000_000`. This ensures the waterfall's frequency
range always matches the real FFT output regardless of sample rate or FFT size.

**Why:** During live testing the waterfall was visibly stuttering — updates arrived
only after LLM inference completed, producing an uneven, jerky scroll. Decoupling
the two data paths (waterfall vs classification) restores smooth waterfall rendering
at the full scan rate.

**Files changed:**
- `core/pipeline/scanner.py` — moved `_broadcast_spectrum_fn` call from `_emit_result`
  to `_scan_loop` (immediately after `compute_psd`); wrapped in isolated try/except
  so broadcast failures never block the AI pipeline; frequency bounds now use actual
  FFT axis (`psd["frequencies_hz"]`) instead of hardcoded +/- 1 MHz
- `tests/core/test_scanner.py` — added `test_scan_loop_broadcasts_spectrum` (verifies
  `_broadcast_spectrum_fn` called from `_scan_loop` with correct args) and
  `test_emit_result_does_not_broadcast_spectrum` (verifies `_broadcast_spectrum_fn`
  NOT called from `_emit_result`)

**Key functions:**

`ScanRunner._scan_loop()` — the capture-and-broadcast thread. Now owns both IQ
capture and spectrum broadcast. The broadcast is isolated via its own try/except
so that a failure (e.g. no connected dashboard) does not prevent fingerprint
queuing for the AI pipeline. Analogy: the waterfall is now a direct pipe from
the FFT to your screen, rather than waiting for the LLM to finish thinking first.

`ScanRunner._emit_result()` — now only prints the classification to the terminal
and emits `scan_result` (classification data) to the dashboard. No longer involved
in spectrum waterfall updates.

**Test counts:** 404/404 (313 pytest + 91 Vitest).

---

### Phase 9F-CPR — ADS-B CPR Pair Accumulator ✓ DONE

**What:** Upgraded the ADS-B position decoder from single-frame `position_with_ref()` to `pyModeS.PipeDecoder` — a stateful, per-ICAO CPR pair accumulator. PipeDecoder buffers even/odd CPR frames per ICAO, pairs them within a 10-second window, and resolves positions globally (no fixed reference point required). Stale per-ICAO state is evicted after 300 seconds of silence. A flush() cycle every 5 seconds releases bootstrap-held positions for aircraft that generate fewer than _BOOTSTRAP_K=5 pairs.

**Why:** Single-frame CPR decoding via `position_with_ref()` gives accurate positions only within ~180 NM of the reference point (Adelaide). Beyond that, positions are mathematically valid but geographically wrong. CPR pair accumulation decodes positions globally, matching how production ADS-B receivers (dump1090, FlightAware, etc.) operate. For Adelaide reception, all receivable aircraft are within 180 NM, but pair accumulation also eliminates reference bias and is more accurate.

**Files changed:**
- `modules/adsb/decoder.py` — PipeDecoder replaces stateless pms_decode; FLUSH_INTERVAL_SEC=5.0; optional timestamp param; flush() method
- `modules/adsb/constants.py` — ADELAIDE_LAT/ADELAIDE_LON comments updated
- `tests/modules/test_adsb_decoder.py` — position tests rewritten for pair-based accumulation

**Key functions:**

`AdsbDecoder.decode(raw_hex, timestamp=None)` — validates a 28-char hex string via PipeDecoder (CRC, DF17/DF18 check, typecode range), then extracts structured fields (ICAO, callsign, altitude, position, groundspeed, track, vertical_rate). Uses stateful CPR pair accumulation for global position decoding without a fixed reference. Automatically flushes the pipe every 5 seconds to release bootstrap-held positions. Analogy: instead of guessing your exact location from a single GPS ping relative to a known landmark, the CPR accumulator waits for two pings and triangulates your position precisely — anywhere on Earth.

`AdsbDecoder.flush()` — manually releases bootstrap-held positions. Intended for unit tests and graceful shutdown.

**Test counts:** 364/364 (308 pytest + 56 Vitest).

---

### Phase 10 — Dashboard UI Redesign ✓ DONE

**What:** Complete redesign of the dashboard frontend from a vanilla JS grid layout to a
professional React application with cyberpunk styling. The new layout uses a three-row
structure: header bar, top half (waterfall + signal details), bottom half (system status /
signal history + AI reasoning / decoded signals). All panels are reorganized for better
information density and readability.

**Why:** The original grid-based layout was functional but lacked the visual polish and
information hierarchy needed for a professional RF monitoring tool. The redesign puts
the most important information (waterfall, signal details) in the top half and supporting
information (history, decoded signals) in the bottom half.

**Files changed:**
- `dashboard/frontend/src/App.jsx` — complete rewrite with three-row layout, band navigation,
  custom frequency input, system status cards, signal history table, AI reasoning panel,
  and decoded signals sub-panels (ADS-B, ACARS, AIS)
- `dashboard/frontend/src/theme/cyberpunk.css` — expanded theme with background layers, border
  colours, waterfall colour ramp stops, and font variables
- `dashboard/frontend/src/components/WaterfallPanel.jsx` — added `singleBand` prop for
  focused-mode waterfall display
- `dashboard/frontend/src/hooks/useSocket.js` — added `aisVessels` alias, `focusFrequency`
  optimistic update
- `dashboard/frontend/src/tests/WaterfallPanel.test.jsx` — updated for 6-band configuration
- `dashboard/frontend/src/tests/App.test.jsx` — updated for new layout
- `dashboard/frontend/src/tests/SignalDetailsFreeze.test.jsx` — new test for AI reasoning
  freeze display
- `dashboard/frontend/src/tests/AdsbTunedState.test.jsx` — new test for ADS-B three-state
  sub-panel logic

**Test counts:** 395/395 (308 pytest + 87 Vitest).

---

### Phase 10-Hotfix — Dashboard Live Testing Fixes ✓ DONE

**What:** Fixed 5 bugs discovered during live testing of the Phase 10 dashboard:

1. **Waterfall missing bands** — Added Aviation (127 MHz) and ACARS (129.125 MHz) to
   `STRIP_CONFIGS` in `WaterfallPanel.jsx`. The 6-band configuration now matches all
   AU-legal passive RX frequencies.
2. **Stale spectrum display** — Changed `spectrumUpdates.find()` from `[...].reverse().find()`
   to `find()` because `useSocket.js` prepends new entries (newest-first), so `find()`
   returns the latest match without copying the array.
3. **Sub-panel tuned states** — Added three-state logic for ADS-B, ACARS, and AIS sub-panels:
   (a) tuned + has data → render panel, (b) tuned + no data → "Listening on X...",
   (c) not tuned → clickable red "▸ TUNE TO X..." prompt.
4. **Font size too small** — Changed `body { font-size: 14px; }` in `cyberpunk.css` and
   changed `--font-display` to `'Share Tech Mono', ...` (Press Start 2P is now used only
   for the MIMIR logo header via inline style).
5. **Band button tuning** — Verified `focusFrequency()` is optimistic (local `setState`
   before `socket.emit`), ensuring immediate UI feedback.

**Also fixed during review:**
- `AisVesselPanel.jsx` — corrected AIS frequency display from 162.000 MHz to 161.975 MHz
  (AU Channel A primary frequency).
- `AGENTS.md` — updated font specification to reflect the new design.

**Test counts:** 395/395 (308 pytest + 87 Vitest).

---

### Phase 10-Fix2 — Waterfall Performance + Signal Details Missing Fields ✓ DONE

**What:** Fixed two issues discovered during live testing:

1. **Waterfall canvas performance** — Replaced CPU-based `getImageData` + pixel-shift +
   `putImageData` scroll with GPU-based `ctx.drawImage(canvas, 0, 1)` for scrolling,
   plus a single-row `createImageData(width, 1)` for the new top row only. The old
   approach read ~1.8MB of pixel data into JS every frame, manipulated it in CPU,
   then wrote it back. The new approach offloads the scroll to the GPU and only
   computes the 1-pixel top row in JS.
2. **Signal Details missing fields** — Added fingerprint fields from `scan_result.fingerprint`
   to the SocketIO `scan_result` payload: `peak_power_db`, `snr_db`, `bandwidth_hz`,
   `spectral_flatness`. These fields were previously computed by the backend pipeline
   but never emitted to the frontend, so the Signal Details panel showed "---" for
   POWER, SNR, BANDWIDTH, and SPECTRAL FLATNESS.

**Files changed:**
- `dashboard/frontend/src/hooks/useWaterfall.js` — GPU scroll via drawImage, single-row
  createImageData/putImageData, endBin clamp with Math.min for safety
- `dashboard/server.py` — extended `broadcast()` data dict with fingerprint fields via
  `fp.get()` (null-safe, no default)
- `dashboard/frontend/src/hooks/useSocket.js` — extended `INITIAL_AI_REASONING` and
  `aiReasoning` builder with `peak_power_db`, `snr_db`, `bandwidth_hz`, `spectral_flatness`
- `dashboard/frontend/src/App.jsx` — synchronised `INITIAL_AI_REASONING` with useSocket.js
  (added the four new fingerprint fields)
- `dashboard/frontend/src/tests/useWaterfall.test.js` — updated for drawImage + createImageData,
  removed full-canvas getImageData assertion
- `dashboard/frontend/src/tests/useSocket.test.js` — updated initial state, added fingerprint
  field propagation test
- `tests/dashboard/test_server_stats.py` — updated expected broadcast payload to include
  fingerprint fields

**Test counts:** 396/396 (308 pytest + 88 Vitest).

---

### Phase 10-Fix3 — Band Grouping, ADS-B Threshold, Waterfall Gap, Default Focus ✓ DONE

**What:** Fixed four issues discovered during live testing of the Phase 10 UI redesign:

1. **Band button grouping** — Replaced the flat BANDS array with a three-category
   `BAND_GROUPS` layout in `App.jsx`. Categories: BROADCAST (FM), AVIATION BAND
   (AVIATION, ACARS, ADS-B), DATA / IoT (APRS, ISM). Each category shows a 9px
   uppercase label above its buttons. Vertical dividers separate the groups.
   Nav bar height increased to 48px to accommodate the two-row layout.
2. **ADS-B preamble threshold** — Reduced `PREAMBLE_THRESHOLD` from `2.0` to `1.5` in
   `modules/adsb/constants.py` after live testing showed no ADS-B decodes at 2.0
   (confirmed aircraft overhead were missed). The 1.5 value is the midpoint of the
   validated range 1.2–2.0 for HackRF One with telescopic whip antenna.
3. **Waterfall gap eliminated** — Added `hideSidebar` prop to `WaterfallStrip` in
   `WaterfallPanel.jsx`. When `singleBand=true` (current mode), the 110px label sidebar
   is hidden, giving the canvas the full available width. The `WATERFALL_LABEL_WIDTH`
   export changed from `110` to `0`, and `SpectrometerBar.jsx` uses it for its left
   spacer, keeping the spectrometer bar aligned with the waterfall canvas.
4. **Default focus frequency** — Changed `focusedFreq` default from `null` to
   `98000000` (FM broadcast) in `useSocket.js`. On first page load, the dashboard
   immediately shows the FM broadcast spectrum instead of waiting for the user to
   click a band button. This aligns with the single-frequency focus mode.

**Files changed:**
- `dashboard/frontend/src/App.jsx` — `BAND_GROUPS` constant, grouped nav bar layout
  (48px height, vertical dividers, 9px category labels), ADS-B badge preserved
- `modules/adsb/constants.py` — `PREAMBLE_THRESHOLD` 2.0 → 1.5, docstring updated
  with validated range and live-testing note
- `dashboard/frontend/src/components/WaterfallPanel.jsx` — `WATERFALL_LABEL_WIDTH` 110 → 0,
  `hideSidebar` prop on `WaterfallStrip`, conditional label rendering
- `dashboard/frontend/src/hooks/useSocket.js` — `focusedFreq` default 98000000,
  `focusedFreqRef` default 98000000
- `dashboard/frontend/src/tests/App.test.jsx` — updated for grouped nav bar
- `dashboard/frontend/src/tests/WaterfallPanel.test.jsx` — updated for hideSidebar
- `dashboard/frontend/src/tests/useSocket.test.js` — updated for 98000000 default
- `dashboard/frontend/src/tests/SpectrometerBar.test.jsx` — updated for 0px width

**Test counts:** 402/402 (311 pytest + 91 Vitest).

---

### Phase 10-Fix4 — Spectral Flatness, Chroma Distance, Waterfall Alignment ✓ DONE

**What:** Fixed four issues discovered during live testing (and one bonus fix):

1. **Spectral Flatness phantom field** — Added `spectral_flatness` (Wiener entropy)
   computation to `core/pipeline/features.py fingerprint_spectrum()`. Formula:
   `geometric_mean(linear_power) / arithmetic_mean(linear_power)`. Clamped to [0.0, 1.0].
   0.0 = pure tone, 1.0 = white noise. Previously the field was referenced in the
   LLM classifier but never computed, so it always defaulted to 0.0.
2. **Chroma Distance not wired to frontend** — Threaded `chroma_distance` from the
   ChromaDB nearest-neighbour query through the entire pipeline: `scanner.py` adds it
   to the fingerprint dict, `server.py` broadcasts it, `useSocket.js` surfaces it in
   `aiReasoning`, and `App.jsx` displays it in the Signal Details panel.
3. **Waterfall / SpectrometerBar alignment** — Exported `WATERFALL_LABEL_WIDTH` constant
   from `WaterfallPanel.jsx` and imported it in `SpectrometerBar.jsx`. Added a left spacer
   div so the spectrometer bar's canvas starts at the same x offset as the waterfall's
   canvas above it. Fixed click handler to correctly compute frequency from canvas-relative
   coordinates (no double offset).
4. **React StrictMode double rendering** — Removed `<React.StrictMode>` wrapper from
   `main.jsx` to eliminate intentional double-mounting of components, which was causing
   duplicate socket listener registration and double canvas renders per frame.

**Files changed:**
- `core/pipeline/features.py` — Wiener entropy computation, clamped to [0.0, 1.0], added
  to empty-PSD early-return dict, docstring updated
- `core/pipeline/scanner.py` — `chroma_distance` extracted from `neighbours_list[0]` and
  added to `item["fingerprint"]` before `ScanResult` construction
- `dashboard/server.py` — `chroma_distance` added to `broadcast()` payload via `fp.get()`
- `dashboard/frontend/src/hooks/useSocket.js` — `chroma_distance` added to
  `INITIAL_AI_REASONING` and `aiReasoning` builder
- `dashboard/frontend/src/App.jsx` — `chroma_distance` added to `INITIAL_AI_REASONING`
- `dashboard/frontend/src/components/WaterfallPanel.jsx` — exported `WATERFALL_LABEL_WIDTH = 110`
- `dashboard/frontend/src/components/SpectrometerBar.jsx` — imported constant, added left
  spacer, fixed click handler (canvas-relative coordinates only)
- `dashboard/frontend/src/main.jsx` — removed `<React.StrictMode>` wrapper
- `tests/core/test_fft_features.py` — 4 new spectral_flatness assertions (key presence, range,
  tone low, noise high)
- `tests/core/test_scanner.py` — chroma_distance assertion in AI loop test
- `tests/dashboard/test_server_stats.py` — chroma_distance in expected broadcast payload
- `dashboard/frontend/src/tests/useSocket.test.js` — chroma_distance in expected objects
- `dashboard/frontend/src/tests/SpectrometerBar.test.jsx` — spacer width, canvas flex, and
  click handler frequency tests

**Test counts:** 402/402 (311 pytest + 91 Vitest).

---

### Phase 9C-Threshold — Gain and Threshold Calibration ✓ DONE

**What:** Calibrated `SIGNAL_THRESHOLD_DB` from 10.0 to 24.0 dB and aligned all
production gain defaults across the codebase to lna=24 dB / vga=26 dB for the
telescopic whip SMA antenna (~1 GHz optimised). The previous defaults (lna=0/vga=0)
were calibrated for a different antenna with better FM coupling. The new telescopic
whip has poor coupling at FM wavelengths (~3 m), requiring gain to compensate.
Threshold was found via `tools/diagnose_threshold.py` sweep: 24 dB produces
196,289 Hz bandwidth, closest to the 200 kHz target for an FM broadcast channel.

**Why:** After switching to the telescopic whip antenna, the previous zero-gain
settings produced weak signals that fell below the detection threshold. All gain
defaults and `SIGNAL_THRESHOLD_DB` needed recalibration for the new antenna.
ADC saturation was confirmed safe at lna=24/vga=26 with live Adelaide FM signals.

**Files changed:**
- `core/pipeline/features.py` — `SIGNAL_THRESHOLD_DB` 10.0 -> 24.0, docstring updated with calibration metadata
- `config/mimir.yaml` — hardware/scanner gain values updated (lna=24, vga=26), inline comments updated
- `core/config/loader.py` — `MimirConfig` dataclass defaults (lna 0.0 -> 24.0, vga 0.0 -> 26.0), docstring added
- `core/device/hackrf_rx.py` — `DEFAULT_LNA_GAIN_DB` 0 -> 24, `DEFAULT_VGA_GAIN_DB` 0 -> 26, class comments updated
- `dashboard/shared_state.py` — `BAND_PROFILES` fm_broadcast gains (0 -> 24/26), comments updated
- `tools/diagnose_threshold.py` — comment updated (constants already correct)
- `core/pipeline/capture.py` — `capture_and_save()` docstring updated
- `tests/core/test_fft_features.py` — new `TestSignalThresholdDb`
- `tests/core/test_config_loader.py` — new `TestMimirConfigDefaults`
- `tests/dashboard/test_shared_state.py` — new `TestBandProfiles`

**Key functions:**

`SIGNAL_THRESHOLD_DB` (24.0 dB) — the dB value above the estimated noise floor
that marks a frequency bin as "signal present". Too low = noise counted as signal
(false positive). Too high = real signals missed (false negative). Calibrated for
the telescopic whip SMA antenna at lna=24/vga=26. Analogy: squelch on a
walkie-talkie.

`MimirConfig` dataclass defaults — the Python-level default gain values used when
`MimirConfig` is constructed directly (bypassing YAML loading). Must match
`config/mimir.yaml` to prevent silent gain mismatches.

`BAND_PROFILES` — per-band gain settings for the dashboard waterfall. Only
fm_broadcast is calibrated for the telescopic whip. Aviation and ADS-B need
revalidation in future phases.

**Deferred items:**
- `tools/calibrate_thresholds.py` still contains stale gain values (lna=32/vga=40)
- `tools/diagnose_fingerprints.py` still contains stale gain values
- Aviation and ADS-B band profiles need revalidation with the new antenna

**Test counts:** 354/354 (298 pytest + 56 Vitest) + 3 new test classes.

---

### Phase 9F — ADS-B Decoder Subscriber ✅ DONE

**What:** Implemented a complete ADS-B (Automatic Dependent Surveillance-Broadcast)
decoder as a subscriber on Mimir's shared IQ bus. ADS-B is a Mode S extended squitter
protocol where aircraft broadcast their position, altitude, callsign, and velocity on
1090 MHz. The decoder includes amplitude-only preamble detection, Pulse Position
Modulation (PPM) bit extraction at 2 MSa/s, CRC validation, and field extraction
via pyModeS. Decoded aircraft messages are broadcast via SocketIO to a new ADS-B
panel in the dashboard.

**Why:** ADS-B at 1090 MHz is one of the strongest and most information-rich aviation
signals receivable in Adelaide. Unlike ACARS and AIS, ADS-B carries structured
aircraft telemetry (position, altitude, speed, callsign) that the LLM classifier
can use directly. A pure-Python demodulator avoids the HackRF single-process
constraint — the same architecture as ACARS (9D) and AIS (9E).

**Files changed:**
- `modules/adsb/__init__.py` — package exports for AdsbSubscriber, AdsbDemodulator, AdsbDecoder, AdsbMessage, and constants
- `modules/adsb/constants.py` — AU ADS-B frequency (1090 MHz), Adelaide reference position for CPR decoding, preamble detection parameters, message length constants
- `modules/adsb/message.py` — `AdsbMessage` dataclass (icao, callsign, altitude, lat/lon, groundspeed, track, vertical_rate, raw_hex, timestamp)
- `modules/adsb/demodulator.py` — `AdsbDemodulator` (vectorised preamble detection via amplitude ratio, PPM bit extraction at 2 MSa/s, hex string packing)
- `modules/adsb/decoder.py` — `AdsbDecoder` (pyModeS decode with CPR pair accumulation via PipeDecoder, CRC validation, field extraction into AdsbMessage)
- `modules/adsb/subscriber.py` — `AdsbSubscriber` (queue + daemon thread, frequency filter at 1090 MHz +/- 2 MHz, demodulate-decode-broadcast pipeline)

**Key functions:**

`AdsbDemodulator.demodulate(iq_chunk)` — scans the amplitude envelope of raw IQ
samples for the 8 us ADS-B preamble (high/low sample ratio >= 2.0), then extracts
112 PPM bits. Returns a list of 28-character hex strings, one per candidate frame.
Analogy: a barcode scanner looking for the right pattern of wide and narrow bars.

`AdsbDecoder.decode(raw_hex)` — validates a 28-char hex string via pyModeS (CRC,
DF17/DF18 check, typecode range), then extracts structured fields (ICAO, callsign,
altitude, position, groundspeed, track, vertical_rate). Uses stateful CPR pair
accumulation via PipeDecoder for global position decoding. **Upgraded in Phase 9F-CPR.**

**Test counts:** 354/354 (298 pytest + 56 Vitest).

---

### Phase 9C — ACARS Decoder Infrastructure ✓ DONE

**What:** Added ACARS (Aircraft Communications Addressing and Reporting System)
decoder infrastructure. ACARS is a VHF data link between aircraft and ground stations
used for flight plans, weather, and maintenance messages. Added `acars` preset to
`config/mimir.yaml` at 129.125 MHz (AU primary). Added `129.125 MHz` to the scanner
frequencies list. Updated `docs/au-legal-reference.md` with ACARS legal reference.
Added a bash guard to `setup.sh` so it can be safely sourced without executing `main()`.

**Why:** ACARS is an active Australian aviation band signal. Mimir needs to scan and
classify it. The setup script guard is a safety improvement for development workflows
where `source setup.sh` might be used to load helper functions.

**Files changed:**
- `setup.sh` — added `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then main; fi` guard
- `config/mimir.yaml` — added `acars` preset at 129125000 Hz, added 129125000 to `scanner.frequencies_hz`
- `docs/au-legal-reference.md` — added ACARS section (129.125 / 130.025 MHz)
- `tests/setup/test_setup_sh.sh` — new bash mock test suite (11 tests, stubs all side-effect commands)

**Analogy:** Adding a new station to your car radio presets — now ACARS is tuned in
and ready to listen.

**Test counts:** 279/279 (223 pytest + 56 Vitest).

---

### Phase 9D — ACARS Pure-Python Decoder Subscriber ✓ DONE

**What:** Implemented a complete ACARS decoder as a subscriber on Mimir's shared IQ
bus. No new process, no second device open — everything runs inside the existing
Python process as a daemon thread. The decoder includes AM envelope detection,
decimation to audio rate, FFSK tone detection (1200/2400 Hz), NRZI decode, frame
sync (preamble + SYN SYN SOH), ARINC 618 field parsing, and CRC-16 validation.
Decoded messages are broadcast via SocketIO to a new ACARS panel in the dashboard.

**Why:** The HackRF cannot be opened by two processes simultaneously. The existing
`acarsdec` binary cannot be used as a subprocess because it would conflict with
Mimir's SoapySDR device handle. A pure-Python decoder running inside Mimir's process
is the only viable architecture for live ACARS decoding.

**Files changed:**
- `modules/acars/__init__.py` — package exports
- `modules/acars/constants.py` — AU ACARS frequencies (129.125 / 130.025 MHz), baud rate, tone constants
- `modules/acars/message.py` — `AcarsMessage` dataclass
- `modules/acars/demodulator.py` — `AcarsDemodulator` (AM envelope, decimation, tone detection, NRZI)
- `modules/acars/decoder.py` — `AcarsDecoder` (frame sync, field parsing, CRC-16 CCITT)
- `modules/acars/subscriber.py` — `AcarsSubscriber` (queue + daemon thread, frequency filter, pipeline)
- `core/pipeline/scanner.py` — `register_iq_subscriber()` + broadcast in `_scan_loop`
- `dashboard/server.py` — `emit_acars_message()` SocketIO emitter
- `scan.py` — instantiate `AcarsSubscriber`, register with `ScanRunner`, stop in finally block
- `dashboard/frontend/src/hooks/useSocket.js` — handle `acars_message` events, keep last 20
- `dashboard/frontend/src/components/AcarsMessagePanel.jsx` — new scrolling table panel
- `dashboard/frontend/src/App.jsx` — add ACARS panel to grid layout
- `tests/modules/test_acars_message.py` — dataclass field tests
- `tests/modules/test_acars_demodulator.py` — synthetic signal DSP tests
- `tests/modules/test_acars_decoder.py` — frame sync, parsing, CRC tests
- `tests/modules/test_acars_subscriber.py` — lifecycle, queue, frequency filter, scan loop integration
- `pyproject.toml` — added `scipy>=1.12.0` dependency
- `docs/wiki.md` — updated phase tracker

**Analogy:** Adding a second radio inside the same receiver. The main receiver
still does its job (spectrum scanning), but now a second circuit listens to the
same audio and decodes the digital messages hidden in it.

---

### pre-9C-seed-autowipe — ChromaDB Seed Auto-Wipe ✓ DONE

**What:** Replace the interactive `check_duplicates()` function in `tools/seed_chromadb.py`
with an automatic `wipe_collection()` that unconditionally deletes and recreates the
ChromaDB collection before each seed run. The old function prompted the user with
an `[y/N]` question; the new one always wipes, eliminating the possibility of
accidental duplicate records (the 800->1600 problem observed during Phase 9B-Hotfix).

**Why:** During the Phase 9B-Hotfix re-seed, running the script without answering
the prompt (or answering incorrectly) produced duplicate records — the collection
grew from 800 to 1600. An automatic wipe is safer: every seed run starts clean.

**Files changed:**
- `tools/seed_chromadb.py` — removed `check_duplicates()`, added `wipe_collection(store)`,
  updated `main()` to wipe then re-create SignalStore (old instance's collection handle
  is stale after deletion). Module docstring now warns that re-running destroys all data.
- `tests/tools/test_seed_chromadb.py` — removed 3 interactive prompt tests, added 4
  wipe-and-reseed tests (populated store, empty store, no doubling, nonexistent collection).

**Key function:**

`wipe_collection(store)` — deletes the existing ChromaDB collection so the seed
run starts from a clean slate. Catches `Exception` broadly because ChromaDB raises
different exception types depending on backend version (`ValueError`, `NotFoundError`,
or others). First-run case (collection does not exist) is also handled.

**Analogy:** Formatting a memory card before loading new photos. You always start
empty so there are never old and new files mixed together.

**Test counts:** 278/278 (222 pytest + 56 Vitest).

---

### pre-9C-gain-defaults — Gain Defaults Housekeeping ✓ DONE

**What:** Align four source files to the settled gain configuration of
`lna=0, vga=0, amp=False`. The old defaults (LNA 16 dB, VGA 20 dB) were
left over from early development and were misleading — Adelaide FM broadcast
is extremely strong, and those values risked ADC saturation. Phase 9B-Hotfix
already set `config/mimir.yaml` to `lna=0, vga=0`, but the Python defaults
and band profiles still carried the old values.

**Why:** When a new `MimirConfig` was constructed directly (bypassing YAML
loading), or when `capture_and_save()` ran without explicit gain arguments,
it silently applied 16/20 dB — too much gain for FM, producing clipped
samples. Making the Python defaults match the YAML eliminates this latent
inconsistency.

**Files changed:**
- `core/config/loader.py` — `MimirConfig` dataclass: `lna_gain_db` 16.0→0.0, `vga_gain_db` 20.0→0.0
- `core/device/hackrf_rx.py` — `DEFAULT_LNA_GAIN_DB` 16→0, `DEFAULT_VGA_GAIN_DB` 20→0
- `core/pipeline/capture.py` — docstring updated to reflect LNA 0 dB / VGA 0 dB with Adelaide FM saturation note
- `dashboard/shared_state.py` — `BAND_PROFILES` gains updated per band:
  - fm_broadcast: 0/0 (Adelaide FM is strong — minimum gain prevents saturation)
  - aviation: 16/20 (VHF weaker than FM — moderate gain needed)
  - adsb: 24/24 (1090 MHz moderate strength — more gain required)
  - noise_floor: 0/0 (reference measurement — same gain as FM)

**Test counts:** 278/278 (222 pytest + 56 Vitest) — no new tests required (defaults-only change).

---

### Phase 9 — Threshold Tuning ✓ DONE

**What:** Tune `SIGNAL_THRESHOLD_DB` — the dB value that decides which frequency
bins count as signal vs noise. Too low = noise counted as signal (false positive).
Too high = real signals missed (false negative). **Completed in Phase 9C-Threshold:
calibrated to 24.0 dB for telescopic whip SMA antenna at lna=24/vga=26.
Expanded in Phase 11: per-band thresholds now override this global value.**

**How:** A debug script loops through threshold values and prints `occupied_bins`
and `bandwidth_hz` at each level. The right value is the one where known signals
are cleanly captured without the noise floor bleeding in. Target: 200 kHz for FM
broadcast. Result: 24 dB -> 196,289 Hz (closest match).

**Analogy:** Squelch on a walkie-talkie. You adjust it until static disappears but
weak transmissions still come through.

**Key variable:** `SIGNAL_THRESHOLD_DB` in `core/pipeline/features.py` (now 24.0 dB).
**Expanded in Phase 11:** per-band thresholds now live in `BAND_PROFILES` (shared_state.py)
and are read live by the scan loop, overriding this global fallback.

---

### Phase 8 — Calibration Tool ✓ DONE

**What:** Measure how far apart different signal types are in fingerprint space.
Capture known signals (FM, ADS-B, etc.), compute pairwise distance scores, derive
classification thresholds automatically.

**Key output:** Distance scores: same-type signals score near 0 (e.g. two ADS-B
signals: 0.0007). Different types score 0.2+. These thresholds feed the classifier.

**Files:** `tools/calibrate.py`

**Key function:**

`compute_distance(fp_a, fp_b)` — takes two fingerprint dicts, returns a float
distance score. Close to 0 = nearly identical. 0.2+ = clearly different types.

---

### Phase 7 — Classification ✓ DONE

**What:** Given a fingerprint, ask the local LLM what type of signal it is.

**Files:** `core/classification/classifier.py`, `core/llm/client.py`

**Key function:**

`classify_signal(fingerprint)` — formats the fingerprint as a prompt, sends it to
yubaba (RTX 3060, llama.cpp), returns `{signal_type, confidence, reasoning}`.

**Analogy:** A bird ID app — you show it a photo, it says "magpie, 94% confident".

---

### Phase 6 — Signal Detection ✓ DONE

**What:** Not everything above the noise floor is a real signal. This phase adds
logic to decide whether `occupied_bins` is meaningful.

**Files:** `core/pipeline/features.py`, `core/detection/detector.py`

**Key function:**

`detect_signals(psd)` — scans PSD for regions that look like real transmissions.
Returns a list of detected regions with frequency bounds and estimated power.

**Analogy:** Motion detection on a security camera — only records when something
actually moves.

---

### Phase 5 — Live Dashboard ✓ DONE

**What:** FastAPI server + browser waterfall. The server runs a single background
capture loop that streams spectrum data over WebSocket to all connected browsers.
Phase 5b fixed a crash: previously each new browser connection opened a new HackRF
RX stream; the hardware only supports one. Fixed by making one loop broadcast to
all clients via `shared_state.spectrum_clients`.

**Files:** `dashboard/server.py`, `dashboard/shared_state.py`,
`dashboard/capture_loop.py`, `dashboard/static/waterfall.js`,
`dashboard/static/index.html`, `dashboard/static/style.css`

**Key function:**

`capture_loop()` — asyncio background task. Runs forever: capture IQ → compute PSD
→ JSON → broadcast to all connected browsers. Never returns. One instance only.

**Analogy:** A broadcast tower. Transmits continuously. Browsers are just receivers.

---

### Phase 4 — Fingerprinting ✓ DONE

**What:** Extract meaningful measurements from the PSD: bandwidth, occupied bins,
peak power. This is the signal's "fingerprint" — what gets passed to the classifier.

**Files:** `core/pipeline/features.py`

**Key function:**

`fingerprint_spectrum(psd_result, signal_threshold_db=None)` — counts bins above
the noise floor plus the effective threshold (per-band override or global fallback),
measures bandwidth they span, finds peak power. Returns a fingerprint dict including
`signal_threshold_db` (the threshold used) and `snr_margin_db` (SNR minus threshold).
Updated in Phase 11 to accept an optional per-band threshold.

**Analogy:** If the PSD is a photo, fingerprint_spectrum measures it — how wide is
the bright area? How many pixels are lit? What's the brightest?

---

### Phase 3 — FFT / PSD ✓ DONE

**What:** Convert raw IQ samples from time-domain numbers into a frequency picture
(PSD) using an FFT.

**Files:** `core/pipeline/fft.py`

**Key function:**

`compute_psd(samples, sample_rate_hz, centre_freq_hz)` — runs FFT on IQ array.
Returns `{freq_hz: [...], power_db: [...]}` — one power value per frequency bin.

**Analogy:** A music equaliser — splits the signal into frequency bands and shows
the strength of each.

---

### Phase 2 — IQ Capture ✓ DONE

**What:** Open the HackRF, tune to a frequency, collect samples, return them.

**Files:** `core/pipeline/capture.py`

**Key function:**

`capture_iq(freq_hz, num_samples, sample_rate_hz, lna_gain_db, vga_gain_db)`

Parameters:
- `freq_hz` — which frequency to tune to (e.g. 96_500_000 = 96.5 MHz FM)
- `num_samples` — how many samples to collect (256,000 ≈ 128 ms at 2 MHz)
- `sample_rate_hz` — samples per second; higher = wider frequency view
- `lna_gain_db` — first amplifier stage; default is 0 dB for strong signals
  like Adelaide FM broadcast (98 MHz). Weaker bands (e.g. aviation VHF, ADS-B)
  may need 16–24 dB. Higher gain = more amplification but risk of clipping.
- `vga_gain_db` — second amplifier stage; default is 0 dB for FM broadcast.
  Weaker bands may need 20–24 dB. LNA and VGA together control total gain —
  too much for a strong signal will saturate the ADC and produce distorted data.

Returns: NumPy array of complex (IQ) numbers.

**Analogy:** Your ear before your brain processes anything — raw vibration data.

---

### Phase 1 — Hardware Setup ✓ DONE

**What:** Install HackRF drivers and Python library, verify USB connection, confirm
raw samples can be received. No signal processing — just a health check.

---

## Frontend Stack

### Architecture Overview

The dashboard has two halves: a Python server (FastAPI + uvicorn) and a browser
client (plain HTML + vanilla JavaScript). They communicate over WebSocket — a
persistent live connection, not normal HTTP request/response.

```
Python server side                    Browser side
──────────────────────────────────    ──────────────────────────────
server.py                             index.html
  starts FastAPI + uvicorn              page skeleton + band buttons
  serves static files                   loads waterfall.js + style.css
  registers WebSocket routes

shared_state.py                       waterfall.js
  spectrum_clients (set of             opens WS to /ws/spectrum
  connected browser sockets)           parses JSON frames
  current_band settings                maps power_db → colours
  shutdown_event                       draws pixels on canvas
  BAND_PROFILES dict                   scrolls canvas each frame
                                       opens WS to /ws/command
capture_loop.py                        sends band switch commands
  asyncio background task
  runs pipeline in loop:             style.css
    capture_iq()                       dark theme layout
    compute_psd()                      band button styles (.band-btn)
    → JSON → broadcast to all          annotation text formatting
      browsers in spectrum_clients
```

### Data Flow — Server to Browser

```
HackRF hardware
  → capture_loop.py: raw IQ samples (NumPy array, in Python memory)
  → compute_psd(): PSD dict {freq_hz, power_db} (in Python memory)
  → capture_loop.py serialises to JSON string
  → WebSocket /ws/spectrum: JSON packet over network
  → waterfall.js parses JSON in browser
  → canvas pixels: power_db values mapped through colourmap (browser GPU)
```

### Band Switching Flow

```
User clicks [ADS-B] button in browser
  → waterfall.js sends: {"action": "set_band", "band": "adsb"}
  → WebSocket /ws/command: JSON packet over network
  → server command handler looks up "adsb" in BAND_PROFILES
  → updates shared_state.current_band (frequency + gain)
  → next capture_loop iteration reads current_band, retunes HackRF
  (no server restart needed)
```

### How the Waterfall Works — Step by Step

1. `capture_loop.py` finishes one pipeline cycle: gets a PSD dict with 2048
   `freq_hz` values and 2048 `power_db` values.
2. Serialises to a JSON string and sends to every socket in `spectrum_clients`.
3. `waterfall.js` receives the JSON and parses it back to a JS object.
4. Loops through each `power_db` value, maps it through the colourmap
   (weak = dark blue/black, strong = yellow/white), draws one pixel per bin
   across the canvas.
5. Before drawing, shifts all existing pixels down one row:
   `ctx.drawImage(canvas, 0, 1)`. This is what makes the waterfall scroll —
   old rows sink, new rows appear at the top.
6. Repeats every time a new PSD arrives (roughly once per capture cycle).

### Frontend Files

| File | Layer | Role |
|---|---|---|
| `dashboard/server.py` | Python | Entry point. Starts Flask-SocketIO server, registers routes, kicks off `scan.py` loop. |
| `dashboard/shared_state.py` | Python | Shared memory. Holds `BAND_PROFILES`, `current_band`, shutdown event, and band-switch lock. |
| `dashboard/static/` | Static | Vite build output (generated). Served by Flask. |
| `dashboard/frontend/src/App.jsx` | React | Root component. Three-row layout: waterfall + signal details (top), system status + signal history + AI reasoning + decoded signals (bottom). Owns `pinnedReasoning` state for pin-to-reasoning feature. OVERVIEW_BANDS (7 entries) for bottom strip. BAND_GROUPS (4 categories) for nav bar. DECODED SIGNALS section conditionally renders decoder sub-panels (ADS-B, ACARS, AIS) based on focused band; shows "NO DECODER FOR THIS BAND" placeholder otherwise. Helper functions: `isTuned()`, `isAcarsTuned()`, `isAisTuned()`. |
| `dashboard/frontend/src/components/SignalHistoryLog.jsx` | React | Scrolling log of scan results. FREQ_COLOUR_MAP colours each row by band (7 AU frequencies, all at 162.000 MHz for AIS). Each row clickable: toggles pin on AIReasoningPanel. Amber highlight on pinned row. Wrapped in React.memo with custom comparison (pinnedTimestamp + scanResults content) to avoid re-render on spectrum_update. |
| `dashboard/frontend/src/components/AIReasoningPanel.jsx` | React | Displays LLM classification output. Shows ◆ PINNED badge when `isPinned` prop is true. Fade transition on new reasoning data. |
| `dashboard/frontend/src/components/FrequencyList.jsx` | React | Sidebar band list. FREQ_CONFIGS (7 entries) drives the clickable band rows. Shows latest signal type and confidence per band. Kept in sync with STRIP_CONFIGS and BAND_GROUPS. |
| `dashboard/frontend/src/components/AisVesselPanel.jsx` | React | AIS vessel data table. Shows decoded AIS messages (MMSI, vessel name, position, speed, course, channel). Displays "Listening on 162.000 MHz..." when tuned to AIS frequency, "Not tuned to AIS frequency" otherwise. |

### Pin-to-Reasoning Data Flow

The user clicks a row in SignalHistoryLog:

1. `SignalHistoryLog` fires `onPinReasoning(entry)` via its `onClick` handler
2. `App.jsx` `handlePinReasoning(entry)` compares identity: if the same row
   (same timestamp + same center_freq_hz) is clicked again, pin is cleared
   (`setPinnedReasoning(null)`). Otherwise, a new pin object is created from
   the entry fields overlaid on `INITIAL_AI_REASONING`.
3. `AIReasoningPanel` receives `aiReasoning={pinnedReasoning || aiReasoning}`
   and `isPinned={!!pinnedReasoning}`. The `key={pinnedTimestamp || 'live'}`
   prop forces a React remount, clearing any stale fade transition.
4. `AIReasoningPanel` renders the ◆ PINNED badge between the frequency and
   signal type lines when `isPinned=true` and `displayData.signal_type` is set.
5. `SignalHistoryLog` sets `data-pinned` attribute and applies amber border +
   background styling on the pinned row for visual feedback.

---

## Hardware Concepts

### Antennas — One Does NOT Fit All

An antenna is physically tuned to a wavelength, not a frequency range. The length
of the antenna determines which frequency it receives best. Too short or too long
and the antenna becomes inefficient — it still picks something up, but weakly.

The rule is straightforward:

- Higher frequency = shorter wavelength = shorter antenna needed
- Lower frequency = longer wavelength = longer antenna needed

Real examples relevant to Mimir:

| Signal type | Frequency | Ideal antenna length |
|---|---|---|
| FM broadcast | ~100 MHz | ~68 cm |
| APRS | 145 MHz | ~49 cm |
| ADS-B | 1090 MHz | ~6.5 cm |

**Why this matters for Mimir:** the antenna you connect to the HackRF directly
affects what you can receive. A short fixed antenna (like a spiral) is optimised
for high frequencies and physically cannot perform well at FM. A telescopic whip
is more flexible — you extend it to match the frequency you want.

**The body effect:** if touching an antenna dramatically improves reception, your
body is acting as an antenna extension. A human body is roughly 68 cm of conducting
material — which is almost exactly the right length for FM broadcast (~100 MHz).
This is a strong sign the connected antenna is too short for that frequency.

**Antenna types in practice:**

- **Telescopic whip** — adjustable length, good all-rounder. Extend it to the right
  length for whatever frequency you are monitoring. One physical antenna, many uses.
- **Fixed spiral / stubby** — short fixed length, optimised for high frequencies
  (800 MHz+). Cannot be extended. Not suitable for FM or other low-frequency bands.
- **Dedicated band antenna** — cut to exactly the right length for one frequency.
  Best performance for that band, useless outside it.

---

## Acronym Glossary

| Term | Full name | Plain English |
|---|---|---|
| ADS-B | Automatic Dependent Surveillance–Broadcast | Aircraft broadcast their position on 1090 MHz. Legal to receive passively. Mimir can demodulate, decode, and classify ADS-B messages — extracting ICAO address, callsign, altitude, position, groundspeed, and track. |
| ACMA | Australian Communications and Media Authority | Australian body that regulates radio spectrum. Mimir's hard requirement — ACMA-compliant frequencies only. |
| ACARS | Aircraft Communications Addressing and Reporting System | A digital data link between aircraft and ground stations. Used for flight plans, weather, and maintenance messages. AU primary frequency: 129.125 MHz. Legal to receive passively. |
| antenna | Antenna | A physical conductor that picks up radio waves. Its length determines which frequency it receives best. Not one-size-fits-all — see Hardware Concepts. |
| APRS | Automatic Packet Reporting System | A digital radio protocol used by amateur radio operators at 145 MHz. Carries GPS position, weather data, and short messages. |
| ASGI | Asynchronous Server Gateway Interface | Python standard for async web servers. FastAPI is an ASGI framework; uvicorn is the ASGI server that runs it. |
| asyncio | Asynchronous I/O | Python's way of doing multiple things concurrently without threads. `capture_loop` runs as an asyncio background task. |
| Canvas | HTML Canvas | Browser element that JavaScript draws on pixel by pixel. The waterfall is drawn here — one row of pixels per PSD frame. |
| colourmap | Colour Map | Lookup table: power (dB) → colour. Weak signals = dark blue. Strong signals = yellow/white. Produces the heat-map look. |
| ChromaDB | ChromaDB | Vector database optimised for similarity search. Mimir stores signal embeddings (7-dimensional numerical fingerprints) in ChromaDB. When a new signal arrives, ChromaDB finds the most similar previously-seen signals and returns them as context for the LLM classifier. Analogy: a library catalog organised by "what things look like" rather than by title. |
| CPR | Compact Position Reporting | ADS-B position encoding scheme. Aircraft transmit latitude/longitude as compressed even/odd frame pairs. A receiver needs both frames (or a known reference position) to resolve the full position. Mimir uses pyModeS.PipeDecoder to accumulate even/odd frame pairs per ICAO and resolve positions globally — no fixed reference point required. Positions appear within ~5 seconds of the first pair. |
| dB | Decibel | Unit of signal strength. Logarithmic scale. Values in Mimir are negative (e.g. -50 dB). Closer to 0 = stronger signal. Noise floor ≈ -50 to -60 dB. |
| DOM | Document Object Model | Browser's internal model of the HTML page. `waterfall.js` uses it to find the canvas element and draw on it. |
| FastAPI | FastAPI | Python web framework. Handles HTTP and WebSocket connections. The engine behind the dashboard server. |
| FFT | Fast Fourier Transform | Maths that converts time-domain samples into frequency + strength data. Answers: "what frequencies are present and how strong is each?" |
| frame | Waterfall Frame | One row of the waterfall. Each new PSD from the server is drawn as one horizontal strip of coloured pixels. |
| HTTP | HyperText Transfer Protocol | Standard web protocol. Used once on page load to fetch `index.html`, JS, and CSS. After that, WebSocket takes over for live data. |
| Hz / MHz / GHz | Hertz / Megahertz / Gigahertz | Units of frequency. FM radio: 88–108 MHz. ADS-B: 1090 MHz. HackRF covers 1 MHz to 6 GHz. |
| IQ | In-phase / Quadrature | Raw format for SDR data. Two number streams (I and Q) that together describe amplitude and phase. "IQ data" = raw radio samples. |
| JSON | JavaScript Object Notation | Text format for structured data. The server sends PSD as JSON: `{"freq_hz": [...], "power_db": [...]}`. |
| LLM | Large Language Model | AI model on yubaba (RTX 3060, llama.cpp) used for signal classification. Reads a fingerprint, says what type of signal it is. |
| LNA | Low Noise Amplifier | First amplifier in the receive chain. Boosts signal before anything else. Set via `lna_gain_db`. Default: 0 dB for strong signals (FM broadcast). Weaker bands may need 16–24 dB. |
| NumPy | Numerical Python | Python library for fast array maths. All IQ samples and PSD values are NumPy arrays. `np.` in code = NumPy. |
| PSD | Power Spectral Density | Output of the FFT. A bar chart of frequency vs signal strength. One dB value per frequency bin. |
| PPM | Pulse Position Modulation | Modulation scheme used by ADS-B. Each bit is transmitted as a pulse in one of two time slots within a bit period. The slot with the larger pulse determines whether the bit is 1 or 0. Mimir demodulates PPM at 2 MSa/s (2 samples per bit). |
| PYTHONPATH | Python Path | Environment variable telling Python where to find modules. `PYTHONPATH=.` means "look from current directory" — needed for debug scripts to find Mimir's own modules. |
| pyModeS | Python Mode S | Python library for decoding Mode S / ADS-B hex strings. Used by `AdsbDecoder`. The stateless `decode()` function validates single frames; `PipeDecoder` (v3+) accumulates per-ICAO state and resolves CPR position pairs globally. Decode-only — no transmit capability. |
| SDR | Software-Defined Radio | A radio where processing is done in software, not hardware circuits. The HackRF is an SDR. |
| shared_state | Shared State Module | `dashboard/shared_state.py`. Holds variables used across the whole server. Because Python caches imports, every file gets the same object. |
| spiral antenna | Spiral Antenna | A compact fixed-length antenna optimised for high frequencies (800 MHz+). Cannot be extended. Poor performance at FM and other low-frequency bands. |
| telescopic whip | Telescopic Whip Antenna | An adjustable-length antenna. Extend it to match the wavelength of the frequency you want. One physical antenna usable across many bands. |
| TX | Transmit | Sending radio signals. Mimir never transmits. Any TX function call must raise `HardwareTransmitError`. AU law — criminal offence without licence. |
| uvicorn | Uvicorn | ASGI server that runs FastAPI. When you start the server, uvicorn listens on the port. FastAPI defines the routes; uvicorn serves them. |
| VGA | Variable Gain Amplifier | Second amplifier stage after LNA. Together LNA + VGA = two gain knobs. Set via `vga_gain_db`. Default: 0 dB for strong signals (FM broadcast). Weaker bands may need 20–24 dB. |
| wavelength | Wavelength | The physical length of one radio wave cycle. Higher frequency = shorter wavelength. An antenna works best when its length matches the wavelength of the signal it is receiving. |
| WebSocket | WebSocket | Persistent two-way browser–server connection. Unlike HTTP (closes after response), it stays open so the server can push data in real time. |
| yubaba | yubaba | Prin's local LLM inference server. RTX 3060 12GB, llama.cpp. Hosts the model used by `classify_signal()`. |
