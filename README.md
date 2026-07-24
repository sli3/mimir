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

### Option A — setup.sh (auto-detects OS, builds dashboard)

```bash
# 1. Clone / place project
cd ~/Repository
git clone <repo> mimir

# 2. Run setup (auto-detects Fedora or Ubuntu/Debian, builds React dashboard)
chmod +x setup.sh
./setup.sh

# 3. Verify Phase 0 — TX is provably impossible
PYTHONPATH=. python -m pytest tests/core/test_rx_only_lock.py -v

# 4. Run full test suite
PYTHONPATH=. python -m pytest tests/ -v

# 5. Start the scanner (PYTHONPATH=. is always required — see note below)
PYTHONPATH=. python scan.py
```

> **`PYTHONPATH=.` is always required** when running `scan.py` or any tool in `tools/`.
> Mimir is not installed as a package — Python needs the repo root on its path to find
> `core/`, `modules/`, `dashboard/`, `embeddings/`, and `llm/`. Without it you will get
> `ModuleNotFoundError: No module named 'core'` (or similar).

### Option B — UV-based (recommended for development)

```bash
# 1. Install system dependencies (UV cannot manage these)
# Fedora:
sudo dnf install hackrf SoapySDR python3-SoapySDR
# Ubuntu/Debian:
sudo apt-get install hackrf soapysdr-module-hackrf python3-soapysdr

# 2. Install UV (if not present)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install all Python dependencies (creates .venv automatically)
uv sync --all-extras

# 4. Verify Phase 0 — TX is provably impossible
uv run pytest tests/core/test_rx_only_lock.py -v

# 5. Run full test suite
uv run pytest

# 6. Start the scanner (PYTHONPATH=. required — SoapySDR is a system package,
#    and Mimir's own modules need the repo root on the import path)
PYTHONPATH=. python scan.py
```

---

## LLM Offline Handling

The LLM classifier now includes offline resilience to handle temporary unavailability of the LLM server on yubaba. Key changes:

- **Startup health check** — `scan.py` calls `classifier.check_connection()` before starting the scan loop. If the server is unreachable, the classifier enters a 60-second cooldown period.
- **Graceful offline results** — During cooldown, classification requests return a `ClassificationResult` with `signal_type="llm_offline"`, confidence "low", and a human-readable reasoning message.
- **Configurable timeouts** — Added `llm_cooldown_sec` and `llm_connect_timeout_sec` configuration fields in `config/mimir.yaml` (defaults: 60 seconds cooldown, 5 seconds connection timeout).

The dashboard displays offline status in the AI Reasoning panel (amber "LLM OFFLINE" label) and Signal History log (amber colour for `llm_offline` entries).

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

Full phase-by-phase history lives in [`docs/ROADMAP.md`](./docs/ROADMAP.md), which is the
single source of truth for phase status and test counts. This section shows
only a quick-glance summary — update `docs/ROADMAP.md` first, then sync this block.

**Current phase: 40b — Device-name UI surface**
**Total: 824 passing (632 pytest + 192 Vitest), 0 failures**

> **Note:** Phase 13 expanded embeddings from 6D to 7D. The production vector
> store (`data/vectorstore/`) must be re-seeded after deploying this build.
> Run `PYTHONPATH=. python tools/seed_chromadb.py` to wipe and re-seed.

---

## Diagnostic Tools

Mimir ships with four standalone tools in `tools/`. These are run manually from the project root — they require the HackRF to be plugged in with an antenna attached, and the Python environment to be active.

All tools are receive-only. No transmission occurs. Jurisdiction: AU/SA — Radiocommunications Act 1992 (Cth).

---

### `tools/diagnose_fingerprints.py`

**What it does:** Captures live IQ samples from the HackRF across four frequency bands and prints the raw feature fingerprint for each — peak power, SNR, spectral flatness, bandwidth estimate, and occupied bins. This is the fastest way to confirm the capture and feature extraction pipeline is working end-to-end and to see what Mimir is actually measuring.

**When to use it:** First thing after a fresh setup, after any changes to `core/pipeline/`, or whenever you want to see what the raw numbers look like for a given frequency.

```bash
PYTHONPATH=. python tools/diagnose_fingerprints.py
```

Output: a table of feature values printed to stdout for each band — FM broadcast (98.9 MHz), ADS-B (1090 MHz), Aviation VHF (127 MHz), and a noise floor reference (433 MHz).

**Note:** Gain values (except noise_floor) are now sourced live from `dashboard.shared_state.BAND_PROFILES` so diagnostic captures use the same gains as the live dashboard. The noise_floor band intentionally uses moderate gain (16/20) for diagnostic visibility and is not sourced from BAND_PROFILES['noise_floor'] (0/0).

---

### `tools/diagnose_threshold.py`

