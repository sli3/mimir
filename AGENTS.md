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
| 9C-Threshold | Calibrate SIGNAL_THRESHOLD_DB | ⏳ PENDING ANTENNA | — |

**Total passing: 404/404 (313 pytest + 91 Vitest)**

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
| `system_stats` | server → browser | hackrf_status, active_frequency_hz, scan_count, queue_depth, llm_last_inference_ms |
| `set_focus_frequency` | browser → server | freq_hz |
| `acars_message` | server → browser | timestamp, freq_hz, registration, label, block_id, text, crc_ok |
| `ais_message` | server → browser | timestamp, mmsi, vessel_name, lat, lon, speed, course, channel |
| `adsb_aircraft` | server → browser | icao, callsign, altitude_ft, latitude, longitude, groundspeed, track, vertical_rate, timestamp |

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
| `FrequencyList.jsx:67` | `confidence_score` lacks null guard | Phase 7B polish |
| CORS wildcard | `cors_allowed_origins="*"` in server.py — fine for dev | Pre-prod |
| Queue max hard-coded | `020` in SystemStatsPanel — should read from systemStats | Phase 7B |
| `sampleRateHz` dead param | Accepted by `useWaterfall.js` but unused | Post 7B |
| ~~`psd_db` uncalibrated~~ | ~~FFT missing nfft normalisation~~ — fixed in Phase 9B-Hotfix (true dBFS) | ~~Post 7B~~ ✅ 9B-Hotfix |
| scan.py startup message | "Scanning N frequencies" is misleading now that single-freq focus mode is active | Post 8C cosmetic |

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

- **ADS-B message.py stale comments (open — Phase 9F-CPR):** `modules/adsb/message.py`
  latitude/longitude field comments still reference "from position_with_ref()" which
  was replaced by PipeDecoder in Phase 9F-CPR. Should read "from PipeDecoder global
  CPR pair resolution". Cosmetic but misleading for future contributors.

- **ADS-B subscriber.py flush gap (open — Phase 9F-CPR):** `AdsbSubscriber.stop()` does
  not call `decoder.flush()` before shutting down the decode thread. Aircraft with fewer
  than BOOTSTRAP_K=5 CPR pairs accumulate in the PipeDecoder but are never released at
  shutdown — their positions are silently discarded. A flush() call in stop() would
  release these bootstrap-held positions to the dashboard before exit.

- **ACARS sub-panel 130.025 MHz inconsistency (open — Phase 10-Hotfix):** `App.jsx`
  `isTuned(focusedFreq, 129125000, 5000)` only matches 129.125 MHz, but `AcarsMessagePanel`
  checks both 129.125 and 130.025 MHz. If user focuses 130.025 MHz, the outer sub-panel
  shows "NOT TUNED" while the inner panel renders correctly. Fix: align the outer `isTuned`
  check with the panel's dual-frequency check.

- **AIS missing from STRIP_CONFIGS/OVERVIEW_BANDS (open — Phase 10-Hotfix):** AIS
  (161.975 MHz) is not in `WaterfallPanel.jsx` STRIP_CONFIGS or `App.jsx` OVERVIEW_BANDS.
  When tuned to AIS, the `singleBand` waterfall falls back to FM Broadcast (STRIP_CONFIGS[0])
  because no config matches within 2 MHz. The waterfall shows FM data while the user is
  tuned to AIS. Intentional omission (AIS is narrowband, may not render visibly) but UX gap.

- **BANDS vs STRIP_CONFIGS ordering mismatch (open — Phase 10-Hotfix):** `App.jsx` BANDS
  order: FM → AVIATION → ACARS → APRS → ISM → ADS-B. `WaterfallPanel.jsx` STRIP_CONFIGS
  order: FM → APRS → AVIATION → ACARS → ISM → ADS-B. APRS and AVIATION/ACARS are swapped.
  Cosmetic but could confuse users expecting visual consistency between nav bar and waterfall.

- **Missing ACARS/AIS tuned-state tests (open — Phase 10-Hotfix):** `AdsbTunedState.test.jsx`
  covers the three-state logic for ADS-B only. The equivalent logic for ACARS (lines 1089–1125)
  and AIS (lines 1159–1195) in `App.jsx` has no test coverage. A regression in `isTuned()`
  margin values or the three-state conditional would go undetected.

