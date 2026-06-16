---
description: "Mimir project wiki — pipeline reference, phase log, acronym glossary, and frontend stack. Updated by @doc-writer at the end of each build."
status: live
last_updated_phase: Spectrum-Broadcast-Decouple
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

### pre-9C-seed-autowipe — ChromaDB Seed Auto-Wipe ▶ ACTIVE

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
calibrated to 24.0 dB for telescopic whip SMA antenna at lna=24/vga=26.**

**How:** A debug script loops through threshold values and prints `occupied_bins`
and `bandwidth_hz` at each level. The right value is the one where known signals
are cleanly captured without the noise floor bleeding in. Target: 200 kHz for FM
broadcast. Result: 24 dB -> 196,289 Hz (closest match).

**Analogy:** Squelch on a walkie-talkie. You adjust it until static disappears but
weak transmissions still come through.

**Key variable:** `SIGNAL_THRESHOLD_DB` in `core/pipeline/features.py` (now 24.0 dB)

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

`fingerprint_spectrum(psd)` — counts bins above `SIGNAL_THRESHOLD_DB`, measures
bandwidth they span, finds peak power. Returns a fingerprint dict.

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
| `dashboard/server.py` | Python | Entry point. Starts FastAPI + uvicorn, registers routes, kicks off `capture_loop`. |
| `dashboard/shared_state.py` | Python | Shared memory. Holds `spectrum_clients`, `current_band`, `shutdown_event`, `BAND_PROFILES`. |
| `dashboard/capture_loop.py` | Python | Pipeline engine. Runs capture → PSD → JSON → broadcast in an asyncio loop. |
| `dashboard/static/index.html` | Browser | Page skeleton. Defines canvas, band buttons, annotation div. |
| `dashboard/static/waterfall.js` | Browser | Browser brain. WebSocket client, colourmap, canvas drawing, band switch commands. |
| `dashboard/static/style.css` | Browser | Visual styling. Dark theme, band button styles. |

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
