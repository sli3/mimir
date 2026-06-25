# Mimir — AI-Powered RF Spectrum Scanner
## OpenCode Project Memory File

> *Mimir (Old Norse: "the rememberer") — the Norse figure of wisdom and
> intelligence, keeper of knowledge. This project listens, remembers,
> and understands RF signals. It never speaks back.*

---

## ⚠️ LEGAL CONSTRAINTS — READ BEFORE EVERY SESSION

These rules are not optional. They apply to every agent, every session,
every code change, without exception.

| Item | Value |
|---|---|
| **Jurisdiction** | Australia — South Australia (Adelaide) |
| **Authority** | ACMA (Australian Communications and Media Authority) |
| **Law** | Radiocommunications Act 1992 (Cth) |
| **Licence held** | NONE |
| **Passive RX** | Legal — no licence required |
| **Any TX** | Criminal offence — do not implement under any circumstances |

### Non-negotiable rules for all agents
1. **Never produce transmit code.** No `writeStream()`, no TX flags,
   no transmit config, no transmit documentation, no TX examples.
2. **Cross-check AU/SA law** before suggesting any RF frequency or operation.
3. **Do not apply FCC (US) or ETSI (EU) rules.** AU jurisdiction only.
4. **Flag every library with TX capability** and document RX-only safe usage.
5. **HardwareTransmitError must be raised** on any call to a TX function —
   this is enforced in `core/legal/compliance_guard.py`.

### Australian frequencies legal to receive passively
| Band | Frequency | Notes |
|---|---|---|
| FM Broadcast | 87.5–108 MHz | Commercial radio |
| Aviation VHF | 118–136 MHz | ATC and aircraft comms |
| ACARS | 129.125 / 130.025 MHz | Aircraft operational messaging, AU primary |
| APRS | 145.175 MHz | AU frequency — NOT 144.390 (US) |
| AIS | 161.975 / 162.025 MHz | Maritime VHF — automatic vessel identification |
| ISM / LoRa | 915 MHz | AU/NZ band — NOT 868 MHz (EU) |
| ADS-B | 1090 MHz | Aircraft position broadcasts |

---

## Hardware

| Item | Detail |
|---|---|
| **SDR** | HackRF One — RECEIVE ONLY |
| **Serial** | (set locally — see hackrf_info output) |
| **Firmware** | 2026.01.3 (API:1.10) |
| **Note** | Older than r6 board — self-test FAIL is cosmetic, device works |
| **Primary OS** | Linux Fedora 44 |
| **Secondary OS** | macOS Intel iMac (not yet configured) |
| **Intelligence** | Local LLM (llama.cpp, OpenAI-compatible API) |
| **Model** | Qwen3-4B-Q4_K_M via llama.cpp on yubaba |
| **LLM URL** | http://192.168.0.66:8080/v1 |
| **LLM config** | max_tokens=300, ctx-size=8192, `/no_think` token appended to system prompt |
| **Project path** | ~/Repository/mimir |

---

## Architecture
HackRF One (RX only — NEVER TX)
│
▼ raw IQ samples (complex64)
core/device/hackrf_rx.py        SoapySDR Python bindings
│
▼ numpy arrays
core/pipeline/                  FFT → feature extraction
│
▼ signal fingerprints
embeddings/                     ChromaDB vector store
│
▼ similarity search
llm/                            Local LLM (OpenAI-compatible API)
│
▼ classification + anomaly detection
dashboard/                      Cyberpunk React dashboard + Flask-SocketIO
│
├── dashboard/server.py     Flask + SocketIO backend (async_mode='threading')
└── dashboard/frontend/     Vite + React frontend
└── npm run build →     dashboard/static/ (Flask serves)

---

## Project Format — Non-Negotiable

- **OpenCode exclusively**: `AGENTS.md` and `opencode.json`
- **Never** Claude Code format (`CLAUDE.md`, `.claude/`)
- **Never** Cursor format (`.cursorrules`)
- All agent config lives in `opencode.json`

---

## Development Setup

### Prerequisites

System-level dependencies (UV cannot manage these):

