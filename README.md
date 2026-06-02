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

## Diagnostic Tools

Mimir ships with three standalone tools in `tools/`. These are run manually from the project root — they require the HackRF to be plugged in with an antenna attached, and the Python environment to be active.

All tools are receive-only. No transmission occurs. Jurisdiction: AU/SA — Radiocommunications Act 1992 (Cth).

---

### `tools/diagnose_fingerprints.py`

**What it does:** Captures live IQ samples from the HackRF across four frequency bands and prints the raw feature fingerprint for each — peak power, SNR, spectral flatness, bandwidth estimate, and occupied bins. This is the fastest way to confirm the capture and feature extraction pipeline is working end-to-end and to see what Mimir is actually measuring.

**When to use it:** First thing after a fresh setup, after any changes to `core/pipeline/`, or whenever you want to see what the raw numbers look like for a given frequency.

```bash
PYTHONPATH=. python tools/diagnose_fingerprints.py
```

Output: a table of feature values printed to stdout for each band — FM broadcast (98.9 MHz), ADS-B (1090 MHz), Aviation VHF (127 MHz), and a noise floor reference (433 MHz).

---

### `tools/diagnose_threshold.py`

**What it does:** Captures a live FM broadcast signal at 98.9 MHz (Adelaide) and sweeps through a range of `SIGNAL_THRESHOLD_DB` values (the dB level above the noise floor that counts as "a signal is present"). For each threshold value it prints the resulting occupied bandwidth and bin count. At the end it recommends the threshold value that produces a bandwidth closest to 200 kHz — the expected width of an FM broadcast signal.

**When to use it:** When bandwidth and occupied_bins readings look wrong, or after any changes to `core/pipeline/features.py`. This tool was built specifically to diagnose BUG-01 (the `psd_db` calibration issue) and to find the correct threshold for your specific hardware and gain settings.

```bash
PYTHONPATH=. python tools/diagnose_threshold.py
```

Output: a table of threshold → bandwidth → bins, followed by a recommended `SIGNAL_THRESHOLD_DB` value. Take the recommended value and update `SIGNAL_THRESHOLD_DB` in `core/pipeline/features.py`.

---

### `tools/calibrate_thresholds.py`

**What it does:** The full calibration workflow. Captures IQ samples from four bands (FM broadcast, ADS-B, Aviation VHF, and a noise floor reference), runs them through the complete pipeline (FFT → features → embedding), stores the resulting vectors in a separate calibration ChromaDB collection at `data/calibration_vectorstore/`, then computes a pairwise distance matrix between all stored vectors. From that matrix it derives and prints recommended similarity threshold values for `llm/classifier.py`.

**This tool does NOT touch `data/vectorstore/` (your production signal store).**

**When to use it:** Before finalising the LLM classifier thresholds, after significant hardware changes (gain settings, antenna swap), or any time the similarity distances returned by ChromaDB seem off. Run it, then update the `STRONG_MATCH`, `POSSIBLE_MATCH`, `DIFFERENT_TYPE`, and `NOVEL_SIGNAL` values in `llm/classifier.py` with the printed recommendations.

```bash
PYTHONPATH=. python tools/calibrate_thresholds.py
```

Output: coloured pairwise distance matrix (green = strong match, yellow = possible match, red = different type) followed by a threshold analysis block with recommended values.

> **Note:** ADS-B at 1090 MHz may produce weaker captures depending on local aircraft traffic. The tool will warn you and ask for confirmation before proceeding.

---

### Recommended tool workflow

If you are setting up Mimir for the first time, or tuning it after a hardware change, run the tools in this order:

1. `diagnose_fingerprints.py` — confirm the pipeline is alive and producing numbers
2. `diagnose_threshold.py` — find the right `SIGNAL_THRESHOLD_DB` for your setup
3. `calibrate_thresholds.py` — derive LLM classifier distance thresholds from real captures

---

## Using Mimir

### Starting the live dashboard

```bash
# From the project root, with your Python environment active:
python scan.py
```

Then open your browser at `http://localhost:5000`. The cyberpunk dashboard will show:

- **Waterfall** — live spectrum activity across the four AU frequency bands
- **AI Reasoning** — LLM classification output for the most recent signal
- **Signal History** — a scrolling log of all detected signals this session
- **Frequency List** — the bands Mimir is currently monitoring
- **System Stats** — scanner status, connection state, and hardware info
- **Character Panel** — visual indicator of current activity level (idle / low / high / anomaly)

The scanner starts automatically when the server starts. It cycles through the configured frequency bands continuously.

---

### How Mimir improves with use

Mimir's signal intelligence comes from its vector store — a database of signal fingerprints it has seen before. The more captures it accumulates, the better its similarity matching becomes.

Each time a signal is detected:

1. The pipeline captures IQ samples and computes a feature fingerprint
2. The fingerprint is converted to a vector and stored in ChromaDB (`data/vectorstore/`)
3. ChromaDB finds the most similar previously-seen signals
4. The local LLM receives the fingerprint plus those nearest neighbours and produces a classification

Over time, ChromaDB builds up a library of known signal types for your specific location and hardware. Signals that were initially flagged as "possibly novel" become confidently classified as the store grows.

**To accelerate this:** run Mimir during periods of known activity — FM broadcasts are always present, but ADS-B is richer during busy flight times, and ISM/LoRa traffic varies by neighbourhood. More captures = richer vector store = better AI context.

---

### Re-calibrating after hardware changes

If you swap antennas, change gain settings in `config/mimir.yaml`, or move the hardware to a new location, the existing calibration thresholds may no longer be optimal. Run the diagnostic tool sequence (see above) to re-derive them.

The production vector store (`data/vectorstore/`) does not need to be cleared — it accumulates captures across calibration cycles. Only the calibration store (`data/calibration_vectorstore/`) is overwritten each time `calibrate_thresholds.py` runs.

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