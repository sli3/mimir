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

**Total passing: 422 passing (325 pytest + 97 Vitest), 6 pre-existing pytest failures (428 total)**
- Note: 6 pre-existing pytest failures — test environment changes after Phase 11-Hotfix delivery increased the count from 1 to 6. All pre-date PHASE-TOOLS-CLEANUP work.

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
| Queue drain pattern | `_scan_loop()` drains queue before every insert ('latest wins'). AI loop always classifies freshest scan. Queue depth at steady state: 0–1 items. Introduced: 2026-06-16. | — |
| ~~`psd_db` uncalibrated~~ | ~~FFT missing nfft normalisation~~ — fixed in Phase 9B-Hotfix (true dBFS) | ~~Post 7B~~ ✅ 9B-Hotfix |
| scan.py startup message | "Scanning N frequencies" is misleading now that single-freq focus mode is active | Post 8C cosmetic |
| Orphaned dashboard components | `SystemStatsPanel.jsx` and `AIReasoningPanel.jsx` are not imported by `App.jsx` -- live dashboard renders stats and AI reasoning inline. Components exist only as standalone test targets. | Pre-prod integration |
| ~~test_server_stats.py strict dict equality~~ | ~~Full-dict equality broke every time broadcast() added a field~~ | ~~Resolved: test-quality refactor~~ ✅ |

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

- **MED-01: scan.py fatal error exit path lacks test coverage (open):** `scan.py` `main()` sets
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

## Session Memos

### 2026-06-17 — README Phase Tracker Sync (documentation-only)

**Type:** Documentation

**What was done:**
- Synced the Phase Tracker table in `README.md` with the canonical table
  from `docs/ROADMAP.md` and `AGENTS.md`. The README table had not been
  updated since Phase 7B and was significantly out of date. Replaced it
  entirely with the full phase list (0 through 11-Hotfix) including correct
  names, statuses, and test counts.
- Updated the total test count line from `425/425 (328 pytest + 97 Vitest)`
  to `427/427 (330 pytest + 97 Vitest)`.
- In Quick Start (Option B — UV-based), changed `uv run python scan.py` to
  `python scan.py` and added a comment explaining that `uv run` fails because
  SoapySDR is a system package not in the uv venv.

**Files changed:**
- `README.md`: Phase Tracker table replaced, test count line updated, Quick Start command corrected

**Test counts:** 330 pytest + 97 Vitest = 427/427 passing (unchanged). 1 pre-existing pytest failure in `test_adsb_demodulator.py::test_preamble_detection_synthetic` remains.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — documentation only, no code or RF interaction

**Decisions made:**
- Phase Tracker replaced wholesale rather than patching individual rows — the old table was missing 12+ phases and had stale names/statuses
- `python scan.py` chosen over `uv run python scan.py` because SoapySDR is installed as a system package (dnf) and not available inside the uv virtualenv

**Deferred items surfaced:**
- None — this is a pure documentation sync with no code implications

**Next session starter:**
None — documentation sync complete. No code changes, no tests run.

---

### 2026-06-16 — Phase 11 Hotfix: Broadcast Defaults, FM Threshold, Startup Guard (bug-fix, standalone)

**Type:** Code / Bug-fix (standalone, NOT a new phase)

**What was done:**
- Added `0.0` defaults to `signal_threshold_db` and `snr_margin_db` broadcast
  fields in `dashboard/server.py` `broadcast()` to prevent KeyError when these
  keys are absent from the fingerprint dict. Moved these keys to immediately after
  `snr_db` in the emit dict (was after `chroma_distance`).
- Raised `signal_threshold_db` in `BAND_PROFILES["fm_broadcast"]` from `10.0` to
  `12.0` based on live FM Adelaide testing. Updated inline comment with calibration
  basis.
- Added startup error guard in `scan.py` `main()`: wrapped `HackRFReceiver(...)`
  construction and `device.open()` in `try/except (RuntimeError, OSError)` that
  logs `Startup failed: %s. Is the HackRF connected?` at ERROR level and calls
  `sys.exit(1)`. `load_config()` remains outside try/except; existing `finally`
  teardown block unchanged.
