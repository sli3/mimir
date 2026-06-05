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

**Total passing: 278/278 (222 pytest + 56 Vitest)**

### Session memo — Phase 8B: Wire ScanRunner stats into system_stats + AGENTS.md cleanup

**Status:** Complete
**Phase context:** Phase 8B — final phase of the 8-phase roadmap

**What was done:**
- Added `_scan_count`, `_active_freq_hz`, `_last_llm_ms` tracking to `ScanRunner.__init__()`
- Added `_active_freq_hz = freq_hz` after `device.set_center_frequency()` in `_scan_loop`
- Added `self._scan_count += 1` at end of each per-frequency iteration
- Timed `self._classifier.classify()` call in `_ai_loop` to populate `_last_llm_ms`
- Added `ScanRunner.get_stats()` public method returning all four runtime metrics
- Modified `start_server()` to accept optional `scanner=` parameter
- Replaced hardcoded zeros in system_stats emit with live scanner values
- Reordered `scan.py` to create scanner before calling `start_server()`
- Removed resolved deferred items from AGENTS.md (system_stats placeholders, event table fix)
- Updated Phase 8B status to ✅ Complete with test counts
- Added 6 scanner tests and 2 server tests

**Files modified:**
- `core/pipeline/scanner.py` — stats tracking fields, get_stats(), timed classify()
- `dashboard/server.py` — scanner parameter, live stats emit
- `scan.py` — scanner created before start_server()
- `AGENTS.md` — phase tracker, total count, deferred items cleanup, this memo block
- `tests/core/test_scanner.py` — 6 new tests for get_stats()
- `tests/dashboard/test_server_stats.py` — 2 new tests for scanner wiring

**Test counts:** 203 pytest + 56 Vitest = 259/259

---

### Session memo — Phase 8C: Single-frequency focus mode + LLM tuning

**Status:** Complete
**Phase context:** Phase 8C — single-frequency focus mode to resolve LLM queue saturation

**What was done:**
- Replaced `for freq_hz in config.frequencies_hz` rotation in `_scan_loop` with single-frequency focus mode
- Added `_focus_freq_hz` (defaults to `config.frequencies_hz[0]` = 98 MHz) and `_focus_lock` to `ScanRunner.__init__()`
- Added `set_focus_frequency(freq_hz)` public method: acquires lock, updates focus freq, flushes queue with `get_nowait()` until `queue.Empty`
- `_scan_loop` now reads focus frequency under lock at start of each iteration, stays on that frequency
- `dashboard/server.py`: `handle_set_focus` now calls `scanner.set_focus_frequency()` via `_scanner_ref` module-level global
- Replaced `test_frequency_hopping_order` with `test_scan_loop_stays_on_focus_frequency`
- Added `test_set_focus_frequency_flushes_queue`
- LLM model swap: Qwen3 → Qwen3-4B-Q4_K_M (llama.cpp on yubaba)
- LLM tuning: `max_tokens=300` added to API request; `/no_think` appended to system prompt end
  (reasoning-budget parameter caused empty responses, so it was removed)
- LLM inference speed: 18–23s → ~2.5s (15x speedup)
- `fm_broadcast` classifying at 95–98% confidence with new model
- Queue depth: permanently pegged at 20/20 → ~0/20 at steady state

**Files modified:**
- `core/pipeline/scanner.py` — `_scan_loop` rewrite, `set_focus_frequency()`, `_focus_freq_hz`, `_focus_lock`
- `dashboard/server.py` — `_scanner_ref`, `handle_set_focus` calls `scanner.set_focus_frequency()`
- `tests/core/test_scanner.py` — focus frequency tests, queue flush test
- `llm/classifier.py` — model default, `max_tokens=300`, `/no_think` system prompt suffix
- `AGENTS.md` — phase tracker, total count, this memo block, LLM hardware info, run command note
- `docs/ROADMAP.md` — phase tracker, Phase 8C section, Phase 9 placeholder

**Test counts:** 204 pytest + 56 Vitest = 260/260

---

### Session memo — Phase 9A: ACMA Reference Expansion + /api/frequencies endpoint

**Status:** Complete
**Phase context:** Phase 9A — expand ACMA band coverage in LLM classifier

