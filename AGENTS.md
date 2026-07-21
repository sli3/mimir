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

## 🔒 SUBAGENT DELEGATION BOUNDARIES — READ BEFORE EVERY SESSION

These rules are not optional. Added 2026-07-07 after a confirmed incident
pattern: a task addressed to a specific named subagent (e.g.
`@frontend-reviewer`) whose permissions denied the requested action was
NOT reported back to the user. The primary/orchestrator agent instead
silently resolved it itself, across three separate test runs, using three
different bypass paths:

1. Read the file and edited it directly with its own `edit` tool,
   bypassing the subagent's `edit: deny`.
2. Reached for the `github` MCP server (`github_get_file_contents` →
   `github_create_or_update_file`) to edit the file via a direct commit
   to the GitHub remote — bypassing both the subagent's restriction AND
   the local `git-workflow` process entirely. This call was interrupted
   before it landed; confirmed via `git log --oneline origin/main` that
   no unreviewed commit reached the remote. It would have if allowed to
   complete.
3. (Third run, correct behaviour, included for contrast) Correctly routed
   to `@frontend-reviewer` via the Task tool and received a clean refusal
   — confirming the fix below is achievable, not just aspirational.

### Non-negotiable rules for all agents
1. **If a message explicitly addresses a specific named subagent**
   (`@agent-name`) and that subagent's permissions do not allow the
   requested action: STOP. Report which subagent was addressed, what was
   requested, and which permission blocked it. Ask the user how to
   proceed. Do not guess at intent or complete the task "helpfully."
2. **Never substitute a different tool or MCP server** to perform the
   same action the named subagent was denied. This includes the native
   `edit`/`write` tool, any `local-files_*` write tool (`write_file`,
   `edit_file`, `create_directory`, `move_file`), any `github_*` write
   tool (`create_or_update_file`, `delete_file`, `push_files`, or any
   tool that commits to a remote), and any future MCP tool not named
   here that can create, modify, or delete a file, directory, or remote
   resource.
3. **Only proceed yourself if the user explicitly confirms** they want
   you — not the named subagent — to do it.
4. **This applies regardless of orchestrator model.** Confirmed reproduced
   under both `kimi-for-coding/k2p7` and a DeepSeek V4 swap used for
   token-cost savings. Do not assume a model swap changes this behaviour
   without a direct retest.
5. The GitHub PAT's own scope (Contents read/write, Mimir repo only —
   see MCP Servers section) limits blast radius to this repo but does
   **not** prevent an unreviewed commit to `main`. Token-level scoping is
   not a substitute for this rule.

### What this does NOT restrict
- Normal `/build` pipeline routing (Steps 3, 5, 5c, 6, 6B, 7, 8, 9), where
  the Project Manager step invokes a reviewer/analyst agent as part of
  its own established step logic. That is standing delegation, not a
  case of "user addressed X and X can't do it."
- Any subagent completing a task within its own granted permissions.
- The orchestrator doing direct work itself when no specific subagent was
  named in the request.
- If a `/build` Step 6B or equivalent gate genuinely cannot complete
  because the assigned reviewer lacks a needed permission: follow the
  existing "STEP FAILURE" convention (Step 6B is non-blocking by design,
  reported as "STEP 6B FAILURE," with `/review-frontend` as the manual
  fallback) — surface it, do not route around it.

### Unconfirmed, worth testing
Per OpenCode's own docs, invoking a subagent via the TUI's `@`
autocomplete/mention picker is a hard route that bypasses the primary
agent's own Task-tool reasoning — even overriding a `permission.task`
deny for that agent. Typed plain text naming an agent does not carry the
same guarantee; the primary model still reads it as ordinary text and can
reinterpret intent. Not yet confirmed against this project's actual
setup — the incidents above all involved typed `@agent-name` text, not
verified use of the picker. If confirmed, using the real mention picker
is a stronger structural guard than this prompt rule, since it removes
the primary model's discretion rather than asking it to behave. The rule
above is required either way, since it also governs the automated
`/build` pipeline case, where no picker is involved.

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