---

## Session Memos

### 2026-06-16 — Spectrum Broadcast Decoupling (bug-fix, standalone)

**Type:** Code / Bug-fix (standalone, NOT a new phase)

**What was done:**
- Decoupled `spectrum_update` from the AI loop in `core/pipeline/scanner.py`.
  The waterfall socket event now fires from `_scan_loop()` immediately after
  `compute_psd()` at ~4-5 Hz, instead of from `_emit_result()` / `_ai_loop()`
  at ~0.4 Hz. This resolves the stuttering waterfall caused by slow LLM inference.
- Added `_broadcast_spectrum_fn` call in `_scan_loop()` with isolated try/except
  so broadcast failures cannot abort the AI pipeline.
- Removed `_broadcast_spectrum_fn` call from `_emit_result()`.
- Frequency bounds for the broadcast now derive from the actual FFT frequency
  axis (`psd["frequencies_hz"]`) instead of hardcoded plus/minus 1 MHz.
- Added two new tests: `test_scan_loop_broadcasts_spectrum` (verifies broadcast
  from scan loop) and `test_emit_result_does_not_broadcast_spectrum` (verifies
  no broadcast from AI loop).

**Files changed:**
- `core/pipeline/scanner.py`: spectrum broadcast moved from `_emit_result()` to `_scan_loop()`; frequency bounds from FFT axis; isolated try/except
- `tests/core/test_scanner.py`: 2 new tests (scan loop broadcasts, AI loop does not)
- `docs/wiki.md`: Spectrum Broadcast Decoupling entry added to Phase Log

**Test counts:** 404/404 (313 pytest + 91 Vitest)

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are RX-only broadcast path refactoring

**Decisions made:**
- Broadcast call placed immediately after `compute_psd()` in scan loop, before the
  AI pipeline runs, so the waterfall receives data at scan rate (~4-5 Hz) independent
  of LLM inference latency
- Frequency bounds derived from FFT axis instead of hardcoded to support any NFFT or
  center frequency without manual range calculation
- Isolated try/except around broadcast prevents transient SocketIO errors from
  aborting the scan loop

**Deferred items surfaced:**
- `dashboard/capture_loop.py` is a second consumer of `_broadcast_spectrum_fn` that
  could fire simultaneously if activated — potential for duplicate `spectrum_update`
  events. Not currently active (not imported by `scan.py`)
- `ScanResult.psd_db` field is now unused by any broadcast path — could be removed
  as a future optimisation

**Next session starter:**
None — standalone bug-fix complete and tested. 404/404 tests passing.

---

### 2026-06-15 — Phase 10-Fix3: Band Grouping, ADS-B Threshold, Waterfall Gap, Default Focus

**Type:** Code / Frontend + Backend

**What was done:**
- Grouped band nav bar buttons into three categories in `App.jsx`: BROADCAST (FM),
  AVIATION BAND (AVIATION, ACARS, ADS-B), DATA / IoT (APRS, ISM). Each category has a
  9px uppercase label and a vertical divider between groups. Nav bar height increased
  to 48px to accommodate the two-row layout.
- Reduced `PREAMBLE_THRESHOLD` from `2.0` to `1.5` in `modules/adsb/constants.py` after
  live testing showed no ADS-B decodes at 2.0 with confirmed aircraft overhead. The 1.5
  value is the midpoint of the validated range 1.2–2.0 for HackRF One with telescopic
  whip antenna.
- Eliminated the waterfall sidebar gap by adding `hideSidebar` prop to `WaterfallStrip`
  in `WaterfallPanel.jsx`. When `singleBand=true` (current mode), the 110px label sidebar
  is hidden. `WATERFALL_LABEL_WIDTH` changed from `110` to `0`, and `SpectrometerBar.jsx`
  uses it for its left spacer, keeping the spectrometer bar aligned with the waterfall.
- Changed `focusedFreq` default from `null` to `98000000` (FM broadcast) in `useSocket.js`.
  On first page load, the dashboard immediately shows the FM broadcast spectrum instead of
  waiting for the user to click a band button.