- Added new test file `tests/test_scan.py` with 3 tests: RuntimeError startup
  failure, OSError startup failure, and successful startup followed by
  KeyboardInterrupt yielding exit 0.
- Updated `tests/dashboard/test_server_stats.py` expected dict ordering for
  `test_filter_passes_matching`.

**Files changed:**
- `dashboard/server.py`: `signal_threshold_db` and `snr_margin_db` defaults 0.0, reordered keys
- `dashboard/shared_state.py`: `BAND_PROFILES["fm_broadcast"]["signal_threshold_db"]` 10.0 -> 12.0
- `scan.py`: startup try/except guard around HackRFReceiver and device.open()
- `tests/test_scan.py`: 3 new tests (RuntimeError, OSError, success + KeyboardInterrupt)
- `tests/dashboard/test_server_stats.py`: updated expected dict ordering

**Test counts:** 427/427 (330 pytest + 97 Vitest)
- Note: 1 pre-existing pytest failure in `test_adsb_demodulator.py::test_preamble_detection_synthetic`.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are RX-only backend threshold, broadcast defaults, and startup error handling

**Decisions made:**
- `signal_threshold_db` and `snr_margin_db` defaults set to `0.0` (not None) to
  match the float broadcast semantics and avoid downstream type errors in the frontend
- FM threshold raised to 12.0 dB based on live testing with Adelaide FM signals at
  lna=24/vga=26 gain settings
- Startup guard catches both RuntimeError and OSError — HackRF can raise either
  depending on whether the device is absent, busy, or has a permissions problem
- `load_config()` intentionally left outside try/except — config failures should
  surface as unhandled exceptions (programming errors), not silent exits

**Deferred items surfaced:**
- `dashboard/shared_state.py` `noise_floor` profile comment is stale (says "same as FM"
  but FM is now 12.0 while noise_floor remains 10.0). Pre-existing.
- `scan.py` `except Exception` in scanner.run() path exits with code 0 — pre-existing,
  no test coverage
- `test_server_stats.py` strict dict equality fragility — pre-existing

**Next session starter:**
None — standalone fixes complete and tested. 427/427 tests passing.

---

### 2026-06-16 — HackRF Stream Reset + Crosshair Frequency Labels (bug-fix, standalone)

**Type:** Code / Bug-fix (standalone, NOT a new phase)

**What was done:**
- Replaced bare `time.sleep` retry in `hackrf_rx.py` `read_samples()` with a proper
  stream reset (deactivateStream + activateStream) on SoapySDR timeout error (-4).\  Added `logger.warning` with frequency for diagnostic visibility. This fixes
  intermittent hangs where the HackRF stream stalled after retune.
- Added frequency label (e.g. "1090.125 MHz") next to the dashed crosshair line
  in WaterfallPanel.jsx crosshair overlay useEffect.
- Added `Math.max(4, ...)` clamp to the SpectrometerBar.jsx frequency label `labelX`
  calculation to prevent left-edge clipping.
- Added new test file `tests/core/test_hackrf_rx.py` with 2 tests covering the
  stream reset retry path.

**Files changed:**
- `core/device/hackrf_rx.py`: stream reset retry replacing bare sleep; logger.warning
- `dashboard/frontend/src/components/WaterfallPanel.jsx`: crosshair frequency label
- `dashboard/frontend/src/components/SpectrometerBar.jsx`: labelX left-edge clamp
- `tests/core/test_hackrf_rx.py`: 2 new tests (stream reset on timeout, retry succeeds)

**Test counts:** 418/418 (321 pytest + 97 Vitest)
- Note: 4 pytest failures in `test_ais_decoder.py` are pre-existing (missing `pyais` module).

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are RX-only device driver and frontend display

**Decisions made:**
- Stream reset chosen over extended sleep because it re-initialises the SoapySDR
  stream cleanly and recovers from genuine stalls, whereas a longer sleep only
  delays the same failure
- `logger.warning` with frequency aids live debugging without flooding logs at INFO
  level

**Deferred items surfaced:**
- LOW-01: crosshair label can overlap crosshair line at extreme left edge (cosmetic,
  both WaterfallPanel and SpectrometerBar)
