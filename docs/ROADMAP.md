# Mimir — Project Roadmap

> Passive RF intelligence for Adelaide, South Australia.
> Capture signals. Understand them. Never transmit.

---

## Phase Tracker

| Phase | Name                              | Status         | Tests    |
|-------|-----------------------------------|----------------|----------|
| BUG-03 | Tool gain/threshold sync to BAND_PROFILES | ✅ Complete | 557 (408 pytest + 149 Vitest) |
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
| 19a | calibrate_thresholds.py — missing bands + ADS-B gain fix | ✅ Complete | 517 (375 pytest + 142 Vitest) |
| 19b | calibrate_thresholds.py — antenna selection, single-band prompt, matrix split | ✅ Complete | 517 (375 pytest + 142 Vitest) |
| 19c | classifier.py — ChromaDB distance threshold recalibration | ✅ Complete | 517 (375 pytest + 142 Vitest) |
| 20 | Live Capture to Vector Store Ingestion Tool | ✅ Complete | 526 (384 pytest + 142 Vitest) |
| 22 | LLM Offline Handling — health check + cooldown system | ✅ Complete | 548 (399 pytest + 149 Vitest) |
| 22-Hotfix | LLM offline emit rate-limit (SocketIO flood fix) | ✅ Complete | 551 (402 pytest + 149 Vitest) |
| 23 | ChromaDB Vector Space 3D Visualisation (isolated side page) | ✅ Complete | 581/581 (419 pytest + 162 Vitest) |
| 24 | OPERATOR Live Anomaly Readout — 4-state badge, novel exposure, tooltip | ✅ Complete | 591/591 (420 pytest + 171 Vitest) |
| 25 | Max-hold burst fingerprinting for ADS-B | ✅ Complete | 606 (435 pytest + 171 Vitest) |
| 26 | calibrate_thresholds.py — derive_thresholds() pure helper, ordering guard, mutually-exclusive noise classification, relative colours, STRONG_MATCH_FLOOR | ✅ Complete | 620 (449 pytest + 171 Vitest) |
| 27 | calibrate_thresholds.py — ADS-B captures raised to 5, p90 same-type spread, CROSS_TYPE_MIN_FLOOR, check_thresholds_cli.py | ✅ Complete | 624 (453 pytest + 171 Vitest) |
| 28 | Cross-session calibration merge + antenna groups + persistence | ✅ Complete | 634 (463 pytest + 171 Vitest) |
| 29 | Live capture loop — forward per-band signal_threshold_db to fingerprint_spectrum() | ✅ Complete | 640 (469 pytest + 171 Vitest) |
| 30 | Spectral cropping for fingerprint_spectrum() — per-band crop_half_width_hz | ✅ Complete | 646 (475 pytest + 171 Vitest) |
| 31 | Decoder panel tuned-state cleanup (isAdsbTuned() helper + Phase 17 dead-branch removal) | ✅ Complete | 646 (475 pytest + 171 Vitest) |
| 32 | Confidence Provenance Gating — dim unverified confidence via `source` field on scan_result | ✅ Complete | 656 (477 pytest + 179 Vitest) |
| 33-Hotfix | Classifier confidence cap + vectordb SNR tools (hotfix, RETROACTIVE — code shipped, tests in 34) | ✅ Complete | 656 (477 pytest + 179 Vitest) [tests added in Phase 34] |
| 34 | Test coverage for Phase 33 classifier cap + vectordb tools (TEST-ONLY) | ✅ Complete | 677 (498 pytest + 179 Vitest), 0 failures |
| 35 | Pluto receiver wrapper — RX-only `PlutoReceiver` SoapySDR wrapper | ✅ Complete | counted at merge — see 36-Hotfix |
| 36 | Device capability + detection layer — DEVICE_PROFILES, enumerate/detect, PLUTO_BAND_PROFILES, band_supported_by_device | ✅ Complete | counted at merge — see 36-Hotfix |
| 36-Hotfix | Pluto hardware bring-up — four SWIG/SoapySDR bugs (by hand) + soapy_doubles.py test infrastructure | ✅ Complete | 741 (562 pytest + 179 Vitest), 0 failures |
| 37 | Device selection wiring — `--device {hackrf,plutosdr}` flag, `build_device()` factory, `ScanRunner` band-skip guard | ✅ Complete | 772 (593 pytest + 179 Vitest), 0 failures |
| 37-Hotfix-1 | Pluto waterfall adaptive per-row colour scaling (frontend-only) | ✅ Complete | 772 (593 pytest + 179 Vitest) — Vitest unchanged |
| 37-Hotfix-2 | ACARS decimation fix + decode-path verification (decoder confirmed correct; no live ACARS present) | ✅ Complete | 781 (602 pytest + 179 Vitest), 0 failures |
| 38 | Device-aware unsupported-band UI — backend addition (current_device + system_stats fields) + frontend greying (opacity 0.35, not-allowed cursor, native title tooltip); empty map = zero visual change for HackRF. **Note:** Phase 35 memo incorrectly scoped this as "frontend-only"; corrected here. | ✅ Complete | 795 (610 pytest + 185 Vitest), 0 failures |
| 38-Hotfix-1 | Tooltip fix: removed `disabled` from BAND_GROUPS buttons (HTML `disabled` suppresses native `title` tooltips). Click guard via onClick omission only. Backend untouched. 5 new regression tests. | ✅ Complete | 800 (610 pytest + 190 Vitest), 0 failures |
| 39 | Pluto gain calibration tooling — `capture_iq_pluto()` + `tools/diagnose_pluto_gain.py` gain sweep (ISM 915 + ADS-B 1090) with interpretation aid. Existing `capture_iq()` byte-for-byte unchanged; existing `diagnose_threshold.py` / `calibrate_thresholds.py` untouched. **No calibrated gain values written — `PLUTO_BAND_PROFILES` placeholders (30.0 / 3.0) stay until the operator runs the new tool on hardware.** | ✅ Complete | 814 (624 pytest + 190 Vitest), 0 failures |

---

### BUG-04 — /vectordb Tooltip Frequency Field Mismatch ✅

**What:** The /vectordb hover tooltip showed FREQ as '---' for seeded ChromaDB
records because `api_vectorstore_points()` read `meta.get("freq_hz")` while
`tools/seed_chromadb.py` writes the frequency under `"center_freq_hz"`.

**Files changed:**
- `dashboard/server.py` — `api_vectorstore_points()` now uses
  `meta.get("center_freq_hz", meta.get("freq_hz"))` so both seeded records and
  live captures resolve correctly.
- `tests/dashboard/test_server_api.py` — added
  `test_center_freq_hz_metadata_key_populates_frequency_hz` covering the seed-key
  path, precedence over `freq_hz` when both keys are present, and null
  snr_db/peak_power_db/timestamp for seed records.

**Investigation outcomes:**
- TASK 2 (colour case): No mismatch. `normaliseLabel()` in `VectorSpacePage.jsx`
  lowercases labels before indexing `VECTOR_COLOUR_MAP`, so uppercase stored
  labels resolve correctly.
- TASK 3 (live-capture keys): No mismatch. `tools/capture_to_vectorstore.py`
  writes `freq_hz`, `snr_db`, `peak_power_db`, and `timestamp` — matching the
  endpoint keys.

**RF/Legal notes:** No TX surfaces; all changes passive RX-only.

**Test counts:** 582 passing (420 pytest + 162 Vitest), 0 failures.

---

### BUG-03 — Tool Gain/Threshold Sync to BAND_PROFILES ✅

**What:** Wired four diagnostic/calibration tools to read per-band `lna_gain_db`,
`vga_gain_db`, and (where applicable) `signal_threshold_db` from
`dashboard.shared_state.BAND_PROFILES` instead of hardcoded literals.

**Files changed:**
- `tools/capture_to_vectorstore.py` — `CAPTURE_TARGETS` now reads all three fields from `BAND_PROFILES`.
- `tools/calibrate_thresholds.py` — `CALIBRATION_TARGETS` gains now read from `BAND_PROFILES` (thresholds already live).
- `tools/diagnose_fingerprints.py` — `TARGETS` gains now read from `BAND_PROFILES`; `noise_floor` intentionally stays at (16, 20).
- `tools/diagnose_threshold.py` — `BAND_SWEEP` gains now read from `BAND_PROFILES`.
- `tests/tools/test_capture_to_vectorstore.py` — updated metadata test; added guard test.
- `tests/tools/test_diagnose_threshold.py` — added guard test.
- `tests/tools/test_calibrate_thresholds.py` — new guard test file.
- `tests/tools/test_diagnose_fingerprints.py` — new guard test file.

**Key behavioural fix:** `tools/diagnose_fingerprints.py` AIS gains corrected from
hardcoded (24, 26) to `BAND_PROFILES['ais']` (16, 20), matching production capture.