**Files changed:**
- `dashboard/frontend/src/App.jsx`: `BAND_GROUPS` constant, grouped nav bar layout
- `modules/adsb/constants.py`: `PREAMBLE_THRESHOLD` 2.0 → 1.5, docstring updated
- `dashboard/frontend/src/components/WaterfallPanel.jsx`: `WATERFALL_LABEL_WIDTH` 0,
  `hideSidebar` prop, conditional label rendering
- `dashboard/frontend/src/hooks/useSocket.js`: `focusedFreq` default 98000000
- `dashboard/frontend/src/tests/App.test.jsx`: updated for grouped nav bar
- `dashboard/frontend/src/tests/WaterfallPanel.test.jsx`: updated for hideSidebar
- `dashboard/frontend/src/tests/useSocket.test.js`: updated for 98000000 default
- `dashboard/frontend/src/tests/SpectrometerBar.test.jsx`: updated for 0px width
- `docs/wiki.md`: Phase 10-Fix3 entry added
- `AGENTS.md`: Phase tracker updated, session memo added

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are RX-only frontend/backend
- PREAMBLE_THRESHOLD change is RX-only decoder sensitivity tuning

**Decisions made:**
- `WATERFALL_LABEL_WIDTH = 0` chosen for `singleBand={true}` mode (always active in App.jsx)
- `focusedFreq = 98000000` is intentional — aligns with single-frequency focus mode and
  provides immediate visual feedback on first page load
- `PREAMBLE_THRESHOLD = 1.5` is a midpoint of the validated range; further reduction to
  1.2 is possible if still no decodes
- BAND_GROUPS test coverage is minimal (only one button click tested in App.test.jsx);
  full coverage deferred due to test complexity

**Deferred items from dual review:**
- Vestigial `focusedFreqRef.current !== null` guard in useSocket.js (dead code, non-blocking)
- Zero-width spacer div in SpectrometerBar.jsx (dead code, non-blocking)
- BAND_GROUPS vs OVERVIEW_BANDS mismatch (6 bands vs 4 bands, pre-existing)
- BANDS vs STRIP_CONFIGS ordering mismatch (cosmetic, pre-existing)
- Missing ACARS/AIS tuned-state tests (pre-existing)

**Next session starter:**
None — all 4 bugs resolved and tested. 402/402 tests passing.

---

### 2026-06-15 — Phase 10-Fix4: Spectral Flatness, Chroma Distance, Waterfall Alignment

**Type:** Code / Frontend + Backend

**What was done:**
- Added `spectral_flatness` (Wiener entropy) computation to `core/pipeline/features.py`.
  Formula: `geometric_mean(linear_power) / arithmetic_mean(linear_power)`. Clamped to
  [0.0, 1.0]. 0.0 = pure tone, 1.0 = white noise. Previously a phantom field (always 0.0).
- Wired `chroma_distance` end-to-end: `scanner.py` extracts from `neighbours_list[0]`, adds
  to fingerprint dict; `server.py` broadcasts; `useSocket.js` surfaces in `aiReasoning`;
  `App.jsx` displays in Signal Details panel.
- Fixed Waterfall / SpectrometerBar alignment by exporting `WATERFALL_LABEL_WIDTH = 110`
  from `WaterfallPanel.jsx` and importing in `SpectrometerBar.jsx`. Added left spacer div.
  Fixed click handler to use canvas-relative coordinates (no double offset).
- Removed `<React.StrictMode>` from `main.jsx` to eliminate double-mounting and duplicate
  socket listeners.
- Updated tests: 4 new spectral_flatness assertions, chroma_distance propagation test,
  SpectrometerBar click handler test.