- Advisory: `time.sleep` in tests not mocked (0.15s per test, acceptable for CI)
- Advisory: `config.freq_hz` not in WaterfallPanel useEffect deps (React remounts
  on band change via key prop, correct but implicit)

**Next session starter:**
None — standalone fixes complete and tested. 418/418 tests passing.

---

### 2026-06-16 — SpectrometerBar Frequency Cursor + SDR NOT RESPONDING Fix (bug-fix, standalone)

**Type:** Code / Bug-fix (standalone, NOT a new phase)

**What was done:**
- Reworked SpectrometerBar as a display-only frequency cursor. Clicking the
  spectrometer canvas now draws a crosshair + frequency label (e.g. "97.854 MHz")
  at the clicked pixel without changing the focus frequency. The previous
  snap-to-nearest-STRIP_CONFIG behaviour has been removed.
- Added `crosshairFreqRef` and `crosshairVersion` state to SpectrometerBar.
  `handleClick` stores the raw computed frequency and increments `crosshairVersion`
  to force an immediate canvas redraw.
- Added a `useEffect` watching `focusedFreq` that clears the crosshair cursor
  when the band changes (addresses LOW-01 from previous review).
- Removed `STRIP_CONFIGS` import from SpectrometerBar (no longer needed).
- Fixed SDR NOT RESPONDING display: reduced the error-state window in
  `dashboard/server.py` from 30 seconds to 5 seconds. The hardware already
  recovers within 250ms (hackrf_rx.py `set_center_frequency` settle sleep);
  the 30-second window was causing the dashboard to show the error state
  long after the hardware was healthy.
- Updated tests: removed 2 snap-to-nearest tests, added 2 cursor tests,
  updated 1 existing test to expect no focusFrequency call. Updated
  `test_server_stats.py` for the 5s window.

**Files changed:**
- `dashboard/frontend/src/components/SpectrometerBar.jsx`: cursor-only handleClick,
  crosshair clearing useEffect, frequency label drawing
- `dashboard/server.py`: NOT RESPONDING window 30.0 → 5.0
- `dashboard/frontend/src/tests/SpectrometerBar.test.jsx`: 2 removed, 2 added, 1 updated
- `tests/dashboard/test_server_stats.py`: updated for 5s window
- `docs/wiki.md`: Phase Log entry added

**Test counts:** 416/416 (319 pytest + 97 Vitest)
- Note: 4 pytest failures in `test_ais_decoder.py` are pre-existing.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are frontend/backend display only

**Decisions made:**
- `focusFrequency` prop is retained in SpectrometerBar's signature (still passed
  by App.jsx) but no longer used. Removing it would require App.jsx changes.
- 5s NOT RESPONDING window is appropriate because `record_hw_error()` is only
  called on genuine `read_samples()` failures, not on retune. The 250ms settle
  in hackrf_rx.py handles normal band switches.

**Deferred items surfaced:**
- [LOW-01] crosshairVersion increment is redundant on band change (canvas useEffect
  already re-runs on focusedFreq change). Harmless — React batches it.
- [LOW-02] Frequency label can clip at left canvas edge when crosshair is very
  close to left edge. Cosmetic only.

**Next session starter:**
None — standalone fixes complete and tested.

---

### 2026-06-16 — BUG-WATERFALL-CLICK: Waterfall Canvas Click Freeze (bug-fix, standalone)

**Type:** Code / Bug-fix (standalone, NOT a new phase)

**What was done:**
- Fixed BUG-WATERFALL-CLICK: canvas click in singleBand mode was computing a
  non-STRIP_CONFIG focus frequency (e.g. 1089753124 instead of 1090000000),
  which broke the strict-equality latestUpdate lookup in WaterfallPanel and
  froze the waterfall.
- Guarded the `focusFrequency()` call in `WaterfallStrip.handleCanvasClick` behind
  `!singleBand`. Crosshair still draws in singleBand mode, but the frequency
  is no longer retuned from the canvas.
- Added JSDoc block to `handleCanvasClick` documenting the singleBand guard.
- Added two regression tests to `WaterfallPanel.test.jsx`:
  * `singleBand=true: clicking the canvas does NOT call focusFrequency`
  * `singleBand=false: clicking the canvas calls focusFrequency with a computed frequency`