**Deferred items:**
1. `diagnose_fingerprints.py` runs its capture loop at module import time. Future refactor: add `if __name__ == "__main__":` guard.
2. `diagnose_threshold.py` `BAND_SWEEP` has no AIS entry (pre-existing).

**RF/Legal notes:** No TX surfaces; all changes passive RX-only.

**Test counts:** 557 passing (408 pytest + 149 Vitest), 0 failures.

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

### Phase 20 — Live Capture to Vector Store Ingestion Tool ✅

**Goal:** Add a standalone tool that captures live IQ samples from the HackRF
across all AU-legal receive bands, runs them through the full pipeline (FFT,
features, embedding), and stores the resulting vectors directly in the
production ChromaDB store at `data/vectorstore/`. This is the fast path to
seeding the production store with fresh live vectors.

**Delivered:**
1. **`tools/capture_to_vectorstore.py`** (NEW) — Standalone CLI tool.
   Antenna selection at startup (telescopic whip, V-dipole, spiral discone);
   only bands within the antenna's usable range are captured. Iterates all
   eligible bands, captures IQ samples, computes PSD + fingerprint + embedding,
   and inserts into production ChromaDB. Append by default; `--wipe` flag
   deletes and recreates the collection before capturing. ADS-B, ACARS, and
   AIS bands warn the user before the first capture because those require
   live aircraft or vessel signals. Prints summary of records stored and a
   reminder to run `calibrate_thresholds.py`. All frequencies AU/SA legal;
   no TX code, no `amp_enable=True`, no direct SoapySDR import.

