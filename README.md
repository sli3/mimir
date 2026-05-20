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
- **Firmware**: 2026.01.3 (API:1.10)
- **Board note**: Older than r6 — self-test FAIL is cosmetic, device works
- **Primary OS**: Linux Fedora 44
- **Secondary OS**: macOS Intel iMac (Phase 2+)
- **Intelligence**: Local LLM server (llama.cpp, OpenAI-compatible API)

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
# 1. Clone the project
cd ~/Repository
git clone <repo> mimir

# 2. Run setup (auto-detects Fedora or Ubuntu/Debian)
chmod +x setup.sh
./setup.sh

# 3. Build SoapyHackRF plugin (Fedora only — not in dnf repos)
cd ~/Repository
git clone https://github.com/pothosware/SoapyHackRF.git
cd SoapyHackRF && mkdir build && cd build
cmake .. && make -j$(nproc) && sudo make install

# 4. Verify Phase 0 — TX is provably impossible
python -m pytest tests/core/test_rx_only_lock.py -v

# 5. Run a test capture (HackRF must be plugged in with antenna)
python3 -c "
from core.pipeline.capture import capture_and_save
import numpy as np
path = capture_and_save(freq_hz=98_000_000, num_samples=2_000_000, sample_rate_hz=2_000_000)
s = np.load(path)
print('Shape:', s.shape)
print('Saved to:', path)
"
```

---

## Phase Tracker

| Phase | Name | Status |
|-------|------|--------|
| **0** | **Hardware Safety Gate** | **✅ Complete** |
| **1** | **IQ Capture Pipeline** | **✅ Complete** |
| 2 | FFT + Feature Extraction | ⬜ Not started |
| 3 | Embedding + Vector Store | ⬜ Not started |
| 4 | LLM Classification | ⬜ Not started |
| 5 | Live Dashboard | ⬜ Not started |

See `ROADMAP.md` for full task breakdown and acceptance criteria.

---

## Project Structure

```
mimir/
├── AGENTS.md                    ← OpenCode memory — read first every session
├── ROADMAP.md                   ← Phase tracker with acceptance criteria
├── opencode.json                ← OpenCode config + local LLM (local only, not committed)
├── README.md
├── setup.sh                     ← Auto-detecting install script (Fedora + Ubuntu/Debian)
├── requirements.txt
├── core/
│   ├── device/
│   │   ├── hackrf_rx.py         ← RX-only HackRF wrapper (TX hard blocked)
│   │   └── device_base.py       ← Abstract device interface
│   ├── legal/
│   │   └── compliance_guard.py  ← HardwareTransmitError TX block
│   └── pipeline/
│       └── capture.py           ← IQ capture and save pipeline
├── modules/
│   └── _base/
│       └── module_base.py       ← Signal module interface (stub)
├── config/
│   └── mimir.yaml               ← Runtime configuration
├── tests/
│   └── core/
│       ├── test_rx_only_lock.py ← Phase 0 acceptance tests (25 tests)
│       └── test_capture_pipeline.py ← Phase 1 acceptance tests (5 tests)
└── docs/
    └── au-legal-reference.md    ← ACMA legal reference
```

---

## Australian Frequencies

All frequencies below are legal to receive passively under the
Radiocommunications Act 1992 (Cth). No licence required for reception.

| Band | Frequency | Notes |
|------|-----------|-------|
| FM Broadcast | 87.5–108 MHz | Commercial and community radio |
| Aviation VHF | 118–136 MHz | ATC and aircraft comms |
| APRS | 145.175 MHz | AU frequency — NOT 144.390 (US) |
| ISM / LoRa | 915 MHz | AU/NZ band — NOT 868 MHz (EU) |
| ADS-B | 1090 MHz | Aircraft GPS position broadcasts |

---

## Development Workflow

This project uses [OpenCode](https://opencode.ai) with a local LLM for all code changes.

Every Code session follows this sequence:
```
code-preflight → write code → @local-reviewer → code-sanity-check → git-workflow
```

Skills and agents live in `.opencode/`. See `AGENTS.md` for full workflow details.

---

## Test Suite

```bash
# All tests (30 total)
python -m pytest tests/ -v

# Phase 0 only — TX safety
python -m pytest tests/core/test_rx_only_lock.py -v

# Phase 1 only — capture pipeline
python -m pytest tests/core/test_capture_pipeline.py -v
```