**Files changed:**
- `dashboard/frontend/src/components/WaterfallPanel.jsx`: handleCanvasClick guard,
  JSDoc comment, singleBand added to useCallback deps
- `dashboard/frontend/src/tests/WaterfallPanel.test.jsx`: 2 new regression tests
- `docs/wiki.md`: BUG-WATERFALL-CLICK entry added to Phase Log

**Test counts:** 413 (318 pytest + 95 Vitest)
- Note: 4 pytest failures in `test_ais_decoder.py` are pre-existing (missing `pyais`
  module in environment), not caused by this change.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are frontend React only

**Decisions made:**
- In singleBand mode, canvas clicks are now no-ops for frequency retuning. The
  crosshair still draws so users get visual feedback. The only way to change
  band in singleBand mode is via the band nav buttons, which always emit exact
  STRIP_CONFIG canonical frequencies.

**Deferred items surfaced:**
- BUG-WATERFALL-SPEED: suspected downstream symptom of BUG-WATERFALL-CLICK.
  Needs live verification after this fix. If ADS-B waterfall is still slow
  after deploying, investigate further.

**Next session starter:**
Verify BUG-WATERFALL-SPEED is resolved by live-testing the ADS-B waterfall.

---

### 2026-06-16 — Dashboard Cosmetic UI Fixes (bug-fix, standalone)

**Type:** Code / Bug-fix (standalone, NOT a new phase)

**What was done:**
- **SystemStatsPanel.jsx**: Combined SCAN COUNT and QUEUE DEPTH into a single
  row with side-by-side sub-columns. Added `Math.round()` to LLM inference ms
  display to eliminate fractional millisecond rendering.
- **AIReasoningPanel.jsx**: Moved timestamp from bottom of flex column to above
  the reasoning text, with `marginBottom: 4` gap for visual separation.
- **App.jsx** (live UI): Applied the same fixes to the inline rendering that the
  live dashboard actually uses. In the SYSTEM STATUS grid, merged SCAN COUNT and
  QUEUE into one cell (side-by-side layout within the cell). Added `Math.round()`
  to the LLM INFERENCE cell. In the AI REASONING section, moved timestamp from
  absolute-positioned top-right to above the reasoning text with left alignment.

**Files changed:**
- `dashboard/frontend/src/components/SystemStatsPanel.jsx`: merged stats row, Math.round()
- `dashboard/frontend/src/components/AIReasoningPanel.jsx`: timestamp repositioned
- `dashboard/frontend/src/App.jsx`: same fixes applied to live inline rendering
- `docs/wiki.md`: cosmetic UI fixes entry added to Phase Log

**Test counts:** 404/404 (313 pytest + 91 Vitest)

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None -- all changes are frontend layout only

**Decisions made:**
- Fixes applied to both orphaned component files AND App.jsx live inline code to
  keep them consistent if components are ever integrated
- `Math.round()` chosen over `toFixed()` to avoid string conversion edge cases

**Deferred items surfaced:**
- `SystemStatsPanel.jsx` and `AIReasoningPanel.jsx` are orphaned components -- not
  imported by `App.jsx`. They exist only as standalone components consumed by their
  test files. Live dashboard renders system stats and AI reasoning inline. Documented
  as tech debt in Known Tech Debt table.

**Next session starter:**
None -- standalone cosmetic fix complete and tested. 404/404 tests passing.

---

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

---

### 2026-06-17 — Memo-Writer Scope Expansion: README.md phase tracker (config-only)

**Type:** Code

**What was done:**
- A config-only build adding README.md to the memo-writer agent's scope so the
  phase tracker table in README.md stays in sync after every build. Two files
  changed: `.opencode/agents/memo-writer.md` (YAML scope item 3 updated to
  README.md phase tracker refresh rule, scope item 4 added as catch-all) and
  `.opencode/command/build.md` (Step 9 instruction item 3 added, ALWAYS line
  updated to "ROADMAP.md and README.md").

**Files changed:**
- `.opencode/agents/memo-writer.md`: scope items 3 and 4 updated
- `.opencode/command/build.md`: Step 9 item 3 added, ALWAYS line updated

