# Mimir — AI-Powered RF Spectrum Scanner

> *Mimir (Old Norse: "the rememberer") — Norse figure of wisdom,
> keeper of knowledge. This project listens and remembers. It never speaks back.*

Passive RF intelligence for Adelaide, South Australia.
Capture signals. Understand them. Never transmit.

---

## ⚠️ Legal Notice

| | |
|---|---|
| **Jurisdiction** | Australia — South Australia (Adelaide) |
| **Authority** | ACMA (Australian Communications and Media Authority) |
| **Law** | Radiocommunications Act 1992 (Cth) |
| **Licence held** | None — passive receive only |

**Transmitting without an ACMA apparatus licence is a criminal offence.**
This software is receive-only by design. No transmission code exists anywhere.
See `docs/au-legal-reference.md` for full details.

---

## Hardware

- **SDR**: HackRF One (receive only — NEVER transmit)
- **Primary OS**: Linux Fedora 44
- **Secondary OS**: macOS Intel iMac (Phase 2+)
- **Intelligence**: Local LLM server (OpenAI-compatible API)
- **Project path**: `~/Repository/mimir`

---

## Architecture

```
HackRF One (RX only — NEVER TX)
    │
    ▼ raw IQ samples (complex64)
core/device/hackrf_rx.py        ← SoapySDR Python bindings
    │
    ▼ numpy arrays
core/pipeline/                  ← FFT + feature extraction
    │
    ▼ signal fingerprints
embeddings/                     ← ChromaDB vector store
    │
    ▼ similarity search
llm/                            ← Local LLM (OpenAI-compatible)
    │
    ▼ classification + anomaly detection
dashboard/                      ← Live waterfall + AI annotations
```

---

## Quick Start

```bash
# 1. Clone / place project
cd ~/Repository
git clone <repo> mimir   # or copy folder here

# 2. Run setup (auto-detects Fedora or Ubuntu/Debian)
chmod +x setup.sh
./setup.sh

# 3. Verify Phase 0 — TX is provably impossible
python -m pytest tests/core/test_rx_only_lock.py -v
```

Phase 0 is complete when all tests pass.

---

## Project Structure

```
mimir/
├── AGENTS.md                    ← OpenCode memory — read first every session
├── opencode.json                ← OpenCode config + local LLM settings
├── README.md
├── setup.sh                     ← Auto-detecting install script
├── requirements.txt
├── core/
│   ├── device/
│   │   ├── hackrf_rx.py         ← RX-only HackRF wrapper (TX hard blocked)
│   │   └── device_base.py       ← Abstract device interface
│   ├── legal/
│   │   └── compliance_guard.py  ← HardwareTransmitError TX block
│   └── pipeline/                ← Phase 1+
├── modules/
│   └── _base/
│       └── module_base.py       ← Signal module interface
├── config/
│   └── mimir.yaml               ← Runtime configuration
├── tests/
│   └── core/
│       └── test_rx_only_lock.py ← Phase 0 acceptance tests
└── docs/
    └── au-legal-reference.md    ← ACMA legal reference
```

---

## Phase Tracker

| Phase | Name | Status |
|---|---|---|
| **0** | **Hardware Safety Gate** | **🔨 In Progress** |
| 1 | IQ Capture Pipeline | Not started |
| 2 | FFT + Feature Extraction | Not started |
| 3 | Embedding + Vector Store | Not started |
| 4 | LLM Classification | Not started |
| 5 | Live Dashboard | Not started |
