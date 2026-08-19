# Mimir — Project Roadmap

> Passive RF intelligence for Adelaide, South Australia.
> Capture signals. Understand them. Never transmit.

---

## Where phase history lives now

Full history for every completed phase (Phase 0 through Phase 66, plus BUG-03/BUG-04)
has moved to the `mimir-wiki` repo, under `03 - Legacy/docs/` — one file per phase,
indexed and searchable via the wiki-search OpenCode tool. This file only tracks
what's actually still ahead.

Looking for what shipped, when, or the detail behind a past phase? Ask `wiki-search`
(e.g. *"what happened in Phase 65"*, *"Pluto gain calibration findings"*) rather than
scrolling a long file — that's exactly the retrieval problem the wiki-RAG system was
built to solve.

---

## Sequencing (do these roughly in order)

1. **Receiver reference position fix** — `modules/adsb/constants.py` `ADELAIDE_LAT`/`ADELAIDE_LON`
   are still a CBD placeholder at 2dp, not the actual receiver location. Wrong origin for
   all bearing/range/θ math downstream. Must ship *before* the anomaly flag strip below,
   since that work depends on correct positions. Fix = real coords at 5dp + rewrite the
   stale comment block + consider renaming to `RECEIVER_LAT`/`RECEIVER_LON`.

2. **Anomaly flag strip** — design already locked (see wiki: continuous anomaly flag
   strip note). Three flags v1: emergency squawk, high turn rate, rapid altitude change.
   Blocked on item 1 above.

3. **Δr precision fix** — `PathPredictionPanel.jsx`'s `.toFixed(1)` rounds range rate to
   "0.0nm/s" for virtually every real contact. Fix: 2–3 decimals, or express in knots.

4. **Aviation/AIS threshold calibration** — flip-flop at 127.0 MHz traced to placeholder
   thresholds sitting inside noise variance. Correct fix is a live `diagnose_threshold.py`
   sweep for both bands, not a debounce workaround.

5. **Live SNR trigger verification** — Phase 65's fixes shipped the code path, but live
   hardware verification against real ADS-B traffic is still blocked on
   `diagnose_threshold.py` gaining `trace_key` plumbing first.

6. **Projection accuracy tracking** — after the receiver position fix and anomaly strip
   are both stable.

7. **ChromaDB similar-trajectory recall** — still an open question whether ChromaDB
   currently stores anything trajectory-shaped, or only signal fingerprints.

---

## Queued, not yet scoped

- **Raw Capture & Replay — design session.** Needs a dedicated design conversation
  before any `/build` prompt. Open questions: trigger mechanism, disk budget, replay UX,
  exact hook point.
- **NOAA / Meteor-M2 satellite module** — after current phases are stable.
- **V-dipole antenna validation** — SDR++ check, then NOAA pass at heavens-above.com,
  then AIS at 162.000 MHz, then revalidate `BAND_PROFILES` gain values.

---

## Known tech debt

Tracked in `AGENTS.md`'s Known Tech Debt table, not duplicated here. That table is the
single source of truth for open defects, stale values, and cross-session housekeeping.

---

## Source of truth reminder

If this file and the wiki ever disagree about what's "next," this file wins for
*current* priorities — it's meant to be kept short and edited often. The wiki's
`03 - Legacy/docs/` archive is historical record only and is not meant to be
edited after migration.

---

## Phase 66 — Manual capture button (2026-08-17)

First live call site for `save_capture()`. Adds `ScanRunner.capture_now()` cross-thread request/response handoff (Event + Lock + dict), `POST /api/capture` Flask route near `/api/radar/reason`, and `ManualCaptureButton.jsx` component on the main dashboard with verdict logic on occupied_bins (frontend-owned via exported pure function). Reuses in-flight scan-loop samples per the Phase 62 timing-integrity rationale — does NOT use `capture_and_save()`. Phase 63 SNR-edge auto-trigger block remains byte-identical.

