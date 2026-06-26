# Mimir — Project Roadmap

> Passive RF intelligence for Adelaide, South Australia.
> Capture signals. Understand them. Never transmit.

---

## Phase Tracker

| Phase | Name                              | Status         | Tests    |
|-------|-----------------------------------|----------------|----------|
| 0     | Hardware Safety Gate              | ✅ Complete    | 25/25    |
| 1     | IQ Capture Pipeline               | ✅ Complete    | 5/5      |
| 2     | FFT + Feature Extraction          | ✅ Complete    | 21/21    |
| 3     | Embedding + Vector Store          | ✅ Complete    | 24/24    |
| 4     | LLM Classification                | ✅ Complete    | 24/24    |
| 5     | Calibration & Thresholds          | ✅ Complete    | —        |
| 6     | Live AI Classification + Dashboard| ✅ Complete    | 108/108  |
| 7A    | Cyberpunk Dashboard — Scaffold    | ✅ Complete    | 108 pytest + 50 Vitest = 158   |
| Data Layer | ACMA frequency reference + RTL-ML ChromaDB seeding | ✅ Complete | 188/188 (165 pytest + 23 new, 50 Vitest) |
| — | UV migration (pip to pyproject.toml + uv.lock) | ✅ Complete | uv sync --all-extras; uv run pytest |
| 7B    | Cyberpunk Dashboard — AI + Polish | ✅ Complete | 233/233 |
| 8A | Wire ACMA frequency_reference.json into LLM classifier user prompt | ✅ Complete | 251/251 |
| 8B | Wire real ScanRunner values into system_stats; fix AGENTS.md event table | ✅ Complete | 259/259 |
| 8C | Single-frequency focus mode + LLM tuning | ✅ Complete | 260/260 |
| 9A | ACMA Ref Expansion + /api/frequencies | ✅ Complete | 278/278 (222 pytest + 56 Vitest) |
| 9B | BUG-01 fix: bandwidth_hz/occupied_bins zero (gain red herring) | ✅ Complete | 278/278 (222 pytest + 56 Vitest) |
| 9B-Hotfix | BUG-01 true root cause: fft.py normalisation | ✅ Complete | 278/278 (222 pytest + 56 Vitest) |
| pre-9C | Latent gain defaults cleanup (housekeeping) | ✅ Complete | 278/278 (222 pytest + 56 Vitest) |
| pre-9C-seed-autowipe | seed_chromadb.py auto-wipe before seeding | ✅ Complete | 279/279 (223 pytest + 56 Vitest) |
| 9C | ACARS Decoder + Setup Infrastructure | ✅ Complete | 290/290 (223 pytest + 56 Vitest + 11 bash) |
| 9D | ACARS Pure-Python Decoder Subscriber | ✅ Complete | 305/305 (249 pytest + 56 Vitest) |
| 9E | AIS Pure-Python Decoder Subscriber | ✅ Complete | 331/331 (275 pytest + 56 Vitest) |
| 9F | ADS-B Pure-Python Decoder Subscriber | ✅ Complete | 354/354 (298 pytest + 56 Vitest) |
| 9F-CPR | ADS-B CPR Pair Accumulator | ✅ Complete | 364/364 (308 pytest + 56 Vitest) |
| 10 | Dashboard UI Redesign | ✅ Complete | 392/392 (308 pytest + 84 Vitest) |
| 10-Hotfix | Dashboard Live Testing Fixes | ✅ Complete | 395/395 (308 pytest + 87 Vitest) |
| 10-Fix2 | Waterfall GPU Scroll + Signal Details Missing Fields | ✅ Complete | 396/396 (308 pytest + 88 Vitest) |
| 10-Fix3 | Band Grouping + ADS-B Threshold + Waterfall Gap + Default Focus | ✅ Complete | 402/402 (311 pytest + 91 Vitest) |
| 10-Fix4 | Spectral Flatness + Chroma Distance + Waterfall Alignment | ✅ Complete | 402/402 (311 pytest + 91 Vitest) |
| 11 | Per-Band Signal Thresholds + All-Bands Sweep | ✅ Complete | 425/425 (328 pytest + 97 Vitest) |
| 9C-Threshold | Calibrate SIGNAL_THRESHOLD_DB | ⏳ PENDING ANTENNA | — |
| 11-Hotfix | Broadcast Defaults + FM Threshold + Startup Guard | ✅ Complete | 427/427 (330 pytest + 97 Vitest) |
| PHASE-TECH-DEBT-1 | Six backend/frontend tech debt fixes | ✅ Complete | 437/437 (332 pytest + 105 Vitest) |
| PHASE-TECH-DEBT-2 | Five frontend small fixes (tech debt) | ✅ Complete | 439/439 (334 pytest + 105 Vitest) |
| PHASE-BUILD-3 | AIS waterfall config, tuned-state test coverage, SignalHistoryLog memoisation | ✅ Complete | 446/446 (334 pytest + 112 Vitest) |
| PHASE-BAND-PROFILE-FIX | Wire band profile into handle_set_focus for per-band thresholds on frequency switch | ✅ Complete | 452/452 (340 pytest + 112 Vitest) |
| PHASE-BUILD-4 | Tech debt clean-up (setup.sh, FREQ_COLOUR_MAP, AIS nav, pin eviction, classifier prompt) | ✅ Complete | 446/446 (334 pytest + 112 Vitest) |
| PHASE-CLASSIFIER-ACCURACY-FIX | Add AIS to BAND_PROFILES; fix ACARS/AIS misclassification | ✅ Complete | 456/456 (344 pytest + 112 Vitest) |
| PHASE-12 | Decoder-driven ADS-B classification (bypass LLM for confirmed decodes) | ✅ Complete | 456/456 (344 pytest + 112 Vitest) |
| PHASE-13 | Spectral flatness embedding expansion (6D to 7D vectors) | ✅ Complete | 489/489 (368 pytest + 121 Vitest) |
| PHASE-14 | CHECKPOINT Parser Fix + AIS Band Profile | ✅ Complete | 492/492 (371 pytest + 121 Vitest) |
| 15 | Frontend AIS Consistency + Nav Bar Completion | ✅ Complete | 493/493 (371 pytest + 122 Vitest) |
| 15b | AIS Waterfall Frequency Migration Completion | ✅ Complete | 493/493 (371 pytest + 122 Vitest) |
| 17 | Feature A: focused decode panel | ✅ Complete | 496/496 (373 pytest + 123 Vitest) |
| 18 | Feature B: Raw ADS-B Hex Decode View | ✅ Complete | 507 (373 pytest + 134 Vitest) |
| 18b | Raw Decode Log — ACARS and AIS | ✅ Complete | 517 (375 pytest + 142 Vitest) |