For the frontend suite, run `npm run test` from `dashboard/frontend` — never `npx vitest`
from the repo root. `npx` ignores the pinned local Vitest version and can pull a different
cached version globally, which silently breaks jsdom/`document` setup and produces false
failures that look like real breakage (see Phase 33-34 session memo, BUG-05 false alarm).

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
| 16 | AIS Frontend Frequency Verification | ✅ Complete | 495 (373 pytest + 122 Vitest) |
| 17 | Feature A: focused decode panel | ✅ Complete | 496 (373 pytest + 123 Vitest) |
| 18 | Feature B: Raw ADS-B Hex Decode View | ✅ Complete | 507 (373 pytest + 134 Vitest) |
| 18b | Raw Decode Log — ACARS and AIS | ✅ Complete | 517 (375 pytest + 142 Vitest) |
| 19a | calibrate_thresholds.py — missing bands + ADS-B gain fix | ✅ Complete | 517 (375 pytest + 142 Vitest) |
| 19b | calibrate_thresholds.py — antenna selection, single-band prompt, matrix split | ✅ Complete | 517 (375 pytest + 142 Vitest) |
| 19c | classifier.py — ChromaDB distance threshold recalibration | ✅ Complete | 517 (375 pytest + 142 Vitest) |
| 20 | Live Capture to Vector Store Ingestion Tool | ✅ Complete | 526 (384 pytest + 142 Vitest) |
| 21 | ADS-B Frame Inspector + SIGNAL INTERCEPT rename | ✅ Complete | 538 (390 pytest + 148 Vitest) |
| 22 | LLM Offline Handling — health check + cooldown system | ✅ Complete | 548 (399 pytest + 149 Vitest) |
| 22-Hotfix | LLM offline emit rate-limit (SocketIO flood fix) | ✅ Complete | 551 (402 pytest + 149 Vitest) |
| 23 | ChromaDB Vector Space 3D Visualisation (isolated side page) | ✅ Complete | 581 (419 pytest + 162 Vitest) |
| 24 | OPERATOR Live Anomaly Readout — 4-state badge, novel exposure, tooltip | ✅ Complete | 591 (420 pytest + 171 Vitest) |
| 25 | Max-hold burst fingerprinting for ADS-B | ✅ Complete | 606 (435 pytest + 171 Vitest) |
| 28 | Cross-session calibration merge + antenna groups + persistence | ✅ Complete | 634 (463 pytest + 171 Vitest) |
| 29 | Live capture loop — forward per-band signal_threshold_db to fingerprint_spectrum() | ✅ Complete | 640 (469 pytest + 171 Vitest) |
| 30 | Spectral cropping for fingerprint_spectrum() — per-band crop_half_width_hz | ✅ Complete | 646 (475 pytest + 171 Vitest) |
| 32 | Confidence Provenance Gating — dim unverified confidence via `source` field on scan_result | ✅ Complete | 656 (477 pytest + 179 Vitest) |
| 33-Hotfix | Classifier confidence cap + vectordb SNR tools (hotfix, RETROACTIVE — code shipped, tests in 34) | ✅ Complete | 656 (477 pytest + 179 Vitest) [tests added in Phase 34] |
| 34 | Test coverage for Phase 33 classifier cap + vectordb tools (TEST-ONLY) | ✅ Complete | 677 (498 pytest + 179 Vitest), 0 failures |
| 35 | Pluto receiver wrapper — `core/device/pluto_rx.py` (`PlutoReceiver`, RX-only SoapySDR stream, real `SOAPY_SDR_RX` captured at open) | ✅ Complete | counted at merge — see 36-Hotfix |
| 36 | Device capability + detection layer — `profiles.py` (`DEVICE_PROFILES`), `detect.py` (`enumerate_devices`/`detect_device`), `PLUTO_BAND_PROFILES` + `band_supported_by_device` | ✅ Complete | counted at merge — see 36-Hotfix |
| 36-Hotfix | Pluto hardware bring-up — four SWIG/SoapySDR bugs fixed by hand + `soapy_doubles.py` (`FakeSoapySDRKwargs`) test infrastructure | ✅ Complete | 741 (562 pytest + 179 Vitest), 0 failures |