**Files changed:**
- `core/pipeline/features.py`: Wiener entropy computation, docstring updated
- `core/pipeline/scanner.py`: chroma_distance added to fingerprint dict
- `dashboard/server.py`: chroma_distance added to broadcast payload
- `dashboard/frontend/src/hooks/useSocket.js`: chroma_distance in INITIAL_AI_REASONING
- `dashboard/frontend/src/App.jsx`: chroma_distance in INITIAL_AI_REASONING
- `dashboard/frontend/src/components/WaterfallPanel.jsx`: exported WATERFALL_LABEL_WIDTH = 110
- `dashboard/frontend/src/components/SpectrometerBar.jsx`: left spacer, click handler fix
- `dashboard/frontend/src/main.jsx`: removed React.StrictMode wrapper
- `tests/core/test_fft_features.py`: 4 new spectral_flatness assertions
- `tests/core/test_scanner.py`: chroma_distance assertion
- `tests/dashboard/test_server_stats.py`: chroma_distance in expected payload
- `dashboard/frontend/src/tests/useSocket.test.js`: chroma_distance in expected objects
- `dashboard/frontend/src/tests/SpectrometerBar.test.jsx`: spacer + click handler tests
- `docs/wiki.md`: Phase 10-Fix4 entry added

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are RX-only frontend/backend

**Decisions made:**
- `WATERFALL_LABEL_WIDTH = 110` matches `singleBand={true}` mode (always active in App.jsx)
- In-place mutation of queued fingerprint dict is safe (single consumer, FIFO queue)
- `spectral_flatness` not added to `EMBEDDING_FEATURES` — deferred to future ChromaDB re-seed

**Deferred items from dual review:**
- `spectral_flatness` in `EMBEDDING_FEATURES` (requires ChromaDB re-seed)
- `setup.js` global mock missing `createImageData` (could break future tests)
- `test_server_stats.py` strict dict equality fragility (future field additions will break it)

**Next session starter:**
None — all 4 bugs resolved and tested. 402/402 tests passing.

---

### 2026-06-15 — Phase 10-Fix2: Waterfall Performance + Signal Details Missing Fields

**Type:** Code / Frontend + Backend

**What was done:**
- Fixed waterfall canvas performance by replacing CPU-based `getImageData` + pixel shift
  with GPU-based `ctx.drawImage(canvas, 0, 1)` + single-row `createImageData(width, 1)`.
  Eliminates ~1.8MB of JS pixel buffer manipulation per frame.
- Fixed Signal Details panel showing "---" for POWER, SNR, BANDWIDTH, SPECTRAL FLATNESS
  by adding fingerprint fields (`peak_power_db`, `snr_db`, `bandwidth_hz`, `spectral_flatness`)
  to the SocketIO `scan_result` broadcast payload.
- Synchronised `App.jsx` `INITIAL_AI_REASONING` with `useSocket.js` to include new fields.
- Fixed `useWaterfall.js` edge case where `0 dBFS` (valid value) was incorrectly replaced
  with `-100` due to `||` instead of `??`.
- Updated tests: `useWaterfall.test.js`, `useSocket.test.js`, `test_server_stats.py`.

**Files changed:**
- `dashboard/frontend/src/hooks/useWaterfall.js`: GPU scroll, single-row putImageData, `??` fix
- `dashboard/server.py`: Extended `broadcast()` with fingerprint fields via `fp.get()`
- `dashboard/frontend/src/hooks/useSocket.js`: Extended `INITIAL_AI_REASONING` and `aiReasoning`
- `dashboard/frontend/src/App.jsx`: Synchronised `INITIAL_AI_REASONING` with new fields
- `dashboard/frontend/src/tests/useWaterfall.test.js`: Updated for drawImage + createImageData
- `dashboard/frontend/src/tests/useSocket.test.js`: Added fingerprint field propagation test
- `tests/dashboard/test_server_stats.py`: Updated expected broadcast payload
- `docs/wiki.md`: Phase 10-Fix2 entry added

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are RX-only frontend/backend

**Decisions made:**
- `spectral_flatness` is a pre-existing phantom field (never computed by `fingerprint_spectrum()`).
  It is added to the broadcast per spec, but will show "---" until the pipeline computes it.
  `classifier.py` already handles this with a default of `0.0`.
- `chroma_distance` is NOT added to the broadcast (not available in `scan_result` — lives in AI loop locals)

**Deferred items from dual review:**
- `spectral_flatness` phantom field — add computation to `core/pipeline/features.py` or remove from dashboard
- `setup.js` global mock missing `createImageData` — could break future tests using global mock
- `test_server_stats.py` strict dict equality is fragile — future field additions will break it

**Next session starter:**
None — all 2 bugs resolved and tested. 396/396 tests passing.

---