- 26 new tests (7 backend + 14 frontend + 5 regression for frontend-reviewer bugs)
- pytest: 899 passed / 1 pre-existing failed
- vitest: 396 passed (33 files), 0 failures
- LIFE-01, EDGE-03, ADV-01 verified green and unmodified
- Frontend-reviewer found 4 bugs (retry-timer race, mountedRef Strict Mode, non-abortable fetch, ARIA), all fixed with regression tests
- See `.session-memos/2026-08-17_manual-capture-button.md` for full session detail

---

## Phase 67 — Manual capture UI split + is_burst threading (2026-08-17)

Splits the Phase 66 combined `ManualCaptureButton` component into `CaptureButton` (top control row, next to TUNE) and `CaptureResultPanel` (right sidebar, between Signal Details and System Status). State machine extracted to `useCapture` custom hook mirroring the existing `useSocket.js` pattern (recommended by both plan-reviewer and frontend-reviewer; reduces App.jsx by 117 lines).

Wires `is_burst` through to the capture response as a top-level sibling of the `fingerprint` sub-dict (NOT folded into it) — mirrors the existing `dashboard/server.py` `scan_result` precedent. The seven `_FINGERPRINT_METADATA_KEYS` are untouched (their tuple governs SigMF metadata; `is_burst` is deliberately excluded as a detection-pipeline internal). Burst Detected verdict is now reachable from live data.

- 3 new tests (1 backend sibling-shape + 2 frontend burst-overrides-wide)
- pytest: 900 passed / 1 pre-existing failed (Pluto 8.0 dB stale test, untouched)
- vitest: 398 passed (33 files), 0 failures
- See `.session-memos/2026-08-17_manual-capture-ui-split.md` for full session detail

---

## Phase 68 + 69 — Record + Waterfall Markers (2026-08-18)

**Type:** Backend recording controls (Phase 68) and frontend event markers (Phase 69). No hardware changes.

**Goal.** Phase 68 adds in-flight recording start/stop controls (no manual capture overhead, coexists with Phase 66 one-shot button). Phase 69 adds three event-marker types (Capture Now / Record start / Record stop) drawn on the existing waterfall crosshair overlay.

**What shipped (Phase 68).** `ScanRunner.start_recording()`/`stop_recording()`/`get_recording_status()`, `save_recording()` in `core/pipeline/capture.py`, POST `/api/record/{start,stop}` routes in `dashboard/server.py`, `RecordButton.jsx` in `App.jsx` (next to TUNE), `useRecording.js` hook with elapsed-time timer and 60s soft-cap warning. Coexists with Phase 66 one-shot `capture_now()` without modifying it. Frontend-only except for backend routes; no frozen-file changes to scanner pipeline.

**What shipped (Phase 69).** Three event-marker types drawn on the existing crosshair overlay canvas in `WaterfallPanel.jsx`: Capture Now (cyan hollow cross), Record start (magenta hollow cross), Record stop (yellow hollow cross). New `useWaterfallMarkers.js` hook manages marker state and tick/prune logic (markers expire after 90s). Frontend-only; no backend changes.

**Live verification.** Phase 68 live-verified against PlutoSDR at 915.825 MHz (488.6 MB SigMF pair, 466 cycles, ~30.5s recording). GNU Radio cross-tool validation confirmed standards-compliant SigMF output (core:frequency, core:sample_rate, mimir:fingerprint_sequence intact, identical cycle count). Phase 69 live-verified on ADS-B waterfall strip with all three marker styles visible and legible during a live recording session.

**Design notes.** Both phases preserve the existing Phase 63 SNR-edge auto-trigger block byte-identically. Recording uses the same `np.concatenate()` pattern as manual capture; Phase 68 deliberately did NOT reuse the Phase 62 deferred capture-and-save path (that path still has no live call sites). Phase 69 markers reuse the existing crosshair canvas overlay; no additional canvas layers added.

**Test counts.** 1387 passing (962 pytest + 425 Vitest), 0 failures. Phase 68 added 10 tests (7 backend + 3 frontend). Phase 69 added 10 tests (frontend-only).

**Resolved tech debt.** None.

