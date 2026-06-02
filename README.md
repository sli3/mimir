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
- **Secondary OS**: macOS Intel iMac
- **Intelligence**: Local LLM server (OpenAI-compatible API)

---

## Architecture

```
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
dashboard/                      ← Cyberpunk React/Vite dashboard (Phase 7A+)
```

---

## Quick Start

```bash
# 1. Clone / place project
cd ~/Repository
git clone <repo> mimir

# 2. Run setup (auto-detects Fedora or Ubuntu/Debian, builds React dashboard)
chmod +x setup.sh
./setup.sh

# 3. Verify Phase 0 — TX is provably impossible
python -m pytest tests/core/test_rx_only_lock.py -v

# 4. Run full test suite
python -m pytest tests/ -v

# 5. Start the scanner
python scan.py
```

---

## Diagnostic Tool

To verify the live pipeline is emitting events correctly (requires `scan.py` running):

```bash
python tools/diagnose_live.py --duration 60 --url http://localhost:5000
```

Output shows live `[spectrum_update]` and `[scan_result]` events per band,
event rate, gap detection, and a PASS/FAIL summary. Use `--duration 60` minimum
— the scanner cycles all four AU bands sequentially and the cycle time is long.

---

## Phase Tracker

| Phase | Name                        | Status       | Tests   |
|-------|-----------------------------|--------------|---------|
| 0     | Hardware Safety Gate        | ✅ Complete  | 25/25   |
| 1     | IQ Capture Pipeline         | ✅ Complete  | 5/5     |
| 2     | FFT + Feature Extraction    | ✅ Complete  | 21/21   |
| 3     | Embedding + Vector Store    | ✅ Complete  | 24/24   |
| 4     | LLM Classification          | ✅ Complete  | 24/24   |
| 5     | Live Scanner + Dashboard    | ✅ Complete  | 9/9     |
| 6     | Socket.IO + Scan Pipeline   | ✅ Complete  | 14/14   |
| 7A    | Cyberpunk React Dashboard   | ✅ Complete  | 158/158 |
| 7B-pre| Frontend Consolidation      | ✅ Complete  | 192/192 |
| 7B    | Data Layer                  | 🔜 Next      | —       |

**Total: 192/192 tests passing (142 pytest + 50 Vitest)**

---

## Project Structure

```
mimir/
├── AGENTS.md                          ← OpenCode memory — read first every session
├── opencode.json                      ← OpenCode config + local LLM settings
├── README.md
├── scan.py                            ← Entry point — starts scanner + dashboard
├── setup.sh                           ← Auto-detecting install + React build
├── requirements.txt
├── core/
│   ├── device/
│   │   ├── hackrf_rx.py               ← RX-only HackRF wrapper (TX hard blocked)
│   │   └── device_base.py             ← Abstract device interface
│   ├── legal/
│   │   └── compliance_guard.py        ← HardwareTransmitError TX block
│   └── pipeline/
│       ├── capture.py                 ← IQ capture + save to disk
│       ├── fft.py                     ← FFT + PSD computation
│       ├── features.py                ← fingerprint_spectrum()
│       └── scan_result.py             ← ScanResult dataclass
├── embeddings/
│   ├── embedder.py                    ← SpectrumEmbedder
│   └── store.py                       ← SignalStore (ChromaDB)
├── llm/
│   └── classifier.py                  ← LLM signal classification
├── dashboard/
│   ├── server.py                      ← Flask + Socket.IO server
│   ├── scanner.py                     ← Scan loop + event emission
│   └── static/                        ← Vite build output (generated)
├── tools/
│   ├── calibrate_thresholds.py        ← ChromaDB threshold calibration
│   ├── diagnose_fingerprints.py       ← Fingerprint diagnostics
│   ├── diagnose_threshold.py          ← Threshold diagnostics
│   └── diagnose_live.py               ← Live pipeline diagnostic (CLI)
├── config/
│   └── mimir.yaml                     ← Runtime configuration
├── tests/
│   ├── core/
│   ├── embeddings/
│   ├── llm/
│   ├── dashboard/
│   └── tools/
│       └── test_diagnose_live.py      ← 34 tests
└── docs/
    ├── au-legal-reference.md
    └── MIMIR_ROADMAP.md
```