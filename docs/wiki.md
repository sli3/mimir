---
description: "Mimir project wiki — architecture and environment reference for cross-cutting knowledge that has no other home. Phase history lives in docs/ROADMAP.md."
status: live
last_updated_phase: "58-FIX-4"
---

# Mimir Wiki

Knowledge base for the Mimir project. Written in plain English for an RF beginner.

**Scope.** This wiki holds only knowledge that has no natural home elsewhere:
cross-cutting architecture, hardware behaviour, and environment gotchas. It
deliberately does NOT duplicate other documents:

| Looking for | Read instead |
|---|---|
| Phase history, what shipped when, test counts | `docs/ROADMAP.md` |
| Open tech debt, agent roster, build rules | `AGENTS.md` |
| What a specific function does | the docstring in the source file |
| Setup and usage | `README.md` |
| Known defects in a tool | the Known Tech Debt table in `AGENTS.md` |

Anything duplicated here would drift out of sync with its source, which is
exactly what happened to the phase log this file used to carry.

---

## Contents

1. [What Mimir Is](#what-mimir-is)
2. [Signal Pipeline](#signal-pipeline)
3. [Frontend Stack](#frontend-stack)
4. [Tools](#tools)
5. [Hardware Concepts](#hardware-concepts)
6. [Environment and Gotchas](#environment-and-gotchas)
7. [Acronym Glossary](#acronym-glossary)

---

## What Mimir Is

Mimir is a passive RF spectrum scanner. It uses a software-defined radio (HackRF One or ADALM-PLUTO) to
listen to the air, processes what it hears through a Python pipeline, classifies
signals using a local LLM running on a machine called yubaba, and displays everything
live in a browser-based waterfall dashboard. When both devices are present, Pluto is selected by default; pass `--device hackrf` or `--device plutosdr` to force a specific device.

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
  1   SDR hardware (HackRF or Pluto) Physical USB device. Converts radio waves to
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

  7   Dashboard / Waterfall         Flask + Flask-SocketIO streams PSD data to the
      dashboard/                    React client, which draws one row of pixels
                                    per frame.
```

---

## Frontend Stack

The backend is Flask with Flask-SocketIO; the frontend is React built with Vite
and served from `dashboard/static/`. Communication is over Socket.IO events, not
plain HTTP.

> **Gap — architecture overview needed.** This section previously carried an
> overview, data-flow, band-switching and waterfall walkthrough written for the
> pre-React stack (FastAPI + uvicorn serving vanilla `waterfall.js`). Those were
> removed rather than rewritten, because rewriting them from memory would have
> reintroduced the same class of error. They should be rebuilt by reading
> `dashboard/server.py` and `dashboard/frontend/src/App.jsx` directly.

### Frontend Files

| File | Layer | Role |
|---|---|---|
| `dashboard/server.py` | Python | Entry point. Starts Flask-SocketIO server, registers routes, kicks off `scan.py` loop. |
| `dashboard/shared_state.py` | Python | Shared memory. Holds `BAND_PROFILES`, `current_band`, shutdown event, and band-switch lock. |
| `dashboard/static/` | Static | Vite build output (generated). Served by Flask. |
| `dashboard/frontend/src/App.jsx` | React | Root component. Three-row layout: waterfall + signal details (top), system status + signal history + AI reasoning + decoded signals (bottom). Owns `pinnedReasoning` state for pin-to-reasoning feature. OVERVIEW_BANDS (7 entries) for bottom strip. BAND_GROUPS (4 categories) for nav bar. DECODED SIGNALS section conditionally renders decoder sub-panels (ADS-B, ACARS, AIS) based on focused band; shows "NO DECODER FOR THIS BAND" placeholder otherwise. Helper functions: `isTuned()`, `isAcarsTuned()`, `isAisTuned()`. |
| `dashboard/frontend/src/components/SignalHistoryLog.jsx` | React | Scrolling log of scan results. FREQ_COLOUR_MAP colours each row by band (7 AU frequencies, all at 162.000 MHz for AIS). Each row clickable: toggles pin on AIReasoningPanel. Amber highlight on pinned row. Wrapped in React.memo with custom comparison (pinnedTimestamp + scanResults content) to avoid re-render on spectrum_update. The amber [PEAK] tag (Phase 45) is driven by the backend's `is_burst` boolean, computed via per-bin max-hold ratio detection in `fingerprint_spectrum()`. The tag renders only when `is_burst === true` (strict equality). |
| `dashboard/frontend/src/components/AIReasoningPanel.jsx` | React | Displays LLM classification output. Shows ◆ PINNED badge when `isPinned` prop is true. Fade transition on new reasoning data. Main-dashboard component — NOT the /radar page's LLM panel (that is `LlmReasoningPanel.jsx`, a separate component). |
| `dashboard/frontend/src/components/FrequencyList.jsx` | React | Sidebar band list. FREQ_CONFIGS (7 entries) drives the clickable band rows. Shows latest signal type and confidence per band. Kept in sync with STRIP_CONFIGS and BAND_GROUPS. |
| `dashboard/frontend/src/components/AircraftDetailPanel.jsx` | React | Phase 51. Aircraft detail panel for the /radar page. Scrollable list of in-range contacts plus a fixed-height (180px) pinned detail card below. The pinned card shows a 2-column grid: static identity fields on the left (callsign, ICAO, squawk, bearing/range - 4 fields, Phase 55 added bearing/range), dynamic per-frame fields on the right (altitude, track, groundspeed, vertical rate - 4 fields). |
| `dashboard/frontend/src/components/AisVesselPanel.jsx` | React | AIS vessel data table. Shows decoded AIS messages (MMSI, vessel name, position, speed, course, channel). Displays "Listening on 162.000 MHz..." when tuned to AIS frequency, "Not tuned to AIS frequency" otherwise. |
| `dashboard/frontend/src/components/PredictionGlyph.jsx` | React | Phase 55. Pure presentational component showing the derived prediction vector as a horizontal row of five dots (two solid "history" dots, three "ghost" projection dots) with a dashed connector. Angle derived from vector.thetaDegPerSec clamped to ±45 degrees. CSS-only pulse animation (gated on prefers-reduced-motion). Wrapped in React.memo. |
| `dashboard/frontend/src/components/PathPredictionPanel.jsx` | React | Phase 52 (restructured Phase 58-FIX-4). Fixed-height strip (300px) below the radar scope on the /radar page. Single-column flex container (Phase 58-FIX-4 replaced the old 2-column grid). In state 3 the prediction glyph and anomaly flag strip sit side-by-side inside `.radar-prediction-glyph-row`, with the Phase 53 `LlmReasoningPanel` (manual "ANALYSE PATH WITH LLM" button) full-width underneath. In state 2 the anomaly strip is a sibling block below the gathering text. The physics-only θ/Δr readout was removed in Phase 58-FIX (that data now lives in the floating scope box on the selected aircraft's blip). Three render states: no selection (placeholder), selection with fewer than 2 trail fixes ("gathering"), and selection with 2+ fixes (glyph + anomaly strip + LLM panel). Makes no network, socket, or inference call of its own. Reads `trailsRef` but never writes it — `RadarScopePanel` is the sole writer. |
| `dashboard/frontend/src/components/LlmReasoningPanel.jsx` | React | Phase 53. The /radar page's LLM trajectory-analysis column, mounted by `PathPredictionPanel` in its State 3. Owns the entire request lifecycle for the manual "ANALYSE PATH WITH LLM" button: POSTs the physics facts to `/api/radar/reason` and renders one of four states (idle, loading with a two-stage message that escalates past 10 s, result, error). Lifecycle guards: resets to idle on ICAO change, aborts the in-flight request via AbortController on ICAO change or unmount, drops late responses whose captured ICAO no longer matches, and checks a mounted ref before every async state transition. Phase 55: HTTP 400 validation rejections now map to a distinct `cause: 'rejected'` rather than being collapsed into `'network'` (which rendered misleadingly as "LLM unreachable"); all other non-200 statuses keep the network classification. Renders `PredictionGlyph` above the verdict text in the result state. Distinct from `AIReasoningPanel.jsx`, which is the main dashboard's classification display. |
| `dashboard/frontend/src/components/RadarScopePanel.jsx` | React | PPI-style radar scope displaying ADS-B aircraft contacts as an SVG polar plot. Renders static chrome (range rings at 25% intervals, 30° radial spokes, centre crosshair, compass labels N/E/S/W) plus dynamic aircraft blips. Each blip is a neon-cyan circle with `filter="url(#mimir-radar-glow)"`; close contacts (inner 25% of range) get a larger blip (3.1 vs 2.2 px radius). Label shows callsign if present, otherwise ICAO. Panel only renders when tuned to ADS-B frequency (1090 ± 2 MHz). Guard filter rejects aircraft with null/undefined/NaN `bearing_deg` or `range_nm`. Uses projection.js for coordinate mapping. |
| `dashboard/frontend/src/components/radar/projection.js` | JS | Pure-math projection module, renderer-agnostic. Two exported functions: `projectToScope(bearingDeg, rangeNm, maxRangeNm, cx, cy, maxR)` converts polar to screen pixels (bearing 0° = north = negative Y, clockwise = positive X), and `isWithinRange(rangeNm, maxRangeNm)` is a null-safe guard that rejects null/undefined/NaN and out-of-range values. No React dependencies. |

### Radar Scope Panel (Phase 49)

The radar scope panel (`RadarScopePanel.jsx`) provides a classic plan-position-indicator (PPI) polar plot of ADS-B aircraft positions. It is a passive receive display only — no transmit capability.

**Location and sizing:**
- Rendered in the third column of Row 3 (DECODED SIGNALS row) in App.jsx.
- Fixed 380px width column with `flexShrink: 0`.
- Single `<svg viewBox="0 0 380 325">` with named constants: `SCOPE_CX=190`, `SCOPE_CY=162.5`, `SCOPE_MAX_R=150`.

**Coordinate system:**
- Bearing 0° = true north (top of scope), increasing clockwise.
- Y is inverted: north maps to `y < cy` because screen Y grows downward.
- All coordinates rounded to 2 decimal places (`r2()`) to avoid float noise in SVG attributes.

**Rendering flow:**
1. Chrome (static): 4 concentric range rings (25%, 50%, 75%, 100% of `maxRangeNm`), 12 radial spokes (30° intervals), centre crosshair (cyan, 1px), compass labels (N/E/S/W). Computed once via `useMemo()` and never re-rendered.
2. Aircraft filtering: Filters `adsbAircraft` via the shared `isValidContact(ac, maxRangeNm)` (from `radar/projection.js`), which rejects entries with null/undefined/NaN `bearing_deg` and out-of-range `range_nm`. This same function is also called by `RadarPage` for its header contact count, so the two can never disagree (Phase 50, resolved TD-49-6). Guard runs before projection so no NaN coordinate reaches SVG. Aircraft that fail this check on a single frame but have recent trail history render at their last known position instead of disappearing — see "Breadcrumb trail" below.
3. Projection: For each filtered aircraft, calls `projectToScope(ac.bearing_deg, ac.range_nm, maxRangeNm, SCOPE_CX, SCOPE_CY, SCOPE_MAX_R)` to get screen coordinates.
4. Blip rendering: Each aircraft renders as a `<circle>` with `fill="var(--neon-cyan)"`, `filter="url(#mimir-radar-glow)"`. Close contacts (inner 25% of range) get larger radius (3.1 vs 2.2 px). Label (`<text>`) shows callsign if present, otherwise ICAO. Uses `key={ac.icao}` for stable React keys.
5. "Not tuned to ADS-B frequency" placeholder: When `isAdsbFreq` is false, shows grey text message instead of SVG.

**Breadcrumb trail (Phase 50):**
- Each contact shows up to 8 prior positions (`TRAIL_MAX_POINTS`) as a fading `<polyline>` + per-point `<circle>` trail behind the current blip, older points fainter and smaller.
- Trail points are stored bearing_deg + range_nm (not raw lat/lon), reusing `projectToScope()` unchanged, in a `useRef` Map keyed by ICAO — a ref rather than state, since trail mutation is a side effect of processing `adsbAircraft` and must not itself trigger a re-render.
- Staleness cutoff: 90 seconds (`TRAIL_STALE_MS`), mirroring the existing literal in `useSocket.js:174`. A gap longer than this clears the trail rather than drawing a straight line across dead time.
- On a single bad frame (missing/NaN `bearing_deg`), the aircraft renders at its last known stored position — blip and trail both — rather than disappearing for that render. This handles ADS-B's irregular message mix (many message types carry no position data at all) without visual flicker. Only once the gap exceeds the staleness cutoff does the aircraft actually stop rendering.
- Trail update/prune logic runs inside the same `useMemo` that computes `contacts`, not a separate `useEffect` — deliberate, so trail state updates in the same render tick it feeds rather than lagging one render behind.
- The frame timestamp arrives from the backend as an ISO 8601 string (`dashboard/server.py:666` emits `msg.timestamp.isoformat()`). The trail buffer is arithmetic-bearing (`ts - last.ts > TRAIL_STALE_MS` and `newest.ts - oldest.ts` inside `derivePredictionVector`), so the string must be coerced to numeric epoch ms at the point of use, via `utils/parseFrameTs.js`. The ISO string wire format is preserved for the six other consumers that legitimately render it (AisVesselPanel, AcarsMessagePanel, App.jsx "LAST SEEN", AIReasoningPanel, SignalHistoryLog, VectorSpacePage). This was found and fixed in Phase 53-HOTFIX — see docs/ROADMAP.md for the root cause and the mocked-seam lesson.

Note: an earlier version of this section described a "load-bearing" empty `useEffect(() => {}, [isAdsbFreq])` as an intentional mount-lifecycle contract for future renderer state. That effect did nothing (the SVG renderer had no state to measure) and the comment was later confirmed to be fabricated documentation, not a real design decision. It was deleted in Phase 50.

**Glow filter:**
- SVG `<filter id="mimir-radar-glow" x="-80%" y="-80%" width="260%" height="260%">` with `feGaussianBlur stdDeviation="2.4"`.
- Applied via `filter="url(#mimir-radar-glow)"` on all aircraft blips.
- Creates a subtle neon glow effect around each contact without obscuring the core blip.

**Data contract with backend:**
- Backend: `BearingTracker.update()` computes `range_nm` using `great_circle_distance_nm()` (haversine, spherical Earth radius 3440.065 NM).
- Backend: `AdsbSubscriber.stop()` and `_decode_loop()` set `msg.range_nm = report.range_nm if report else None`.
- Backend: `emit_adsb_aircraft()` (server.py:397) emits `"range_nm": getattr(msg, "range_nm", None)`.
- Frontend: RadarScopePanel expects each `adsbAircraft` entry to have `bearing_deg`, `range_nm`, `icao`, and optionally `callsign`. Null/undefined/NaN values are filtered out before projection.

**Why the geometry:**
- 380×325 viewBox fits the 380px column width with reasonable vertical proportion.
- `SCOPE_MAX_R=150` provides margin: 150 px from centre to edge leaves 40 px for labels (N/E/S/W) and crosshair without clipping.
- 4 range rings (25%, 50%, 75%, 100%) give the operator quick distance reference without visual clutter.

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

## Tools

Standalone scripts in `tools/`. Run from the repository root with `PYTHONPATH=.`
unless a script says otherwise. Descriptions below come from each script's own
docstring and argparse definition.

The **Writes** column matters: some of these mutate the vector store or hardware
calibration data. Check it before running anything unfamiliar.

### Calibration

| Tool | What it does | Writes |
|---|---|---|
| `calibrate_thresholds.py` | Calibrates classifier thresholds from real RF captures. Persists results in `data/calibration_vectorstore/` across runs; `--wipe` deletes the collection first for a full re-baseline. | Yes — calibration vector store |
| `diagnose_threshold.py` | Sweeps per-band signal thresholds and prints a recommended threshold (dB) and bandwidth per band. `--band <name>` sweeps one band instead of all six; valid names come from `BAND_KEYS`. | No |
| `check_thresholds_cli.py` | Exercises the pure `derive_thresholds()` guard logic from `calibrate_thresholds.py` without touching hardware, ChromaDB, or the capture pipeline. Runs a fixed suite of cases with expected results when given no arguments. | No |

### Diagnostics

| Tool | What it does | Writes |
|---|---|---|
| `diagnose_live.py` | Live diagnostic tool for the scanner. | No |
| `diagnose_fingerprints.py` | Prints raw fingerprint features for each band. Useful when a classification looks wrong and you want to see what the classifier actually received. | No |
| `diagnose_pluto_gain.py` | Pluto gain calibration diagnostic. Sweeps gain and reports noise floor and excursions per step. See Environment and Gotchas for how to read the output — the spur onset above roughly 30 dB and the 35 dB gain-table anomaly both show up here. | No |
| `compare_decode_rate.py` | Compares HackRF One against ADALM-PLUTO on ADS-B decode rate. Receive-only; carries its own ACMA legal notice. | No |

### Vector store

| Tool | What it does | Writes |
|---|---|---|
| `seed_chromadb.py` | Seeds ChromaDB with the RTL-ML reference signal dataset. | Yes — signal store |
| `capture_to_vectorstore.py` | Live capture to vector store ingestion. Captures signals off the air and writes them into the store. | Yes — signal store |
| `inspect_snr.py` | Read-only SNR inspection of stored vectors, by label. Use this to see what is in the store before deleting anything. | No |
| `delete_low_snr.py` | Deletes low-SNR vectors for one label. Has its own safety gates. | Yes — deletes from signal store |

### Reference data

| Tool | What it does | Writes |
|---|---|---|
| `build_frequency_reference.py` | Converts a raw pdfplumber extraction of the ACMA Radiofrequency Spectrum Plan into a structured `frequency_reference_raw.json`. A one-off data pipeline script: run it, review the output, then copy the reviewed file into `data/`. | Yes — JSON output file |

**Known defects in these tools are tracked in the Known Tech Debt table in
`AGENTS.md`, not here.** At the time of writing that includes stale gain values
in two of the calibration and diagnostic tools, and a re-seed hazard in
`seed_chromadb.py`. Check the table before trusting a tool's defaults.

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

## Environment and Gotchas

This section records environment-specific facts and gotchas discovered during
development. These are not bugs, but behaviours that operators need to be aware of.

### Pluto (ADALM-PLUTO) Gain Behaviour

The ADALM-PLUTO SDR exhibits two measured behaviours that affect gain calibration:

**Spurs above ~30 dB combined gain:** Above roughly 30 dB combined gain, a
picket fence of small spurious spikes appears across the frequency span. These
are Pluto-generated, not environmental — a HackRF capture at the same frequency,
antenna, and moment showed a clean trace. Operational impact: spurs land in the
PSD, become part of the spectral fingerprint, and could cluster in ChromaDB as
if they were signal patterns. When choosing a calibrated gain value, run
`tools/diagnose_pluto_gain.py` and observe the "excursions" column — a sharp
rise past ~30 dB is the spur onset. See `core/device/pluto_rx.py` module docstring
"MEASURED FINDINGS" for the full context.

**Gain-table boundary at ~35 dB:** The noise floor does NOT rise monotonically
with gain. At 35 dB the floor drops ~3–4 dB below the 30 dB value, then resumes
rising. This was reproduced across two independent sweep runs on different days.
Suspected AD9363 internal gain-table boundary, not confirmed. Operational impact:
gain values are not uniformly spaced in effect. When the diagnostic sweep shows
a drop in the "noise_floor" column at 35 dB, it is not an improvement to chase —
the lower value is an artefact, not better sensitivity. See `core/device/pluto_rx.py`
module docstring "MEASURED FINDINGS" for the full context.

### SoapySDR Device() Argument Format

SoapySDR's `Device()` constructor requires its arguments as a string, not a
Python dict. The string format is `"key=value,key2=value2"`. Passing a dict
directly (e.g. `{"driver": "plutosdr", "uri": "usb:3.19.5"}`) fails with
"make() no match" because SWIG's dict marshalling does not produce Kwargs that
match what the plugin's `find()` returns. The string path uses the plugin's own
parser. This was discovered during Pluto development — `hackrf_rx.py` has always
used the string form, but `pluto_rx.py` initially used a dict and could not
open its device. Any new device wrapper must use the string form.

Example:
```python
# Correct
device = SoapySDR.Device("driver=plutosdr,uri=usb:3.19.5")

# Fails with "make() no match"
device = SoapySDR.Device({"driver": "plutosdr", "uri": "usb:3.19.5"})
```

---

## Acronym Glossary

| Term | Full name | Plain English |
|---|---|---|
| ADS-B | Automatic Dependent Surveillance–Broadcast | Aircraft broadcast their position on 1090 MHz. Legal to receive passively. Mimir can demodulate, decode, and classify ADS-B messages — extracting ICAO address, callsign, altitude, position, groundspeed, and track. |
| ACMA | Australian Communications and Media Authority | Australian body that regulates radio spectrum. Mimir's hard requirement — ACMA-compliant frequencies only. |
| ACARS | Aircraft Communications Addressing and Reporting System | A digital data link between aircraft and ground stations. Used for flight plans, weather, and maintenance messages. AU primary frequency: 129.125 MHz. Legal to receive passively. |
| antenna | Antenna | A physical conductor that picks up radio waves. Its length determines which frequency it receives best. Not one-size-fits-all — see Hardware Concepts. |
| APRS | Automatic Packet Reporting System | A digital radio protocol used by amateur radio operators at 145 MHz. Carries GPS position, weather data, and short messages. |
| Canvas | HTML Canvas | Browser element that JavaScript draws on pixel by pixel. The waterfall is drawn here by the React client — one row of pixels per PSD frame. |
| colourmap | Colour Map | Lookup table: power (dB) → colour. Weak signals = dark blue. Strong signals = yellow/white. Produces the heat-map look. |
| ChromaDB | ChromaDB | Vector database optimised for similarity search. Mimir stores signal embeddings (7-dimensional numerical fingerprints) in ChromaDB. When a new signal arrives, ChromaDB finds the most similar previously-seen signals and returns them as context for the LLM classifier. Analogy: a library catalog organised by "what things look like" rather than by title. |
| CPR | Compact Position Reporting | ADS-B position encoding scheme. Aircraft transmit latitude/longitude as compressed even/odd frame pairs. A receiver needs both frames (or a known reference position) to resolve the full position. Mimir uses pyModeS.PipeDecoder to accumulate even/odd frame pairs per ICAO and resolve positions globally — no fixed reference point required. Positions appear within ~5 seconds of the first pair. |
| dB | Decibel | Unit of signal strength. Logarithmic scale. Values in Mimir are negative (e.g. -50 dB). Closer to 0 = stronger signal. Noise floor ≈ -50 to -60 dB. |
| FFT | Fast Fourier Transform | Maths that converts time-domain samples into frequency + strength data. Answers: "what frequencies are present and how strong is each?" |
| frame | Waterfall Frame | One row of the waterfall. Each new PSD from the server is drawn as one horizontal strip of coloured pixels. |
| Hz / MHz / GHz | Hertz / Megahertz / Gigahertz | Units of frequency. FM radio: 88–108 MHz. ADS-B: 1090 MHz. HackRF covers 1 MHz to 6 GHz. |
| IQ | In-phase / Quadrature | Raw format for SDR data. Two number streams (I and Q) that together describe amplitude and phase. "IQ data" = raw radio samples. |
| JSON | JavaScript Object Notation | Text format for structured data. PSD is sent to the browser as JSON: `{"freq_hz": [...], "power_db": [...]}`. |
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
| VGA | Variable Gain Amplifier | Second amplifier stage after LNA. Together LNA + VGA = two gain knobs. Set via `vga_gain_db`. Default: 0 dB for strong signals (FM broadcast). Weaker bands may need 20–24 dB. |
| wavelength | Wavelength | The physical length of one radio wave cycle. Higher frequency = shorter wavelength. An antenna works best when its length matches the wavelength of the signal it is receiving. |
| WebSocket | WebSocket | Persistent two-way browser–server connection. Unlike a normal HTTP request (which closes after its response), it stays open so the server can push data in real time. Mimir uses Socket.IO, which runs over WebSocket. |
| yubaba | yubaba | Prin's local LLM inference server. RTX 3060 12GB, llama.cpp. Hosts the model used by `classify_signal()`. |

---

**Phase 55 (2026-08-06):** Added radar prediction panel bundle — Bearing/Range field in AircraftDetailPanel, PredictionGlyph component (pure presentational, displays derived prediction vector), 400→rejected error mapping in LlmReasoningPanel, theta bound widening (±30→±90) in server.py validation, and radar prediction panel sizing updates in RadarPage.css. Test count: 1170 passing (823 pytest + 347 Vitest). Three LOW-55 cosmetic/consistency items were surfaced during the build; two were fixed by hand before commit (`align-self: flex-end` on `.prediction-glyph`, and `overflow-wrap: break-word` on `.radar-prediction-llm-notes`). The third — `formatBearingRange` in `AircraftDetailPanel.jsx` not applying `% 360` the way the shared `formatBearing()` in `aircraftFormat.js` does — remains open and is tracked in the Known Tech Debt table in AGENTS.md as TD-55-1.