```bash
# Fedora
sudo dnf install hackrf SoapySDR python3-SoapySDR
# NOTE: SoapySDR-module-hackrf does NOT exist in dnf repos.
# Build from source: https://github.com/pothosware/SoapyHackRF
# acarsdec — ACARS decoder, must be built from source
# NOT in dnf repos. Build: https://github.com/f00b4r0/acarsdec
# Deps: SoapySDR-devel cmake gcc make git
# Run setup.sh — build_acarsdec() handles this automatically

# Ubuntu/Debian
sudo apt-get install hackrf soapysdr-module-hackrf python3-soapysdr
# acarsdec: build from source (see setup.sh — handled automatically)
```

### Install UV (if not present)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install all Python dependencies

```bash
uv sync --all-extras
```

This creates a `.venv` virtual environment and installs everything.

### Run the scanner

```bash
python scan.py
```

Note: `uv run python scan.py` does not work in this environment — use system Python directly.

### Run tests

```bash
uv run pytest
```

### Run a tool script

```bash
uv run python tools/seed_chromadb.py
```

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
| 7B    | Cyberpunk Dashboard — AI + Polish | ✅ Complete | 233/233 |
| — | UV migration (pip to pyproject.toml + uv.lock) | ✅ Complete | uv sync --all-extras; uv run pytest |
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
| PHASE-TECH-DEBT-2 | Five frontend small fixes | ✅ Complete | 439/439 (334 pytest + 105 Vitest) |
| PHASE-BUILD-3 | AIS waterfall config, tuned-state tests, SignalHistoryLog memo | ✅ Complete | 446/446 (334 pytest + 112 Vitest) |
| PHASE-BUILD-4 | Tech debt clean-up (setup.sh, FREQ_COLOUR_MAP, AIS nav, pin eviction, classifier prompt) | ✅ Complete | 446/446 (334 pytest + 112 Vitest) |
| PHASE-BAND-PROFILE-FIX | Wire band profile into handle_set_focus for per-band thresholds | ✅ Complete | 452/452 (340 pytest + 112 Vitest) |
| PHASE-CLASSIFIER-ACCURACY-FIX | Add AIS to BAND_PROFILES; fix ACARS/AIS misclassification | ✅ Complete | 456/456 (344 pytest + 112 Vitest) |
| 12 | Decoder-Driven ADS-B Classification | ✅ Complete | 489 (368 pytest + 121 Vitest) |
| 13 | Spectral Flatness Embedding Expansion | ✅ Complete | 489 (368 pytest + 121 Vitest) |
| 14 | CHECKPOINT Parser Fix + AIS Band Profile | ✅ Complete | 492 (371 pytest + 121 Vitest) |
| 15 | Frontend AIS Consistency + Nav Bar Completion | ✅ Complete | 493 (371 pytest + 122 Vitest) |
| 15b | AIS Waterfall Frequency Migration Completion | ✅ Complete | 493 (371 pytest + 122 Vitest) |

**Total passing: 493 passing (371 pytest + 122 Vitest), 0 failures**
- Note: All pre-existing pytest failures resolved. Updated 2026-06-24 after Phase 13.

---

## MCP Servers

Two MCP servers are configured in `opencode.json` and active in all OpenCode sessions.

| Server | Type | Transport | Purpose |
|---|---|---|---|
| `local-files` | local | npx @modelcontextprotocol/server-filesystem | Read/write access to `/home/sli3/Repository/mimir` |
| `github` | remote | https://api.githubcopilot.com/mcp/ | GitHub repo access — commits, issues, file history |

### GitHub MCP — setup notes

- Auth: fine-grained PAT stored as `GITHUB_PERSONAL_ACCESS_TOKEN` in fish shell (`~/.config/fish/config.fish`)
- PAT scope: Mimir repo only — Contents (read/write), Issues (read/write), Metadata (read-only), Pull requests (read-only)
- Config key in `opencode.json`: `"mcp"` block with `"type": "remote"`, `"oauth": false`
- Token uses `{env:GITHUB_PERSONAL_ACCESS_TOKEN}` interpolation — never hardcoded in config
- PAT expiry: 90 days — rotate when GitHub sends expiry email, update fish env var and restart OpenCode
- Verified working: `opencode mcp list` shows both servers as connected (●  ✓)