**What it does:** Captures live IQ samples from each AU-legal Mimir band and sweeps through a range of `SIGNAL_THRESHOLD_DB` values (the dB level above the noise floor that counts as "a signal is present"). For each band and each threshold value it prints the resulting occupied bandwidth and bin count. At the end it recommends the per-band threshold value that produces a bandwidth closest to the expected width for that signal type.

**When to use it:** When bandwidth and occupied_bins readings look wrong on any band, or after any changes to `core/pipeline/features.py` or hardware configuration. This tool was built specifically to diagnose BUG-01 (the `psd_db` calibration issue) and to find the correct per-band threshold for your specific hardware and gain settings.

```bash
# Sweep all six bands
PYTHONPATH=. python tools/diagnose_threshold.py

# Sweep a single band
PYTHONPATH=. python tools/diagnose_threshold.py --band adsb
```

Valid `--band` values: `fm_broadcast`, `aviation_vhf`, `acars`, `aprs`, `ism_lora`, `ads_b`.

Output: per-band tables of threshold → bandwidth → bins, a recommended value for each band, and a summary table. Take the recommended values and update `signal_threshold_db` in `BAND_PROFILES` (dashboard/shared_state.py).

**Note:** Gain values (lna_gain_db, vga_gain_db) are now sourced live from `dashboard.shared_state.BAND_PROFILES` so threshold sweeps use the same gains as the live dashboard. The AIS band is not included in the sweep (pre-existing limitation).

---

### `tools/calibrate_thresholds.py`

**What it does:** The full calibration workflow. At startup you select your connected
antenna (telescopic whip, V-dipole, or spiral discone); only bands within that
antenna's usable range are captured. The tool captures IQ samples, runs them through
the complete pipeline (FFT, features, embedding), stores the resulting vectors in a
separate calibration ChromaDB collection at `data/calibration_vectorstore/`, then
computes a pairwise distance matrix between all stored vectors. From that matrix it
derives and prints recommended similarity threshold values for `llm/classifier.py`.

ADS-B, ACARS, and AIS require live aircraft or vessel signals to produce meaningful
vectors. The tool warns you before each of those bands and lets you skip them if no
traffic is present. The distance matrix is split into two halves when there are more
than 8 capture entries so the output fits a standard terminal.

**This tool does NOT touch `data/vectorstore/` (your production signal store).**

**When to use it:** Before finalising the LLM classifier thresholds, after significant
hardware changes (gain settings, antenna swap), or any time the similarity distances
returned by ChromaDB seem off. Run it, then update the `STRONG_MATCH`,
`POSSIBLE_MATCH`, `DIFFERENT_TYPE`, and `NOVEL_SIGNAL` values in `llm/classifier.py`
with the printed recommendations.

```bash
PYTHONPATH=. python tools/calibrate_thresholds.py
```

Output: antenna selection prompt, per-band captures (with warnings for ADS-B, ACARS,
AIS), coloured pairwise distance matrix (green = strong match, yellow = possible match,
red = different type) split into halves if needed, followed by a threshold analysis
block with recommended values.

**Note:** Gain and threshold values (lna_gain_db, vga_gain_db, signal_threshold_db) are
sourced live from `dashboard.shared_state.BAND_PROFILES` so calibration vectors
always match the live dashboard configuration.

---

### `tools/capture_to_vectorstore.py`

**What it does:** Captures live IQ samples from the HackRF across AU-legal receive
bands, computes spectral fingerprints, converts them to embeddings, and stores them
directly in the **production** vector store at `data/vectorstore/`. This is the fast
path to seeding the production store with fresh live vectors -- faster than waiting
for `scan.py` to accumulate captures organically over time.

At startup you select your connected antenna (telescopic whip, V-dipole, or spiral
discone); only bands within that antenna's usable range are captured. ADS-B, ACARS,
and AIS warn you before the first capture of each band because those require live
aircraft or vessel signals to produce meaningful vectors.

**When to use it:** After reseeding the vector store, after hardware changes (antenna
swap, gain adjustment), or whenever you want to deliberately add fresh live vectors
to the production store. Run `tools/calibrate_thresholds.py` afterwards to recompute
distance thresholds.

```bash
# Capture all bands for the connected antenna
PYTHONPATH=. python tools/capture_to_vectorstore.py

# Wipe existing vectors before capturing (destructive -- all previous embeddings lost)
PYTHONPATH=. python tools/capture_to_vectorstore.py --wipe
```

> **Important:** Stop `scan.py` before running this tool. Both processes write to
> `data/vectorstore/` and concurrent access may cause SQLite lock errors.

Output: antenna selection prompt, per-band captures with progress and SNR margin
readings, summary of records stored, and a reminder to run `calibrate_thresholds.py`.

---

### Recommended tool workflow

If you are setting up Mimir for the first time, or tuning it after a hardware change, run the tools in this order:

