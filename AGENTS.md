# Mimir Agent Protocol

> *Mimir (Old Norse: "the rememberer") listens, remembers and understands RF
> signals. It never speaks back.*

Mimir is an AI-powered passive RF spectrum scanner: HackRF One and ADALM-PLUTO
SDRs (receive only) → FFT and feature extraction → ChromaDB vector store →
local LLM classification → a Flask-SocketIO + React dashboard.

- Use British English (colour, analyse, behaviour, licence as a noun)
- Be concise. No em dashes in governance prose
- Always read the actual file before making a suggestion or plan. Summaries,
  memos and agent reports are unverified hypotheses until checked on disk
- Never ask clarifying questions with interactive menus or checklists

---

## ⚠️ LEGAL CONSTRAINTS — READ BEFORE EVERY SESSION

These rules apply to every agent, every session and every code change, Codex
included, without exception.

| Item | Value |
|---|---|
| **Jurisdiction** | Australia — South Australia (Adelaide) |
| **Authority** | ACMA (Australian Communications and Media Authority) |
| **Law** | Radiocommunications Act 1992 (Cth) |
| **Licence held** | NONE |
| **Passive RX** | Legal — no licence required |
| **Any TX** | Criminal offence — do not implement under any circumstances |

### Non-negotiable rules
1. **Never produce transmit code.** No `writeStream()`, no TX flags, no
   transmit config, no transmit documentation, no TX examples.
2. **Cross-check AU/SA law** before suggesting any RF frequency or operation.
3. **Do not apply FCC (US) or ETSI (EU) rules.** AU jurisdiction only.
4. **Flag every library with TX capability** and document RX-only safe usage.
5. **`HardwareTransmitError` must be raised** on any call to a TX function.
   This is enforced in `core/legal/compliance_guard.py`, and
   `tests/test_no_transmit.py` fails the suite if any source file calls a TX
   function, references `SOAPY_SDR_TX`, or leaves a TX stub unguarded.
6. **Agents never touch the radio hardware.** No `hackrf_transfer`,
   `hackrf_spiflash`, `hackrf_cpldjtag`, `iio_attr`, `iio_writedev` or
   `SoapySDRUtil`, and no live `scan.py` run. Live hardware verification is
   Prin's job, done by hand.

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

### User RF knowledge level
Prin is an RF beginner. Explain RF concepts from first principles: what a thing
is AND why it matters, not just how to use it. Never assume knowledge of IQ
data, modulation, FFT or antenna theory.

---

## Agents

`pm` is the orchestrator, run on demand with `claude --agent pm`. It runs the
`/build` and `/finalise-build` skills and delegates to three subagents. It also
runs Codex (ChatGPT) itself with `codex exec`: `gpt-6.1-sol` writes the code,
and `gpt-6-astra` reviews and debugs it. Each agent's behaviour, permissions
and model are defined in its own file under `.claude/agents/`. This file
deliberately does not restate them, so it cannot drift out of date.

Claude Code reads this file via `CLAUDE.md`'s `@AGENTS.md` import. Codex reads
it directly.

| Agent | Mode | Purpose |
|-------|------|---------|
| `pm` | primary | Orchestrates a build, gates output, runs tests, browser checks, governance records and the session memo |
| `plan-reviewer` | subagent | Read-only plan, scope and TX / AU-law gate. Sets the task size |
| `code-writer` | subagent | Fallback writer when Codex fails or hits its limit |
| `deep-bug-hunter` | subagent | Fallback reviewer and debugger when Codex fails or hits its limit |

Skills: `/build "<task>"` runs the autonomous build cycle and stops before any
documentation or commit. `/finalise-build "<summary>"` runs after Prin has
verified the build on real hardware. `/multi @agent ...` runs several agents
in parallel. `git-workflow` commits, only when Prin asks.

Only the agents in the table above exist. If a skill, memo or document tells
you to invoke any other agent (for example `@senior-dev`, `@analyst`,
`@security-analyst`, `@memo-writer`, `@doc-writer`), it is out of date: do not
attempt it, and report it to Prin. Never use the Codex plugin's
`codex:codex-rescue` agent or its `/codex:` commands: they start Codex without
its sandbox.

### If you are Codex

`pm` runs you with `codex exec` in one of three modes, named at the start of
your brief. Your sandbox (`.codex/config.toml`) and rules (`.codex/rules/`)
block the protected files and hardware commands in Safety Gates below; treat
them as off-limits anyway. In every mode: never commit, never run hardware
commands, follow the LEGAL CONSTRAINTS, Python Style and Frontend sections
below, and skip the Session Management section, which is for Claude Code
agents.

