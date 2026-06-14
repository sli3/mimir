---
description: "Mimir project wiki — pipeline reference, phase log, acronym glossary, and frontend stack. Updated by @doc-writer at the end of each build."
status: live
last_updated_phase: 9C-Threshold
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
- `modules/adsb/decoder.py` — `AdsbDecoder` (pyModeS decode with Adelaide reference position, CRC validation, field extraction into AdsbMessage)
- `modules/adsb/subscriber.py` — `AdsbSubscriber` (queue + daemon thread, frequency filter at 1090 MHz +/- 2 MHz, demodulate-decode-broadcast pipeline)

**Key functions:**

`AdsbDemodulator.demodulate(iq_chunk)` — scans the amplitude envelope of raw IQ
samples for the 8 us ADS-B preamble (high/low sample ratio >= 2.0), then extracts
112 PPM bits. Returns a list of 28-character hex strings, one per candidate frame.
Analogy: a barcode scanner looking for the right pattern of wide and narrow bars.

`AdsbDecoder.decode(raw_hex)` — validates a 28-char hex string via pyModeS (CRC,
DF17/DF18 check, typecode range), then extracts structured fields (ICAO, callsign,
altitude, position, groundspeed, track, vertical_rate). Uses a fixed Adelaide
reference position for CPR single-frame position decoding. Analogy: translating
a shorthand code into a full aircraft report.

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
| CPR | Compact Position Reporting | ADS-B position encoding scheme. Aircraft transmit latitude/longitude as compressed even/odd frame pairs. A receiver needs both frames (or a known reference position) to resolve the full position. Mimir uses a fixed Adelaide reference for single-frame decoding. |
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
| pyModeS | Python Mode S | Python library for decoding Mode S / ADS-B hex strings. Used by `AdsbDecoder` to validate CRC and extract structured fields (ICAO, callsign, altitude, position). Decode-only — no transmit capability. |
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