### GitHub MCP — what agents can use it for

- Read commit history and file diffs without manual copy-paste
- Create and close GitHub Issues from build reports
- Verify AGENTS.md is in sync with remote before starting a new session
- Cross-machine context check (Fedora machine vs macOS iMac)

### GitHub MCP — toolset note

The GitHub MCP server registers a large number of tools. If context window bloat
becomes an issue in future, add the following to `opencode.json` to disable tools
globally and re-enable per-agent:

```json
"tools": {
  "github_*": false
},
"agent": {
  "github-helper": {
    "tools": { "github_*": true }
  }
}
```

Do not apply this pre-emptively — only if context problems are observed.

---

## Dashboard Architecture (Phase 7A complete)

### SocketIO events — do not rename or merge

| Event | Direction | Payload |
|---|---|---|
| `scan_result` | server → browser | timestamp, center_freq_hz, signal_type, confidence, confidence_score, novel, au_legal_status, reasoning |
| `spectrum_update` | server → browser | center_freq_hz, psd_db (2048 floats dBFS) |
| `system_stats` | server → browser | hackrf_status, active_frequency_hz, scan_count, queue_depth, **last_backlog**, **llm_call_count**, llm_last_inference_ms |
| `set_focus_frequency` | browser → server | freq_hz |
| `acars_message` | server → browser | timestamp, freq_hz, registration, label, block_id, text, crc_ok |
| `ais_message` | server → browser | timestamp, mmsi, vessel_name, lat, lon, speed, course, channel |
| `adsb_aircraft` | server → browser | icao, callsign, altitude_ft, latitude, longitude, groundspeed, track, vertical_rate, timestamp |

> **`scan_result` emission paths (Phase 12):** (1) `ScanRunner._emit_result()` via LLM pipeline — fingerprint-based, all fields populated. (2) `emit_adsb_scan_result()` via confirmed ADS-B decode — `confidence_score=1.0`, fingerprint fields `None`

### Critical field name facts
- `timestamp` — ISO string e.g. `"2026-06-01T22:21:57.549402"` — use `new Date(ts)` not `new Date(ts * 1000)`
- `confidence_score` — float 0.0–1.0 — use for percentage display
- `confidence` — string "high"/"medium"/"low" — do not multiply by 100
- `center_freq_hz` — used in both `scan_result` and `spectrum_update`
- `useSocket.js` maps `spectrum_update.center_freq_hz` → internal `frequency_hz`

### Frontend stack
- Vite + React, plain JS/JSX — no TypeScript, no Tailwind
- Dev server: port 5173 (Vite default)
- Build output: `dashboard/static/` (`build.outDir = '../static'`)
- Socket proxy: `/socket.io` → `http://localhost:5000`
- Fonts: Share Tech Mono (all UI text — headings, data readouts, labels). Press Start 2P is used only for the MIMIR logo in the header (inline style, not CSS variable).
- Theme tokens in `src/theme/cyberpunk.css`
- No `<form>` tags anywhere — use onClick handlers

### Backend constraints
- `async_mode='threading'` in `server.py` — never change to eventlet/gevent
- `broadcast_spectrum` is defined inside `start_server()` — not importable directly
- Retrieve via `start_server._broadcast_spectrum_fn` after calling `start_server()`
- `_emit_result` in `scanner.py` calls `_broadcast_fn` only; `_broadcast_spectrum_fn` is called in `_scan_loop()` immediately after `compute_psd()`, decoupled from the AI loop (~4-5 Hz vs ~0.4 Hz)

---

## User RF Knowledge Level

**Complete beginner.** All agents must:
- Explain RF concepts from first principles before using them
- Explain what a thing is AND why it matters, not just how to use it
- Never assume knowledge of IQ data, modulation, FFT, or antenna theory
- Flag and explain TX capabilities of every library used

---

## Key Files

