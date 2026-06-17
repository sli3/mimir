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

**Test counts:** 427/427 (330 pytest + 97 Vitest) at delivery. Current: 427 passing (330 pytest + 97 Vitest), 1 pre-existing pytest failure.

**Current totals: 427 tests passing (330 pytest + 97 Vitest)**
- Note: 1 pre-existing pytest failure (test_adsb_demodulator::test_preamble_detection_synthetic).

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

## Known Tech Debt

| Item | Detail | Fix in |
|---|---|---|
| `config/mimir.yaml` not loaded | Runtime config loading not yet implemented | Phase 2+ |
| `scan.py` startup message | Misleading "Scanning N frequencies" in single-freq mode | Post 8C |
| MED-01: scan.py fatal error exit | `except Exception` sets fatal_error=True but no test verifies exit code 1 | Follow-up build |
| ADS-B gain divergence | tools use (32/38) for ADS-B gain, shared_state.py uses (24/24). Both tool values labelled provisional. | Live ADS-B test |