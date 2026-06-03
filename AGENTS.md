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
| 7B    | Cyberpunk Dashboard — AI + Polish | 🔜 Next        | —        |
| — | UV migration (pip to pyproject.toml + uv.lock) | ✅ Complete | uv sync --all-extras; uv run pytest |

**Total passing: 215/215 (165 pytest + 50 Vitest)**

### Session — UV Migration

**Status:** Complete
**Work area:** Dependency management / project tooling

**What changed:**
- Migrated from pip + requirements.txt to UV (pyproject.toml + uv.lock)
- `pyproject.toml` created at project root with all runtime deps in `[project.dependencies]`
  and test deps (pytest, pytest-cov) in `[project.optional-dependencies.dev]`
- `uv.lock` generated — 99 packages resolved, no version conflicts
- `requirements.txt` retained as legacy reference; deprecation comment added at top
- `.venv/` added to .gitignore
- AGENTS.md Development Setup section updated to UV commands
- README.md updated with Option B (UV-based) quick-start path

**Key commands going forward:**
- Install deps: `uv sync --all-extras`
- Run scanner: `uv run python scan.py`
- Run tests: `uv run pytest`
- Run tool scripts: `uv run python tools/<script>.py`
- Regenerate requirements.txt from lockfile: `uv export --format requirements-txt > requirements.txt`

**Test counts (post-migration, ground truth):**
- pytest: 165/165 passing
- vitest: 50/50 passing
- Total: 215/215 passing

**Note on test count:** Previous session memo recorded 188/188. Correct baseline is
165 pytest + 50 vitest = 215. The 23 extra tests from the data-layer session
(test_seed_chromadb.py) are not present in this environment — count of 165 is verified.

**Files created:**
- `pyproject.toml` — UV project manifest; all deps + dev group + pytest config
- `uv.lock` — generated lockfile (99 packages)

**Files modified:**
- `requirements.txt` — legacy reference comment added at top
- `.gitignore` — `.venv/` entry added
- `AGENTS.md` — Development Setup section updated to UV; phase tracker updated
- `README.md` — Option B (UV-based) quick-start added
- `docs/ROADMAP.md` — phase tracker synced with AGENTS.md

### Data Layer — built this session
- `tools/inspect_acma_pdf.py` — one-off PDF diagnostic (pdfplumber + tabula)
- `tools/build_frequency_reference.py` — extracts and cleans ACMA spectrum plan PDF into structured JSON
- `data/frequency_reference.json` — 432 entries, HackRF range 1–6000 MHz, extracted from ACMA Radiofrequency Spectrum Plan (2025 Update) 2021. 5 Mimir bands tagged: fm_broadcast, aviation_vhf, aprs, ism_lora, adsb
- `tools/seed_chromadb.py` — downloads TrevTron/rtl-ml-dataset from HuggingFace, processes through Mimir pipeline, seeds ChromaDB
- `tests/tools/test_seed_chromadb.py` — 23 tests, all synthetic
- ChromaDB now seeded: 800 records, 7 classes: APRS, FM_broadcast, FRS_GMRS, ISM_sensors_433, NOAA_weather, noise, pager
- ADS_B and NOAA_APT absent from RTL-ML v2 dataset
- Known limitation: pager BW=0 on most samples due to SIGNAL_THRESHOLD_DB=27dB — deferred to Phase 5

### Notes
- **data/vectorstore/ is gitignored** (inside data/). ChromaDB must be re-seeded on fresh clone by running: `uv run python tools/seed_chromadb.py`

### Deferred items

- **BUG-01 — psd_db calibration (deferred to Phase 5):** Three compounding errors in `fft.py` compute_psd: no nfft scaling, no Hann window power correction, peak normalisation forcing relative rather than absolute dBFS. When addressed in Phase 5, explain the bug in plain English before writing any code.

- **ADS_B reference vectors missing:** RTL-ML v2 dataset does not include ADS_B captures. ADS_B vectors must come from live HackRF captures in a future phase. Consider a calibration-style capture script to seed them into ChromaDB.

- **Pager bandwidth threshold:** SIGNAL_THRESHOLD_DB=27dB is too high for narrow pager bursts. Most pager vectors in ChromaDB have BW=0 Hz, bins=0. Deferred to Phase 5 threshold calibration.

### Phase 7B remaining work
1. Fix `hackrf_status` in `get_stats()` — always shows DISCONNECTED
2. `AIReasoningPanel` — full LLM reasoning for focused frequency
3. `focus_frequency` server-side filter in `scanner.py` Thread B
4. `CharacterPanel` — 4-state PNG swap (idle/signal_low/signal_high/anomaly)
5. Signal type colour-coding audit across all panels
6. Neon glow polish — box-shadow pulse on active panels
7. `npm run build` → `dashboard/static/` verified, Flask serves prod bundle

---

## Dashboard Architecture (Phase 7A complete)

### SocketIO events — do not rename or merge

| Event | Direction | Payload |
|---|---|---|
| `scan_result` | server → browser | timestamp, center_freq_hz, signal_type, confidence, confidence_score, novel, au_legal_status, reasoning |
| `spectrum_update` | server → browser | center_freq_hz, psd_db (2048 floats dBFS) |
| `system_stats` | server → browser | hackrf_status, active_frequency_hz, scan_count, queue_depth, llm_last_inference_ms |
| `focus_frequency` | browser → server | frequency_hz |

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
| `hackrf_status` broken | `get_stats()` always returns DISCONNECTED even when scanning | Phase 7B |
| Waterfall scroll rate slow | One row per dwell cycle (~8–10s). High-rate streaming requires separate FFT loop decoupled from classification | Post 7B |
| `FrequencyList.jsx:67` | `confidence_score` lacks null guard | Phase 7B polish |
| CORS wildcard | `cors_allowed_origins="*"` in server.py — fine for dev | Pre-prod |
| Queue max hard-coded | `020` in SystemStatsPanel — should read from systemStats | Phase 7B |
| `sampleRateHz` dead param | Accepted by `useWaterfall.js` but unused | Post 7B |
| `psd_db` uncalibrated | FFT missing nfft normalisation — absolute dBFS wrong, SNR unaffected | Post 7B |