| File | Purpose |
|---|---|
| `core/legal/compliance_guard.py` | `HardwareTransmitError` — TX hard block |
| `core/device/hackrf_rx.py` | RX-only HackRF wrapper |
| `core/device/device_base.py` | Abstract device interface |
| `core/pipeline/fft.py` | FFT + PSD computation |
| `core/pipeline/features.py` | Spectrum fingerprinting |
| `core/pipeline/scan_result.py` | `ScanResult` dataclass (includes psd_db) |
| `core/pipeline/scanner.py` | `ScanRunner` — two-thread scan + AI loop |
| `core/config/loader.py` | `MimirConfig`, `load_config()` |
| `embeddings/embedder.py` | SpectrumEmbedder — fingerprint to vector |
| `embeddings/store.py` | SignalStore — ChromaDB wrapper |
| `llm/acma_reference.py` | `AcmaReference` — ACMA spectrum plan lookup |
| `llm/classifier.py` | `SignalClassifier` — LLM classification |
| `dashboard/server.py` | Flask + Flask-SocketIO backend |
| `dashboard/frontend/` | Vite + React cyberpunk frontend |
| `dashboard/frontend/src/hooks/useSocket.js` | SocketIO state management |
| `dashboard/frontend/src/hooks/useWaterfall.js` | Canvas ImageData rendering |
| `dashboard/frontend/src/utils/colourmap.js` | PSD dBFS → RGB colourmap |
| `modules/acars/subscriber.py` | AcarsSubscriber — IQ bus subscriber + decode thread |
| `modules/acars/demodulator.py` | AcarsDemodulator — AM envelope + FFSK tone detection |
| `modules/acars/decoder.py` | AcarsDecoder — frame sync + field parsing + CRC-16 |
| `modules/acars/message.py` | AcarsMessage dataclass |
| `modules/acars/constants.py` | AU ACARS frequencies and modulation constants |
| `modules/aIS/subscriber.py` | AisSubscriber — IQ bus subscriber + decode thread |
| `modules/aIS/demodulator.py` | AisDemodulator — frequency shift + GMSK differential + HDLC extract |
| `modules/aIS/decoder.py` | AisDecoder — NMEA sentence reconstruction + pyais decode |
| `modules/aIS/message.py` | AisMessage dataclass |
| `modules/aIS/constants.py` | AU AIS frequencies (161.975/162.025 MHz) and GMSK constants |
| `modules/adsb/subscriber.py` | AdsbSubscriber — IQ bus subscriber + decode thread |
| `modules/adsb/demodulator.py` | AdsbDemodulator — PPM demodulation + pulse extraction |
| `modules/adsb/decoder.py` | AdsbDecoder — message frame parsing + pyModeS decode |
| `modules/adsb/message.py` | AdsbMessage dataclass |
| `modules/adsb/constants.py` | AU ADS-B frequency (1090 MHz) and demod constants |
| `dashboard/static/` | Vite build output — served by Flask |
| `scan.py` | CLI entry point |
| `config/mimir.yaml` | Runtime configuration |
| `setup.sh` (build_acarsdec) | Builds acarsdec from source on first run |
| `docs/au-legal-reference.md` | ACMA legal reference |
| `docs/ROADMAP.md` | Phase tracker and build history |

---