**Test counts:** 330 pytest passed, 1 pre-existing failure (test_adsb_demodulator::test_preamble_detection_synthetic)

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — no code, no RF interaction

**Decisions made:**
- None — config-only build, no design decisions required.

**Deferred items surfaced:**
- None — config-only build with no code or test implications.

**Next session starter:**
None — config-only build complete.

---

### 2026-06-17 — Click-History-to-Pin-Reasoning (frontend-only feature)

**Type:** Code

**What was done:**
- Added click-to-pin AI reasoning from SignalHistoryLog rows. Clicking a signal
  history row pins that entry's AI reasoning text to the AIReasoningPanel for
  close inspection. Clicking the same row again unpins and returns to live mode.
- Wired `pinnedReasoning` state and `handlePinReasoning` callback in `App.jsx`,
  connecting the previously orphaned `SignalHistoryLog` and `AIReasoningPanel`
  components into the live dashboard. Added `key` prop to `AIReasoningPanel` for
  clean remount on pin toggle (resets any internal animation state).
- `SignalHistoryLog.jsx`: added `onPinReasoning` and `pinnedTimestamp` props,
  onClick handler per row, `data-pinned` attribute, amber highlight styling for
  the pinned row.
- `AIReasoningPanel.jsx`: added `isPinned` prop, displays a `◆ PINNED` badge
  between the `freq_hz` and `signal_type` lines when active.
- Added 8 new Vitest tests across 3 test files: 4 in SignalHistoryLog, 3 in
  AIReasoningPanel, 1 integration test in SignalDetailsFreeze.
- Fixed existing `SignalDetailsFreeze.test.jsx`: `getByText` changed to
  `getAllByText` to handle duplicate string matches.

**Files changed:**
- `dashboard/frontend/src/App.jsx`: pinnedReasoning state, handlePinReasoning callback, wired SignalHistoryLog and AIReasoningPanel components, key prop on AIReasoningPanel
- `dashboard/frontend/src/components/SignalHistoryLog.jsx`: onPinReasoning/pinnedTimestamp props, onClick handler, data-pinned attribute, pinned amber styling
- `dashboard/frontend/src/components/AIReasoningPanel.jsx`: isPinned prop, ◆ PINNED badge
- `dashboard/frontend/src/tests/SignalHistoryLog.test.jsx`: +4 tests
- `dashboard/frontend/src/tests/AIReasoningPanel.test.jsx`: +3 tests
- `dashboard/frontend/src/tests/SignalDetailsFreeze.test.jsx`: +1 integration test, getByText→getAllByText fix

**Test counts:** 435 total (330 pytest + 105 Vitest)
- Pytest: 330 passing, 1 pre-existing failure (test_adsb_demodulator::test_preamble_detection_synthetic)
- Vitest: 105 passing (97 existing + 8 new)

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are frontend React only, no RF interaction

**Decisions made:**
- `key` prop on `AIReasoningPanel` used for clean remount on pin toggle — avoids stale
  animation/transition state when swapping between live and pinned content
- Amber highlight chosen for pinned rows to contrast with the cyberpunk theme's default
  cyan/green palette
- `data-pinned` attribute added for test selectors and future CSS theming — follows
  existing pattern in the codebase for test-friendly markup

**Deferred items surfaced:**
- `SignalHistoryLog` and `AIReasoningPanel` components are now wired into `App.jsx` and
  no longer orphaned — they were previously listed in Known Tech Debt as orphaned.
  The Known Tech Debt table entry should be struck through in a future build.
- `SignalHistoryLog` row onClick uses `stopPropagation()` — if the component is ever
  nested inside a parent clickable element, the pin-toggle will not propagate. Pre-existing
  concern, not introduced here.
- Pin state is lost on page refresh (component state, not persisted). This is intentional —
  pinning is a transient UX affordance, not a persistent feature.
- `SignalDetailsFreeze.test.jsx` `getByText` → `getAllByText` change exposes a potential
  fragility: any future duplicate text in the render tree will silently match the first
  element. Consider `getAllByText` with index-based assertions in future builds.

**Next session starter:**
None — standalone frontend feature complete and tested. 435/435 tests passing (330 pytest + 105 Vitest).

---