### 2026-06-15 — Phase 10-Hotfix: Dashboard Live Testing Fixes

**Type:** Code / Frontend Hotfix

**What was done:**
- Fixed 5 bugs discovered during live testing of Phase 10 UI redesign
- Added Aviation (127 MHz) and ACARS (129.125 MHz) to STRIP_CONFIGS
- Fixed stale spectrum display by using `find()` instead of `[...].reverse().find()`
- Added three-state logic for ADS-B, ACARS, and AIS sub-panels (tuned+data / tuned+no-data / not-tuned)
- Changed body font-size to 14px and `--font-display` to Share Tech Mono (Press Start 2P now only for MIMIR logo)
- Verified `focusFrequency()` optimistic update works correctly
- Fixed AisVesselPanel showing wrong AIS frequency (162.000 → 161.975 MHz) — AU compliance
- Updated AGENTS.md font specification to match new design
- Updated docs/wiki.md with Phase 10 and Phase 10-Hotfix entries

**Files changed:**
- `dashboard/frontend/src/components/WaterfallPanel.jsx`: Added 2 bands, `singleBand` prop, `find()` fix
- `dashboard/frontend/src/App.jsx`: Complete redesign with three-row layout, sub-panel states, band nav
- `dashboard/frontend/src/hooks/useSocket.js`: Added `aisVessels` alias
- `dashboard/frontend/src/theme/cyberpunk.css`: Expanded theme tokens, font-size fix
- `dashboard/frontend/src/components/AisVesselPanel.jsx`: Fixed AIS frequency (162.000 → 161.975)
- `dashboard/frontend/src/tests/WaterfallPanel.test.jsx`: Updated for 6 bands, singleBand tests
- `dashboard/frontend/src/tests/AdsbTunedState.test.jsx`: New test for ADS-B three-state logic
- `dashboard/frontend/src/tests/App.test.jsx`: Updated for new layout
- `AGENTS.md`: Phase tracker updated, font spec updated, session memo added
- `docs/wiki.md`: Phase 10 and Phase 10-Hotfix entries added

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all frontend changes, no RF hardware interaction
- AIS frequency display corrected to AU Channel A primary (161.975 MHz)

**Decisions made:**
- `aisVessels` alias kept as `aisMessages` (server emits `ais_message`, panel expects `aisMessages` prop)
- `adsbAircraft` kept as object (keyed by ICAO) — panel expects object, `Object.values()` used where array needed
- `spectrumUpdates.find()` used because array is newest-first (prepending in useSocket.js)
- Press Start 2P retained only for MIMIR logo inline style — all other UI text uses Share Tech Mono

**Deferred items from dual review:**
- ACARS sub-panel 130.025 MHz recognition (pre-existing inconsistency, not introduced by hotfix)
- AIS missing from STRIP_CONFIGS/OVERVIEW_BANDS (UX gap, waterfall fallback to FM when tuned to AIS)
- BANDS vs STRIP_CONFIGS ordering mismatch (cosmetic — APRS and AVIATION/ACARS swapped)
- Missing ACARS and AIS tuned-state tests (coverage gap — only ADS-B tested)
- `aisVessels` alias naming indirection (intentional, working, but smelly)

**Next session starter:**
None — all 5 hotfix bugs resolved and tested. 395/395 tests passing.

---

### 2026-06-14 — Phase 9C-Threshold Calibration

**Type:** Code / Calibration

**What was done:**
- Calibrated SIGNAL_THRESHOLD_DB from 10.0 to 24.0 dB with live antenna testing
- Updated production gain settings: LNA 24 dB, VGA 26 dB across config, loader, device, and band profiles
- Added 8 new tests (306 pytest total, 362 with Vitest)

**Files changed:**
- `core/pipeline/features.py`: SIGNAL_THRESHOLD_DB 10.0 → 24.0, calibration metadata in docstring
- `config/mimir.yaml`: lna_gain_db 0 → 24, vga_gain_db 0 → 26
- `core/config/loader.py`: MimirConfig defaults lna 0.0 → 24.0, vga 0.0 → 26.0
- `core/device/hackrf_rx.py`: DEFAULT_LNA 0 → 24, DEFAULT_VGA 0 → 26
- `dashboard/shared_state.py`: BAND_PROFILES fm_broadcast lna 0 → 24, vga 0 → 26
- `tools/diagnose_threshold.py`: comment updated
- `core/pipeline/capture.py`: docstring updated
- `tests/core/test_fft_features.py`: TestSignalThresholdDb (1 test)
- `tests/core/test_config_loader.py`: TestMimirConfigDefaults (3 tests)
- `tests/dashboard/test_shared_state.py`: TestBandProfiles (4 tests)

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are RX-only gain and threshold settings