## Known Tech Debt
| Item | Detail | Fix in |
|---|---|---|
| ~~Waterfall scroll rate slow~~ | ~~One row per dwell cycle (~8–10s)~~ — decoupled from AI loop in spectrum broadcast fix (~4-5 Hz from scan loop). Resolved. | ~~Post 7B~~ ✅ |
| ~~`FrequencyList.jsx:67`~~ | ~~`confidence_score` lacks null guard~~ | ~~Phase 7B polish~~ ✅ RESOLVED in PHASE-TECH-DEBT-2 |
| ~~CORS wildcard~~ | ~~`cors_allowed_origins="*"` in server.py~~ | ~~Pre-prod~~ ✅ PHASE-CORS-FIX |
| Queue max hard-coded | `020` in SystemStatsPanel — should read from systemStats | Phase 7B |
| ~~`sampleRateHz` dead param~~ | ~~Accepted by `useWaterfall.js` but unused~~ | ~~Post 7B~~ ✅ RESOLVED in PHASE-TECH-DEBT-1 |
| Queue drain pattern | `_scan_loop()` drains queue before every insert ('latest wins'). AI loop always classifies freshest scan. Queue depth at steady state: 0–1 items. Introduced: 2026-06-16. | — |
| ~~`psd_db` uncalibrated~~ | ~~FFT missing nfft normalisation~~ — fixed in Phase 9B-Hotfix (true dBFS) | ~~Post 7B~~ ✅ 9B-Hotfix |
| ~~scan.py startup message~~ | ~~"Scanning N frequencies" is misleading now that single-freq focus mode is active~~ | ~~Post 8C cosmetic~~ ✅ PHASE-TECH-DEBT-1 |
| ~~Orphaned dashboard components~~ | ~~`SystemStatsPanel.jsx` and `AIReasoningPanel.jsx` are not imported by `App.jsx`~~ — `AIReasoningPanel.jsx` integrated in Phase 10. `SystemStatsPanel.jsx` deleted 2026-06-24. | ~~Pre-prod integration~~ ✅ |
| ~~test_server_stats.py strict dict equality~~ | ~~Full-dict equality broke every time broadcast() added a field~~ | ~~Resolved: test-quality refactor~~ ✅ |
| SignalHistoryLog memoisation | `React.memo` with custom comparator — compares `pinnedTimestamp` + `scanResults` content equality | ✅ PHASE-BUILD-3 |
| BAND_PROFILES dict ordering dependency | `fm_broadcast` and `noise_floor` both at 98 MHz; `get_band_for_freq` relies on dict insertion order (`fm_broadcast` first). Documented in docstring. | — (tracked) |
| Clear-focus path does not reset current_band | `handle_set_focus(None)` leaves `shared_state.current_band` pointing to the last tuned band. Acceptable under single-frequency-focus architecture. | — (tracked) |
| Thread-safety stress test blind spot | `test_get_band_for_freq_concurrent` doesn't exercise `current_band_lock` write path (test frequencies don't match BAND_PROFILES). | — (advisory) |
| ~~Classifier schema missing acars/ais~~ | ~~`llm/classifier.py` _JSON_SCHEMA and _AU_BAND_REFERENCE don't list "acars" or "ais" as valid signal_type values.~~ | ~~— (tracked)~~ ✅ RESOLVED in PHASE-CLASSIFIER-SCHEMA-FIX |
| ~~AIS BAND_PROFILES centre vs demodulator centre mismatch~~ | ~~BAND_PROFILES centre_freq_hz (161.975 MHz = CH1) differs from AIS demodulator expected centre (162.000 MHz for dual-channel).~~ Backend resolved in Phase 14: BAND_PROFILES now uses 162.000 MHz. Frontend fully aligned in Phase 16. | ~~— (tracked)~~ ✅ Phase 16 (frontend + backend fully aligned) |
| ~~Frontend/backend AIS frequency mismatch~~ | ~~Frontend hardcodes 161.975 MHz (CH1). BAND_PROFILES expects 162.000 MHz (dual-channel centre).~~ Fixed across Phase 15 and 15b: BAND_GROUPS, OVERVIEW_BANDS, isTuned(), focusFrequency, display text (Phase 15); WaterfallPanel STRIP_CONFIGS, SignalHistoryLog FREQ_COLOUR_MAP, AisVesselPanel isAisFreq, FrequencyList FREQ_CONFIGS (Phase 15b). | ~~Post-Phase 14~~ ✅ Phase 15 + 15b |
| ChromaDB distance reference stale (Phase 13) | `_DISTANCE_SCALE_REFERENCE` in `llm/classifier.py` calibrated for 6D L2 distances. After 7D reseed, thresholds over-classify known signals as "novel." Needs recalibration via live captures. | 9C-Threshold |
| ~~CHECKPOINT arg parser failure~~ | ~~`/build` command `$2` positional arg silently dropped when `$1` is a long multi-line string.~~ Fixed in Phase 14: `build.md` PHASE-TRACKER GATE now supports both `$2 CHECKPOINT` flag and `CHECKPOINT_MODE: ON` embedded in the task body. | ~~— (tracked)~~ ✅ Phase 14 |
| ~~ADS-B subscriber flush gap~~ | ~~`AdsbSubscriber.stop()` did not harvest bootstrap-held CPR positions before shutdown.~~ Resolved in PHASE-TECH-DEBT-1.5: `stop()` now calls `flush()` and broadcasts harvested messages. | ~~— (tracked)~~ ✅ PHASE-TECH-DEBT-1.5 |
| ~~`config/mimir.yaml` stale comment~~ | ~~Comment said "runtime loading not yet implemented" but `scan.py` already calls `load_config()`.~~ | ~~Phase 2+~~ ✅ 2026-06-24 |