1. `diagnose_fingerprints.py` — confirm the pipeline is alive and producing numbers
2. `diagnose_threshold.py` — find the right `SIGNAL_THRESHOLD_DB` for your setup
3. `calibrate_thresholds.py` — derive LLM classifier distance thresholds from real captures
4. `capture_to_vectorstore.py` — seed the production vector store with live captures (stop `scan.py` first)

---

## Using Mimir

### Starting the live dashboard

```bash
# From the project root, with your Python environment active:
PYTHONPATH=. python scan.py
```

Then open your browser at `http://localhost:5000`. The cyberpunk dashboard will show:

- **Waterfall** — live spectrum activity across all seven monitored AU frequency bands (FM, APRS, Aviation VHF, ACARS, ISM/LoRa, AIS, ADS-B)
- **AI Reasoning** — LLM classification output for the most recent signal
- **Signal History** — a scrolling log of all detected signals this session
- **Frequency List** — the bands Mimir is currently monitoring
- **System Stats** — scanner status, connection state, and hardware info
- **Character Panel** — visual indicator of current activity level (idle / low / high / anomaly)
- **Decoded Signals** — decoder sub-panels for the currently focused band (ADS-B aircraft, ACARS messages, AIS vessels). Only the relevant panel for the tuned band is shown; a "NO DECODER FOR THIS BAND" placeholder appears for non-decoder bands (FM, APRS, Aviation VHF, ISM/LoRa).

The scanner starts automatically when the server starts. It cycles through the configured frequency bands continuously.

If no supported SDR is connected, `scan.py` logs a clear error message and exits with code 1 (no traceback). Use `--device hackrf` or `--device plutosdr` to force a specific device.

### Vector Space Visualisation

A separate vector space visualisation page is available at `http://localhost:5000/vectordb`. This page provides an interactive 3D scatter plot of all stored ChromaDB embeddings, helping you explore the structure of signal fingerprints and identify clustering patterns. The page is isolated from the main dashboard to avoid clutter and provides a focused view of the vector space.

**Note:** The vector space page requires scikit-learn and React Three.js dependencies. These are automatically installed when running `uv sync --all-extras` or `setup.sh`.

### Dependencies

The project uses UV for dependency management. The following Python dependencies are required:

- numpy>=1.26.0
- PyYAML>=6.0
- requests>=2.31.0
- chromadb>=0.5.0
- flask>=3.0.0
- flask-socketio>=5.3.0
- python-engineio>=4.8.0
- python-socketio[client]>=5.11.0
- huggingface-hub>=0.24.0
- scipy>=1.12.0
- pyais>=3.0.0
- pyModeS>=3.0
- scikit-learn>=1.9.0

Frontend dependencies are managed via npm:

- @react-three/fiber^8.18.0
- @react-three/drei^9.122.0
- react^18.3.1
- react-dom^18.3.1
- socket.io-client^4.7.5
- three^0.185.1

To install all dependencies:

```bash
# Using UV (recommended for development)
uv sync --all-extras

# Or using setup.sh (auto-detects OS)
chmod +x setup.sh
./setup.sh
```

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

## Signal Decoder Modules

Mimir includes three pure-Python signal decoder modules that run inside the main process as daemon threads on the shared IQ bus. No additional hardware or separate processes are required.

| Module | Signal | Frequency | Library | What it decodes |
|---|---|---|---|---|
| `modules/acars/` | ACARS | 129.125 MHz | None (pure Python) | Aircraft data link messages — registration, label, text |
| `modules/ais/` | AIS | 161.975 / 162.025 MHz | `pyais>=3.0.0` | Vessel identification — MMSI, name, position, speed |
| `modules/adsb/` | ADS-B | 1090 MHz | `pyModeS>=3.0` | Aircraft transponder — ICAO, callsign, altitude, position, groundspeed, track |

All three are installed automatically by `uv sync --all-extras`. No additional system packages are needed.

**Legal:** All decoders are passive receive-only. pyModeS and pyais are decode-only libraries with no transmit capability. Jurisdiction: AU/SA — Radiocommunications Act 1992 (Cth).

---

## Project Structure

```
mimir/
├── AGENTS.md                          ← OpenCode memory — read first every session
├── opencode.json                      ← OpenCode config + local LLM settings
├── README.md
├── scan.py                            ← Entry point — starts scanner + dashboard
├── setup.sh                           ← Auto-detecting install + React build
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
├── modules/
│   ├── acars/                         ← ACARS decoder (Phase 9D)
│   ├── ais/                           ← AIS decoder (Phase 9E)
│   └── adsb/                          ← ADS-B decoder (Phase 9F)
├── dashboard/
│   ├── server.py                      ← Flask + Socket.IO server
│   ├── scanner.py                     ← Scan loop + event emission
│   └── static/                        ← Vite build output (generated)
├── tools/
│   ├── calibrate_thresholds.py        ← ChromaDB threshold calibration
│   ├── capture_to_vectorstore.py      ← Live capture → production vector store
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
    └── ROADMAP.md
```