**Total passing: 741 passing (562 pytest + 179 Vitest), 0 failures**
- Note: Phase 24 added 2026-07-07. Mascot/CharacterPanel.jsx wiring deferred to a future phase (pending art asset).
- Note: Phases 35+36 merged 2026-07-20. Intermediate per-phase subtotals were not separately captured under the doc freeze; the 741 total is verified live at the merge checkpoint (`PYTHONPATH=. uv run pytest` + `npm run test`). The four hardware bugs in 36-Hotfix were fixed by hand, not via `/build`.

---

## MCP Servers

Four MCP servers are configured in `opencode.json` and active in all OpenCode sessions.

| Server | Type | Transport | Purpose |
|---|---|---|---|
| `local-files` | local | npx @modelcontextprotocol/server-filesystem | Read/write access to `/home/sli3/Repository/mimir` |
| `github` | remote | https://api.githubcopilot.com/mcp/ | GitHub repo access — commits, issues, file history |
| `context7` | remote | https://mcp.context7.com/mcp | Live library/API docs lookup (e.g. ChromaDB `collection.get()` syntax). Free tier, 1,000 calls/month, no auth required. |
| `playwright` | local | npx @playwright/mcp@latest --headless | Browser automation to observe the live Vite dev server. RX-equivalent — view-only, no interaction with RF/SDR hardware. |

### Context7 MCP — scoping

Context7 tools are **denied globally** and re-enabled only for the two agents
that plausibly need library/API docs lookups, via the standard OpenCode
global-deny + per-agent-override pattern:

```json
"permission": {
  "context7_*": "deny"
}
```

```json
"researcher": {
  "tools": { "context7_*": true }
}
```
```json
"plan-reviewer": {
  "tools": { "context7_*": true }
}
```

All other agents (main, analyst, deep-analyst, security-analyst, doc-writer,
memo-writer, deep-bug-hunter, local-reviewer, frontend-reviewer) have no
Context7 access. Live-tested 2026-07: correctly resolved ChromaDB's library ID
and returned real `collection.get()` API docs including `where`/`where_document`
filter syntax.

### Playwright MCP — scoping and Chromium dependency

Playwright tools are **denied globally** and re-enabled only for
`frontend-reviewer`, using the modern `permission` key for the global block and
`tools` for the per-agent MCP wildcard override (this is the one place `tools`
is still correct — MCP wildcard re-enablement uses `tools`, built-in
permissions like `edit`/`bash`/`webfetch` use `permission`):

```json
"permission": {
  "playwright_*": "deny"
}
```

```json
"frontend-reviewer": {
  "tools": { "playwright_*": true },
  "permission": {
    "edit": "deny", "bash": "deny", "webfetch": "allow", "websearch": "allow"
  }
}
```

**Machine-level dependency (not in opencode.json):** Playwright MCP needs a
Chromium binary to drive, which is not bundled with the npm package. Install
once per machine:

```bash
npx playwright install chromium --only-shell
```

- Downloads to `~/.cache/ms-playwright/` (Chrome for Testing + Chrome Headless
  Shell + FFmpeg).
- Fedora is not an officially supported Playwright platform — install will show
  `BEWARE: your OS is not officially supported; downloading fallback build for
  ubuntu24.04-x64`. This is expected, not an error.
- Binary download and standalone launch confirmed working on Fedora 44
  (2026-07-06) via `npx playwright screenshot https://example.com /tmp/test.png`
  — no missing shared-library errors.