### Phase 11 Hotfix — Broadcast Defaults + FM Threshold + Startup Guard ✅

**Goal:** Fix three issues discovered during live testing of Phase 11:
KeyError on missing broadcast fields, FM threshold too low, and unhandled
startup exception when HackRF is disconnected.

**Delivered:**
- `dashboard/server.py` — `signal_threshold_db` and `snr_margin_db` broadcast
  defaults set to `0.0`; keys reordered after `snr_db`
- `dashboard/shared_state.py` — `fm_broadcast` `signal_threshold_db` 10.0 -> 12.0,
  calibrated against live FM Adelaide at lna=24/vga=26
- `scan.py` — startup guard: `HackRFReceiver()` + `device.open()` wrapped in
  `try/except (RuntimeError, OSError)` with ERROR log and `sys.exit(1)`;
  `load_config()` intentionally left outside try/except
- `tests/test_scan.py` — 3 new tests: RuntimeError failure, OSError failure,
  success + KeyboardInterrupt -> exit 0
- `tests/dashboard/test_server_stats.py` — updated expected dict ordering

**Test counts:** 427/427 (330 pytest + 97 Vitest) at delivery. Current: 428 passing (331 pytest + 97 Vitest), 0 pre-existing pytest failures.

**Current totals: 437 tests passing (332 pytest + 105 Vitest)**

**BUG-01 status:** Code fixed in 9B-Hotfix. Full calibration deferred to Phase 9C pending telescopic whip antenna (~68 cm SMA) purchase.

---

## Phase 0 — Hardware Safety Gate ✅

**Goal:** Prove that TX is structurally impossible in software.

**Delivered:**
- `core/legal/compliance_guard.py` — `HardwareTransmitError` raised on any TX call
- `core/device/device_base.py` — abstract device interface, TX methods blocked at base
- `core/device/hackrf_rx.py` — receive-only HackRF wrapper, all TX methods blocked
- `tests/core/test_rx_only_lock.py` — 25 tests proving TX block works

**Complete when:** `python -m pytest tests/core/test_rx_only_lock.py -v` → 25/25

---

## Phase 1 — IQ Capture Pipeline ✅

**Goal:** Capture real IQ samples from the HackRF and save to disk.

**Delivered:**
- `core/pipeline/capture.py` — `capture_iq()`, `save_capture()`, `capture_and_save()`
- Accumulation loop fix — `readStream()` returns ~131k samples per call;
  loop runs until `num_samples` collected
- First real hardware capture: 98 MHz FM Adelaide verified as real signal
- `tests/core/test_capture_pipeline.py` — 5 tests

**Complete when:** Capture shape is `(2000000,)` not `(131072,)`

---

## Phase 2 — FFT + Feature Extraction ✅

**Goal:** Convert raw IQ samples into frequency-domain features.

**Delivered:**
- `core/pipeline/fft.py` — `compute_psd()` — Hann window, chunk averaging,
  fftshift centred output, absolute frequency array, DEFAULT_NFFT = 2048
- `core/pipeline/features.py` — `fingerprint_spectrum()` — peak detection,
  noise floor (10th percentile), SNR, bandwidth, occupied bins
- `tests/core/test_fft_features.py` — 20 tests (10 PSD + 10 fingerprint)

**Pipeline chain:**
```python
psd    = compute_psd(samples, sample_rate_hz=2_000_000, center_freq_hz=98_000_000)
report = fingerprint_spectrum(psd)
```

**Known tech debt:**
- BUG-01 — initially marked closed here, later found to be unresolved.
  Gain fix attempted in 9B (red herring). True root cause: fft.py
  normalisation. Fixed in Phase 9B-Hotfix.

**Complete when:** `python -m pytest tests/core/test_fft_features.py -v` → 20/20

---

## Phase 3 — Embedding + Vector Store ⬜

**Goal:** Convert spectrum fingerprints into vector embeddings and store
them in a local vector database for similarity search.

**Planned:**
- `embeddings/` module — convert fingerprint dict to embedding vector
- ChromaDB local vector store — store and query embeddings
- Similarity search — given a new fingerprint, find closest known signal
- Unit tests

**Acceptance:** Given a fingerprint dict, produce a vector embedding,
store it in ChromaDB, and retrieve it by similarity search.

---

## Phase 4 — LLM Classification ⬜

**Goal:** Use the local LLM to classify signals and detect anomalies.

**Planned:**
- Pass fingerprint + nearest neighbours to local LLM
- LLM produces signal classification and confidence score
- Anomaly detection — flag signals with no close match in vector store

---

## Phase 5 — Live Dashboard ✅

**Goal:** Real-time waterfall display with AI annotation overlay.

**Delivered:**
- Shared HackRF capture loop (single device open, broadcast to all browsers)
- FastAPI WebSocket server on port 8899
- Live waterfall canvas with percentile normalisation
- Four AU-legal band profiles: FM, Aviation, ADS-B, noise floor
- Band switching via WebSocket command channel

---

## Phase 8A — ACMA Reference Wiring ✅

**Goal:** Wire `data/frequency_reference.json` (432 ACMA spectrum allocation
entries) into the LLM classifier user prompt so the LLM receives real
regulatory context alongside the signal fingerprint.

**Delivered:**
- `llm/acma_reference.py` — `AcmaReference` class with range-based lookup
- `llm/classifier.py` — `classify()` and `_build_user_prompt()` accept
  `acma_allocations` parameter; appends ACMA SPECTRUM PLAN section when provided
- `core/pipeline/scanner.py` — `AcmaReference` instantiated once per
  `ScanRunner`; lookup called before each classify() pass
- `tests/llm/test_acma_reference.py` — 12 tests
- `tests/llm/test_phase4_classifier.py` — 6 new ACMA section tests

**Complete when:** `uv run pytest` → 195/195 + `vitest` → 56/56 = 251 total

---

## Phase 8B — Live system_stats + Event Table Fix ✅

**Goal:** Wire real ScanRunner values into system_stats (active_frequency_hz,
scan_count, queue_depth, llm_last_inference_ms are currently hardcoded zeros).
Fix AGENTS.md event table: rename focus_frequency to set_focus_frequency.

**Delivered:**
- `ScanRunner` tracks `_scan_count`, `_active_freq_hz`, `_last_llm_ms`
- `get_stats()` returns live runtime metrics
- `dashboard/server.py` emits real scanner values via `system_stats`
- `scan.py` reordered so scanner exists before `start_server()`

**Complete when:** `python -m pytest tests/` → 259/259

---

## Phase 8C — Single-Frequency Focus Mode + LLM Tuning ✅

**Goal:** Eliminate LLM queue saturation by locking the scan loop onto one
frequency at a time, and tune the LLM for faster inference.