**New tech debt.** Two new desk-fixable rows logged in `AGENTS.md`: (1) Record has no backend memory cap (OOM risk on unattended runs) — not urgent but should not be left indefinitely. (2) Marker tick effect keys on `[latestPsd]`; `useWaterfall.js` keys on `[psdDb, device]` — theoretical pre-interaction-window race; low priority.

**RF/Legal notes.** No TX surfaces; all changes are read-only access to in-flight scan data and UI state management. No new RF capability or legal exposure. Jurisdiction: AU/SA, ACMA, Radiocommunications Act 1992 (Cth).

---

## Phase 70 — Raw Capture & Replay Tool + API (2026-08-19)

**Type:** Backend replay pipeline + CLI tool + API route. No hardware changes.

**Goal.** Add a replay capability that re-loads previously-saved SigMF captures (one-shot `mimir:fingerprint` or Record-mode `mimir:fingerprint_sequence`) through the existing fingerprinting pipeline against today's `BAND_PROFILES` thresholds. No hardware touched; pure offline analysis.

**What shipped.** `core/pipeline/replay.py` (`replay_capture()` shared by both entry points), `tools/replay_capture.py` (CLI), and `POST /api/replay` route in `dashboard/server.py`. Replays a previously-saved SigMF capture through the existing fingerprinting pipeline — the same `fingerprint_spectrum()` and `SignalClassifier` code paths as live scanning, but reading from a file instead of the SDR stream. Both one-shot and Record-mode captures supported.

**Live verification.** CLI and API both live-verified: 317/317 chunks matched, 0.000 dB delta on a real PlutoSDR ADS-B Record-mode capture at 1090 MHz. The replay correctly re-fingerprinted every chunk and produced byte-identical spectral_flatness/peak_freq_hz/bandwidth_hz/occupied_bins values to the original capture, despite the 7→9D embedding-space re-seed between capture and replay (distance differences are expected; the re-seed does not affect replay correctness).

**Design notes.** Frozen files untouched (capture.py, scanner.py, features.py, fft.py, shared_state.py). The replay path is read-only; it never writes to the vectorstore or triggers any LLM call. The `REPLAY_LOCK` is a process-wide threading.Lock protecting the replay thread; the CLI and API route run as separate processes, so they can run concurrently despite the lock (this is intentional, not a bug). Max-one-shot-samples cap (50M) is generous (~380x a legitimate one-shot capture); defensible as-is.

**Test counts.** 1387 passing (962 pytest + 425 Vitest), 0 failures. Phase 70 added 41 tests (all pytest: `TestReplayCapture` with 24 tests covering CLI/API both, plus 17 tolerance-related tests for `MIN_DELTA_DB`/`MAX_DELTA_DB`/`RESULT_THRESHOLD_DB`/`TOLERANCE_DB`). Vitest unchanged at 425.

**Resolved tech debt.** None.

**New tech debt.** Five new desk-fixable rows logged in `AGENTS.md` as TD-70-1 through TD-70-5: LOW-01 (`if True:` refactor artifact), LOW-02 (SAVED_MEASUREMENT_KEYS duplicates _FINGERPRINT_METADATA_KEYS), LOW-03 (tolerance_db unvalidated), LOW-04 (NaN serialisation), LOW-05 (int(core_freq_hz) truncation), plus four ADVISORY rows (REPLAY_LOCK process-wide only, large replay runs in live scan.py, 503 fast-fail path verified clean, MAX_ONE_SHOT_SAMPLES generous, consider adding delta report).

**RF/Legal notes.** No TX surfaces; all changes are read-only file reads and replay through the existing fingerprinting pipeline. No hardware interaction, no new RF capability or legal exposure. Jurisdiction: AU/SA, ACMA, Radiocommunications Act 1992 (Cth).

---

## Phase 71 — Raw Capture & Replay UI (2026-08-19)

**Type:** Read-only listing endpoint + frontend page. No backend pipeline changes, no hardware changes.