**What was built:**
- llm/classifier.py: _AU_BAND_REFERENCE expanded from 5 to 23 mimir_band labels
  with AU-only frequency ranges and plain-English descriptions.
  _JSON_SCHEMA comment updated to list all 23 valid signal_type values.
  Notes pass-through added to _build_user_prompt — non-empty notes fields from
  frequency_reference.json now appear in the ACMA section of the LLM user prompt.
  Marine HF range corrected to 4–27.5 MHz. UHF CB narrowed to 476.425–477.400 MHz.
- dashboard/server.py: GET /api/frequencies endpoint added with query param
  support (?min_mhz, ?max_mhz, ?tagged_only=1). Returns filtered JSON array
  from data/frequency_reference.json, read fresh per request. Returns 500 on file
  read failure. handle_set_focus now coerces input to float with try/except —
  invalid or missing values clear focus safely.
- tests/dashboard/test_server_api.py: 10 tests — all filter combinations, schema
  validation, empty range, error paths. Counts loaded dynamically from
  frequency_reference.json to avoid brittleness.
- tests/dashboard/test_server_stats.py: 2 new tests for handle_set_focus type
  coercion and invalid string handling.
- tests/llm/test_phase4_classifier.py: 4 new tests — notes appear/omit, all 23
  mimir_band labels in system prompt, no FCC/ETSI in system prompt.
- tests/llm/test_acma_reference.py: 2 new tests — notes field present, non-empty
  notes preserved in lookup results.