**Delivered:**
- `core/pipeline/scanner.py` — `_scan_loop` rewritten as single-frequency focus mode
- `set_focus_frequency()` flushes queue on frequency switch to prevent stale fingerprints
- `dashboard/server.py` — `handle_set_focus` calls `scanner.set_focus_frequency()`
- `llm/classifier.py` — model swap to Qwen3-4B-Q4_K_M, `max_tokens=300`, `/no_think` suffix
- LLM inference speed: 18–23s → ~2.5s (15x speedup)
- Queue depth: permanently 20/20 → ~0/20 at steady state
- `fm_broadcast` classifying at 95–98% confidence

**Complete when:** `python -m pytest tests/` → 260/260

---

## Phase 9 — Scan Loop Polish + NOAA/Meteor-M2 Module Planning 🟡

**Goal:** Clean up remaining Phase 8C tech debt and plan satellite reception module.

**Delivered (9A):** ACMA band expansion (5->23 labels), /api/frequencies endpoint, notes pass-through
**Delivered (9B):** BUG-01 gain fix (red herring — gain raised to lna=32/vga=40, did not resolve bug)
**Delivered (9B-Hotfix):** BUG-01 true root cause fixed — fft.py normalisation corrected, true dBFS achieved
**Delivered (pre-9C-seed-autowipe):** seed_chromadb.py auto-wipe before seeding — fixed duplicate insert bug

**Remaining:**
- Fix `scan.py` startup message ("Scanning N frequencies" -> reflect single-freq mode)
- NOAA/Meteor-M2 satellite planning: 137.620, 137.9125, 137.100, 137.9 MHz
- Antenna requirements: V-dipole or QFH for 137 MHz satellite band

---

### Phase 9A — ACMA Reference Expansion + /api/frequencies ✅
Goal: Expand ACMA band coverage in LLM classifier from 5 to 23 mimir_band
labels, add notes pass-through to user prompt, fix two factual band range
errors (Marine HF, UHF CB), add handle_set_focus input validation, and
expose GET /api/frequencies Flask endpoint for frontend consumption in
Phase 9C.
Tests: 278/278 (222 pytest + 56 Vitest)

---

### Phase 9B — BUG-01 fix: bandwidth_hz/occupied_bins zero ✅ (red herring)

**Goal:** Fix BUG-01 where bandwidth_hz and occupied_bins were always zero in
live ChromaDB embeddings because production gain settings (lna=16, vga=20)
yielded only 6-10 dB live SNR, below the 27 dB SIGNAL_THRESHOLD_DB.

**Root cause (initial, incorrect):** Threshold was calibrated at lna=32/vga=40
against live FM Adelaide (98.9 MHz) but production config was never updated from
the old 16/20 values. **This turned out to be a red herring** — live hardware
testing after the fix revealed peak power was always exactly 0.0 dBFS regardless
of gain. The true root cause was in fft.py normalisation (see Phase 9B-Hotfix).

**Delivered:**
- `config/mimir.yaml` — raised lna_gain_db 16->32, vga_gain_db 20->40 (both hardware and scanner sections)
- `core/pipeline/features.py` — updated SIGNAL_THRESHOLD_DB comment with calibration context, fixed inline comment bug
- `tools/diagnose_threshold.py` — fixed header comment inaccuracy
- `tests/core/test_config_loader.py` — updated fixture and assertions for new gain values
- `tests/core/test_scanner.py` — updated fixture gain values for consistency

**Known follow-up items (outside scope):**
- `MimirConfig` dataclass defaults still at lna=16 / vga=20 (latent BUG-01 path)
- `hackrf_rx.py` DEFAULT_LNA/DEFAULT_VGA still 16/20 (used by capture_and_save)
- `config/mimir.yaml` hardware section gains duplicated but never consumed by load_config()

**Complete when:** `uv run pytest` → 278/278

---

### Phase 9B-Hotfix — BUG-01 true root cause: fft.py normalisation ✅

**Goal:** Fix the real BUG-01 root cause after Phase 9B gain fix proved to be a
red herring. Live hardware testing showed peak power was always 0.0 dBFS
regardless of gain — the fft.py normalisation was self-referential.

**Root cause:** `core/pipeline/fft.py` `compute_psd()` divided `averaged_power`
by `max_power` before converting to dBFS, forcing the peak bin to always be
0.0 dBFS by definition. This made the threshold comparison in `features.py`
mathematically impossible to pass — `occupied_bins` and `bandwidth_hz` could
never be non-zero regardless of gain settings.

**Delivered:**
- `core/pipeline/fft.py` — replaced `/max_power` with `/ (nfft * window_power)` standard Welch periodogram normalisation, producing true dBFS referenced to ADC full scale
- `core/pipeline/features.py` — set `SIGNAL_THRESHOLD_DB = 10.0` (provisional, old value derived from broken normalisation)
- `config/mimir.yaml` — set lna=0, vga=0, amp_enable=false (minimum gain prevents ADC saturation on strong Adelaide FM)
- `tools/diagnose_threshold.py` — gain defaults 0/0, expanded threshold candidates to [3,5,8,10,12,15,18,21,24,27]
- `tests/core/test_fft_features.py` — tightened PSD assertion from < -3.0 to < -10.0 for true dBFS

**Key normalisation change:**
```python
# Before (broken — peak always 0.0 dBFS):
psd = 10 * log10(averaged_power / max_power + epsilon)

# After (correct — true dBFS):
psd = 10 * log10(averaged_power / (nfft * window_power) + epsilon)
```

**Complete when:** `uv run pytest` → 278/278

---

### Phase pre-9C — Latent gain defaults cleanup (housekeeping) ✅

**Goal:** Align all remaining gain default values to the settled safe
configuration (lna=0, vga=0, amp=False). After Phase 9B-Hotfix corrected the
fft.py normalisation and set production gains to 0/0 in `config/mimir.yaml`,
four latent defaults still referenced the old 16/20 dB values.

**Delivered:**
- `core/config/loader.py` — MimirConfig dataclass defaults: lna 16.0->0.0, vga 20.0->0.0
- `core/device/hackrf_rx.py` — DEFAULT_LNA_GAIN_DB 16->0, DEFAULT_VGA_GAIN_DB 20->0
- `core/pipeline/capture.py` — capture_and_save() docstring: LNA 0 dB / VGA 0 dB
- `dashboard/shared_state.py` — BAND_PROFILES gains updated and documented per band
- `docs/wiki.md` — Phase Log, parameter descriptions, glossary entries (by @doc-writer)

**Resolved deferred items:**
- `MimirConfig` dataclass defaults (was lna=16, vga=20)
- `hackrf_rx.py` DEFAULT_LNA/DEFAULT_VGA (was 16/20)
- `capture_and_save()` docstring (was "LNA 16 dB, VGA 20 dB")
- `dashboard/shared_state.py` BAND_PROFILES inconsistent gains (now documented)