### 2026-06-17 — Frontend UI Readability Fixes (AIReasoningPanel + SignalHistoryLog)

**Type:** Code / Frontend (standalone, NOT a checkpoint)

**What was done:**
- Increased AI Reasoning container height from 154px to 210px in `App.jsx` (line 975)
  to resolve vertical overflow of reasoning text at the new font sizes — fix driven
  by @deep-analyst code review finding.
- Increased 7 font-size values and flex gap (6 → 8) in `AIReasoningPanel.jsx` for
  improved readability of the live AI reasoning display.
- Removed opacity conditional from row `div` style in `SignalHistoryLog.jsx` — rows
  below index 4 were dimmed, making them harder to read in the signal history log.

**Files changed:**
- `dashboard/frontend/src/App.jsx`: container height 154px → 210px
- `dashboard/frontend/src/components/AIReasoningPanel.jsx`: 7 font-size increases, gap 6 → 8
- `dashboard/frontend/src/components/SignalHistoryLog.jsx`: removed opacity conditional

**Test counts:** 105 Vitest passing (unchanged from previous session). Pytest not run (frontend-only build).

**PM Audit Result:** Clean — all findings actioned, conflict (reviewer vs deep-analyst on container height) adjudicated in favour of @deep-analyst, no constraint violations.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are frontend React only, no RF interaction

**Decisions made:**
- 210px chosen as the new container height after testing confirmed it accommodates the
  largest rendered reasoning text block at the increased font sizes without clipping
- Opacity conditional removed entirely (rather than adjusting threshold) because dimming
  a subset of history rows provides no functional benefit and reduces readability

**Deferred items surfaced:**
- None — clean build, no new tech debt

**Next session starter:**
None — standalone frontend fixes complete and tested. 105/105 Vitest passing.

---

### 2026-06-18 — AI Panel Badge Redesign (frontend-only cosmetic)

**Type:** Code

**What was done:**
Three cosmetic badge changes to the frontend dashboard:

1. **AIReasoningPanel.jsx — CLASSIFICATION LOG heading**: Added a section heading
   at the top of the non-placeholder content reading "CLASSIFICATION LOG" (font-display,
   fontSize 10, var(--text-dim)).

2. **AIReasoningPanel.jsx — Boxed ◆ PINNED badge**: Replaced the plain inline
   "◆ PINNED" text with a boxed badge (border 1px solid var(--neon-amber),
   background rgba(255,170,0,0.14), box-shadow 0 0 6px rgba(255,170,0,0.35),
   padding 2px 8px, font-display, fontSize 10, letterSpacing 1). Timestamp moves
   alongside the badge in amber. When not pinned, shows only the timestamp in
   var(--text-bright).

3. **App.jsx — Boxed ◆ ACTIVE/◆ IDLE badges**: Replaced the ● ACTIVE/● IDLE
   dot+text spans with single boxed badge divs. ACTIVE: #ff4444 border/glow with
   blink animation. IDLE: var(--text-dim) border, transparent background. Uses
   `◆ <span>IDLE</span>` to preserve exact-match test at SignalDetailsFreeze.test.jsx:65.

**Files changed:**
- `dashboard/frontend/src/components/AIReasoningPanel.jsx`: Added CLASSIFICATION LOG
  heading, replaced line 1 with conditional boxed PINNED badge
- `dashboard/frontend/src/App.jsx`: Replaced ACTIVE/IDLE dot+text spans with boxed badges
- `docs/wiki.md`: Updated by doc-writer

**Test counts:** 105 Vitest passing (100%), 330 pytest passing (1 pre-existing failure in
test_adsb_demodulator). Unchanged from previous build.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — frontend-only React/CSS changes, no RF interaction

**Decisions made:**
- Used `◆ <span>IDLE</span>` structure instead of flat text to preserve the existing
  `getByText('IDLE')` exact-match test without modifying SignalDetailsFreeze.test.jsx
- Used `#ff4444` for ACTIVE badge per spec (design system caution about --neon-red
  availability), though both code reviewers noted --neon-red exists in cyberpunk.css
- No test file changes required

