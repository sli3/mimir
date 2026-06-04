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
| 5     | Live Dashboard                    | ✅ Complete    | —        |
| 6     | Live AI Classification + Dashboard| ✅ Complete    | 108/108  |
| 7A    | Cyberpunk Dashboard — Scaffold    | ✅ Complete    | 108 pytest + 50 Vitest = 158   |
| Data Layer | ACMA frequency reference + RTL-ML ChromaDB seeding | ✅ Complete | 188/188 (165 pytest + 23 new, 50 Vitest) |
| — | UV migration (pip to pyproject.toml + uv.lock) | ✅ Complete | uv sync --all-extras; uv run pytest |
| 7B    | Cyberpunk Dashboard — AI + Polish | ✅ Complete | 233/233 |
| 8A | Wire ACMA frequency_reference.json into LLM classifier user prompt | ✅ Complete | 251/251 |
| 8B | Wire real ScanRunner values into system_stats; fix AGENTS.md event table | ✅ Complete | 259/259 |
| 8C | Single-frequency focus mode + LLM tuning | ✅ Complete | 260/260 |

**Total: 260/260 tests passing (204 pytest + 56 Vitest)**

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
- BUG-01 CLOSED — SIGNAL_THRESHOLD_DB calibrated to 27 dB
  against live FM Adelaide capture (98.9 MHz). Bandwidth now
  correctly reports ~185 kHz for FM broadcast. Fixed in this session.

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

**Planned:**
- Fix `scan.py` startup message ("Scanning N frequencies" → reflect single-freq mode)
- Address BUG-01 (bandwidth_hz=0 / occupied_bins=0 from low SNR threshold)
- NOAA/Meteor-M2 satellite planning: 137.620, 137.9125, 137.100, 137.9 MHz
- Antenna requirements: V-dipole or QFH for 137 MHz satellite band

---

## Known Tech Debt

| Item | Detail | Fix in |
|---|---|---|
| `config/mimir.yaml` not loaded | Runtime config loading not yet implemented | Phase 2+ |
| `scan.py` startup message | Misleading "Scanning N frequencies" in single-freq mode | Post 8C |