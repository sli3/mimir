# Mimir — Project Roadmap
## AI-Powered RF Spectrum Scanner

> *Passive RF intelligence for Adelaide, South Australia.
> Capture signals. Understand them. Never transmit.*

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Complete |
| 🔨 | In Progress |
| ⬜ | Not Started |
| 🚫 | Blocked |

---

## Phase 0 — Hardware Safety Gate ✅

**Goal:** TX is provably impossible in software before any other code is written.

| Task | Status |
|------|--------|
| HackRF One drivers installed (Fedora 44, dnf) | ✅ |
| Firmware verified: 2026.01.3 (API:1.10) | ✅ |
| SoapySDR + python3-SoapySDR installed | ✅ |
| SoapyHackRF plugin built from source (no dnf package on Fedora 44) | ✅ |
| `HardwareTransmitError` implemented in `core/legal/compliance_guard.py` | ✅ |
| All TX methods on `HackRFReceiver` raise `HardwareTransmitError` | ✅ |
| Abstract `DeviceBase` TX methods blocked | ✅ |
| 25/25 Phase 0 tests passing | ✅ |

**Acceptance test:**
```bash
python -m pytest tests/core/test_rx_only_lock.py -v
```

---

## Phase 1 — IQ Capture Pipeline ✅

**Goal:** Capture real IQ samples from the HackRF and save them to disk.

| Task | Status |
|------|--------|
| `core/pipeline/capture.py` written | ✅ |
| `capture_iq()` — open device, tune, capture, return ndarray | ✅ |
| `save_capture()` — save ndarray to `data/captures/` as timestamped `.npy` | ✅ |
| `capture_and_save()` — convenience wrapper | ✅ |
| `read_samples()` accumulation loop fix (single readStream = ~131k not 2M) | ✅ |
| 5/5 Phase 1 tests passing (30/30 total) | ✅ |
| First real hardware capture: 98 MHz FM, Adelaide | ✅ |
| `.npy` file verified as real signal (not flat noise) | ✅ |

**Verify Phase 1 fix:**
```bash
python3 -c "
from core.pipeline.capture import capture_and_save
import numpy as np
path = capture_and_save(freq_hz=98_000_000, num_samples=2_000_000, sample_rate_hz=2_000_000)
s = np.load(path)
print('Shape:', s.shape)   # must be (2000000,)
"
```

---

## Phase 2 — FFT + Feature Extraction ⬜

**Goal:** Convert raw IQ samples into frequency-domain features that can be fingerprinted.

| Task | Status |
|------|--------|
| `core/pipeline/fft.py` — FFT on IQ samples | ⬜ |
| Power spectral density (PSD) calculation | ⬜ |
| Peak detection — find signal peaks above noise floor | ⬜ |
| Feature vector extraction (centre freq, bandwidth, peak power, SNR) | ⬜ |
| `core/pipeline/features.py` — structured feature output | ⬜ |
| Unit tests for FFT pipeline | ⬜ |
| Visualisation: waterfall plot or spectrum plot (optional, debug aid) | ⬜ |

**Acceptance:** Given a real `.npy` capture, produce a structured feature dict with
centre frequency, bandwidth estimate, peak power, and noise floor.

---

## Phase 3 — Embedding + Vector Store ⬜

**Goal:** Convert signal features into embeddings and store them in a vector database for similarity search.

| Task | Status |
|------|--------|
| Choose embedding strategy (local model or feature hashing) | ⬜ |
| `embeddings/` module — convert feature dict → embedding vector | ⬜ |
| ChromaDB integration — store and query embeddings | ⬜ |
| Similarity search — find closest known signal to a new capture | ⬜ |
| Seed database with known AU signals (FM, ADS-B, APRS, LoRa) | ⬜ |
| Unit tests for embedding + retrieval | ⬜ |

**Acceptance:** Given a new capture, return the top-N most similar known signals
from the vector store with similarity scores.

---

## Phase 4 — LLM Classification ⬜

**Goal:** Use the local LLM to classify signals and detect anomalies using retrieved context.

| Task | Status |
|------|--------|
| `llm/` module — OpenAI-compatible API client | ⬜ |
| Prompt design — signal classification from features + retrieved context | ⬜ |
| Anomaly detection — flag signals with no close match in vector store | ⬜ |
| Structured output — classification label, confidence, explanation | ⬜ |
| AU legal check in LLM prompt (passive RX only context) | ⬜ |
| Integration test: capture → FFT → embed → retrieve → classify | ⬜ |

**Acceptance:** End-to-end pipeline from raw IQ to LLM classification label
with explanation, running on local LLM server.

---

## Phase 5 — Live Dashboard ⬜

**Goal:** Real-time waterfall display with AI annotation overlay.

| Task | Status |
|------|--------|
| Choose dashboard framework (Textual TUI or web-based) | ⬜ |
| Live waterfall display — scrolling frequency vs time vs power | ⬜ |
| AI annotation overlay — classification labels on detected signals | ⬜ |
| Frequency preset selector (FM, Aviation, APRS, LoRa, ADS-B) | ⬜ |
| Anomaly alert — highlight unknown signals | ⬜ |
| Session logging — save annotated captures with classifications | ⬜ |

**Acceptance:** Live display running with real HackRF capture, showing
waterfall and AI annotations updating in real time.

---

## Infrastructure & Tooling

| Item | Status |
|------|--------|
| OpenCode workflow (preflight → code → review → sanity → git) | ✅ |
| `AGENTS.md` project memory file | ✅ |
| `.opencode/agents/` — local-reviewer, cloud-reviewer, plan-reviewer | ✅ |
| `.opencode/skills/` — preflight, sanity-check, git-workflow, session-memo, bug-hunt | ✅ |
| SoapyHackRF built from source at `~/Repository/SoapyHackRF` | ✅ |
| `setup.sh` — auto-detecting Fedora/Ubuntu install script | ✅ |
| `docs/au-legal-reference.md` — ACMA compliance reference | ✅ |
| macOS Intel iMac setup | ⬜ |

---

## Known Issues / Tech Debt

| Issue | Priority | Phase to fix |
|-------|----------|--------------|
| `config/mimir.yaml` comment says "auto-generated on first run" — false, file is manually maintained and not yet loaded at runtime | Low | Phase 2 |
| `data/captures/` excluded from git (`.gitignore`) — no capture archiving strategy yet | Low | Phase 3 |
| USB bus contention warning from `hackrf_info` — 4 other devices on same bus, may affect high sample rates | Low | Phase 2 |

---

## Hardware Reference

| Item | Detail |
|------|--------|
| SDR | HackRF One — RECEIVE ONLY |
| Firmware | 2026.01.3 (API:1.10) |
| Board | Older than r6 — self-test FAIL is cosmetic, device works |
| SoapySDR plugin | Built from source: `~/Repository/SoapyHackRF` |
| Primary OS | Linux Fedora 44 |
| Secondary OS | macOS Intel iMac (not yet configured) |
| Local LLM | llama.cpp server on yubaba (192.168.0.66:8080) |

---

*Last updated: 2026-05-20 — Phase 1 complete*
