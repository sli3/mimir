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
- **Secondary OS**: macOS Intel iMac (Phase 5+)
- **Intelligence**: Local LLM server (OpenAI-compatible API)

---

## Architecture
HackRF One (RX only — NEVER TX)
│
▼ raw IQ samples (complex64)
core/device/hackrf_rx.py        ← SoapySDR Python bindings
│
▼ numpy arrays
core/pipeline/capture.py        ← IQ capture + save to disk
│
▼ .npy files
core/pipeline/fft.py            ← FFT + power spectral density
│
▼ psd_result dict
core/pipeline/features.py       ← fingerprint_spectrum()
│
▼ feature dict
embeddings/                     ← ChromaDB vector store (Phase 3)
│
▼ similarity search
llm/                            ← Local LLM classification (Phase 4)
│
▼ classification + anomaly detection
dashboard/                      ← Live waterfall + AI annotations (Phase 5)

---

## Quick Start

```bash
# 1. Clone / place project
cd ~/Repository
git clone <repo> mimir

# 2. Run setup (auto-detects Fedora or Ubuntu/Debian)
chmod +x setup.sh
./setup.sh

# 3. Verify Phase 0 — TX is provably impossible
python -m pytest tests/core/test_rx_only_lock.py -v

# 4. Run full test suite
python -m pytest tests/ -v
```

---

## Phase Tracker

| Phase | Name | Status | Tests |
|---|---|---|---|
| **0** | **Hardware Safety Gate** | ✅ Complete | 25/25 |
| **1** | **IQ Capture Pipeline** | ✅ Complete | 5/5 |
| **2** | **FFT + Feature Extraction** | ✅ Complete | 20/20 |
| 3 | Embedding + Vector Store | ⬜ Next | — |
| 4 | LLM Classification | ⬜ Not started | — |
| 5 | Live Dashboard | ⬜ Not started | — |

**Total: 50/50 tests passing**

---

## Project Structure
mimir/
├── AGENTS.md                       ← OpenCode memory — read first every session
├── opencode.json                   ← OpenCode config + local LLM settings
├── README.md
├── setup.sh                        ← Auto-detecting install script
├── requirements.txt
├── core/
│   ├── device/
│   │   ├── hackrf_rx.py            ← RX-only HackRF wrapper (TX hard blocked)
│   │   └── device_base.py          ← Abstract device interface
│   ├── legal/
│   │   └── compliance_guard.py     ← HardwareTransmitError TX block
│   └── pipeline/
│       ├── capture.py              ← IQ capture + save to disk
│       ├── fft.py                  ← FFT + PSD computation
│       └── features.py             ← fingerprint_spectrum() feature extraction
├── embeddings/                     ← Phase 3+
├── llm/                            ← Phase 4+
├── dashboard/                      ← Phase 5+
├── config/
│   └── mimir.yaml                  ← Runtime configuration (manually maintained)
├── tests/
│   └── core/
│       ├── test_rx_only_lock.py    ← Phase 0: TX hard block tests
│       ├── test_capture_pipeline.py ← Phase 1: IQ capture tests
│       └── test_fft_features.py    ← Phase 2: FFT + fingerprint tests
└── docs/
├── au-legal-reference.md       ← ACMA legal reference
└── MIMIR_ROADMAP.md            ← Full phase roadmap