**Complete when:** `uv run pytest` → 278/278

---

### Phase pre-9C-seed-autowipe — seed_chromadb.py auto-wipe before seeding ✅

**Goal:** Fix known seed_chromadb.py tech debt where the script could insert
duplicate records into ChromaDB (800→1600 observed during re-seed). The old
`check_duplicates()` function relied on an interactive prompt which blocked
automated use.

**Delivered:**
- `tools/seed_chromadb.py` — removed `check_duplicates()`, added `wipe_collection()` that unconditionally deletes and recreates the collection before seeding, updated module docstring with data destruction warning
- `tests/tools/test_seed_chromadb.py` — removed `TestSkipDuplicateDetection` (3 tests), added `TestWipeAndReseed` (4 tests)

**Resolved deferred items:**
- `seed_chromadb.py` tech debt: script must wipe collection before inserting to prevent duplicate records — replaced interactive prompt with automatic wipe

**Complete when:** `uv run pytest` → 279/279

---

### Phase 9C — ACARS Decoder + Setup Infrastructure ✅

**Goal:** Add acarsdec build support to setup.sh for all supported OSes,
add mock test coverage for setup.sh, add ACARS frequency to config,
and update all legal/reference documentation for ACARS band coverage.

**Delivered:**
- setup.sh: `build_acarsdec()` function — builds f00b4r0/acarsdec from
  source, all OS blocks updated (Fedora/RHEL/Debian/Ubuntu/Arch/openSUSE/macOS)
- `tests/setup/test_setup_sh.sh` — bash mock suite for setup.sh (11 tests)
- `docs/au-legal-reference.md` — ACARS section added
- `config/mimir.yaml` — acars preset + frequency added
- `AGENTS.md` — prerequisites, key files, frequency table updated
- `docs/ROADMAP.md` — Phase 9C section, phase tracker updated
- `docs/wiki.md` — Phase 9C log entry and ACARS glossary entry (by @doc-writer)

**Complete when:** `bash tests/setup/test_setup_sh.sh` → all tests pass.
                `uv run pytest` → all existing tests still passing (no regressions)

**Test counts:** 290/290 (223 pytest + 56 Vitest + 11 bash)

---

### Phase 9C-Threshold — Calibrate SIGNAL_THRESHOLD_DB ⏳ PENDING ANTENNA

**Goal:** Run `tools/diagnose_threshold.py` on live hardware with the new
telescopic whip antenna (SMA, ~1 GHz optimised) to derive the final
`SIGNAL_THRESHOLD_DB` value and align all production gain settings.

**Background:** The stock stub antenna nearly saturated the HackRF at FM
frequencies in Adelaide with lna=0/vga=0. The new telescopic whip has poor
coupling at FM wavelengths (~3 m), requiring gain to compensate. Initial
calibration produced lna=24/vga=26 and threshold 24 dB but requires live
re-validation with the antenna before final sign-off.

**Delivered:**
- `core/pipeline/features.py` — `SIGNAL_THRESHOLD_DB`: 10.0 → 24.0 dB.
  Calibrated at lna=24/vga=26, FM Adelaide 98.9 MHz. Method:
  tools/diagnose_threshold.py threshold sweep, target 200 kHz FM channel width.
- `config/mimir.yaml` — scanner gain: lna=0/vga=0 → lna=24/vga=26
- `core/config/loader.py` — `MimirConfig` defaults: lna_gain_db 0.0→24.0,
  vga_gain_db 0.0→26.0
- `core/device/hackrf_rx.py` — `DEFAULT_LNA_GAIN_DB` 0→24,
  `DEFAULT_VGA_GAIN_DB` 0→26, docstring updated
- `dashboard/shared_state.py` — `BAND_PROFILES` fm_broadcast: lna 0→24,
  vga 0→26. Comment updated to explain antenna mismatch at FM wavelengths.
- `tools/diagnose_threshold.py` — `LNA_GAIN_DB` 0→24, `VGA_GAIN_DB` 0→26,
  saturation comment updated to reflect new antenna behaviour
- ChromaDB re-seeded via `tools/seed_chromadb.py` — reference embeddings
  regenerated with corrected gain and threshold values

**Deferred:**
- `tools/calibrate_thresholds.py` CALIBRATION_TARGETS still uses old gain
  values (lna=32/vga=40 for FM, etc.) — needs updating in a future phase
- `tools/diagnose_fingerprints.py` TARGETS still uses old gain values —
  needs updating in a future phase
- Other BAND_PROFILES entries (aviation, adsb) need revalidation with the
  new telescopic whip antenna — gains were set for the stock stub

**Test counts:** 362/362 (306 pytest + 56 Vitest) at calibration time. Current: 427 passing (330 pytest + 97 Vitest), 1 pre-existing pytest failure.

---

### Phase 9F — ADS-B Pure-Python Decoder Subscriber ✅

**Goal:** Add ADS-B (1090 MHz) decoding to Mimir's shared IQ bus, following
the established ACARS (9C/9D) and AIS (9E) subscriber pattern.

**Delivered:**
- `modules/adsb/constants.py` — AU ADS-B frequency (1090 MHz) and demodulation constants
- `modules/adsb/message.py` — AdsbMessage dataclass (icao, callsign, altitude, position, velocity)
- `modules/adsb/demodulator.py` — AdsbDemodulator — PPM demodulation + pulse extraction from IQ samples
- `modules/adsb/decoder.py` — AdsbDecoder — message frame parsing + pyModeS v3 decode with single-frame CPR position resolution
- `modules/adsb/subscriber.py` — AdsbSubscriber — IQ bus subscriber + decode thread (queue maxsize=64, timeout=0.1s)
- `dashboard/server.py` — `emit_adsb_aircraft()` for SocketIO broadcast
- `dashboard/frontend/src/hooks/useSocket.js` — `adsb_aircraft` event handler + state (keyed by ICAO, max 30, 90s expiry)
- `dashboard/frontend/src/components/AdsbAircraftPanel.jsx` — cyberpunk aircraft table
- `dashboard/frontend/src/App.jsx` — AdsbAircraftPanel added to grid
- `scan.py` — registered AdsbSubscriber, start()/stop()
- `pyproject.toml` — added `pyModeS>=3.0`
- `docs/au-legal-reference.md` — updated ADS-B legal section
- `tests/modules/test_adsb_message.py` — 5 tests
- `tests/modules/test_adsb_demodulator.py` — 6 tests
- `tests/modules/test_adsb_decoder.py` — 6 tests
- `tests/modules/test_adsb_subscriber.py` — 6 tests