**Writer (no mode named).** Edit only the files your brief lists, and end with
the files changed and what changed. Update the docstrings and comments of
every function you change in the same pass: a stale comment is a defect here.
Do not run the test suites: `pm` runs them itself. If your brief points to a
hand-off file under `.session-memos/`, read it first: it holds the findings or
test output to act on, word for word.

**Review mode.** Do not edit any file. Run `git status --short` and
`git diff HEAD` to find the changed lines (`pm` stages the build before a
review, so a plain `git diff` would be empty). Report only problems on changed
lines. Check for, in this order:
1. Anything that could transmit: a call to `writeStream`, `setupTxStream`,
   `activateTxStream`, `set_tx_gain`, `set_tx_frequency`, `transmit` or
   `write_samples`; any use of `SOAPY_SDR_TX` or direction `0` in
   `setupStream`; anything that weakens `transmit_guard()` or
   `HardwareTransmitError`. Any of these is a hard-stop finding.
2. Frequencies or band plans from another jurisdiction (868 MHz, 144.390 MHz).
3. Logic errors; missing or wrong exception handling; missing type hints;
   style breaks (logging not print, no bare except, pathlib not os.path).
4. Stale docstrings or comments on changed functions.
5. The bearing-rate / range-rate naming trap (see Frontend) and renamed or
   merged SocketIO events or fields (see Dashboard Architecture).
6. Anything that departs from the plan in your brief.
No refactors or unrelated suggestions. Report:
- Findings: file:line and the problem, or "Zero findings"

**Diagnosis mode.** Do not edit any file. Trace the execution path to the
fault, using the failing test output in your brief or hand-off file (do not
run the suites: `pm` runs them), and report: the root cause in one sentence,
your confidence (High, Medium or Low), the execution path, the affected files
and functions, what not to touch, the fix strategy (no code), and unknowns.

---

## Safety Gates

- `AGENTS.md`, `CLAUDE.md`, `.mcp.json`, everything under `.claude/` and
  `.codex/`, and `opencode.json` are edited by Prin only
