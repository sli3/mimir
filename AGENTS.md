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
| **Project path** | (set locally) |

---

## Architecture

```
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
dashboard/                      Live waterfall + AI annotation overlay
```

---

## Project Format — Non-Negotiable

- **OpenCode exclusively**: `AGENTS.md` and `opencode.json`
- **Never** Claude Code format (`CLAUDE.md`, `.claude/`)
- **Never** Cursor format (`.cursorrules`)
- All agent config lives in `opencode.json`

---

## Phase Tracker

| Phase | Name | Status |
|---|---|---|
| 0 | Hardware Safety Gate | 🔨 In Progress |
| 1 | IQ Capture Pipeline | Not started |
| 2 | FFT + Feature Extraction | Not started |
| 3 | Embedding + Vector Store | Not started |
| 4 | LLM Classification | Not started |
| 5 | Live Dashboard | Not started |

### Phase 0 complete when
```
python -m pytest tests/core/test_rx_only_lock.py -v
```
All tests pass. TX is provably impossible in software.

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
| `tests/core/test_rx_only_lock.py` | Phase 0 acceptance tests |
| `config/mimir.yaml` | Runtime configuration |
| `docs/au-legal-reference.md` | ACMA legal reference |