**Key decisions:**
- pyModeS v3 `decode(msg, reference=(lat, lon))` used for single-frame airborne CPR
  position resolution (v2's `position_with_ref()` removed in v3).
- Empty-ICAO guard in decoder to avoid broadcasting invalid frames.
- Surface position messages (typecodes 5-8) not decoded; acceptable for Adelaide.

**Known debt:**
- `PREAMBLE_THRESHOLD = 2.0` provisional — requires live field testing.
- CPR pair accumulator (even/odd frames without fixed reference) deferred.

**Complete when:** `uv run pytest` → 354/354 (298 pytest + 56 Vitest)

---

### Phase 9F-CPR — ADS-B CPR Pair Accumulator ✅

**Goal:** Upgrade the ADS-B decoder from single-frame CPR position resolution
(requiring a fixed lat/lon reference) to a stateful per-ICAO CPR pair accumulator
that pairs even/odd frames and resolves positions globally.

**Background:** Phase 9F used pyModeS `decode()` with a fixed Adelaide reference
lat/lon. This worked but introduced position error for aircraft far from the
reference point and could not resolve positions for aircraft whose even and odd
CPR frames arrive at different times. `pyModeS.PipeDecoder` handles frame pairing
and global resolution automatically.

**Delivered:**
- `modules/adsb/decoder.py` — replaced stateless `pms_decode()` with `pyModeS.PipeDecoder`:
  per-ICAO even/odd frame buffering, 10-second pairing window, global position
  resolution without fixed reference, 300-second stale state eviction, flush()
  cycle every 5 seconds (BOOTSTRAP_K=5) to release positions for intermittent aircraft
- `modules/adsb/decoder.py` — optional `timestamp: float | None = None` param on `decode()`
  for test determinism (defaults to `time.time()` internally)
- `modules/adsb/decoder.py` — new `flush()` method exposed for tests and graceful shutdown
- `modules/adsb/constants.py` — ADELAIDE_LAT/ADELAIDE_LON comments updated (retained for
  diagnostic/fallback use only, no longer used for primary decoding)
- `tests/modules/test_adsb_decoder.py` — three position tests rewritten: single frame yields
  no position; pair + flush yields valid global position; non-position fields unaffected
  by accumulator change
- `docs/wiki.md` — Phase 9F-CPR entry, CPR glossary update, pyModeS glossary update

**Key decisions:**
- PipeDecoder chosen over manual even/odd frame pairing for robustness and upstream maintenance
- BOOTSTRAP_K=5 to avoid premature position release for aircraft with intermittent reception
- 300-second stale eviction matches ADS-B transponder reporting rates (typically 0.5-1 Hz)

**Known debt:**
- `modules/adsb/message.py` stale comments: latitude/longitude field comments still say
  "from position_with_ref()" — should reference "from PipeDecoder global CPR pair resolution"
- `AdsbSubscriber.stop()` does not call `decoder.flush()` — bootstrap-held positions
  silently discarded at shutdown
- DF11 test path: `test_non_adsb_downlink_format_returns_none` uses a 28-char DF11 string
  which hits `InvalidLengthError` rather than the DF gate directly

**Test counts:** 364/364 (308 pytest + 56 Vitest)

---

### Phase PHASE-TECH-DEBT-1 — Six backend/frontend tech debt fixes ✅

**Goal:** Address six accumulated tech debt items across the backend and frontend: misleading startup message, fragile test dict equality, missing fatal-error test coverage, stale ADS-B comments, dead frontend parameter, and the open ADS-B subscriber flush gap.

**Delivered:**

1. **`scan.py` startup message** — `main()` print updated from "Scanning N frequencies" to "Focus mode: cycling through N band(s) one at a time", accurately reflecting single-frequency focus mode. (cosmetic fix for Post-8C item)

2. **`tests/dashboard/test_server_stats.py`** — `TestFocusFrequencyFilter.test_filter_passes_matching` and `.test_passes_all_when_focus_is_none`: replaced strict `payload["key"]` assertions with `payload.get("key")` subset-iteration pattern using an Expected dict, so future broadcast field additions do not break the test. (resolves strict dict equality tech debt)

3. **`tests/test_scan.py`** — Added `TestScanStartupErrors.test_fatal_error_exits_with_code_1` covering the generic-Exception → `sys.exit(1)` path (MED-01). Also patched `scan.time.sleep` in the autouse fixture to remove a ~1s real sleep. (resolves MED-01)

4. **`modules/adsb/message.py`** — `AdsbMessage.latitude`/`longitude` docstrings updated from "from position_with_ref()" (stale pyModeS v2 API) to "from PipeDecoder global CPR pair resolution (no fixed reference)". (resolves Phase 9F-CPR stale comment debt)

5. **`dashboard/frontend/src/hooks/useWaterfall.js`** — Removed unused `sampleRateHz` parameter from hook destructuring, from `WaterfallPanel.jsx` call site, and from 3 test call sites in `useWaterfall.test.js`. (resolves `sampleRateHz` dead param tech debt)

6. **`modules/adsb/subscriber.py`** — `AdsbSubscriber.stop()`: added `self._decoder.flush()` before `self._running = False` to release bootstrap-held ADS-B positions before shutdown. (partial step toward full harvest-and-emit pattern — see below)

**Code review conflict adjudication:**
- @review-second found zero issues across all 6 changes
- @deep-analyst found MAJOR-01: `flush()` in `stop()` is functionally inert and introduces thread-safety concerns (decode thread calls `decode()` which calls `pipe.flush()` every 5s internally; flush before `_running=False` may help the last iteration but does not harvest results)
- PM adjudication: Accepted as an incremental improvement. The harvest gap is recorded as open tech debt.

**Resolved deferred items:**
- `scan.py` startup message (Post 8C cosmetic) — message now accurate
- `test_server_stats.py` strict dict equality — using subset-iteration pattern
- `sampleRateHz` dead param in useWaterfall.js — removed from all call sites
- `modules/adsb/message.py` stale comments (Phase 9F-CPR) — updated to PipeDecoder reference
- MED-01: scan.py fatal error exit path — test coverage added

**Partially resolved:**
- `AdsbSubscriber.stop()` flush gap (Phase 9F-CPR) — flush() added but harvest gap remains open

**Test counts:** 437/437 (332 pytest + 105 Vitest)

---

### Phase PHASE-BUILD-3 — AIS waterfall config, tuned-state test coverage, SignalHistoryLog memoisation ✅

**Goal:** Add AIS (161.975 MHz) to the waterfall STRIP_CONFIGS so the single-band
waterfall renders correctly when tuned to AIS; add ACARS/AIS tuned-state test
coverage for the three-state logic (NOT TUNED / TUNED / TUNED+EMPTY); wrap
SignalHistoryLog in React.memo with a custom comparator for re-render optimisation.

**Delivered:**
1. **`dashboard/frontend/src/components/WaterfallPanel.jsx`** — Added AIS
   (161.975 MHz, `--neon-red`) to STRIP_CONFIGS, bringing total to 7 entries.
   The singleBand waterfall now renders AIS data correctly when tuned to AIS.

2. **`dashboard/frontend/src/components/SignalHistoryLog.jsx`** — Wrapped in
   `React.memo` with a custom comparator that checks `pinnedTimestamp` identity
   and `scanResults` content equality (shallow item comparison), preventing
   unnecessary re-renders when unrelated state changes.

3. **`dashboard/frontend/src/tests/AdsbTunedState.test.jsx`** — Refactored with
   `makeMock` helper. Added ADS-B NOT TUNED test (now 2 tests for ADS-B).

4. **`dashboard/frontend/src/tests/AcarsTunedState.test.jsx`** (NEW) — 2 tests
   covering ACARS NOT TUNED and TUNED+EMPTY three-state logic.

5. **`dashboard/frontend/src/tests/AisTunedState.test.jsx`** (NEW) — 2 tests
   covering AIS NOT TUNED and TUNED+EMPTY three-state logic.

6. **`dashboard/frontend/src/tests/WaterfallPanel.test.jsx`** — Updated canvas
   count assertion (12→14), added AIS label and name assertions, added AIS click
   test (now 18 tests, up from 11).

**Resolved deferred items:**
- ACARS sub-panel 130.025 MHz inconsistency (Phase 10-Hotfix) — `isAcarsTuned()` helper
  added to App.jsx, ORs both 129.125 and 130.025 MHz checks with 5 kHz margins
- Missing ACARS/AIS tuned-state tests (Phase 10-Hotfix) — test coverage added
- AIS waterfall STRIP_CONFIGS (Phase 10-Hotfix) — AIS now in STRIP_CONFIGS

**Partially resolved:**
- AIS missing from OVERVIEW_BANDS — STRIP_CONFIGS resolved, but App.jsx
  OVERVIEW_BANDS and BAND_GROUPS still list only 6 bands (AIS absent from nav bar)

**Open deferred items surfaced:**
- AIS missing from OVERVIEW_BANDS — after adding AIS to STRIP_CONFIGS (now 7),
  App.jsx OVERVIEW_BANDS and BAND_GROUPS still have 6 entries. Nav bar overview
  waterfall omits AIS. Requires adding AIS to both OVERVIEW_BANDS and BAND_GROUPS.

**Test counts:** 446/446 (334 pytest + 112 Vitest)

---

### Phase PHASE-BAND-PROFILE-FIX — Wire band profile into handle_set_focus for per-band thresholds on frequency switch ✅

**Goal:** Make per-band `signal_threshold_db` values actually apply when the user
switches frequencies via the dashboard. Previously, `handle_set_focus` retuned the
HackRF but never updated `shared_state.current_band`, so every non-FM band was
evaluated against the FM broadcast threshold (21.0 dB), suppressing Aviation VHF
(~11 dB SNR) and keeping bandwidth_hz/occupied_bins at zero.

**Delivered:**

1. **`dashboard/shared_state.py`** — Added `get_band_for_freq(freq_hz)` — returns
   a dict copy of the matching BAND_PROFILES entry, or None if no match.
   Thread-safe by design (read-only, returns copy). Depends on dict insertion
   order for the `fm_broadcast`/`noise_floor` ambiguity at 98 MHz — documented
   in docstring.

2. **`dashboard/server.py`** — Added `import dashboard.shared_state as shared_state`.
   Updated `handle_set_focus` to call `shared_state.get_band_for_freq(freq_hz)` and
   update `shared_state.current_band` under `current_band_lock` when a known band
   frequency is detected.

3. **`tests/dashboard/test_shared_state.py`** — 4 new tests (TestGetBandForFreq class):
   test_known_band_returns_profile, test_unknown_band_returns_none,
   test_fm_broadcast_found, test_matches_frequency_within_margin.

4. **`tests/dashboard/test_server_stats.py`** — 2 new tests in TestFocusFrequencyFilter:
   test_focus_wires_shared_state_band, test_focus_unknown_does_not_set_band.

**Open tech debt surfaced:**
- BAND_PROFILES dict ordering dependency (fm_broadcast vs noise_floor at 98 MHz)
- Clear-focus (None) path does not reset current_band — acceptable under current architecture
- Thread-safety stress test does not exercise current_band_lock write path

**Test counts:** 452/452 (340 pytest + 112 Vitest)

---

### Phase PHASE-BUILD-4 — Tech debt clean-up ✅

**Goal:** Address accumulated tech debt items: setup.sh rewrite, FREQ_COLOUR_MAP
consolidation, AIS navigation wiring, pin eviction logic, and classifier prompt
improvements.

**Delivered:**
- setup.sh rewrite for uv sync + uv export workflow
- requirements.txt removed (replaced by pyproject.toml + uv.lock)
- PYTHONPATH=. requirement documented throughout
- FREQ_COLOUR_MAP consolidated
- AIS navigation wiring fixes
- Pin eviction logic improvements
- Classifier prompt refinements

**Test counts:** 446/446 (334 pytest + 112 Vitest)

---

### Phase PHASE-CLASSIFIER-ACCURACY-FIX — ACMA reference entries for ACARS and AIS ✅

**Goal:** Fix ACARS and AIS misclassification by adding AIS to BAND_PROFILES
and expanding ACMA reference entries so the LLM classifier can distinguish
ACARS from AIS signals.

**Delivered:**
- AIS added to BAND_PROFILES with appropriate threshold and gain settings
- ACMA reference entries expanded for ACARS and AIS bands
- Classifier prompt updated to include ACARS and AIS as valid signal types

**Test counts:** 456/456 (344 pytest + 112 Vitest)

---

### Phase PHASE-12 — Decoder-driven ADS-B classification ✅

**Goal:** Bypass the LLM pipeline for confirmed ADS-B decodes. When the
AdsbSubscriber successfully decodes an aircraft message, emit a scan_result
event directly with ground-truth confidence, giving the Signal History log
instant ADS-B entries.

**Delivered:**
- `modules/adsb/subscriber.py` — optional `scan_result_fn` callback parameter
  and call site in decode loop
- `dashboard/server.py` — `emit_adsb_scan_result()` function with focus filter
  (suppresses emissions when user is focused on non-ADS-B bands)
- `scan.py` — wired `emit_adsb_scan_result` as `scan_result_fn`
- `tests/modules/test_adsb_subscriber.py` — 3 new tests
- `tests/dashboard/test_server_stats.py` — 7 new tests (TestEmitAdsbScanResult class)

**Key decisions:**
- Confidence set to 1.0 / confidence_score 1.0 because ADS-B decoding is
  ground-truth (not LLM inference)
- Focus filter uses existing AU_ADSB_FREQUENCY_HZ and FREQ_TOLERANCE_HZ
  constants from modules/adsb/constants.py
- No frontend changes required — existing scan_result handler in useSocket.js
  already processes these events

**Test counts:** 456/456 (344 pytest + 112 Vitest)

---

### Phase PHASE-13 — Spectral flatness embedding expansion (6D to 7D vectors) ✅

**Goal:** Add `spectral_flatness` (Wiener entropy) as the 7th dimension of the
embedding vector in `embeddings/embedder.py`, enabling ChromaDB similarity
search to leverage a feature already computed by the pipeline and displayed
in the dashboard.

**Delivered:**
- `embeddings/embedder.py` — "spectral_flatness" added to EMBEDDING_FEATURES
  (index 6) and NORMALISATION_RANGES; docstrings updated 6→7
- Existing tests updated: 6D→7D assertions across 4 test files
- ChromaDB wiped and re-seeded: 800 records inserted as 7D vectors

**Key changes:**
- Embedding dimensionality: 6 → 7
- No new tests added — existing assertions updated in-place (count unchanged)
- ChromaDB distance thresholds in `llm/classifier.py` now stale (calibrated
  for 6D L2 distance) — tracked under 9C-Threshold

**Test counts:** 489/489 (368 pytest + 121 Vitest), 0 failures

---

### Phase 14 — CHECKPOINT Parser Fix + AIS Band Profile ✅

**Goal:** Fix the longstanding CHECKPOINT flag parsing issue where `$2` was
silently dropped with long multi-line task strings, and correct the AIS
band profile centre frequency to match the dual-channel demodulator.

**Delivered:**

1. **`.opencode/command/build.md`** — PHASE-TRACKER GATE updated to support
   both `$2 CHECKPOINT` positional flag AND `CHECKPOINT_MODE: ON` embedded
   in the task body. Fixes the longstanding issue where `$2` was silently
   dropped when `$1` was a long multi-line string.

2. **`dashboard/shared_state.py`** — BAND_PROFILES["ais"]: centre frequency
   corrected from 161_975_000 Hz (CH1 only) to 162_000_000 Hz (matching
   `modules/ais/constants.py` AU_AIS_CENTRE_FREQ_HZ, the correct dual-channel
   centre between CH1 161.975 MHz and CH2 162.025 MHz). Gains adjusted from
   24/26 to 16/20 (consistent with VHF-low peers aviation/ACARS). Entry
   reordered after APRS (cosmetic -- ascending frequency order).

3. **`tests/dashboard/test_shared_state.py`** — 3 new/updated tests pinning
   the corrected AIS BAND_PROFILES values and documenting the known
   frontend/backend frequency mismatch.

**Deferred:**
- Frontend/backend AIS frequency mismatch: frontend still hardcodes 161.975 MHz.
  When user clicks AIS, `get_band_for_freq(161_975_000)` returns None so AIS
  threshold/gains not applied. HackRF retunes correctly (unconditional) so
  reception works, but band profile config is stale. Fix in a future phase.

**Test counts:** 492/492 (371 pytest + 121 Vitest), 0 failures

---

### Phase 15 — Frontend AIS Consistency + Nav Bar Completion ✅

**Goal:** Align all frontend AIS frequency references to match the Phase 14
backend BAND_PROFILES correction (162.000 MHz centre), and add AIS to the
nav bar overview waterfall.

**Delivered:**

1. **`dashboard/frontend/src/App.jsx`** — BAND_GROUPS and OVERVIEW_BANDS
   updated from 161.975 MHz to 162.000 MHz (matches backend BAND_PROFILES).
   `isTuned()` tuned-state check updated with 100 kHz tolerance around
   162.000 MHz. `focusFrequency` call updated to send 162000000. Display
   text strings updated. JSDoc comments added to `isTuned()` and
   `isAcarsTuned()`.

2. **`dashboard/frontend/src/tests/App.test.jsx`** — Added regression test
   for AIS button click calling `focusFrequency(162000000)`. Updated test
   title from 6 to 7 band buttons.

3. **`dashboard/frontend/src/tests/AisTunedState.test.jsx`** — Updated
   frequency assertions from 161975000 to 162000000 and display text to
   match App.jsx changes.

**Research notes:**
- AIS dual-channel structure: CH1 161.975 MHz, CH2 162.025 MHz, centre 162.000 MHz
- Backend subscriber accepts +/-100 kHz tolerance around 162.000 MHz centre
- Centre-frequency with 100 kHz tolerance pattern used for isTuned()

**Test counts:** 493/493 (371 pytest + 122 Vitest), 0 failures

**Deferred:**
- Fix 3 (queue max audit) deferred per task specification — no action taken
- WaterfallPanel.jsx STRIP_CONFIGS AIS entry still uses 161975000 (AIS waterfall frozen)
- SignalHistoryLog.jsx and AisVesselPanel.jsx use stale 161.975 MHz references

---

### Phase 15b — AIS Waterfall Frequency Migration Completion ✅

**Goal:** Complete the remaining AIS frequency migration across all frontend
components that Phase 15 left at 161.975 MHz. Phase 15 updated App.jsx
(BAND_GROUPS, OVERVIEW_BANDS, isTuned, focusFrequency) but four other
components still referenced the old CH1 frequency, causing the AIS waterfall
to freeze when tuned, visual degradation in signal history, and fragile
frequency checks in the vessel panel.

**Delivered:**

1. **`dashboard/frontend/src/components/WaterfallPanel.jsx`** — STRIP_CONFIGS
   AIS entry updated: `freq_hz` 161975000 -> 162000000, `label` '161.975 MHz'
   -> '162.000 MHz'. JSDoc comment updated to note all configs now in sync.

2. **`dashboard/frontend/src/components/SignalHistoryLog.jsx`** — FREQ_COLOUR_MAP
   key updated 161975000 -> 162000000. `freqLabel()` return value updated
   '161.975 MHz' -> '162.000 MHz'.

3. **`dashboard/frontend/src/components/AisVesselPanel.jsx`** — `isAisFreq`
   centre constant updated 161_975_000 -> 162_000_000. Display text updated
   'Listening on 161.975 MHz...' -> 'Listening on 162.000 MHz...'.

4. **`dashboard/frontend/src/components/FrequencyList.jsx`** — FREQ_CONFIGS AIS
   entry updated: `freq_hz` 161975000 -> 162000000, `label` '161.975 MHz' ->
   '162.000 MHz'.

5. **`dashboard/frontend/src/tests/WaterfallPanel.test.jsx`** — Updated 3 AIS
   frequency assertions (label, test title, expected value) to 162000000 /
   '162.000 MHz'.

**No backend changes. No new features. No hardware required.**

**Resolved deferred items:**
- WaterfallPanel.jsx STRIP_CONFIGS AIS entry (Phase 15 deferred)
- SignalHistoryLog.jsx FREQ_COLOUR_MAP stale 161.975 MHz reference
- AisVesselPanel.jsx isAisFreq fragile centre constant
- FrequencyList.jsx FREQ_CONFIGS stale AIS entry (discovered during sweep)
- "Frontend/backend AIS frequency mismatch" tech debt item fully resolved

**Test counts:** 493/493 (371 pytest + 122 Vitest), 0 failures

---

### Phase 18 — Feature B: Raw ADS-B Hex Decode View ✅

**Goal:** Display raw ADS-B hex message data in the dashboard, allowing users
to inspect the original transponder frames alongside decoded aircraft fields.

**Delivered:**
1. **`dashboard/server.py`** — `emit_adsb_aircraft()` now includes `raw_hex`
   field in the SocketIO event payload (pass-through from `AdsbMessage`).
   Docstring updated.

2. **`dashboard/frontend/src/hooks/useSocket.js`** — Added `adsbRawLog` state
   as a ring buffer (cap 50, newest-first) keyed by ICAO. Handles `adsb_aircraft`
   events, prepending `raw_hex` entries with timestamp. Defensive guard
   `if (!data.raw_hex) return prev` handles legacy events without the field.

3. **`dashboard/frontend/src/App.jsx`** — Destructures `adsbRawLog` from
   `useSocket()` and passes it as a prop to `AdsbAircraftPanel`.

4. **`dashboard/frontend/src/components/AdsbAircraftPanel.jsx`** — Added
   `hexToBin()` and `hexToSpaced()` helper functions. Added RAW DECODE section
   with HEX/BIN toggle, rendering hex bytes or binary representation from the
   ring buffer. RAW DECODE section always renders when panel is mounted (parent
   already gates on ADS-B tuned state).

5. **`AGENTS.md`** — Updated SocketIO event table: `adsb_aircraft` payload
   now includes `raw_hex`.

6. **`dashboard/frontend/src/tests/AdsbRawDecode.test.jsx`** (NEW) — 8 tests:
   hexToBin correctness, hexToBin error handling, hexToSpaced formatting,
   empty log renders empty state, raw hex bytes rendered, binary toggle works,
   timestamp formatting, ring buffer cap at 50.

**Key decisions:**
- No TX code introduced — pure display layer only
- Ring buffer cap at 50 matches existing `adsbAircraftHistory` pattern
- Defensive guard handles legacy events without `raw_hex` field gracefully
- RAW DECODE section always renders when `AdsbAircraftPanel` is mounted
  (parent already gated on ADS-B tuned state via Phase 17 wrappers)

**Known debt (optional polish):**
- `emit_adsb_aircraft()` has zero unit tests (LOW priority — field is
  trivial pass-through)
- `hexToBin`/`hexToSpaced` could be exported to `utils/` for better testability
- `key={idx}` in RAW DECODE render could use composite key for React best practice

**Test counts:** 507 (373 pytest + 134 Vitest), 0 failures

---

### Phase 18b — Raw Decode Log — ACARS and AIS ✅

**Goal:** Extend the raw decode log concept from Phase 18 (ADS-B `raw_hex`)
to ACARS (decoded text) and AIS (`raw_nmea` sentences), giving users visibility
into the raw decoder output for all three decoder sub-panels.

**Delivered:**
1. **`dashboard/server.py`** — `emit_acars_message()` now includes `raw` field
   (pass-through from `AcarsMessage.text`). `emit_ais_message()` now includes
   `raw` field (pass-through from `AisMessage.raw_nmea`).

2. **`dashboard/frontend/src/hooks/useSocket.js`** — Added `acarsRawLog` and
   `aisRawLog` ring-buffer states (cap 50, newest-first). Both include
   defensive guards for legacy events without the `raw` field.

3. **`dashboard/frontend/src/App.jsx`** — Destructures `acarsRawLog` and
   `aisRawLog` from `useSocket()` and passes them as props to
   `AcarsMessagePanel` and `AisVesselPanel`.

4. **`dashboard/frontend/src/components/AcarsMessagePanel.jsx`** — Added
   RAW DECODE section showing decoded ACARS text from the ring buffer.

5. **`dashboard/frontend/src/components/AisVesselPanel.jsx`** — Added
   RAW DECODE section showing raw NMEA sentences from the ring buffer.

6. **`AGENTS.md`** — Updated SocketIO event table: `acars_message` and
   `ais_message` payloads now include `raw`.

7. **`tests/dashboard/test_server_emit.py`** — new pytest tests for `raw`
   field presence in ACARS and AIS emission payloads.

8. **`dashboard/frontend/src/tests/AcarsRawLog.test.jsx`** (NEW) — 4 tests.

9. **`dashboard/frontend/src/tests/AisRawLog.test.jsx`** (NEW) — 4 tests.

10. Updated `useSocket` mocks in 7 existing test files to include
    `acarsRawLog: []` and `aisRawLog: []`.

**Key decisions:**
- No TX code introduced — pure display layer only
- Phase 18 ring-buffer pattern translated cleanly to ACARS and AIS
- ACARS raw shows decoded text; AIS raw shows raw NMEA sentences
- Both follow 50-entry cap and newest-first ordering

**Test counts:** 517 (375 pytest + 142 Vitest), 0 failures

---

## Known Tech Debt

| Item | Detail | Fix in |
|---|---|---|
| `config/mimir.yaml` not loaded | Runtime config loading not yet implemented | Phase 2+ |
| ~~`scan.py` startup message~~ | ~~Misleading "Scanning N frequencies" in single-freq mode~~ | ~~Post 8C~~ ✅ |
| ~~MED-01: scan.py fatal error exit~~ | ~~`except Exception` sets fatal_error=True but no test verifies exit code 1~~ | ~~PHASE-TECH-DEBT-1~~ ✅ |
| ADS-B gain divergence | tools use (32/38) for ADS-B gain, shared_state.py uses (24/24). Both tool values labelled provisional. | Live ADS-B test |
| ~~Frontend/backend AIS frequency mismatch~~ | ~~Frontend hardcodes 161.975 MHz (CH1). BAND_PROFILES expects 162.000 MHz (dual-channel centre). `get_band_for_freq(161_975_000)` returns None, so AIS threshold/gains not applied. HackRF retunes correctly (unconditional), so reception works but band profile config is stale.~~ Fixed across Phase 15 (BAND_GROUPS, OVERVIEW_BANDS, isTuned, focusFrequency) and Phase 15b (STRIP_CONFIGS, FREQ_COLOUR_MAP, isAisFreq, FREQ_CONFIGS). All frontend AIS references now use 162.000 MHz. | ~~Post-Phase 14~~ ✅ Phase 15 + 15b |