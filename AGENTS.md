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
| APRS | 145.175 MHz | AU frequency — NOT 144.390 (US) |
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
| **Intelligence** | Local LLM server (OpenAI-compatible API) |
| **LLM URL** | http://192.168.0.66:8080/v1 (llama.cpp, OpenAI-compatible) |
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

# Ubuntu/Debian
sudo apt-get install hackrf soapysdr-module-hackrf python3-soapysdr
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
uv run python scan.py
```

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
| 8B | Wire real ScanRunner values into system_stats; fix AGENTS.md event table | 🟡 Next | — |

**Total passing: 251/251 (195 pytest + 56 Vitest)**

### Session memo — Phase 8A: ACMA Reference Wiring (Complete)

Phase: 8A -- Wire data/frequency_reference.json into LLM classifier
Status: Complete
Tests: 195 pytest + 56 vitest = 251 total (all passing)

Files created:

  llm/acma_reference.py
    New AcmaReference class. Loads data/frequency_reference.json at __init__
    time into an internal list. Exposes lookup(freq_hz: float) -> list[dict]
    which converts Hz to MHz and returns all entries where
    freq_start_mhz <= freq_mhz <= freq_end_mhz. Logs a warning and sets an
    empty list if the file is missing or fails to parse -- never raises.
    No SDR imports, no TX patterns.

  tests/llm/test_acma_reference.py
    12 tests covering: range match for all four AU bands (FM/APRS/ISM/ADS-B),
    out-of-range empty return, missing file graceful handling, corrupted file
    graceful handling, expected field presence, inclusive boundary checks (lower
    and upper), TX pattern safety check, no-SDR-import check. All passing.

Files modified:

  llm/classifier.py
    classify() and _build_user_prompt() now accept optional
    acma_allocations: list[dict] | None = None parameter.
    When non-empty, appends an "ACMA SPECTRUM PLAN" section to the user prompt
    showing allocation ranges, services list, and mimir_band tag per entry.
    When None or empty, prompt is unchanged -- fully backwards compatible.

  core/pipeline/scanner.py
    ScanRunner.__init__() now instantiates AcmaReference (imported from
    llm.acma_reference) once as self._acma_reference. The AI loop calls
    self._acma_reference.lookup(fingerprint["center_freq_hz"]) before each
    classify() call and passes the result as acma_allocations.

  tests/llm/test_phase4_classifier.py
    6 new tests added in TestAcmaAllocationsInPrompt: ACMA section present when
    allocations provided, section contains frequency range, section contains
    service name, empty list produces no ACMA section, None produces no ACMA
    section, classify() passes allocations through without crash. All passing.

Key architectural fact:
data/frequency_reference.json uses range-based allocations (freq_start_mhz /
freq_end_mhz), not point frequencies. This matches how ACMA documents the AU
spectrum plan. Multiple entries may match one frequency (overlapping allocations
are normal). The LLM now receives real regulatory data per scan cycle -- this
directly addresses the 98 MHz FM misclassification as "noise" by giving the LLM
the "BROADCASTING 87.5-108.0 MHz, mimir_band: fm_broadcast" entry in its prompt.

---

## Deferred Items

- **BUG-01 (open, deferred post-8B):** bandwidth_hz=0 and occupied_bins=0 in all
  live embeddings because live SNR (6-10 dB) is below SIGNAL_THRESHOLD_DB (27 dB).
  Only 4/6 embedding features are active. FM misclassification is now partially
  mitigated by ACMA context wiring (Phase 8A) but the threshold issue remains.
  Address after Phase 8B. When fixing: always explain the bug in plain English
  before writing any code.

- **system_stats placeholders (deferred to Phase 8B):** active_frequency_hz,
  scan_count, queue_depth, llm_last_inference_ms are hardcoded zeros in the
  stats emit. Not wired to real ScanRunner values yet.

- **AGENTS.md event table (deferred to Phase 8B):** still lists old event name
  focus_frequency -- should be set_focus_frequency.

- **NOAA/Meteor-M2 satellite module (post-Phase 8):** HackRF covers 137-138 MHz.
  NOAA 15 (137.620 MHz), NOAA 18 (137.9125 MHz), NOAA 19 (137.100 MHz),
  Meteor-M2 (137.9 MHz). Requires V-dipole or QFH antenna. Address after all
  8x phases are closed.

---

## Dashboard Architecture (Phase 7A complete)

### SocketIO events — do not rename or merge

| Event | Direction | Payload |
|---|---|---|
| `scan_result` | server → browser | timestamp, center_freq_hz, signal_type, confidence, confidence_score, novel, au_legal_status, reasoning |
| `spectrum_update` | server → browser | center_freq_hz, psd_db (2048 floats dBFS) |
| `system_stats` | server → browser | hackrf_status, active_frequency_hz, scan_count, queue_depth, llm_last_inference_ms |
| `set_focus_frequency` | browser → server | freq_hz |

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
- Fonts: Press Start 2P (headings), Share Tech Mono (data readouts)
- Theme tokens in `src/theme/cyberpunk.css`
- No `<form>` tags anywhere — use onClick handlers

### Backend constraints
- `async_mode='threading'` in `server.py` — never change to eventlet/gevent
- `broadcast_spectrum` is defined inside `start_server()` — not importable directly
- Retrieve via `start_server._broadcast_spectrum_fn` after calling `start_server()`
- `_emit_result` in `scanner.py` calls both `_broadcast_fn` and `_broadcast_spectrum_fn`

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
| `dashboard/static/` | Vite build output — served by Flask |
| `scan.py` | CLI entry point |
| `config/mimir.yaml` | Runtime configuration |
| `docs/au-legal-reference.md` | ACMA legal reference |

---

## Known Tech Debt

| Item | Detail | Fix in |
|---|---|---|
| Stats panel placeholders | active_frequency_hz, scan_count, queue_depth, llm_last_inference_ms hardcoded in system_stats emit | Post 7B |
| Waterfall scroll rate slow | One row per dwell cycle (~8–10s). High-rate streaming requires separate FFT loop decoupled from classification | Post 7B |
| `FrequencyList.jsx:67` | `confidence_score` lacks null guard | Phase 7B polish |
| CORS wildcard | `cors_allowed_origins="*"` in server.py — fine for dev | Pre-prod |
| Queue max hard-coded | `020` in SystemStatsPanel — should read from systemStats | Phase 7B |
| `sampleRateHz` dead param | Accepted by `useWaterfall.js` but unused | Post 7B |
| `psd_db` uncalibrated | FFT missing nfft normalisation — absolute dBFS wrong, SNR unaffected | Post 7B |