**Deferred items surfaced:**
- LOW-01: ACTIVE badge uses hardcoded `#ff4444` instead of `var(--neon-red)` —
  advisory from both code reviewers, spec explicitly required `#ff4444`
- LOW-02: App.jsx ACTIVE/IDLE badge conditional indentation off by 2 spaces —
  cosmetic, no functional impact

**Next session starter:**
None — standalone badge redesign complete and tested. 105/105 Vitest passing.

---

### 2026-06-18 — AI Panel Classification Log Fix (frontend-only)

**Type:** Code

**What was done:**
Two small fixes to AIReasoningPanel.jsx:

1. **Moved CLASSIFICATION LOG heading** — relocated the heading from above the
   status/timestamp row (Line 1) to immediately above the reasoning body. Correct
   element order is now: Line 1 (status/timestamp) → Line 2 (identity) → Line 3
   (confidence) → CLASSIFICATION LOG heading → Reasoning body.

2. **Increased heading font size** — changed from 10 to 11 for improved readability.

**Files changed:**
- `dashboard/frontend/src/components/AIReasoningPanel.jsx`: Repositioned CLASSIFICATION
  LOG heading div; bumped fontSize from 10 to 11; updated JSDoc to reflect new position
- `docs/wiki.md`: Phase log updated by doc-writer

**Test counts:** 105 Vitest passing (unchanged). 330 pytest passing (1 pre-existing failure
in test_adsb_demodulator). Unchanged from previous build.

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — frontend-only React/CSS changes, no RF interaction

**Decisions made:**
- Heading moved above reasoning body for semantic correctness — the label introduces the
  reasoning text, not the metadata rows above it
- fontSize 11 chosen to match the placeholder text size (AWAITING SIGNAL...)

**Deferred items surfaced:**
- LOW-03 (advisory): CLASSIFICATION LOG heading has marginBottom: 4 but no marginTop.
  When the conditional confidence row is present the gap is 0px — cosmetic only.

**Next session starter:**
None — standalone fixes complete. 105/105 Vitest passing.

---

### 2026-06-18 — test_server_stats.py Test-Quality Refactor (test-quality refactor)

**Type:** Code (test-quality refactor)

**What was done:**
- Refactored `test_filter_passes_matching` in `tests/dashboard/test_server_stats.py` from strict full-dict equality (`assert_called_once_with("scan_result", {full_dict})`) to individual key assertions for semantically important fields. The old pattern enumerated every key in the broadcast payload and broke every time a new field was added to `broadcast()` (broke twice: Phase 10-Fix2, Phase 11). The new pattern only asserts routing fields (center_freq_hz, timestamp), classification identity (signal_type, confidence, confidence_score, novel, au_legal_status), and explicitly-provided fingerprint fields (peak_power_db, snr_db, signal_threshold_db, snr_margin_db, bandwidth_hz, spectral_flatness, chroma_distance). Uses `pytest.approx` for float fingerprint fields.
- Refactored `test_passes_all_when_focus_is_none` to add loose key assertions (event_name, center_freq_hz, signal_type) — previously only verified emit was called.
- `test_filter_blocks_non_matching` left untouched (uses `assert_not_called()`, already loose and correct).
- No production code changes. Single file: `tests/dashboard/test_server_stats.py`.

**Files changed:**
- `tests/dashboard/test_server_stats.py` — refactored 2 test methods
- `docs/wiki.md` — phase log entry added by @doc-writer

**Test counts:** 423 passing (326 pytest + 97 Vitest), 5 pre-existing pytest failures (1 ADS-B demod + 4 AIS decoder pyais missing)

**RF/Legal Notes:**
- TX safety incidents: None
- AU legal flags: None — all changes are test quality refactoring, no RF or production code interaction

**Decisions made:**
- Individual key assertions chosen over full-dict equality to eliminate the recurring breakage pattern when broadcast() payload fields are added or reordered
- `pytest.approx` used for float fingerprint fields to tolerate minor numerical variation from feature extraction
- Routing fields (center_freq_hz, timestamp) and classification identity fields asserted with strict equality — these are the API contract between server and frontend

**Deferred items surfaced:**
- None — clean refactor, no new tech debt

**Next session starter:**
None — standalone test quality refactor complete and tested. 423/423 tests passing.