**QA re-run note:** Original build had misconfigured agent model strings
(opencode/ prefix instead of opencode-go/). Fixed in opencode.json and all
.opencode/agents/*.md files. Re-run caught two factual errors in band reference
data and one input validation bug — all fixed before commit.

**Files modified:**
- llm/classifier.py — _AU_BAND_REFERENCE, _JSON_SCHEMA, notes pass-through
- dashboard/server.py — /api/frequencies endpoint, handle_set_focus type coercion
- tests/dashboard/test_server_api.py — new file (10 tests)
- tests/dashboard/test_server_stats.py — 2 focus type tests
- tests/llm/test_phase4_classifier.py — 4 ACMA / band reference tests
- tests/llm/test_acma_reference.py — 2 notes field tests

**Test counts:** 222 pytest + 56 Vitest = 278/278

---

### Session memo — Chore: Agent model string fix + analyst bash guard

**Status:** Complete
**Phase context:** Infrastructure/tooling — not tied to a numbered phase

**What was done:**
- All agent model strings in opencode.json and .opencode/agents/*.md
  corrected from opencode/ prefix to opencode-go/ prefix
- deep-bug-hunter.md duplicate model: key fixed
- analyst.md and opencode.json analyst description updated to explicitly
  state analyst does not run bash — receives pre-run pytest output from PM
- Agents now firing correctly under OpenCode Go subscription

**Files modified:**
- opencode.json — corrected all agent model IDs
- .opencode/agents/*.md — corrected model strings where applicable

**Test counts:** No tests run — infrastructure/tooling change only.

---

### Session memo — Chore: /build workflow overhaul + agent roster update

**Status:** Complete
**Phase context:** Infrastructure/tooling — not tied to a numbered phase

**What was done:**
- /build command updated to 8-step workflow: plan → research → security
  gate → code → QA loop → PM audit → docs → report
- New agents: @security-analyst (opencode-go/glm-5.1, pre-code TX/AU legal
  gate, read-only), @review-second (opencode-go/minimax-m2.7, replaces
  retired cloud-reviewer, read-only), @doc-writer (opencode-go/mimo-v2.5,
  docs only, does not touch ROADMAP)
- @cloud-reviewer retired and removed
- Full roster: main=opencode-go/kimi-k2.6, plan-reviewer=opencode-go/minimax-m2.7,
  researcher=opencode-go/mimo-v2.5, analyst=opencode-go/mimo-v2.5-pro,
  deep-analyst=opencode-go/glm-5.1, deep-bug-hunter=opencode-go/glm-5.1,
  security-analyst=opencode-go/glm-5.1, review-second=opencode-go/minimax-m2.7,
  doc-writer=opencode-go/mimo-v2.5, local-reviewer=local-llama/Qwen3.5-9B(Q4)

**Files modified:**
- opencode.json — updated agent roster and model strings
- .opencode/skills/ — updated workflow descriptions

**Test counts:** No tests run — infrastructure/tooling change only.

---

### Session memo — GitHub MCP setup (chore)

**Status:** Complete
**Phase context:** Infrastructure/tooling — not tied to a numbered phase

**What was done:**
- Installed GitHub MCP server for OpenCode using the remote transport option
  (`https://api.githubcopilot.com/mcp/`) — no Docker required
- Created a fine-grained GitHub PAT scoped to the Mimir repo only with permissions:
  Contents (read/write), Issues (read/write), Metadata (read-only), Pull requests (read-only)
- Set `GITHUB_PERSONAL_ACCESS_TOKEN` as a global fish shell env var in `~/.config/fish/config.fish`
- Added `"mcp"` block to `opencode.json` using `{env:GITHUB_PERSONAL_ACCESS_TOKEN}` interpolation
  so the token is never hardcoded in the config file
- Fixed a pre-existing typo in `.opencode/agents/local-reviewer.md`: `temperature: 0.s`
  corrected to `temperature: 0.3` — this was causing OpenCode config validation to fail
  on startup with "Expected number | undefined, got '0.s'"
- Verified both MCP servers connected: `opencode mcp list` shows `local-files` and `github`
  both as ● ✓ connected

**Files modified:**
- `opencode.json` — added `"mcp"` block for github remote server
- `.opencode/agents/local-reviewer.md` — fixed temperature typo (0.s → 0.3)
- `~/.config/fish/config.fish` — added GITHUB_PERSONAL_ACCESS_TOKEN env var (outside repo)

**Test counts:** No tests run this session — infrastructure/tooling change only.

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

## Deferred Items

- **BUG-01 (open, deferred post-8B):** bandwidth_hz=0 and occupied_bins=0 in all
  live embeddings because live SNR (6-10 dB) is below SIGNAL_THRESHOLD_DB (27 dB).
  Only 4/6 embedding features are active. FM misclassification is now partially
  mitigated by ACMA context wiring (Phase 8A) but the threshold issue remains.
  Address after Phase 8B. When fixing: always explain the bug in plain English
  before writing any code.

- **NOAA/Meteor-M2 satellite module (post-Phase 8):** HackRF covers 137-138 MHz.
  NOAA 15 (137.620 MHz), NOAA 18 (137.9125 MHz), NOAA 19 (137.100 MHz),
  Meteor-M2 (137.9 MHz). Requires V-dipole or QFH antenna. Address after all
  8x phases are closed.

- **GitHub MCP toolset scoping** — The github MCP server registers many tools and may
  bloat agent context windows in future. Deferred because it is not yet causing problems.
  When addressed: add `"tools": { "github_*": false }` globally to `opencode.json` and
  re-enable per-agent as needed. See MCP Servers section for the exact config block.

- **GitHub PAT rotation reminder** — PAT expires in 90 days from date of creation.
  When it expires: generate a new fine-grained PAT with identical scopes (Contents r/w,
  Issues r/w, Metadata r/o, Pull requests r/o, Mimir repo only), update
  `GITHUB_PERSONAL_ACCESS_TOKEN` in `~/.config/fish/config.fish`, restart OpenCode,
  verify with `opencode mcp list`.

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
| Waterfall scroll rate slow | One row per dwell cycle (~8–10s). High-rate streaming requires separate FFT loop decoupled from classification | Post 7B |
| `FrequencyList.jsx:67` | `confidence_score` lacks null guard | Phase 7B polish |
| CORS wildcard | `cors_allowed_origins="*"` in server.py — fine for dev | Pre-prod |
| Queue max hard-coded | `020` in SystemStatsPanel — should read from systemStats | Phase 7B |
| `sampleRateHz` dead param | Accepted by `useWaterfall.js` but unused | Post 7B |
| `psd_db` uncalibrated | FFT missing nfft normalisation — absolute dBFS wrong, SNR unaffected | Post 7B |
| scan.py startup message | "Scanning N frequencies" is misleading now that single-freq focus mode is active | Post 8C cosmetic |