- If a future machine (or the macOS iMac) hits `Host system is missing
  dependencies to run browsers` with a list of `.so` files, `npx playwright
  install-deps` will **not** self-heal on Fedora (it shells out to `apt-get`,
  which doesn't exist). Install the equivalent Fedora packages manually via
  `dnf` — match missing library names against Fedora 44 package names rather
  than guessing a fixed list.

**Confirmed working `playwright` MCP entry in `opencode.json` (2026-07-06):**

```json
"playwright": {
  "type": "local",
  "command": [
    "npx",
    "@playwright/mcp@latest",
    "--headless",
    "--executable-path",
    "/home/sli3/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell",
    "--no-sandbox"
  ],
  "enabled": true,
  "timeout": 30000
}
```

Two flags were required beyond the plain `--headless` config, discovered when
`@frontend-reviewer` first tried to observe the live Vite dev server:

- **`--executable-path`** — Playwright MCP's default `chrome` channel looks
  for a system Google Chrome install at `/opt/google/chrome/chrome`, which
  does not exist on this machine. Pointing `--executable-path` directly at the
  downloaded `chrome-headless-shell` binary bypasses that lookup entirely.
  `frontend-reviewer` attempted a `sudo ln -sf` workaround to symlink the
  binary into the expected location first — this failed (no terminal for sudo
  password) and is unnecessary; `--executable-path` is the correct fix and
  does not require root.
- **`--no-sandbox`** — disables Chrome's OS-level process sandbox. This is a
  documented, standard Playwright MCP flag (not a security workaround
  specific to this project) and is commonly required on Linux where the
  sandbox needs kernel namespace permissions not always available to
  unprivileged processes. Low-risk in this context: the browser is
  headless, driven only by `frontend-reviewer`, and only ever navigates to
  `localhost:5173` (our own dev server) — not arbitrary internet content.
  Revisit if `frontend-reviewer`'s scope ever expands to browsing untrusted
  external URLs.
- `frontend-reviewer` needed a JSON entry in `opencode.json`'s `agent` block in
  addition to its `.opencode/agents/frontend-reviewer.md` file — the markdown
  alone is not enough for the main agent to discover and delegate to it. The
  markdown supplies the system prompt; the JSON entry supplies
  routing/model/permissions.

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
| `acars_message` | server → browser | timestamp, freq_hz, registration, label, block_id, text, crc_ok, **raw** |
| `ais_message` | server → browser | timestamp, mmsi, vessel_name, lat, lon, speed, course, channel, **raw** |
| `adsb_aircraft` | server → browser | icao, callsign, altitude_ft, latitude, longitude, groundspeed, track, vertical_rate, timestamp, raw_hex |

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
| `tools/capture_to_vectorstore.py` | Live IQ capture across AU-legal bands, pipeline to production ChromaDB |
| `docs/au-legal-reference.md` | ACMA legal reference |
| `docs/ROADMAP.md` | Phase tracker and build history |

---

## Known Tech Debt

> Live open debt only. Resolved items are archived in docs/ROADMAP.md under
> "Resolved Tech Debt — Historical". Accepted/working-as-intended items are in
> the subsection at the bottom of this table, not the active-work list.

### Open — blocked on a field session (⛔ FIELD — cannot close at desk)

| Item | Detail | Fix in |
|---|---|---|
| AIS `crop_half_width_hz` field-verify (HIGH-01) | Corrected 2026-07-13 from 12_500 → 50_000 (window 161.950–162.050 MHz, covers CH1 161.975 + CH2 162.025, each ±25 kHz from the 162.000 MHz dual-channel midpoint). Corrected in `dashboard/shared_state.py` but NOT field-verified — needs a real AIS vessel packet (Port Adelaide / Outer Harbor shipping) to confirm the width. | Field verification |
| Placeholder `crop_half_width_hz` — `aviation` (12_500) | Estimated from 25 kHz VHF voice channel spacing (half of 25 kHz). Centre 127 MHz is a real channel, so a single-channel half-width should be right — but not field-verified. One-line fix in `dashboard/shared_state.py`. | Field verification |
| Placeholder `crop_half_width_hz` — `acars` (12_500) | Same reasoning as aviation; centre 129.125 MHz is AU ACARS primary. Not field-verified. | Field verification |
| confidence_score still LLM-only after Phase 33 cap | confidence_score has no deterministic component — it is set entirely by the LLM, not derived from any signal metric or ChromaDB distance. The Phase 33 post-LLM cap clamps it to [0,1] and floors low-quality signals, but the raw NUMBER still shows scan-to-scan variance on the 4B local model at temp 0.1. Future direction: derive confidence_score partly deterministically. Design conversation, not scheduled. | Future phase |
| Placeholder `crop_half_width_hz` — `ism` (250_000) | Centre 915.000 MHz does NOT land on a real AU915 channel (AU915 starts 915.2 MHz; 125 kHz / 500 kHz channels). 2 MHz span covers 4–5 channels, so no single value is intrinsically right; 250_000 = half the widest (500 kHz) channel, conservative. Not field-verified. | Field verification |
| Placeholder `crop_half_width_hz` — `adsb` (900_000) | Conservative. Sources disagree on Mode S occupied BW (~1 MHz vs ~2 MHz). 900_000 (1.8 MHz window) stays inside the ~1 MHz `diagnose_threshold.py` prior with margin. Not field-verified — needs live-aircraft capture with the spiral discone. | Field verification |
| ChromaDB distance reference stale | `_DISTANCE_SCALE_REFERENCE` in `llm/classifier.py` was calibrated for 6D L2 distances; after 7D reseed, thresholds over-classify known signals as "novel." Needs recalibration via live captures. | 9C-Threshold |
| Missing ADS-B / NOAA_APT ChromaDB entries | Both classes absent from the RTL-ML seed dataset — 0 records in the production vectorstore for these bands until live capture runs via `tools/capture_to_vectorstore.py`. | Pending live capture window |
| ADS-B max-hold field recalibration | Max-hold raises the apparent noise floor; existing ADS-B `signal_threshold_db` was calibrated against the averaged trace and must be re-calibrated against max-hold before running `capture_to_vectorstore.py` for ADS-B. Phase 27 (p90 over ≥5 captures) unblocked this. | Field session |
| ADS-B vector store single-basis caveat | Existing ADS-B vectors were computed on the averaged trace and are not directly comparable to new max-hold vectors. Operator must decide whether to clear existing ADS-B vectors before re-capturing. | Field session |
| `capture_loop.py` not passing `trace_key` | Live ADS-B path still uses the averaged trace (`psd_db`) instead of max-hold (`psd_max_hold_db`). Intentionally deferred until ADS-B max-hold field recalibration is complete. | Pending ADS-B recalibration |
| Deferred ACARS/AIS max-hold extension | ACARS and AIS share the burst characteristic with ADS-B but are NOT on max-hold yet; extending it must be bundled with their own field threshold recalibration. | Future phase |
| Live scanner vs tool embedding-space mismatch (Phase 30) | Live scanner forwards `crop_half_width_hz` to `fingerprint_spectrum()`; the 5 offline tools still call with default `None` (uncropped). Zero difference for single-signal captures; up to 5 differing embedding dims for multi-signal captures, biasing L2 distance. Fix: thread `crop_half_width_hz` into `capture_to_vectorstore.py` + `seed_chromadb.py`, re-ingest, optionally re-tune `_DISTANCE_SCALE_REFERENCE`. | Future phase |
| `server.py` `snr_margin_db` 0.0 default | `dashboard/server.py` `broadcast()` defaults `snr_margin_db` to `0.0` when the fingerprint lacks it, making a missing margin indistinguishable from a real +0.0 dB margin. Phase 32 provenance gate (`source="fingerprint"|"decode"`) sidesteps this for confidence display, but a missing margin should ideally default to `None`. TODO comment added in source. Deferred from Phase 32. | Future phase |
| Pluto gain-table non-monotonicity | Noise floor does not rise monotonically with gain — at 35 dB it drops 3–4 dB below the 30 dB value, then resumes rising. Reproduced across two independent sweeps on different days. Suspected AD9363 internal gain-table boundary, unconfirmed. Means gain values are not uniformly spaced in effect. | Phase 39 |
| Pluto spurs above ~30 dB gain | A picket fence of spurious spikes appears across the span above ~30 dB combined gain. Pluto-generated — a HackRF capture at same antenna/freq/moment was clean. Spurs land in the PSD, enter the embedding, and could cluster in ChromaDB as if they were signal. | Phase 39 |
| setup.sh missing SoapyPlutoSDR | setup.sh has not been updated with the SoapyPlutoSDR build steps. A fresh machine gets no Pluto support. Note: libiio (0.26) and libad9361-iio (0.3) ARE packaged in Fedora 44 — libiio-devel + libad9361-iio-devel are needed for headers; only SoapyPlutoSDR needs a source build. | Future phase |
| hackrf_rx.py hardcodes RX direction | core/device/hackrf_rx.py line ~85 sets _SOAPY_RX_DIRECTION = 1 and uses it in every call including open(). pluto_rx.py was deliberately fixed to capture the real SOAPY_SDR_RX from SoapySDR at open() because assuming this value on TX-capable hardware was judged unacceptable — the same reasoning applies unchanged to HackRF, which is also TX-capable. Not currently broken (SOAPY_SDR_RX == 1 in current SoapySDR) and self-consistent, so no divergence bug exists today. But the codebase is asymmetric: the newer device is guarded, the primary one is not. Fix: mirror the pluto_rx.py pattern. | Own phase |
| Pluto band profiles uncalibrated | `PLUTO_BAND_PROFILES` gain_db (30.0) and signal_threshold_db values are placeholders copied from the HackRF profiles, not calibrated for Pluto. gain 30.0 was chosen from a spur observation, not a calibration session. Pluto must not become the default device until this closes. | Phase 39 |
| HackRF vs Pluto RX sensitivity unresolved | Three A/B script attempts all failed on threshold artefacts (mean-PSD averaged bursty squitters away; absolute threshold made HackRF's peak unreachable by construction; per-device percentile fixed the count at ~10 by definition). Kurtosis flipped between runs. Both devices demonstrably hear ADS-B; which hears it better is unknown. Settling test: run each device through Mimir's real pyModeS decoder for ~10 min and count valid frames — no thresholds, no interpretation. Now possible since PlutoReceiver exists. | Field/decode-rate session |
| ACARS decoder unvalidated against live signal | Decoder confirmed CORRECT against captured IQ (rejects non-ACARS cleanly, verified through the real decode path), but never exercised on a *real* ACARS frame — no ACARS traffic present during the 2026-07-21 session (129.125 + 131.550 both confirmed quiet four ways: HackRF FFT, SDR++, 20 min burst-catcher, offline decode of the one transient). "Awaiting decodes…" on a quiet channel is EXPECTED, not a bug. Revisit at a busier Adelaide traffic window; a genuine ACARS burst is ~2.4 kHz wide, 100 ms+. | Live-traffic window (37-Hotfix-2) |

### Open — desk-fixable (no hardware required)

| Item | Detail | Fix in |
|---|---|---|
| `shared_state.py` mid-file import | `from core.device.profiles import DEVICE_PROFILES` sits mid-file (PEP 8 E402), not at the top. Deliberate — Phase 36's append-only constraint forbade touching existing lines. Move to the top of the file when that constraint no longer applies. | Future phase |
| Dict-based SoapySDR mocks | Mocks returning plain dicts are more permissive than real `SoapySDRKwargs` (SWIG C++ map, no `.get()`), which let the Phase 36 `AttributeError` ship green through 27 passing tests and left `PlutoReceiver.open()` unable to open its device for all of Phase 35. `detect.py` and `pluto_rx.py` now convert via `dict()` at the boundary; tests use `FakeSoapySDRKwargs` (`tests/core/soapy_doubles.py`). Any future test mocking SoapySDR enumeration must use the double, not a dict. | Ongoing discipline |
| SoapySDR `Device()` args must be strings | `SoapySDR.Device({"driver": "plutosdr", "uri": "usb:3.19.5"})` raises `make() no match`; the identical values as `"driver=plutosdr,uri=usb:3.19.5"` open the device. Verified 2026-07-17, fresh process, no contention. Cause: SWIG dict marshalling does not produce Kwargs matching what the plugin's `find()` returns; the string path uses the plugin's own parser. `hackrf_rx.py` has always used the string form — `pluto_rx.py` used a dict and never opened its device across all of Phase 35. Any new device wrapper must use the string form. | Resolved — kept as environment fact |
| `dashboard/capture_loop.py` is dead code | Not imported by `scan.py` or `server.py` — superseded by `ScanRunner`'s own `_broadcast_spectrum_fn` (confirmed by grep across both entry points during Phase 37). No Pluto wiring was added here; wiring it would have modified code that never runs. Either delete or revive intentionally. | Future phase |
| `config/mimir.yaml` `hardware.driver` not wired | Phase 37 added `--device {hackrf,plutosdr}` on `scan.py`, but device selection is flag-only — the yaml field is not read for this purpose. Wiring it requires exposing `.driver` on `MimirConfig` (`core/config/loader.py`), which Phase 37 deliberately did not touch. | Future phase |
| `system_stats` `hackrf_status` label is device-agnostic | `dashboard/server.py`'s `system_stats` event reports `hackrf_status` regardless of which device is actually open (HackRF or Pluto). Cosmetic — `_compute_hackrf_status()` works correctly for both via `is_open`, only the field name is misleading on a Pluto run. Rename when Phase 38 touches device-aware frontend UI. | Phase 38 |
| `unsupported_bands_for_device` no defensive `"reason"` key | If a future PLUTO_BAND_PROFILES entry is flipped supported→False without a reason string, the helper raises KeyError from inside a daemon thread (emit_stats), silently killing the system_stats poll. Fix: `.get("reason", "Unsupported on this device")` in the helper, or wrap the call in emit_stats with try/except KeyError. | Phase 39 / future |
| `emit_stats` lacks try/except around new helper | Same crash path as above. An unknown device string (hard to reach today because `current_device` is set from argparse choices, but a future hot-swap endpoint could break that invariant) would kill the stats thread silently. | Phase 39 / future |
| App.jsx `OVERVIEW_BANDS` hasRecent-bar rationale comment misleading on Pluto runs | Comment says "hearing something near that frequency is information" but on a Pluto run the scanner never captures on unsupported bands, so the bar is always grey. The visual result is correct; the rationale is wrong. doc-writer tightened the comment in this same build; this row is a cross-reference. | Fixed in Phase 38 (comment) |
| `FrequencyList.jsx` is dead code | Not imported by App.jsx or any production file — only by its own test file. The actual user-facing band lists are BAND_GROUPS and OVERVIEW_BANDS in App.jsx. Phase 38 spec calling FrequencyList the "primary band list" was inaccurate. Defensive changes were applied per the spec but the file is currently unused. Future: delete or revive intentionally. | Future cleanup phase |
| 2-second pre-first-poll window on Pluto runs | `unsupportedBands` is `{}` until the first system_stats arrives (~2 s). The user could click an unsupported band in that window. Less serious than it sounds — the backend scanner (`core/pipeline/scanner.py:197-220`) has its own authoritative guard. Frontend greying is a UX nicety, not a safety surface. Worth a comment in `pluto_rx.py` documenting the assumption. | Future polish |

### Accepted / Won't Fix (documented, working as intended — not active work)

| Item | Why it stays |
|---|---|
| BAND_PROFILES dict ordering dependency | `fm_broadcast` and `noise_floor` both at 98 MHz; `get_band_for_freq` relies on dict insertion order (fm_broadcast first). Documented in docstring. |
| Clear-focus path doesn't reset `current_band` | `handle_set_focus(None)` leaves `shared_state.current_band` on the last tuned band. Acceptable under single-frequency-focus architecture. |
| Queue drain pattern | `_scan_loop()` drains the queue before each insert ("latest wins"); AI loop always classifies the freshest scan. Steady-state depth 0–1. By design. |
| Thread-safety stress test blind spot | `test_get_band_for_freq_concurrent` doesn't exercise the `current_band_lock` write path (test freqs don't match BAND_PROFILES). Advisory only. |
| `fingerprint_queue` orphaned in `capture_loop` | `capture_loop.py` writes fingerprints to `fingerprint_queue` every 20 frames but no production code consumes it; the live AI loop is fed via the parallel `ScanRunner._scan_loop` path. Pre-existing; operator-visible effect nil. |
| SoapySDR `Device()` args must be strings | ... | Resolved — kept as environment fact |

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

- **~~ADS-B gain divergence (tools vs production)~~:** ~~`tools/calibrate_thresholds.py`
  and `tools/diagnose_fingerprints.py` used (32/38) for ADS-B gain (lna/vga) while
  `dashboard.shared_state.py` BAND_PROFILES uses (24/24).~~ All four tools now read
  gains directly from `BAND_PROFILES`. `calibrate_thresholds.py` resolved in Phase 19a;
  `diagnose_fingerprints.py` resolved in BUG-03. | ✅ Phase 19a + BUG-03

- **BUG-02 (RESOLVED — this session):** `tools/calibrate_thresholds.py` was calling
  `fingerprint_spectrum(psd_result)` without passing `signal_threshold_db`, so all
  bands fell back to the module constant 24.0 dB instead of using their per-band
  production thresholds (e.g. ADS-B 3.0 dB, AIS 5.0 dB, FM 21.0 dB). Fixed by
  importing `BAND_PROFILES` from `dashboard.shared_state`, adding
  `signal_threshold_db` to every `CALIBRATION_TARGETS` entry, and passing it at the
  call site. This aligns calibration vectors with the live dashboard and removes a
  plausible cause of `bandwidth_hz=0` / `occupied_bins=0` in field logs.
  Commit: `d012f01`.

- **BUG-03 (RESOLVED — this session):** Wired four diagnostic/calibration tools to
  `dashboard.shared_state.BAND_PROFILES` for gains and thresholds:
  `tools/capture_to_vectorstore.py`, `tools/calibrate_thresholds.py`,
  `tools/diagnose_fingerprints.py`, and `tools/diagnose_threshold.py`. All four now
  read lna/vga gain values and signal_threshold_db live from BAND_PROFILES instead
  of using module constants or legacy defaults. Additionally, `diagnose_fingerprints.py`
  AIS gains were corrected from (24, 26) to match BAND_PROFILES['ais'] (16, 20).
  Test counts: 557 passing (408 pytest + 149 Vitest), 0 failures.

- **BUG-04 (RESOLVED — this session):** `/vectordb` tooltip showed FREQ as '---'
  for seeded ChromaDB records because `api_vectorstore_points()` read
  `meta.get("freq_hz")` while the seed script writes `"center_freq_hz"`. Fixed by
  using `meta.get("center_freq_hz", meta.get("freq_hz"))` so both seeded records
  and live captures resolve correctly. Added
  `test_center_freq_hz_metadata_key_populates_frequency_hz` to cover the seed-key
  path and the precedence rule. Colour case (TASK 2) and live-capture key names
  (TASK 3) required no changes. Test counts: 582 passing (420 pytest + 162 Vitest).

- **Mascot/CharacterPanel.jsx wiring deferred:** `CharacterPanel.jsx` component exists
  in `dashboard/frontend/src/components/` but is not yet wired into the live operator
  state system. Integration will connect mascot display to OPERATOR_STATE_CONFIG
  transitions (MONITORING/NORMAL/VERIFY/ANOMALY) with appropriate visual states.
  Deferred to next session when mascot assets and animation framework are ready.

---