**Decisions made:**
- Gain values (24/26) selected based on live testing with telescopic whip antenna
- Threshold set to 24 dB as noise floor + 6 dB margin above typical FM broadcast signals
- Old gain defaults (0/0) replaced with production values (24/26)

**Not finished:**
- `tools/calibrate_thresholds.py` CALIBRATION_TARGETS still uses old gain values
- `tools/diagnose_fingerprints.py` TARGETS still uses old gain values
- Aviation and ADS-B band profiles need revalidation with new antenna

**Next session starter:**
Update `tools/calibrate_thresholds.py` CALIBRATION_TARGETS to use new gain values (24/26) for FM broadcast band.

### 2026-06-15 — Phase 9F-CPR: ADS-B CPR Pair Accumulator

**Type:** Code / Decoder Improvement

**What was done:**
- Upgraded `modules/adsb/decoder.py` from single-frame `position_with_ref()` to `pyModeS.PipeDecoder` — a stateful, per-ICAO CPR pair accumulator
- PipeDecoder buffers even/odd CPR frames per ICAO, pairs them within a 10-second window, and resolves positions globally (no fixed reference point required)
- Stale per-ICAO state is evicted after 300 seconds of silence
- A flush() cycle every 5 seconds releases bootstrap-held positions for aircraft that generate fewer than _BOOTSTRAP_K=5 pairs
- `decode()` gains optional `timestamp: float | None = None` param (defaults to `time.time()` internally) for test determinism
- New `flush()` method exposed for tests and graceful shutdown
- Removed `ADELAIDE_LAT`/`ADELAIDE_LON` import from decoder.py (constants kept in constants.py with updated comments for diagnostic/fallback use)
- All downstream field extraction (`result.get(...)`) unchanged — PipeDecoder returns the same `Decoded` dict subclass as stateless `decode()`

**Files changed:**
- `modules/adsb/decoder.py`: PipeDecoder replaces stateless pms_decode; FLUSH_INTERVAL_SEC=5.0; optional timestamp param; flush() method; updated docstrings
- `modules/adsb/constants.py`: ADELAIDE_LAT/ADELAIDE_LON comments updated (no longer used for primary decoding)
- `tests/modules/test_adsb_decoder.py`: position tests rewritten for pair-based accumulation (single frame yields no position; pair+flush yields valid global position; non-position fields unaffected)
- `docs/wiki.md`: Phase 9F-CPR entry, CPR glossary, pyModeS glossary

**Test counts:** 364/364 (308 pytest + 56 Vitest)

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are RX-only decoder improvements
- pyModeS remains decode-only, no TX capability

**Decisions made:**
- PipeDecoder chosen over manual even/odd frame pairing for robustness and upstream maintenance
- BOOTSTRAP_K=5 chosen to avoid premature position release for aircraft with intermittent reception
- 300-second stale eviction matches ADS-B transponder reporting rates (typically 0.5-1 Hz)
- ADELAIDE_LAT/ADELAIDE_LON retained in constants.py for diagnostic/fallback use only

**Not finished:**
- `modules/adsb/message.py` stale comments: latitude/longitude field comments still say "from position_with_ref()" — should be updated to "from PipeDecoder global CPR pair resolution"
- `modules/adsb/subscriber.py` graceful shutdown: `AdsbSubscriber.stop()` does not call `decoder.flush()` — bootstrap-held positions silently discarded at shutdown
- DF11 test path: `test_non_adsb_downlink_format_returns_none` uses a 28-char DF11 string which hits `InvalidLengthError` rather than the DF gate directly

**Next session starter:**
Update `modules/adsb/message.py` field comments to reference PipeDecoder CPR pair resolution instead of `position_with_ref()`.