2. **`tests/tools/test_capture_to_vectorstore.py`** (NEW) — 9 tests:
   - structure (argparse, band iteration, antenna mapping)
   - antenna coverage (all 3 antennas produce valid band lists)
   - metadata (embedding dimensionality, band label presence)
   - 5-capture loop (captures across multiple bands without error)
   - RuntimeError recovery (single-band failure does not abort tool)
   - `--wipe` flag (collection deleted and recreated before capture)
   - Ctrl+C skip (KeyboardInterrupt during capture is handled gracefully)
   - per-band `signal_threshold_db` passthrough (BAND_PROFILES threshold
     used for each band's fingerprint computation)

3. **`tests/tools/test_seed_chromadb.py`** — Updated ISM assertions from
   433 MHz to 915 MHz to match current `CLASS_META`.

4. **`docs/wiki.md`** — Phase 20 log entry, function entries for
   `capture_to_vectorstore`, ChromaDB glossary update (by @doc-writer).

5. **`README.md`** — Phase 20 tracker row added; tool usage section with
   `--wipe` flag documented; recommended tool workflow updated (by @doc-writer).

**Known debt / deferred items:**
- `tools/diagnose_fingerprints.py` gain values now read from `BAND_PROFILES` — resolved in BUG-03.
- ChromaDB distance reference stale (Phase 13) remains open; tool prints
  a reminder to re-run `tools/calibrate_thresholds.py` after capture.
- `--wipe` flag prints a warning but has no interactive confirmation
  (accepted as non-blocking for this phase).
- Concurrent writes to `data/vectorstore/` if `scan.py` is running are
  documented in README (user must stop scan.py first).

**Test counts:** 526 (384 pytest + 142 Vitest), 0 failures

---

### Phase 22 — LLM Offline Handling ✅

**Goal:** Add a configurable LLM health-check and cooldown system to prevent the scanner from hanging when the local LLM server is unreachable.

**Delivered:**
- `llm/classifier.py` — New `check_connection()` method probes `GET {base_url}/models` at startup and on demand. Cooldown system: only `ConnectionError` triggers `_offline_until`; HTTP errors/malformed JSON → `signal_type="unavailable"`. Auto-recovery clears `_offline_until` on successful response.
- `llm/classifier.py` — `classify()` fast-fails during cooldown with `signal_type="llm_offline"` and zero network calls.
- `config/mimir.yaml` — Added optional `llm_cooldown_sec` (default 60.0) and `llm_connect_timeout_sec` (default 5.0).
- `core/config/loader.py` — Extended `MimirConfig` dataclass with new LLM timeout fields.
- `scan.py` — Calls `classifier.check_connection()` at startup before creating `ScanRunner`; does NOT exit or raise on failure.
- Frontend: `AIReasoningPanel.jsx` and `SignalHistoryLog.jsx` display `llm_offline` in amber with "LLM OFFLINE" label.
- Tests: 9 new pytest tests in `tests/llm/test_classifier_offline.py`; 1 existing pytest test renamed/updated in `tests/llm/test_phase4_classifier.py`; 1 new Vitest test in `dashboard/frontend/src/tests/AIReasoningPanel.test.jsx`.

**Deferred items recorded:**
1. **SIGNAL_THRESHOLD_DB discrepancy**: Field log reported 21 dB threshold, project memory says 27 dB. Value lives in `core/pipeline/features.py`. Needs verification against live file before next calibration run.
2. **scanner.py `_llm_call_count` inflation during offline/cooldown**: The AI loop increments `_llm_call_count` even when `classify()` fast-fails during cooldown, inflating the metric. Consider fixing in a future phase.
3. **Timeout in `classify()` does not trigger cooldown**: Per explicit Phase 22 spec, only `ConnectionError` in `classify()` sets cooldown; `Timeout` still returns `unavailable`. `check_connection()` does treat Timeout as offline. Asymmetry could be addressed in a future robustness pass.

**Test counts:** 557 (408 pytest + 149 Vitest), 0 failures

---

### Phase 25 — Max-hold Burst Fingerprinting for ADS-B ✅

**Goal:** Add a max-hold PSD trace to `compute_psd()` so short ADS-B Mode S Extended
Squitter bursts (~120 μs at 1090 MHz) are not diluted by the existing averaged
Welch trace. Only ADS-B switches to the max-hold trace in this phase; all
continuous bands remain on the averaged trace.

**Delivered:**
1. **`core/pipeline/fft.py`** — `compute_psd()` now returns `psd_max_hold_db`
   alongside `psd_db`. Both traces use identical Welch periodogram normalisation
   (`/ (nfft * window_power)`). Empty-array early-return paths preserve the new
   key. Docstring frequency-resolution corrected to ~976.6 Hz at nfft=2048 and
   2 MSa/s.

2. **`core/pipeline/features.py`** — `fingerprint_spectrum()` gains an optional
   `trace_key` parameter defaulting to `'psd_db'`. All downstream feature maths
   (peak, noise floor, SNR, bandwidth, occupied bins) operate on whichever
   trace is selected.

3. **Tool wiring (ADS-B only):**
   - `tools/capture_to_vectorstore.py` — ADS_B target carries
     `trace_key='psd_max_hold_db'`; call site forwards
     `target.get('trace_key', 'psd_db')`.
   - `tools/calibrate_thresholds.py` — Same ADS_B-only max-hold pattern.
   - `tools/diagnose_threshold.py` — ADS-B band entry carries max-hold key.
   - `tools/diagnose_fingerprints.py` — `TARGETS` converted to dicts; ADS_B entry
     carries max-hold key.
   ACARS, AIS, and all continuous bands remain on the averaged trace.

4. **Tests** — Added coverage for `psd_max_hold_db` key/shape/invariant,
   early-return empty arrays, `psd_db` regression snapshot, `trace_key` selection,
   missing-key error, and ADS-B-only max-hold configuration across all four tools.

**Field-session notes / deferred items:**
- Max-hold raises the apparent noise floor. The operator must run
  `diagnose_threshold.py` for ADS_B first, update `BAND_PROFILES['adsb']['signal_threshold_db']`,
  and only then run `capture_to_vectorstore.py` for ADS-B. Existing ADS_B vectors
  in the store are on the averaged basis and are not directly comparable to new
  max-hold vectors; consider clearing the existing ADS_B cluster before re-capturing.
- ACARS and AIS share the burst characteristic with ADS-B but are intentionally
  left on the averaged trace. Extending max-hold to them must be bundled with
  their own field threshold recalibration.

**Test counts:** 606 (435 pytest + 171 Vitest), 0 failures

---

### Phase 26 — calibrate_thresholds.py Ordering Guard + Relative Colours + Strong-Match Floor ✅

**Goal:** `calibrate_thresholds.py` had two independent copies of the STRONG_MATCH /
POSSIBLE_MATCH / DIFFERENT_TYPE / NOVEL_SIGNAL derivation logic (one in the matrix
column-stats block, one in the pairwise-stats block), used stale absolute-distance
colour cutoffs left over from the 6D embedding era (Phase 13 moved to 7D), double
counted `noise_floor` pairs against both same-type and cross-type buckets, and could
silently emit `STRONG_MATCH = 0.000` on very clean captures — none of which was
caught because nothing checked whether `cross_type_min` was actually large enough
relative to `same_type_max` for the four thresholds to stay monotonic.

**Delivered:**

1. **`tools/calibrate_thresholds.py`** —
   - New pure helper `derive_thresholds(same_type_max, cross_type_min) -> dict`
     replacing both inline derivation sites. Returns `ok`, `strong_match`,
     `possible_match`, `different_type`, `novel_signal`, `reason`.
   - `SEPARABILITY_FACTOR = 2.5` — ordering guard requires
     `cross_type_min > SEPARABILITY_FACTOR * same_type_max` for a monotonic
     threshold set to exist. When it fails, the distance matrix and stats still
     print (for diagnosis) but a FAIL banner replaces the paste-ready threshold
     block, `logger.warning()` fires, and the tool exits non-zero — no
     bad thresholds can be silently pasted into `llm/classifier.py`.
   - `STRONG_MATCH_FLOOR = 0.002` — floors `strong_match` so a very clean
     same-type capture set can't round the strong-match ceiling down to
     `0.000` (which would make every future capture register as "strong match"
     regardless of actual distance).
   - Pair classification made mutually exclusive (`if / elif / elif` instead of
     three independent `if`s): a `noise_floor` pair is now noise-only, never
     also double-counted into cross-type. `noise_min` now measures genuine
     noise-to-signal separation instead of an inflated mixed bucket.
   - Summary-stat terminal colours (green/yellow/red) now computed relative to
     the run's own `same_type_max` / `cross_type_min` values via the
     `SEPARABILITY_FACTOR` ratio, retiring the stale hardcoded 6D-era absolute
     cutoffs (`0.010` / `0.022` / `0.031`).

2. **Tests** — 5 new tests in `tests/tools/test_calibrate_thresholds.py`:
   monotonic-output parametrised case, the 2026-07-08 real inverted-ADS-B
   overlap run reproduced as a regression test, strong-match floor engaging,
   floor NOT overriding when the computed value already clears it, and the
   exact-boundary (`cross == SEPARABILITY_FACTOR * same`) case correctly
   failing under strict inequality.

**Field-session origin:** Found via a live ADS-B calibration run on 2026-07-08
where `same_type_max` (0.0179) exceeded `cross_type_min / 2.5` (0.0143), meaning
the ADS-B same-type captures were less self-similar than they were to other
signal types — a genuinely unusable calibration that the tool would previously
have turned into paste-ready (but meaningless) thresholds without complaint.

**Deferred items:**
- The ordering guard uses `same_type_max` (worst-case), which one noisy capture
  can dominate. Addressed in Phase 27 by switching to the 90th percentile.

**Test counts:** 620 (449 pytest + 171 Vitest), 0 failures

---

### Phase 27 — ADS-B Captures Raised to 5 + p90 Same-Type Spread + Absolute Noise Floor ✅

**Goal:** Phase 26's ordering guard closed the silent-bad-threshold hole, but two
gaps remained from the same 2026-07-08 field session: (1) `same_type_max` is a
worst-case statistic — a single near-noise ADS-B capture window (no aircraft
overhead) can dominate and fail the guard even when most captures were clean;
(2) the `SEPARABILITY_FACTOR` ratio gate can pass by coincidence on a fully
degenerate run where both `same_type` and `cross_type` distances have collapsed
into noise-level jitter, since the ratio only compares them to each other, not
to any absolute floor.

**Delivered:**

1. **`tools/calibrate_thresholds.py`** —
   - `CALIBRATION_TARGETS` ADS-B capture count raised from 2 to 5, reducing the
     odds that a single near-noise window (no aircraft in range during capture)
     dominates the same-type statistic.
   - `derive_thresholds()` same-type metric changed from `max()` to the 90th
     percentile (`np.percentile(same_type_dists, 90)`), both at the matrix
     column-stats call site and the pairwise-stats call site — a lone outlier
     capture no longer single-handedly fails the ordering guard.
   - `CROSS_TYPE_MIN_FLOOR = 0.005` — a new **absolute** floor, independent of
     the `SEPARABILITY_FACTOR` ratio. Catches the case found in the live
     2026-07-08 degenerate run where `cross_type_min` collapsed to noise-level
     (~0.0005) and the ratio gate passed by coincidence (both values were tiny)
     even though neither number carried real signal — the run that had
     previously produced meaningless near-zero pasted thresholds.
   - FAIL banner text de-hardcoded from ADS-B-specific wording to generic,
     band-agnostic remediation guidance (applies to any band's degenerate run).
   - `cross_type_min` itself is unchanged — still the worst-case `min()`, since
     for cross-type separation the worst case (closest pair) is the one that
     actually matters for classifier safety.

2. **`tools/check_thresholds_cli.py`** (new file) — standalone harness for the
   pure `derive_thresholds()` guard logic, independent of any live capture.
   Two modes: a self-check suite of fixed test cases, and `--eval SAME CROSS`
   for evaluating an arbitrary pair by hand. Intended for pre-commit sanity
   checks and field verification without needing the HackRF connected.

3. **Tests** — 4 new tests in `tests/tools/test_calibrate_thresholds.py`
   covering the floor gate: the exact 2026-07-08 degenerate run now correctly
   fails via `CROSS_TYPE_MIN_FLOOR` (not just the ratio), a case where the
   ratio alone would pass but the absolute floor still correctly fails it, the
   floor boundary (`cross == CROSS_TYPE_MIN_FLOOR`) passing under `>=`, and
   floor-failure vs. overlap-failure producing distinct, distinguishable
   `reason` strings so an operator can tell "dead capture" from "genuinely
   overlapping classes" at a glance.

**Independent of** the separate `BAND_PROFILES['fm_broadcast']['signal_threshold_db']`
recalibration (27.0 → 21.0 dB) done via `diagnose_threshold.py` in the same
field session — that was a live hardware calibration value change, not a
`calibrate_thresholds.py` guard-logic change, and is not part of this phase.

**Test counts:** 624 (453 pytest + 171 Vitest), 0 failures

---

### Phase 28 — Cross-session Calibration Merge ✅

**Goal:** Make `calibrate_thresholds.py` persist the calibration vectorstore across
runs so per-band thresholds survive restarts, exclude stale bands from the merged
ladder, and drive antenna selection by band group rather than a single hardcoded value.

**Delivered:**

1. **`embeddings/store.py`** — `SignalStore.delete_by_label(label)` for targeted
   deletion of stored calibration entries by band label.

2. **`tools/calibrate_thresholds.py`** — Full rewrite:
   - Calibration vectorstore persists across runs (no longer wiped at startup).
   - `--wipe` CLI flag for full re-baseline.
   - `STALENESS_DAYS = 14` constant and `_compute_band_freshness()` helper; stale
     bands excluded from the merged ladder.
   - Startup summary prints each stored band's age and FRESH/STALE status.
   - Replace-per-band logic: `delete_by_label` for each band before writing new
     captures.
   - Merge logic: fresh captures + stored non-stale records for bands not captured
     this run.
   - Band-driven antenna groups replace single hardcoded antenna selection, with
     mid-run antenna-swap prompts.
   - Cross-type minimum pair reporting in threshold analysis.
   - Testable helpers `_merge_stored_entries` and `_find_cross_type_min_pair`.

3. **Tests** — 11 new pytest tests (3 `delete_by_label` + 8 staleness/merge/cross-type).

**Test counts:** 634 (463 pytest + 171 Vitest), 0 failures

**Field-session notes / deferred items:**
- Real multi-antenna merged calibration run (telescopic + spiral) still pending.
- `llm/classifier.py` `_DISTANCE_SCALE_REFERENCE` update after real merged run.
- ADS_B `signal_threshold_db` field recalibration against max-hold trace still pending.

---

### Phase 29 — Live capture loop forwards per-band signal_threshold_db to fingerprint_spectrum() ✅

**Goal:** Make the live dashboard capture loop honour the per-band
`signal_threshold_db` values already defined in `BAND_PROFILES` when it
fingerprints each spectrum frame. Previously the loop called
`fingerprint_spectrum(psd_result)` with no `signal_threshold_db` kwarg, so
every band (FM 21 dB, ADS-B 3 dB, AIS 5 dB, etc.) was fingerprinted against
the module-level fallback of 24.0 dB. This over-suppressed weak bands
(`occupied_bins`/`bandwidth_hz` stuck at zero for anything below 24 dB SNR)
and made the live fingerprints dimensionally inconsistent with the offline
capture tool (`tools/capture_to_vectorstore.py`), which already passes the
per-band threshold.

**Delivered:**

- `dashboard/capture_loop.py` — one-line change at the fingerprint call site:
  `fingerprint_spectrum(psd_result)` →
  `fingerprint_spectrum(psd_result, signal_threshold_db=band.get("signal_threshold_db"))`.
  `band` is the per-iteration band snapshot taken under `current_band_lock`
  (line 49); `band.get()` returns `None` defensively if the key is ever
  absent, in which case `fingerprint_spectrum` falls back to 24.0 dB — no crash.
- `tests/dashboard/test_capture_loop.py` (NEW) — 2 tests using
  `asyncio.run()` directly (no pytest-asyncio dependency). A shared helper
  drives `run_shared_capture_loop` through exactly one fingerprint iteration
  via the real event loop + default ThreadPoolExecutor, with
  `HackRFReceiver` / `compute_psd` / `fingerprint_spectrum` patched. A
  `side_effect` captures the forwarded `signal_threshold_db`, then sets
  `band_change_event` and `shutdown_event` so the loop exits cleanly. Tests:
  - `test_fm_band_threshold_forwarded_to_fingerprint_spectrum` (expected 21.0)
  - `test_adsb_band_threshold_forwarded_to_fingerprint_spectrum` (expected 3.0,
    proving the forwarding is per-band, not a single value)

**Out of scope (explicitly deferred per task spec):**

- `trace_key` is NOT forwarded. The live ADS-B path stays on the averaged
  trace (`psd_db`) until a field session recalibrates the ADS-B threshold
  against the max-hold trace.
- No changes to gains, centre frequencies, sample rate, `num_samples`,
  `fingerprint_spectrum()` itself, `BAND_PROFILES` values, or the
  occupied-bins/bandwidth cropping logic.

**Test counts:** 640 (469 pytest + 171 Vitest), 0 failures

**Red-then-green verification:** Both new tests confirmed to FAIL on the
pre-change code (`got [None]` — bare call forwards no kwarg) and PASS on the
patched code (`got [21.0]` / `got [3.0]`).

**Deferred items:**

- Forwarding `trace_key=band.get("trace_key", "psd_db")` to switch the live
  ADS-B path to max-hold — blocked on the ADS-B max-hold field
  recalibration (see Phase 25 deferred items and Phase 28 session memo).

---

### Phase 30 — Spectral Cropping for fingerprint_spectrum() ✅

**Goal:** Restrict peak search, occupied_bins, and bandwidth to per-band windows defined by `crop_half_width_hz` in BAND_PROFILES, while keeping noise floor and waterfall broadcast at full span.

**Delivered:**

- `core/pipeline/features.py`: `fingerprint_spectrum()` checks `band.get("crop_half_width_hz")` before computing peak index, occupied bins, and bandwidth. Falls back to module defaults when field is absent.
- Noise floor (`noise_floor_db`) uses the full PSD span — unaffected by crop.
- Waterfall broadcast remains full-span (no change to spectrum_update payload).
- Placeholder values verified for aviation, acars, ais, ism, adsb (5 of 8 bands).

**Test counts:** 646 passing (475 pytest + 171 Vitest), 0 failures.

---

### Phase 32 — Confidence Provenance Gating ✅

**Goal:** Visual honesty. The dashboard was displaying "95%" confidence in bright neon-green even when the classification was purely a frequency + ChromaDB proximity guess with no real signal behind it. The AI reasoning text was honest; the headline number wasn't.

**What was delivered (8 files):**

- `dashboard/server.py` — Added `"source": "fingerprint"` to `broadcast()` and `'source': 'decode'` to `emit_adsb_scan_result()`. Inline docstrings added. TODO comment on `snr_margin_db` 0.0 default.
- `dashboard/frontend/src/hooks/useSocket.js` — `source: null` in `INITIAL_AI_REASONING`, `source: data.source ?? null` in scan_result handler. JSDoc updated.
- `dashboard/frontend/src/App.jsx` — `handlePinReasoning` carries `source`, `snr_db`, `bandwidth_hz`. Telemetry rows use an IIFE to compute `isConfirmedDecode`, `hasRealMeasurement`, `dimConfidence`. CONFIDENCE value/bar use `var(--text-dim)` when dimmed.
- `dashboard/frontend/src/components/AIReasoningPanel.jsx` — Same gate logic. Confidence value span uses `var(--text-dim)` when dimmed. JSDoc updated.
- `tests/dashboard/test_server_stats.py` — `TestScanResultSourceProvenance` class (2 tests).
- `dashboard/frontend/src/tests/useSocket.test.js` — 4 toEqual updated for `source: null`; 2 new tests for source propagation.
- `dashboard/frontend/src/tests/App.test.jsx` — Restructured mock to manual `vi.mock(...)`; 3 new gate tests.
- `dashboard/frontend/src/tests/AIReasoningPanel.test.js` — 3 new gate tests.

**Provenance semantics:**

The `scan_result` payload now carries a `source` field with two values:

- `"fingerprint"` — Classification from the LLM pipeline (frequency + ChromaDB proximity). Unverified by ground truth.
- `"decode"` — Classification from the ADS-B decoder (PipeDecoder). Ground truth, confidence_score=1.0.

**The gate:**

```javascript
const isConfirmedDecode = source === "decode";
const hasRealMeasurement = snr_db != null && bandwidth_hz != null;
const dimConfidence = !isConfirmedDecode && !hasRealMeasurement;
```

When `dimConfidence` is true, the confidence value and bar render with `var(--text-dim)` instead of normal brightness. Confirmed ADS-B decodes always keep full brightness regardless of other fields.

**Snr_db / bandwidth_hz indirection:**

Both paths emit nulls on these fields when there is no real measurement (e.g. a pure frequency match with no PSD data). The gate must key off provenance (`source`) rather than trusting these values, since their absence is itself informative — it means there was no spectrum data to analyse.

**Test counts:** 656 passing (477 pytest + 179 Vitest), 0 failures.

**Deferred items:**

- **snr_margin_db 0.0 default** — `dashboard/server.py` `broadcast()` defaults `snr_margin_db` to `0.0` when the fingerprint lacks it, making a missing margin indistinguishable from a real +0.0 dB margin. Phase 32 provenance gate sidesteps this for confidence display, but a missing margin should ideally default to `None`. TODO comment added in source. Deferred from Phase 32.
- **App.jsx INITIAL_AI_REASONING divergence** — `INITIAL_AI_REASONING` in App.jsx does not include `source: null`, creating a small inconsistency with the gate logic that expects it. Flagged as LOW by @deep-analyst and @analyst. Deferred.

---

### Phase 33 — Classifier Confidence Cap + Vectordb SNR Tools (hotfix, retroactive) ✅

**Type:** Hotfix. Code was already committed and hardware-validated on origin/main
(`dadae70` + `007d8dd`) before a phase number was assigned; this entry is retroactive
governance bookkeeping. Test coverage follows in Phase 34.

**Problem.** A noise blip at an ACMA-allocated frequency could score 95%/HIGH confidence
purely from its location. A 5.7 dB SNR, 5 kHz-wide, 0.987-flatness blip at 1090.000 MHz
rendered a bright-green "ADSB" verdict before the fix. Root cause: `confidence_score` is set
entirely by the LLM, and the prompt told the LLM that ACMA/frequency was authoritative and
took precedence over vector-store neighbour evidence.

**What was delivered (`llm/classifier.py`):**

- `bandwidth_hz`, `occupied_bins`, and `snr_margin_db` are now wired into the user prompt with
  plain-English labels (previously computed upstream by `fingerprint_spectrum()` but silently
  dropped).
- System prompt reordered: vector-store neighbours + measured signal characteristics are now
  PRIMARY evidence; ACMA/frequency is demoted to a plausibility check — "noise at an allocated
  frequency still matches the allocation."
- Deterministic post-LLM cap `_apply_confidence_caps()`: clamps `confidence_score` to 0.4/"low"
  when EITHER `snr_margin_db` < `_MARGIN_FLOOR_DB` (6.0 dB), OR `occupied_bins` <= 1 AND
  `spectral_flatness` >= 0.9 (single-bin spike that is also noise-flat — narrow tonal signals
  with low flatness are deliberately spared by the AND condition).
- A previously-attempted `peak_bin_power_db`/"burst structure" label was removed entirely — it
  is uncalibrated and mislabelled real FM broadcast as ADS-B. Not to be reintroduced until real
  ADS-B and real FM captures establish true per-band gap distributions.

**Vectordb SNR maintenance tools:**

- `tools/inspect_snr.py` — read-only per-label SNR histogram + `--max-snr` preview.
- `tools/delete_low_snr.py` — guarded destructive delete: dry-run default, timestamped backup
  before any real delete, typed exact-record-count confirmation, aborts cleanly if backup fails.

**Safety contract:** `classify()` (fingerprint path) and `emit_adsb_scan_result()` (decode path)
are mutually exclusive per signal — a confirmed ADS-B decode never routes through the cap, so a
real aircraft cannot be dimmed by it. Verified in the caller code and locked in by Phase 34
regression tests.

**Test counts:** 656 at ship time (477 pytest + 179 Vitest) — unchanged by the hotfix code
itself; automated coverage added in Phase 34.

---

### Phase 34 — Test Coverage for Phase 33 (test-only) ✅

**Goal.** Add the automated coverage the Phase 33 hotfix shipped without. Test-only phase — no
production logic changed.

**What was delivered:**

- `tests/llm/test_classifier_confidence_caps.py` — `_apply_confidence_caps` cap-fires cases
  (1090 MHz noise margins +1.7/+2.9 dB; single-bin + near-white flatness), cap-does-NOT-fire on
  a strong 104.7 MHz FM signal (margin +23.1, flatness 0.005) and on the narrow-tonal carve-out,
  graceful degradation on missing/None fields, plus prompt-content regression guards (evidence
  reorder present; demoted-ACMA framing present; burst/`peak_bin_power_db` text absent).
- `tests/tools/test_inspect_snr.py` and `tests/tools/test_delete_low_snr.py` — read-only
  invariant, strict-less-than selection (on-threshold record excluded), dry-run default,
  backup-before-delete, typed-confirmation gate, backup-failure abort, happy-path delete. Shared
  `tests/tools/conftest.py` temp-store fixture; production `data/vectorstore` never touched.
- `tests/dashboard/test_server_stats.py` — caller-separation regression tests (static: decode
  emitter never references `classify(`/`_apply_confidence_caps`; behavioural: payload carries
  `source="decode"`, `confidence_score=1.0`).
- `tests/llm/test_phase4_classifier.py` — two stale ACMA-section assertions updated to match the
  Phase 33 prompt (which intentionally names "ACMA allocation" in the evidence-priority text even
  with no allocations passed).

**Test counts:** **677 passing (498 pytest + 179 Vitest), 0 failures** — both suites
live-verified (`uv run pytest` from the repo root with `PYTHONPATH=.`; `npm run test` from
`dashboard/frontend`). pytest is +21 from the 477 baseline; Vitest unchanged at 179.

---

### Phase 35 — Pluto Receiver Wrapper ✅

**What:** `PlutoReceiver`, an RX-only SoapySDR wrapper for the ADALM-PLUTO, mirroring
the HackRF wrapper's receive-only contract. Pluto is TX-capable hardware, so the
zero-TX rule is enforced in software: the wrapper requests `SOAPY_SDR_RX` streams only
and never touches the TX stream API. Unlike `hackrf_rx.py`, it captures the real
`SOAPY_SDR_RX` constant from SoapySDR at `open()` rather than hardcoding the direction,
because assuming that value on TX-capable hardware was judged unacceptable.

**Files changed:**
- `core/device/pluto_rx.py` — new `PlutoReceiver` wrapper (RX-only).
- `tests/core/test_pluto_rx.py` — wrapper test coverage.

**Known at ship / resolved in 36-Hotfix:** shipped green with all tests passing, three
agent reviews clean — but could not open its device on real hardware. Two of the four
36-Hotfix bugs live here (SWIG `.get()` on enumeration results; `SoapySDR.Device()`
requiring string args, not a dict). One test (`test_usb_uri_preferred_over_ip`) had
encoded the dict form as the specification.

**RF/Legal notes:** Pluto is TX-capable; zero-TX enforced in software. RX stream only,
TX stream API never referenced. No TX surfaces.

**Test counts:** merged at the 35+36 checkpoint — see 36-Hotfix for the verified total.

---

### Phase 36 — Device Capability + Detection Layer ✅

**What:** Device profiles plus runtime detection/selection so Mimir knows which SDR is
present and what each can physically and legally cover.

**Files changed:**
- `core/device/profiles.py` — `DEVICE_PROFILES`. HackRF 1 MHz–6 GHz, split gain, max
  62.0 dB. Pluto 325–3800 MHz, combined gain, max 74.5 dB. Both ranges verified against
  official vendor docs (Great Scott Gadgets hackrf repo; wiki.analog.com Pluto specs),
  cited in the docstring.
- `core/device/detect.py` — `enumerate_devices()`, `detect_device(preferred=None)`,
  frozen `DetectedDevice` dataclass. Returns the wrapper **class**, never an instance.
  HackRF is preferred when both are present (Pluto stays uncalibrated until Phase 39).
- `dashboard/shared_state.py` — appended `PLUTO_BAND_PROFILES` (all 8 bands; only `ism`
  and `adsb` `supported=True`; the six bands below Pluto's 325 MHz floor carry
  `supported=False` + a reason string) and `band_supported_by_device(band, device)`.
  Additive-only append — zero existing content lines removed.
- `core/device/pluto_rx.py` — docstring band count corrected "four of seven" →
  "six of eight".

**Design decision:** the `supported` flag is the source of truth (Option B), with one
cross-check test proving it agrees with `DEVICE_PROFILES` frequency limits.

**RF/Legal notes:** No TX surfaces; all changes passive RX-only.

**Test counts:** merged at the 35+36 checkpoint — see 36-Hotfix for the verified total.

---

### Phase 36-Hotfix — Pluto Hardware Bring-Up (four bugs, fixed by hand) ✅

**What:** First real-hardware run of the Pluto path surfaced four bugs that 30+ passing
tests had certified as working. All fixed by hand, not via a `/build` prompt. The root
cause in three of the four was that test mocks were more permissive than the SWIG-wrapped
C++ objects the hardware actually returns.

**The four bugs:**
1. `detect.py` — `result.get("driver")` raised `AttributeError`: SoapySDR's
   `Device.enumerate()` returns SWIG-wrapped C++ maps, not dicts — no `.get()`. Every
   test mocked it with plain dicts, which *do* have `.get()`.
2. `pluto_rx.py` — the same bug at three call sites in `open()`'s URI-discovery block.
3. `pluto_rx.py` — `SoapySDR.Device({"driver": ..., "uri": ...})` raises `make() no
   match`; the identical values as a string `"driver=plutosdr,uri=usb:3.19.5"` open the
   device. SWIG dict marshalling doesn't produce Kwargs matching what the plugin's
   `find()` returns; the string path uses the plugin's own parser. `hackrf_rx.py` has
   always used the string form — which is why it always worked.
4. (Logged in Phase 35 review, fixed here) `hackrf_rx.py` hardcodes RX direction where
   `pluto_rx.py` captures the real `SOAPY_SDR_RX` at open. Not currently a divergence bug
   (`SOAPY_SDR_RX == 1` today) but asymmetric; tracked as remaining tech debt.

**Fixes:** `dict(r)` conversion at the enumeration boundary in both files; string args in
`pluto_rx.py` `open()`.

**New test infrastructure:**
- `tests/core/soapy_doubles.py` — `FakeSoapySDRKwargs`, which deliberately has **no**
  `.get()` method, mimicking the real SWIG object. All SoapySDR enumeration mocks in
  `test_detect.py` and `test_pluto_rx.py` migrated onto it. Four guard tests protect the
  double itself (if someone adds `.get()` for convenience, every test using it silently
  reverts to proving nothing). Full fail-before (21 failures) / pass-after cycle
  demonstrated.

**Verified live on hardware (2026-07-17):**
- `enumerate_devices()` → `['hackrf', 'plutosdr']` with both plugged in; `detect_device()`
  correctly selects HackRF; `detect_device('plutosdr')` correctly forces Pluto.
- `PlutoReceiver` opened its device for the first time and pulled 65,536 complex64 samples
  at 1090 MHz, 30 dB gain, mean abs 0.00058. AGC read-back, explicit bandwidth, and stream
  setup all proven in that run. (Pluto's USB URI changes every replug; the `usb:` entry is
  preferred over the two `ip:pluto.local` entries it also advertises.)

**RF/Legal notes:** Pluto is TX-capable; zero-TX enforced in software. RX stream only. No
TX surfaces.

**Test counts:** **741 passing (562 pytest + 179 Vitest), 0 failures** — both suites
live-verified at the merge checkpoint (`PYTHONPATH=. uv run pytest` from repo root;
`npm run test` from `dashboard/frontend`). +64 pytest from the 498 baseline; Vitest
unchanged at 179.

---

### Phase 37 — Device Selection Wiring ✅

**Branch:** `feat/pluto-device-support`. **Type:** Feature (invasive wiring).

**What shipped.** Mimir's live scan can now run on either the HackRF One or the
ADALM-PLUTO, selected via a new `--device {hackrf,plutosdr}` flag on `scan.py`.
HackRF remains the default; its behaviour is byte-for-byte unchanged when the flag
is absent.

**Delivered:**
- `core/device/factory.py` (new) — `build_device(driver, lna_gain_db, vga_gain_db,
  amp_enable)`, a single construction seam. Accepts the HackRF gain vocabulary but
  deliberately does NOT forward it to `PlutoReceiver` (different gain semantics —
  Pluto constructs at its own 30.0 dB default until Phase 39). RX-only.
- `scan.py` — `--device` flag via argparse; construction routed through
  `build_device()`; on a Pluto run only, startup focus moves to the first
  `frequencies_hz` entry whose band Pluto supports (via `band_key_for_freq` +
  `band_supported_by_device`), with `current_band` set to match.
- `core/pipeline/scanner.py` — `ScanRunner.__init__` gains `device_driver="hackrf"`.
  The scan-loop tune point is guarded: strict no-op for HackRF (hot path unchanged);
  for other drivers, an unsupported band is skipped with a once-per-focus log line
  instead of being tuned.
- `dashboard/shared_state.py` — additive `band_key_for_freq(freq_hz) -> str | None`
  (returns the BAND_PROFILES key, needed because `band_supported_by_device()` takes
  a key not a frequency).

**Design notes.** The anticipated per-band HackRF-LNA/VGA vs Pluto-combined-gain
collision did not exist — `ScanRunner` sets gain once at construction, never per band.
Pluto startup-band reassignment was found mandatory (not optional): `frequencies_hz[0]`
is 98 MHz FM, below Pluto's 325 MHz floor, so a naive Pluto run would fail on the first
tune. `dashboard/capture_loop.py` was confirmed dead code (not imported by `scan.py`
or `server.py`) and removed from scope — logged as tech debt.

**Test counts:** 772 (593 pytest + 179 Vitest), 0 failures — both suites live-verified.
+31 pytest over the 741 baseline; Vitest unchanged (backend-only).

**Not yet verified:** actual `--device plutosdr` hardware behaviour was untested at
memo time (mocked tests prove wiring logic, not end-to-end streaming). Hardware
verification was subsequently done in the 37-Hotfix-1 session (Pluto ADS-B decode
confirmed CRC-valid on real hardware).

---

### Phase 37-Hotfix-1 — Pluto Waterfall Adaptive Colour ✅

**Type:** Hotfix (frontend-only, non-checkpoint). **Branch:** `feat/pluto-device-support`.

**Problem.** The dashboard waterfall was effectively invisible on the ADALM-PLUTO —
a flat near-black field — despite correct decoding (ADS-B CRC-valid, ISM classified)
and a healthy canvas. Pixel readout showed every bin mapping to `rgb(3, 8, 16)`, the
darkest gradient stop.

**Root cause.** `normalisePsd()` in `colourmap.js` used a fixed absolute dBFS window
(-80 to 0) tuned for HackRF's calibrated per-band gain. Pluto at its uncalibrated
30 dB default delivers a much lower-amplitude signal, so its entire averaged PSD curve
sat below that window -> near-black. A real per-device physical difference, not a driver
defect (confirmed against Pluto's own hardware notes; ruled out websocket, canvas
layout, and sample-scaling causes by direct measurement first).

**Fix.** Made the waterfall colour scale adaptive and self-scaling, keyed off the data
rather than any fixed range or device identity:
- `colourmap.js` — `normalisePsd(value, minDb, maxDb)` now takes an explicit window.
- `useWaterfall.js` — derives the window per row: floor = 70th-percentile
  (`SCALE_FLOOR_PERCENTILE = 0.7`) minus a pad (anchoring to noise floor, not row min,
  keeps noise dark); ceiling = row max + 6 dB (`SCALE_CEIL_PAD_DB`). Single-pass,
  NaN/Infinity-guarded, no spread-based Math.min/max (avoids call-stack blow-up on the
  2048-bin array).

**Forward note.** The waterfall is now device- and gain-independent; Phase 39 Pluto
calibration needs no waterfall changes. Do NOT reintroduce a fixed per-device dBFS
range in `colourmap.js`.

**Test counts:** 179 Vitest passing, 0 failures (pytest untouched — no backend change).
Combined suite remains 772. Live-verified on Pluto (ISM 915, ADS-B 1090) and HackRF
(ACARS 129.125).

---

### Phase 37-Hotfix-2 — ACARS Decimation Fix + Decode-Path Verification ✅

**Type:** Hotfix + investigation. Code fix committed (`71784c5`); the larger result is
a verification — the ACARS decoder was proven correct, not buggy.

**Problem.** ACARS produced no decodes on 129.125 MHz despite an apparent strong
carrier. Three hypotheses: signal quality, subscriber wiring, or decoder bug.

**Investigation (env-gated `MIMIR_ACARS_DIAG` instrumentation + offline analysis).**
- Wiring correct: `arrivals == loop_chunks`, no queue drops.
- Chunk length fine: 65.5 ms/chunk holds a full ACARS frame.
- Root cause: **no ACARS on air.** Confirmed four ways — HackRF IQ+FFT capture (DC/LO
  spike + flat noise, no ACARS bandwidth), SDR++ reference receiver (129.125 + 131.550,
  AM), a 20 min burst-catcher (peak/mean 10-12 vs 6-10 baseline), and the single
  threshold-crossing burst (peak/mean 19.3) run through the real decoder offline — a
  ~6 ms, 0.2 kHz carrier blip (not the ~2.4 kHz / 100 ms+ ACARS signature). Decoder
  correctly returned NO SYNC.

**What was delivered (`modules/acars/demodulator.py`, `subscriber.py`).**
- Latent bug found en route: single-stage `scipy.signal.decimate(factor=41)` exceeded
  SciPy's documented IIR-safe limit of 13, degrading the anti-alias filter. NOT the
  cause of no-decodes (band was quiet), but a real defect affecting any high-decimation
  path (incl. Pluto rates).
- `_stage_factors()` splits any factor into IIR-safe stages (each <=13), exact-split with
  prime-fallback. `decimate_to_audio()` decimates in stages, targets 50 kHz (factor
  40 = 10x4 at 2 MHz), returns `(signal, actual_rate)` so tone detection uses the true
  rate. Device-independent. Decode logic unchanged.

**Verification outcome.** ACARS decoder confirmed CORRECT — rejects non-ACARS input
cleanly, verified against real captured IQ through the genuine decode path. "Awaiting
decodes..." on a quiet channel is expected, not a bug. Live-traffic validation parked
(see Known Tech Debt).

**Test counts:** 781 (602 pytest + 179 Vitest), 0 failures. +9 pytest (`_stage_factors`)
over the 772 baseline; Vitest unchanged.

---

### Phase 38 — Device-Aware Unsupported-Band UI ✅

**What:** Grey out and disable the bands the currently-active SDR cannot
physically receive, on both live band surfaces (BAND_GROUPS top nav and
OVERVIEW_BANDS bottom strip). On Pluto, five of the eight bands
(FM, Aviation, ACARS, APRS, AIS) sit below its 325 MHz tuning floor; on
HackRF every band is receivable, so the greying map is empty and the UI
renders exactly as before.

**Scope correction.** The Phase 35 memo scoped this as "frontend-only —
backend capability already exists (`band_supported_by_device`)". That was
incorrect. Nothing surfaced *which device is currently active* to the
frontend, so the existing backend function had no second argument to be
called with. A backend addition was required first — confirmed by reading
the real `system_stats` payload, `shared_state.py`, and `scan.py` before
any code was written.

**Backend changes:**
- `dashboard/shared_state.py` — new `current_device` / `current_device_lock`
  (mirrors the existing `current_band` / `current_band_lock` pattern).
  New `unsupported_bands_for_device(device)` helper: iterates
  `BAND_PROFILES`, skips `noise_floor`, calls the existing
  `band_supported_by_device()`, and reads each unsupported band's reason
  string from `PLUTO_BAND_PROFILES`. Backend stays the sole source of
  truth — the frontend never re-derives Pluto's 325 MHz rule itself.
- `scan.py` — writes `current_device` from `args.device` at startup, for
  both devices (not just Pluto), so the empty-map HackRF case is correct
  from the first stats tick.
- `dashboard/server.py` — `emit_stats()` adds two keys to the existing
  `system_stats` payload: `device` and `unsupported_bands`. No new
  endpoint, no new socket event — rides the existing 2 s poll.

**Frontend changes:**
- `dashboard/frontend/src/hooks/useSocket.js` — exposes `device` and
  `unsupportedBands` derived from `systemStats`, defaulting to `null` / `{}`
  before the first `system_stats` event arrives.
- `dashboard/frontend/src/App.jsx` — BAND_GROUPS and OVERVIEW_BANDS grey
  unsupported bands: `opacity: 0.35`, `cursor: not-allowed`, a native
  `title` tooltip carrying the backend's reason string, and
  `data-unsupported="true"`. Click is blocked by omitting the `onClick`
  handler for unsupported rows (`isUnsupported ? undefined : () => ...`).
- `dashboard/frontend/src/components/FrequencyList.jsx` — same treatment
  applied for consistency, though this component is dead code (not
  imported by `App.jsx` or any production file — see Known Tech Debt).

**Known issue at ship (fixed in 38-Hotfix-1):** the greyed BAND_GROUPS
buttons also carried the HTML `disabled` attribute, which suppresses
native `title` tooltips — the reason text was present in the DOM but
never appeared on hover.

**RF/Legal notes:** Pure UI/state plumbing. No hardware I/O, no TX
surface. Receive-only, AU/SA, ACMA, Radiocommunications Act 1992 (Cth).

**Test counts:** 795 (610 pytest + 185 Vitest), 0 failures. +8 pytest
(`unsupported_bands_for_device` + `system_stats` device-field coverage),
+6 Vitest (`FrequencyList` greying behaviour, `useSocket` device exposure).

---

### Phase 38-Hotfix-1 — Unsupported-Band Tooltip Fix ✅

**Type:** Hotfix (frontend-only). **Verified live** on real hardware —
both ADALM-PLUTO (5 greyed bands, working tooltips) and HackRF (no
greying, zero visual change) — after the code fix landed.

**Problem.** Hovering a greyed band on a Pluto run showed no tooltip.
DOM inspection (right-click → Inspect on a live greyed button) confirmed
the `title` attribute was present with the correct reason text — the bug
was not in the data path.

**Root cause.** The greyed BAND_GROUPS `<button>` elements carried both
`title` (the reason string) and the HTML `disabled` attribute. Browsers
remove `disabled` controls from hit-testing, so `mouseover` never fires
and the native `title` tooltip never appears — this is spec behaviour
across all browsers, not a project-specific bug. The backend data,
the `unsupported_bands` map, and the reason strings in
`PLUTO_BAND_PROFILES` were all correct throughout.

**Fix.** Removed the `disabled` attribute from the BAND_GROUPS button.
Click safety is unaffected: the `onClick` omission guard
(`isUnsupported ? undefined : () => focusFrequency(...)`) already blocked
the click independently of `disabled`, so removing it does not re-open
clicking on greyed bands. `OVERVIEW_BANDS` and `FrequencyList.jsx` render
`<div>` elements, which have no native `disabled` attribute — audited,
confirmed unaffected, no change needed there. A WHY comment was added at
the fix site so a future contributor does not re-add `disabled` "for
extra safety."

**Forward note.** Do NOT set `disabled` or `pointer-events: none` on any
element that also needs a hover tooltip — both remove the element from
the browser's hit-test path and silently kill the tooltip.

**Test counts:** 800 (610 pytest + 190 Vitest), 0 failures. pytest
unchanged (no backend touched). +5 Vitest regression tests asserting a
greyed control carries `title` AND is *not* `disabled` — the specific
combination that slipped through Phase 38's original test coverage
(which checked `title` presence but not reachability).

---

### Phase 39 — Pluto Gain Calibration Tooling ✅

**Type:** CHECKPOINT (core + tools + tests). **Tooling only — NOT verified on live hardware in this phase.** Phase 39 ships the diagnostic a future operator hardware-sweep run (Phase 39b) needs in order to calibrate PLUTO_BAND_PROFILES gain and signal_threshold values.

**What.** Shipped the Pluto-side capture function and the gain-sweep diagnostic. `core/pipeline/capture.py` now exposes a new sibling function `capture_iq_pluto(freq_hz, num_samples, sample_rate_hz, gain_db, bandwidth_hz=None)` that drives the existing `PlutoReceiver` via its context manager. Pluto uses a single combined gain stage (0–74.5 dB), so the new function takes one `gain_db` argument where the HackRF `capture_iq` takes a `(lna_gain_db, vga_gain_db)` pair. The HackRF function is preserved byte-for-byte. `tools/diagnose_pluto_gain.py` is a new standalone CLI tool that sweeps `GAIN_CANDIDATES = [0, 10, 20, 25, 28, 30, 32, 35, 38, 40, 45, 50, 55, 60, 65, 70, 74.5]` on ISM (915 MHz) and ADS-B (1090 MHz) only — the two Mimir bands inside Pluto's stock 325–3800 MHz range. Per (band, gain) step it captures via `capture_iq_pluto`, computes PSD, and prints a row of `gain / noise_floor / excursions / max`. The excursion count is `int(np.sum(psd_db > noise_floor_db + SPUR_MARGIN_DB))` with `SPUR_MARGIN_DB = 10.0` — a deliberately simple proxy for the picket-fence spurs observed above ~30 dB combined gain. The tool finishes with a static 3-bullet interpretation aid (no automated recommendation) and a summary table. CLI: `--band {ism,adsb}` only; default sweeps both. Empty-PSD steps and per-step `RuntimeError`/`OSError`/`ValueError` are caught and skipped (a single USB hiccup on a 34-capture sweep does not abort the rest).

**Why.** Two measured Pluto behaviours — spurs above ~30 dB combined gain, and a non-monotonic AD9363 gain-table boundary at ~32 dB (measured 2026-07-21, both bands; the original 2026-07-16/17 finding estimated ~35 dB) — were discovered on hardware in 2026-07-16/17 (recorded in `core/device/pluto_rx.py` module docstring "MEASURED FINDINGS"). The `PLUTO_BAND_PROFILES` entries for `ism` and `adsb` carry placeholder `gain_db = 30.0` and `signal_threshold_db = 3.0` copied from the HackRF profiles; gain 30 was chosen from the spur observation, not a calibration session. Phase 39 provides the tool that lets an operator pick calibrated values by reading the sweep. No automatic `PLUTO_BAND_PROFILES` edit — that is Phase 39b after the operator runs the tool on hardware.

**Files changed.**
- `core/pipeline/capture.py` — added `capture_iq_pluto()` as a new sibling function. PlutoReceiver import added. Existing `capture_iq()`, `save_capture()`, `capture_and_save()` untouched.
- `tools/diagnose_pluto_gain.py` — new file. Per-band sweep with per-step exception handling and a static interpretation aid.
- `tests/core/test_capture_pipeline.py` — added `TestCaptureIqPluto` (5 tests) and `TestCaptureIqUnchanged` (1 test). The TX-safety test asserts none of the 7 PlutoReceiver transmit-family methods (`transmit`, `write_samples`, `writeStream`, `set_tx_gain`, `set_tx_frequency`, `setupTxStream`, `activateTxStream`) is called, and that no transmit-family kwarg is passed to the PlutoReceiver constructor.
- `tests/tools/test_diagnose_pluto_gain.py` — new file, 8 tests across `TestSweepBand` and `TestMainBandSelection`.

**Design decisions.**
- **New sibling function, not a refactor of `capture_iq`.** Branching or re-parameterising the existing function would have broken four downstream tools (`diagnose_threshold.py`, `calibrate_thresholds.py`, `capture_to_vectorstore.py`, `diagnose_fingerprints.py`) which all use the HackRF split-gain signature.
- **No automatic split-to-combined gain translation.** `core/device/profiles.py` already documents that no principled translation exists between HackRF LNA/VGA and Pluto combined-gain. Callers pass a native Pluto gain.
- **Excursion proxy is deliberately simple.** Spur-vs-signal classification is a judgement call; the tool's job is to make the curve visible, not to make the call. The 3-bullet interpretation aid points the operator at the excursion column (spur onset), the noise-floor column near 30–35 dB (non-monotonic boundary; dip measured at 32 dB), and the spur-vs-signal confirmation step (compare a clean HackRF trace, as the original 2026-07-16/17 finding did).
- **Per-step exception handling.** The deep-analyst review flagged that a single USB hiccup on a 34-capture unattended run would previously have aborted the whole sweep. Added try/except matching the existing empty-PSD skip pattern, plus a one-line `__exit__.assert_called_once()` regression test (LOW-03 and LOW-05 from the deep-analyst review).
- **`diagnose_threshold.py` and `calibrate_thresholds.py` remain HackRF-only.** They sweep per-band SIGNAL_THRESHOLD_DB at a fixed gain, not a gain sweep. Pluto support is a deferred future phase.

**RF-Legal notes.** Receive-only. Jurisdiction: AU/SA, ACMA, Radiocommunications Act 1992 (Cth). 915 MHz (ISM, AU — NOT 868 MHz EU) and 1090 MHz (ADS-B) are AU-legal to receive passively. Pluto RX-only enforced by `PlutoReceiver` (every transmit-family method is wrapped in `transmit_guard` from `core/legal/compliance_guard.py`). The new `capture_iq_pluto()` function drives only the public RX API — `__init__` → `__enter__`/`open` → `read_samples` → `__exit__`/`close` — and adds no `direction=` parameter and no TX-path call.

**Test counts.** 814 total (624 pytest + 190 Vitest), 0 failures. +14 pytest over the 800 baseline (5+1 capture + 8 tool). Vitest unchanged (no frontend touched). Zero regressions.

**Tech debt updated in AGENTS.md.**
- "Pluto band profiles uncalibrated" — now notes Phase 39 ships the calibration tooling; awaiting operator hardware-sweep run and manual profile edit (Phase 39b).
- "Pluto spurs above ~30 dB gain" — now describes the actual excursion-count algorithm and the static interpretation aid. Spur-vs-signal is ultimately confirmed against a clean HackRF trace.

---

## Resolved Tech Debt — Historical

> Migrated out of AGENTS.md's live Known Tech Debt table on 2026-07-13 to keep
> the active tracker readable. Retained here for regression forensics.

- **Waterfall scroll rate slow** — one row per dwell cycle; decoupled from the AI loop in the spectrum-broadcast fix (~4–5 Hz from the scan loop). *(Post-7B)*
- **`FrequencyList.jsx:67` confidence_score null guard** — added. *(PHASE-TECH-DEBT-2)*
- **CORS wildcard** — `cors_allowed_origins="*"` removed. *(PHASE-CORS-FIX)*
- **`sampleRateHz` dead param** — removed from `useWaterfall.js`. *(PHASE-TECH-DEBT-1)*
- **Calibration store wiped at every startup** — `calibrate_thresholds.py` deleted the vectorstore each run, losing cross-session data. Replaced with persistent storage, a `--wipe` flag for full re-baseline, and `STALENESS_DAYS = 14` exclusion from the merged ladder. *(Phase 28)*
- **`psd_db` uncalibrated (fft.py normalisation)** — ROOT CAUSE: `compute_psd()` divided `averaged_power` by `max_power` before dBFS conversion, forcing the peak bin to always read 0.0 dBFS (the "gain red herring"). Fixed with standard Welch periodogram normalisation `/ (nfft * window_power)`. Any future fft.py normalisation change re-invalidates existing embeddings. *(Phase 9B-Hotfix)*
- **scan.py startup message** — "Scanning N frequencies" corrected for single-freq focus mode. *(PHASE-TECH-DEBT-1)*
- **Orphaned dashboard components** — `AIReasoningPanel.jsx` integrated in Phase 10; `SystemStatsPanel.jsx` deleted 2026-06-24 (replaced by inline stats JSX in `App.jsx`).
- **test_server_stats.py strict dict equality** — full-dict equality broke on every new broadcast field; refactored.
- **SignalHistoryLog memoisation** — `React.memo` with custom comparator on `pinnedTimestamp` + `scanResults` content equality. *(PHASE-BUILD-3)*
- **Inline single-antenna selection** — `calibrate_thresholds.py` hardcoded one antenna for all bands; replaced with band-driven antenna groups + mid-run swap prompts. *(Phase 28)*
- **Classifier schema missing acars/ais** — added to `_JSON_SCHEMA` and `_AU_BAND_REFERENCE`. *(PHASE-CLASSIFIER-SCHEMA-FIX)*
- **AIS BAND_PROFILES centre vs demodulator mismatch** — profile centre (161.975 = CH1) differed from the dual-channel demod centre (162.000). Backend fixed Phase 14 (now 162.000); frontend fully aligned Phase 16.
- **Frontend/backend AIS frequency mismatch** — frontend hardcoded 161.975; aligned to 162.000 across BAND_GROUPS, OVERVIEW_BANDS, isTuned(), STRIP_CONFIGS, FREQ_COLOUR_MAP, isAisFreq, FREQ_CONFIGS. *(Phase 15 + 15b)*
- **CHECKPOINT arg parser failure** — `/build` `$2` positional silently dropped when `$1` was a long multi-line string. `build.md` PHASE-TRACKER GATE now accepts both `$2 CHECKPOINT` and `CHECKPOINT_MODE: ON` embedded in the body. *(Phase 14)*
- **ADS-B subscriber flush gap** — `AdsbSubscriber.stop()` now calls `flush()` and broadcasts harvested bootstrap-held CPR positions before shutdown. *(PHASE-TECH-DEBT-1.5)*
- **`config/mimir.yaml` stale comment** — "runtime loading not yet implemented" removed; `scan.py` already calls `load_config()`. *(2026-06-24)*
- **RTL-ML sample rate in seed_chromadb.py** — `compute_psd` called at 1,024,000 Hz (RTL-ML) dimension-corrupted `bandwidth_hz`/`occupied_bins` vs live 2,000,000 Hz vectors. Fixed to `MIMIR_SAMPLE_RATE = 2_000_000`. *(seed hotfix, pre-Phase 20)*
- **Phase 19b/19c governance rows missing** — tracker entries added retroactively (checkpoint was off for both builds).
- **capture_loop.py not passing signal_threshold_db** — live fingerprinting always used the 24.0 dB module fallback; now forwards `band.get("signal_threshold_db")`. *(Phase 29)*
- **BUG-04 `/vectordb` tooltip frequency mismatch** — seeds write `center_freq_hz`, live captures write `freq_hz`; tooltip showed null for seeds. Fixed with `meta.get("center_freq_hz", meta.get("freq_hz"))`. *(Phase 23)*
- **Missing `isAdsbTuned()` helper** — ADS-B tuning check factored into a helper alongside `isAcarsTuned`/`isAisTuned`. *(Phase 31)*
- **Inner NOT TUNED badge dead code** — six unreachable ternary else-branches (NOT TUNED badges + "TUNE TO ..." prompts) removed across the ADS-B/ACARS/AIS decoder panels; outer tuned-guards already gated them. *(Phase 31)*
- **Queue max hard-coded `020` in SystemStatsPanel** — OBSOLETE: `SystemStatsPanel.jsx` was deleted 2026-06-24 and replaced by inline stats JSX in `App.jsx`, whose "IN QUEUE" readout reads `systemStats.queue_depth` live with no hard-coded max. No fix required. *(Verified 2026-07-13)*
- **SIGNAL_THRESHOLD_DB discrepancy** — RECONCILED 2026-07-13: `core/pipeline/features.py:30` = `24.0` (documented conservative module-level fallback); the "21 dB" figure was the FM per-band value in `BAND_PROFILES`; the "27 dB" figure was stale memory. No code change — the debt row itself was the stale artefact. *(2026-07-13)*
- **MED-01: scan.py fatal-error exit path** — `main()`'s `except Exception` sets `fatal_error=True` and exits code 1; test coverage for the exit-code-1 path added. *(PHASE-TECH-DEBT-1)*
- **ADS-B gain divergence (tools vs production)** — `calibrate_thresholds.py` and `diagnose_fingerprints.py` used (32/38) for ADS-B gain while `shared_state.py` BAND_PROFILES uses (24/24); all four tools now read gains from BAND_PROFILES. *(Phase 19a + BUG-03)*
- **BUG-03: diagnostic/calibration tools wired to BAND_PROFILES** — `capture_to_vectorstore.py`, `calibrate_thresholds.py`, `diagnose_fingerprints.py`, `diagnose_threshold.py` now read lna/vga gains + `signal_threshold_db` live from BAND_PROFILES; `diagnose_fingerprints.py` AIS gains corrected (24, 26) → (16, 20). *(this session)*

---

### BUG-04 Detail (Phase 23)

#### Summary
Tooltip frequency field null for legacy seeded records due to metadata key mismatch between seeding workflow and live capture pipeline. Live captures use `freq_hz`, seeded data uses `center_freq_hz`. Tooltip showed null when querying `/vectordb` with legacy seed keys.

#### Root Cause
- Seeded ChromaDB points: metadata key `center_freq_hz` (from RTL-ML dataset)
- Live capture points: metadata key `freq_hz` (from ScanResult pipeline)
- Tooltip component: hardcoded to query `freq_hz` field
- Result: legacy seeds returned null in tooltip frequency display

#### Fix Applied
Modified `api_vectorstore_points()` in `dashboard/server.py`:
```python
meta.get("center_freq_hz", meta.get("freq_hz"))
```

This provides fallback precedence: `center_freq_hz` (seeds) over `freq_hz` (live). Null SNR/peak/timestamp values preserved for legacy seeded records to maintain data integrity.

#### Testing
- 420 pytest + 162 Vitest = 582 tests passing, 0 failures
- Verified tooltip displays frequency correctly for both seed and live-capture vectors
- Legacy seeds retain null SNR/peak/timestamp fields as expected

#### Impact
No phase tracker entry required. This is a targeted bug fix within Phase 23 scope. Preceded by Phase 22 LLM offline handling work. Follows successful completion of Phase 17 (focused decode panel) and Phase 18 (raw ADS-B hex decode view). Resolved after Phase 22 hotfix for rate-limiting SocketIO flood during LLM offline state.

---

## Deferred Items