**Goal.** Add a read-only `GET /api/captures` endpoint that lists saved SigMF captures, plus a `/replay` page with a picker and results view over the existing Phase 70 `POST /api/replay` endpoint. The new endpoint peeks at `.sigmf-meta` JSON only (never reads `.sigmf-data`). The new frontend page iterates `Object.entries(comparison.field_results)` (no hardcoded seven-field list). Every record-mode chunk cell is clickable (matched AND mismatched — twice-corrected design call).

**What shipped.** `GET /api/captures` route in `dashboard/server.py` (read-only, malformed-file-tolerant, returns a sorted list of captures with metadata summary), `useCaptures.js` and `useReplay.js` hooks (state machines mirroring `useCapture.js`), `ReplayPage.jsx` + `ReplayPage.css` (new `/replay` page with picker view and results view), React Router wiring in `dashboard/frontend/src/main.jsx`, `TestApiCaptures` class in `tests/dashboard/test_server_api.py` (8 tests covering empty/missing dir, oneshot/record mode detection, malformed-file tolerance, sort order, path-containment defence-in-depth, subdirectory exclusion), `ReplayPage.test.jsx` (14 tests covering picker states, one-shot card, record-mode grid, click-on-matched-chunk, click-on-mismatched-chunk, back-to-picker, failure mapping).

**Live verification.** Playwright gate caveat: environmental failure (Vite proxy → Flask backend not running in this session; bash permission scope didn't allow backgrounding `python3` via nohup). API contract verified by pytest (all 8 TestApiCaptures tests pass). React state transitions verified by 14 vitest tests (all pass, including the twice-corrected click-on-matched-chunk test). Live happy-path verification deferred to operator workflow.

**Design notes.** The picker iterates `Object.entries(comparison.field_results)` rather than hardcoding the seven-field list — this satisfies the "no hardcoded names" constraint except for a special case for `spectral_flatness` delta formatting (exponential scale; see TD-71-3). Every record-mode chunk cell is clickable (both matched and mismatched cells trigger replay of that chunk) — this was an explicit design call, corrected twice during planning after the initial proposal made only mismatched cells clickable. The listing endpoint is read-only and malformed-file-tolerant (it peeks at `.sigmf-meta` JSON only and gracefully handles missing or malformed files without crashing).

**Test counts.** 1387 passing (962 pytest + 425 Vitest), 0 failures. +22 vs. pre-build baseline (1365 = 954 pytest + 411 Vitest). Pytest delta: +8 from `TestApiCaptures` (8 new tests covering empty/missing dir, oneshot/record mode detection, malformed-file tolerance, sort order, path-containment defence-in-depth, subdirectory exclusion). Vitest delta: +14 from `ReplayPage.test.jsx` (picker states, one-shot card, record-mode grid, click-on-matched-chunk, click-on-mismatched-chunk, back-to-picker, failure mapping).

**Build chronology.** Phase 71 build completed in two implementation passes plus two defensive fix passes. The second implementation pass was triggered by senior-dev returning empty `task_result` four consecutive times during the build despite confirmed-correct config, diagnosed as a transient Kimi-for-Coding endpoint issue (user confirmed `kimi-for-coding/kimi-for-coding` IS the correct bare-alias per OpenCode's CLI model picker — the user was right all along, the endpoint was flaky). Defensive fix passes addressed: record-mode-with-1-chunk UI bug, formatTimestamp crash on non-string, band_resolution/file_metadata missing crash, em dashes, unused useMemo, NaN frequency.

**Resolved tech debt.** None.

**New tech debt.** Five new desk-fixable rows logged in `AGENTS.md` as TD-71-1 through TD-71-5: TD-71-1 (BACK does not abort in-flight replay, MEDIUM), TD-71-2 (validation asymmetry, LOW), TD-71-3 (spectral_flatness hardcoded, LOW), TD-71-4 (refetch dead, LOW), TD-71-5 (O(n) uncapped listing, ADVISORY).

**RF/Legal notes.** No TX surfaces; all changes are read-only file reads and React state. No hardware interaction, no new RF capability or legal exposure. Jurisdiction: AU/SA, ACMA, Radiocommunications Act 1992 (Cth).