- Governance docs: `docs/ROADMAP.md`, `docs/TECH_DEBT.md` and the two
  "Phase Tracker" summary lines in `README.md` are edited only by `pm`, only
  in `/finalise-build` or when Prin asks in the session, with targeted Edit
  calls (rules in `pm`'s own file). No other agent, and not Codex, edits them
- `data/` holds Prin's IQ captures and vector stores. No agent writes,
  moves or deletes anything under it
- Never `git push`. Never use `--force`. Never `git reset --hard`
- Agents never commit, with one exception: `pm` may commit through the
  `git-workflow` skill when Prin asks in the session and then types "OK" to
  the staged diff
- Never modify a file without first reading its current contents
- Never work around a permission deny, hook block or `ask` prompt: no string
  building, encoding, `python -c` wrappers, subprocess calls, MCP tools or
  alternative tools. If a rule blocks legitimate work, stop and report the
  exact command and rule to Prin

### Delegation boundaries (from a confirmed incident, July 2026)

Under OpenCode, an orchestrator whose named subagent was denied an action
quietly did the work itself instead, once with its own edit tool and once
through the GitHub MCP server (a direct commit to the remote, interrupted
before it landed). Therefore:
1. If a request names a specific agent and that agent's permissions do not
   allow the action, STOP. Report which agent, what was asked and which rule
   blocked it, and ask Prin how to proceed.
2. Never substitute a different tool, agent or MCP server to perform an
   action that was denied.
3. Only do it yourself if Prin explicitly says so.

---

## Verification Discipline

- **Narration is not evidence.** `git show HEAD` and `git diff` beat any
  agent's report. Run the tests yourself rather than trusting a reported count
- **Green tests are necessary, not sufficient.** Several bugs (Phases 35/36,
  72, the ADS-B `PREAMBLE_THRESHOLD`) were only found on real hardware. Mock
  tests can be more permissive than hardware (`SoapySDRKwargs` vs plain dicts)
- **No design from summaries.** Read the actual source (`features.py`,
  `fingerprint.py`, ...) before scoping work
- **Sequencing.** Resolve upstream issues before downstream work: calibrate
  thresholds before re-seeding ChromaDB, fix stale thresholds before capture
- **Governance prose** must never contain absence claims ("files not
  changed"), invented rationale, derived test arithmetic, or named
  identifiers (test names, line numbers, constants) not confirmed with `grep`
  or `git diff` in the same run. Two fabrication incidents came from exactly
  these

---

## Editing and Scope

- Make ONLY the change that was agreed. Do not change formatting, imports or
  unrelated lines
- If you notice something unrelated that could be improved, do NOT change it:
  list it under "Not Finished" in the session memo or report instead
- Edit only what a plan approved by Prin covers. Under `/build`, the submitted
  task is that approval. Outside `/build`, show the change and wait for an
  explicit "OK" first
- After any edit to a commented function, fix its comments in the same pass

---

## Python Style

- PEP 8; type hints on every function signature; a docstring on every
  function and class (one line is enough)
- `logging`, never `print`, for diagnostic output
- Never a bare `except:`; catch specific exceptions
- `pathlib.Path` for file paths
- Never hardcode credentials. Network endpoints come from `config/mimir.yaml`

## Frontend

- Vite + React, plain JS/JSX. No TypeScript, no Tailwind, no `<form>` tags
- Every SocketIO listener is removed in its effect's cleanup
- **Naming trap:** `delta_r_deg_per_sec` (`bearing_tracker.py`) is the
  BEARING rate in °/s. `deltaRNmPerSec` (frontend) is the RANGE rate in nm/s.
  Different quantities, near-identical names: call it out in any brief or
  review that touches either

---

## Running Python and Tests

- Python tests: `uv run pytest` from the repo root
- Frontend tests: `npm run test --prefix dashboard/frontend`. Never
  `npx vitest` from the repo root: `npx` can pull a different cached Vitest,
  which breaks the jsdom setup and produces false failures (BUG-05)
- Tool scripts: `PYTHONPATH=. uv run python tools/<script>.py`
- The scanner itself runs on system Python (`python scan.py`) because the
  SoapySDR bindings are system packages. Agents never run it against
  hardware. Demo mode (`python scan.py --demo --demo-files <sigmf-file>`)
  needs no SDR and is what browser checks look at; Prin starts it himself
- System dependencies UV cannot manage: `hackrf`, `SoapySDR`,
  `python3-SoapySDR` (dnf). SoapyHackRF and acarsdec are built from source
  (`setup.sh` handles acarsdec). They are not in the Fedora repos

---

## Hardware

| Item | Detail |
|---|---|
| **SDRs** | HackRF One and ADALM-PLUTO, both RECEIVE ONLY. Either/or, never simultaneous. Pluto is the default when both are connected; HackRF for sub-325 MHz bands |
| **Primary OS** | Fedora 44 |
| **LLM** | llama.cpp on yubaba, OpenAI-compatible API (endpoint in `config/mimir.yaml`) |
| **Vector store** | ChromaDB |
| **Project path** | `~/Repository/mimir` |

## Architecture

```text
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
```

## Dashboard Architecture

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
| `modules/ais/subscriber.py` | AisSubscriber — IQ bus subscriber + decode thread |
| `modules/ais/demodulator.py` | AisDemodulator — frequency shift + GMSK differential + HDLC extract |
| `modules/ais/decoder.py` | AisDecoder — NMEA sentence reconstruction + pyais decode |
| `modules/ais/message.py` | AisMessage dataclass |
| `modules/ais/constants.py` | AU AIS frequencies (161.975/162.025 MHz) and GMSK constants |
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

## Project Documents

| File | Purpose | Who edits |
|---|---|---|
| `docs/ROADMAP.md` | Phase tracker and build history (single source of truth) | `pm` (finalise) |
| `docs/TECH_DEBT.md` | Known tech debt, accepted items, deferred items, resolved archive | `pm` (finalise) |
| `docs/au-legal-reference.md` | ACMA legal reference | Prin |
| `.session-memos/` | Session memos, gitignored and local only | `pm` |
| `README.md` | Public overview. Only its two Phase Tracker summary lines are `pm`'s | Prin, `pm` |

Read `docs/TECH_DEBT.md` and the latest session memo before planning any build.

## MCP Servers (`.mcp.json`)

| Server | Purpose | Who uses it |
|---|---|---|
| `context7` | Live library and API docs (ChromaDB, SoapySDR, pyModeS, pyais, Flask-SocketIO, React) | `plan-reviewer`, `pm` |
| `playwright` | Headless browser for checking the dashboard on `localhost` | `pm` only, enforced by `agent_guard.py` |
| `wiki-search` | Read-only semantic search of the private mimir-wiki | `pm`, `plan-reviewer` |

There is deliberately no filesystem MCP server and no GitHub MCP server: both
were write paths around the permission rules in the July 2026 incident.

## Session Management

`/build` and `/finalise-build` handle their own preflight and memo. For
sessions run directly:
- To find the latest memo: `ls -t .session-memos/` (the first entry is newest)
- Run the `session-memo` skill when Prin says "memo", and suggest it when the
  context is getting full
- For a non-trivial bug outside `/build`, use the `deep-bug-analysis` skill
  before anyone changes code