---

## Deferred Items

- **BUG-01 (RESOLVED — Phase 9B-Hotfix):** True root cause was in `core/pipeline/fft.py`:
  `compute_psd()` divided `averaged_power` by `max_power` before dBFS conversion,
  forcing peak bin to always be 0.0 dBFS. Fixed by replacing with standard Welch
  periodogram normalisation (`/ (nfft * window_power)`). Gain settings were a red
  herring. Threshold recalibrated to 10.0 dB (provisional). Requires live testing
  with `tools/diagnose_threshold.py` to confirm.

- **ChromaDB re-seed required (open):** Old embeddings computed under broken normalisation
  are now incompatible with new captures. Must re-seed after deploy.

- **ChromaDB re-seed future-proofing (open):** Any future change to fft.py normalisation will
  again invalidate existing embeddings. Document this as a migration requirement.

- **seed_chromadb.py tech debt (RESOLVED — pre-9C-seed-autowipe):** Script must wipe
  collection before inserting to prevent duplicate records (800→1600 observed during
  re-seed). Replaced interactive `check_duplicates()` with automatic `wipe_collection()`.

- **Latent BUG-01 paths (RESOLVED — pre-9C-gain-defaults):** `MimirConfig`
  dataclass defaults updated to lna=0.0 / vga=0.0, `hackrf_rx.py` DEFAULT_LNA/DEFAULT_VGA
  updated to 0/0, `capture_and_save()` docstring updated to "LNA 0 dB / VGA 0 dB".
  `dashboard/shared_state.py` BAND_PROFILES gains documented with per-band rationale.
  All aligned to settled safe configuration (lna=0, vga=0, amp=False).

- **NOAA/Meteor-M2 satellite module (post-Phase 8):** HackRF covers 137-138 MHz.
  NOAA 15 (137.620 MHz), NOAA 18 (137.9125 MHz), NOAA 19 (137.100 MHz),
  Meteor-M2 (137.9 MHz). Requires V-dipole or QFH antenna. Address after all
  8x phases are closed.

- **pyais library with TX capability (post-9E):** `pyais>=3.0.0` is used for AIS NMEA
  decoding. Its `encode` module is loaded at package level but is NEVER called by
  Mimir. It produces NMEA text strings only and has no interaction with radio hardware.
  Documented as RX-only safe usage in `modules/ais/decoder.py` TX-Safety Note.
  Should be added to a future "Libraries with TX capability" tracking table in AGENTS.md.

- **GitHub MCP toolset scoping** — The github MCP server registers many tools and may
  bloat agent context windows in future. Deferred because it is not yet causing problems.
  When addressed: add `"tools": { "github_*": false }` globally to `opencode.json` and
  re-enable per-agent as needed. See MCP Servers section for the exact config block.

- **GitHub PAT rotation reminder** — PAT expires in 90 days from date of creation.
  When it expires: generate a new fine-grained PAT with identical scopes (Contents r/w,
  Issues r/w, Metadata r/o, Pull requests r/o, Mimir repo only), update
  `GITHUB_PERSONAL_ACCESS_TOKEN` in `~/.config/fish/config.fish`, restart OpenCode,
  verify with `opencode mcp list`.

- **ADS-B message.py stale comments (RESOLVED — PHASE-TECH-DEBT-1):** `modules/adsb/message.py`
  latitude/longitude field comments still reference "from position_with_ref()" which
  was replaced by PipeDecoder in Phase 9F-CPR. Should read "from PipeDecoder global
  CPR pair resolution". Cosmetic but misleading for future contributors.

- **ADS-B subscriber.py flush gap (RESOLVED — PHASE-TECH-DEBT-1.5):** `AdsbSubscriber.stop()`
  now calls `decoder.flush()` before shutting down the decode thread. `AdsbDecoder.flush()`
  tracks position-bearing result dicts during bootstrap and returns `list[AdsbMessage]` after
  `PipeDecoder.flush()` retro-fills lat/lon in-place. `stop()` broadcasts each harvested message
  via the same `self._broadcast_fn` used during normal decode operation before fully stopping.
  Verified with `test_stop_broadcasts_harvested_messages` and `test_stop_no_broadcast_when_flush_empty`.

- **ACARS sub-panel 130.025 MHz inconsistency (RESOLVED — PHASE-BUILD-3-fix):** `App.jsx`
  `isTuned(focusedFreq, 129125000, 5000)` only matched 129.125 MHz, but `AcarsMessagePanel`
  checked both 129.125 and 130.025 MHz. When focused to 130.025 MHz, the outer header showed
  "NOT TUNED" while the inner panel rendered correctly. Fixed by adding an `isAcarsTuned()`
  helper that ORs both frequency checks (with 5 kHz margins) and using it at both `isTuned`
  call sites in the ACARS sub-panel. Tests added for 130.025 MHz tuned state.

- **AIS missing from OVERVIEW_BANDS (RESOLVED — Phase 15):** AIS (162.000 MHz,
  `--neon-red`) was added to `App.jsx` OVERVIEW_BANDS and BAND_GROUPS in Phase 15,
  completing the nav bar coverage. STRIP_CONFIGS resolved in PHASE-BUILD-3;
  OVERVIEW_BANDS and BAND_GROUPS resolved in Phase 15.

- **BANDS vs STRIP_CONFIGS ordering mismatch (RESOLVED — PHASE-TECH-DEBT-2):** `App.jsx`
  OVERVIEW_BANDS was genuinely missing AVIATION VHF (127 MHz) and ACARS (129.125 MHz)
  entirely (not just misordered). Both bands added in PHASE-TECH-DEBT-2, now matching
  all 6 entries in `WaterfallPanel.jsx` STRIP_CONFIGS. Minor cosmetic ordering difference
  remains (BANDS: FM→AVIATION→ACARS→APRS→ISM→ADS-B vs STRIP_CONFIGS: FM→APRS→AVIATION→ACARS→ISM→ADS-B)
  but both lists now contain the same 6 bands.

- **Missing ACARS/AIS tuned-state tests (RESOLVED — PHASE-BUILD-3):** `AdsbTunedState.test.jsx`
  covered the three-state logic for ADS-B only. The equivalent logic for ACARS (lines 1089–1125)
  and AIS (lines 1159–1195) in `App.jsx` had no test coverage. Added `AcarsTunedState.test.jsx`
  (2 tests) and `AisTunedState.test.jsx` (2 tests) covering NOT TUNED / TUNED / TUNED+EMPTY
  three-state logic. A regression in `isTuned()` margin values or the three-state conditional
  would now be caught.

- **MED-01: scan.py fatal error exit path lacks test coverage (RESOLVED — PHASE-TECH-DEBT-1):** `scan.py` `main()` sets
  `fatal_error = True` in the `except Exception` handler and exits with code 1, but there is
  no test verifying the exit code 1 path. The existing `test_scan.py` only covers startup
  failure (RuntimeError/OSError) and KeyboardInterrupt. A test for `except Exception` would
  require mocking `ScanRunner.run()` to raise a generic exception. Deferred because this build
  explicitly forbade test file changes.

- **ADS-B gain divergence (open — tools vs production):** `tools/calibrate_thresholds.py` and
  `tools/diagnose_fingerprints.py` use (32/38) for ADS-B gain (lna/vga) while
  `dashboard/shared_state.py` BAND_PROFILES uses (24/24). Both tool files correctly label
  their values as provisional/stock-stub. Documented in inline TODOs. Will resolve when ADS-B
  is live-tested with the telescopic whip antenna.

---