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

## Recently completed

### Phase 76 — Demo Mode (--demo flag) for scan.py ✅

**Goal:** Let operators run the full, genuinely live, interactive Mimir dashboard against a looping replayed SigMF capture with no SDR hardware attached and no live network dependency on the yubaba LLM server (cached responses instead). Built for SDR Conference 2026 (Flinders University, Adelaide, 29 Sep–2 Oct) so the operator can take real questions from the audience and click through the dashboard interactively, instead of playing back pre-recorded video.

**Delivered:**
- `core/pipeline/demo_producer.py` (new) — DemoProducer daemon thread; reads SigMF chunks via `_load_sigmf`/`_validate_sequence` from the existing replay tooling, runs them through `core/pipeline/fingerprint.py:fingerprint_from_psd` (newly extracted so PSD is computed once, not twice), paces itself via `DEMO_CHUNK_INTERVAL_SEC = 0.05s` independent of `config.dwell_time_sec`, and pushes onto the same queue `_ai_loop` consumes in `ScanRunner`.
- `core/pipeline/fingerprint.py` (new) — `fingerprint_from_psd()`, extracted from `core/pipeline/replay.py` so both the live `core/pipeline/scanner.py` path and the demo `DemoProducer` path share one PSD-then-fingerprint implementation.
- `llm/demo_classifier.py` (new) — DemoSignalClassifier subclasses the real SignalClassifier (Option A: subclass/wrap, NOT a flag on the production class — deliberate to keep demo-only logic fully out of the production LLM path) and serves pre-generated cached responses instead of a live HTTP call to yubaba.
- `tools/generate_demo_cache.py` (new) — one-time cache-generation tool; run once with a live yubaba connection against a chosen SigMF file to produce the JSON cache that DemoSignalClassifier reads at demo runtime.
- `core/pipeline/scanner.py` — `ScanRunner.__init__` gains `is_demo_device: bool = False` (default zero behaviour change for live mode); `set_focus_frequency()` skips its queue drain when `is_demo_device=True` (the drain semantics are correct for live hardware retuning but wrong for demo mode where there is no real device to invalidate against).
- `scan.py` — new `--demo` and `--demo-files` CLI flags; bypasses `build_device`, `device.open`, and the Pluto startup-focus check; does NOT start the ACARS/AIS/ADS-B raw-IQ decoder subscribers (deliberate scope boundary — see "Decode-path scope" below).
- `dashboard/frontend/src/utils/frequency.js` (new) — tolerance-based `freqMatches(a, b, toleranceHz)` and `findCanonicalValue(freq, canonicalMap)` helpers; `FREQ_TOLERANCE_HZ = 100_000`. Applied at six frontend sites where a strict-equality `===` between emitted and canonical frequencies was silently failing.
- `core/pipeline/frequency.py` (new) — backend twin of `frequency.js`; `FOCUS_FREQ_TOLERANCE_HZ = 100_000` (deliberately named differently from the three pre-existing `FREQ_TOLERANCE_HZ` constants in `modules/adsb/constants.py` (2 MHz), `modules/ais/constants.py` (100 kHz — the identical-value trap), and `modules/acars/constants.py` (5 kHz) to avoid import collision). `freq_matches()` helper applied inside `dashboard/server.py:broadcast()`.

**FIVE live-verified bugs found after the initial build, all missed by the 1022+ passing tests.** This is a real, recent example of the project's standing "green tests are necessary but not sufficient" principle:
1. Double PSD computation + zero-value `dwell_time_sec` pacing → extracted `fingerprint_from_psd`, added `DEMO_CHUNK_INTERVAL_SEC`.
2. Live-mode focus-change flushed the demo's queue on every socket reconnect → `is_demo_device` skip-queue-drain flag.
3. WaterfallPanel opened a second competing socket connection → added `skipInitialRetune: true` mirroring RadarPage.jsx's existing read-only-consumer pattern.
4. Strict-equality `===` on real captured frequency vs rounded canonical band constant, six frontend sites → `frequency.js` tolerance helper applied at all six sites.
5. Backend `broadcast()` ALSO used strict equality, one line, one file → `frequency.py` `freq_matches()` helper + `FOCUS_FREQ_TOLERANCE_HZ` constant + cross-language contract test pinning Python to JS.

**Decode-path scope boundary (by design):** RAW DECODE and FRAME INSPECTOR panels correctly remain empty in demo mode (and the `/radar` page is not affected). These need RAW IQ SAMPLES, which the fingerprint-only demo producer does not provide. A future phase would need a genuinely different producer feeding AdsbSubscriber. NOT currently scoped or scheduled — see TD-76-7. (RESOLVED 2026-09-03: commit `4edbb108` added `AdsbDemoProducer` (`core/pipeline/adsb_demo_producer.py`), a raw-IQ producer feeding `AdsbSubscriber`, wired into `scan.py`'s `--demo` branch via the new optional `--demo-files-adsb` flag. See the closed TD-76-7 row in AGENTS.md.)

**Test counts:** 1515 total passing (1042 pytest + 473 Vitest), 0 failures. pytest delta = +69 (new test files `tests/core/test_demo_producer.py`, `tests/core/test_frequency.py`, plus `tests/dashboard/test_server_emit.py` updates for the Fix 5 broadcast-filter contract).

**Commits:** `fda66cb` (initial demo mode + Fixes 1-4) and `4e05c57` (Fix 5: backend broadcast tolerance).

**Test counts ground-truth statement:** Every figure in this entry was verified in the finalise-build session that wrote it. pytest was run via `uv run pytest` and Vitest via `npx vitest run` from `dashboard/frontend/`. The two source commits are on `main`; `git status` shows the only working-tree changes are docstring polish in `core/pipeline/demo_producer.py` and `dashboard/frontend/src/utils/frequency.js` (no behaviour change).

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

---

## Phase 72 — Fix ADS-B burst-detection self-cancellation and one-shot trace_key omission (2026-08-20)

**Type:** Code-only bugfix. No frontend changes, no hardware changes.

**Goal.** Fix two bugs in the ADS-B burst-detection path: (1) `fingerprint_spectrum()`'s burst comparator aliased both operands when `trace_key='psd_max_hold_db'`, making `is_burst` permanently unreachable for ADS-B; (2) `capture_and_save()` never resolved `trace_key` at all, silently defaulting to `'psd_db'` for every band including ADS-B.

**What shipped.** `core/pipeline/features.py` burst-detection block rewritten with `true_avg_db = psd_result.get("psd_db", psd_db)` sourced independently of `trace_key` (used by both wide-window sum and single-bin comparator paths). New BUGFIX comment block at lines 233–243 documents the root cause. `core/pipeline/capture.py` `capture_and_save()` now forwards `trace_key=profile.get("fingerprint_trace_key", "psd_db")` to `fingerprint_spectrum()`. Comment at lines 594–600 updated to include `trace_key='psd_db'` in the list of fallback defaults. Docstring at the `band:` parameter (lines 528–531) updated to enumerate `fingerprint_trace_key` alongside the other three per-band parameters. Three new regression tests: `test_burst_ratio_db_distinct_traces_with_max_hold_trace_key` (features.py, primary guard for Bug 1), `test_burst_ratio_db_identical_traces_returns_zero` (proves the fix distinguishes "genuinely no burst" from "comparator broken"), and `test_valid_adsb_band_passes_trace_key_max_hold` (capture.py, regression guard for Bug 2). Extended `test_valid_band_produces_fingerprint_and_passes_to_save_capture` to assert `trace_key` kwarg forwarding for `fm_broadcast`.

**Live verification.** Live-verified against two independent ADS-B captures (332 and 474 chunks) at 1090 MHz using PlutoSDR. Previous replays showed `burst_excess_db` flat at -6.75 dB across all chunks; post-fix replays show real per-chunk variation (-2.6 to 11.3 dB), with `is_burst` correctly firing on 13-25% of chunks depending on capture strength. `burst_excess_db` ceiling agrees within 0.1 dB across both captures (11.17 and 11.27 dB). No TX-capable code introduced.

**Design notes.** The burst-detection fix intentionally leaves the function-local `psd_db` (bound to `psd_result[trace_key]` at the function top) unchanged elsewhere in the function — peak search, noise floor, SNR, bandwidth, occupied bins, and spectral flatness all correctly use the trace_key-selected trace. The `capture_and_save()` fix mirrors the existing pattern in `scanner.py` and `replay.py` (both already forward `trace_key` to `fingerprint_spectrum()`). Bug 2 severity is LOW because `capture_and_save()` has zero live call sites today (verified via `grep -rn "capture_and_save(" .` excluding tests/binaries).

**Test counts.** 1398 passing (972 pytest + 426 Vitest), 0 failures. 972 pytest = 969 baseline + 3 new tests this phase. 426 Vitest = unchanged from Phase 71 (no frontend touched).

**Build chronology.** Single-pass implementation. No defensive fixes required.

**Resolved tech debt.** Updated AGENTS.md Known Tech Debt row for `[PEAK]` burst-detection metric to mark fault (3) as RESOLVED by Phase 72, and to flag faults (1)-(2) as stale relative to the current implementation (Phase 45's single-chunk comparator replaced the old per-bin max-hold comparator).

**New tech debt.** None.

**RF/Legal notes.** No TX surfaces; all changes are read-only spectrum analysis and metadata plumbing. No hardware interaction, no new RF capability or legal exposure. Jurisdiction: AU/SA, ACMA, Radiocommunications Act 1992 (Cth).

---

## Phase 73 — Replay burst fade UI overlay (frontend-only) (2026-08-20)

**Type:** Frontend-only. No backend changes, no hardware changes.

**Goal.** Surface the post-Phase-72 burst-detection data visually in `/replay`. Phase 72 fixed the backend burst detection so `is_burst` actually fires; Phase 73 surfaces that data visually in the replay results view.

**What shipped.** Three new helper functions in `ReplayPage.jsx`: `burstIntensity()` (calibrated to BURST_MARGIN_DB=6.0, MAX_OBSERVED_EXCESS_DB=11.27 from Phase 72's two ADS-B captures), `interpolateBurstColour()` (smooth sRGB lerp green→amber), `burstRingStyle()`. Matched chunks fade green→amber as burst intensity rises. Mismatched chunks keep solid red background and gain an amber box-shadow ring. One-shot cards get an amber burst badge gated on `is_burst`, showing "BURST XdB" or "BURST ---dB" fallback when burst_excess_db is NaN. Data source: `chunk.replayed_fingerprint.is_burst` / `burst_excess_db` (already populated by `core/pipeline/replay.py:_fingerprint_samples()` post-Phase 72). CSS: new `.replay-burst-badge` rule using `color-mix(in srgb, var(--neon-amber) 15%, transparent)` — the codebase's first color-mix() use. Tests: 13 new Vitest tests in `ReplayPage.test.jsx` (burst helpers, RecordResult grid, OneShotResult badge, NaN handling), new paired-constant contract test `tests/dashboard/test_replay_burst_thresholds.py` (mirrors the HIGH_TURN_RATE pattern in `test_path_reasoner_thresholds.py`).

**Live verification.** No hardware required. Existing 15 ReplayPage tests all pass unchanged. Zero backend files touched; no TX-capable code introduced.

**Design notes.** The 11.27 dB MAX_OBSERVED_EXCESS_DB is an empirical ceiling from Phase 72's two ADS-B captures (332 and 474 chunks), agreeing within 0.1 dB across both captures. The lerp is pure sRGB (no HSL conversion) for speed; this is acceptable because we're interpolating between two fixed cyberpunk theme colours, not arbitrary hue shifts. The mismatched solid red is deliberate (high-contrast alert), but the amber ring provides burst awareness without losing the mismatched signal. One-shot badge is gated on `is_burst` rather than burst_excess_db > 0 to respect the backend's boolean verdict; the "---dB" fallback handles the NaN case for non-bursting captures. The paired-constant contract test mirrors the existing `test_path_reasoner_thresholds.py` pattern and validates that BURST_MARGIN_DB in `core/pipeline/features.py` and MAX_OBSERVED_EXCESS_DB in `ReplayPage.jsx` stay in sync across future phases.

**Test counts.** 1412 passing (973 pytest + 439 Vitest), 0 failures. Vitest +13 (12 first-pass tests + 1 mid-intensity interpolation test). Pytest +1 (paired-constant contract test).

**Resolved tech debt.** None.

**New tech debt.** Two new desk-fixable rows logged in `AGENTS.md` as TD-73-1 and TD-73-2: (1) a11y on chunk cell title — burst intensity is colour-only (green→amber fades are deuteranopia-inaccessible). (2) Live visual check of the burst badge (color-mix) at the next dashboard serve — jsdom doesn't load stylesheets so Vitest can't verify badge rendering; operator should confirm in a real browser after the next `npm run build`.

**RF/Legal notes.** No TX surfaces; all changes are pure frontend styling and state management. No hardware interaction, no new RF capability or legal exposure. Jurisdiction: AU/SA, ACMA, Radiocommunications Act 1992 (Cth).

---

## Phase 74 — Replay burst analysis panel (frontend-only) (2026-08-20)

**Type:** Frontend-only. No backend changes, no hardware changes.

**Goal.** Extend the Phase 73 burst fade overlay with three new `/replay` UI features: (1) small dim `[SAVED]` and `[REPLAYED]` labels on the seven-field comparison row, (2) a `burst_excess_db` row showing the dB excess value with a BURST badge or threshold note, and (3) a collapsible burst analysis panel with statistics, timeline strip, and legend.

**What shipped.** Three pure-frontend changes: (1) `FieldRow.jsx` label augmentation — small dim `[SAVED]` and `[REPLAYED]` labels added to the seven-field comparison row in both OneShotResult and RecordResult's chunk-detail panel via the shared `FieldRow` component (one component change, two callers). (2) `burst_excess_db` row — new row after the seven compared fields (Record-mode only), shows `burst_excess_db` formatted as "XdB" with a `[REPLAYED]` label (no `[SAVED]` — field was never in the saved set). When `is_burst === true`, appends the existing amber `.replay-burst-badge` "BURST" pill (reused from Phase 73). When `is_burst === false`, appends a dim note reading "below {BURST_MARGIN_DB.toFixed(1)} dB threshold" — interpolated from the existing constant at ReplayPage.jsx:47, NOT a hardcoded "6.0" (locked by the contract test `tests/dashboard/test_replay_burst_thresholds.py`). (3) Collapsible burst analysis panel — positioned between `.replay-summary-line` and `.replay-chunk-grid`, expanded by default via local `useState(true)`. Contains 4 computed statistics (burst count + rate, burst range, strongest burst, full range) computed once via `useMemo` on `chunks` array, clickable timeline strip (one button per chunk) sharing the existing `setSelectedIndex(idx)` state with the main chunk grid (NOT a separate state), and 4-swatch legend (matched-no-burst green, matched-burst amber, mismatch red, mismatch-burst red+amber ring). Colours via CSS variables and the same `interpolateBurstColour()`/`burstRingStyle()` helpers from Phase 73 (NOT hardcoded hex). Helpers reused: `burstIntensity()`, `interpolateBurstColour()`, `burstRingStyle()` from Phase 73.

**Live verification.** No hardware required. Existing ReplayPage tests all pass unchanged. Zero backend files touched; no TX-capable code introduced.

**Design notes.** The timeline strip deliberately shares the existing `setSelectedIndex(idx)` state with the main chunk grid — clicking a timeline chunk behaves identically to clicking the corresponding grid cell, avoiding duplicate state and keeping selection logic in one place. The panel is collapsed by state (`useState(true)`) rather than by CSS, so the collapsed/expanded choice is React-managed and can be persisted to localStorage in a future phase if desired. The 4-swatch legend uses the same `interpolateBurstColour()`/`burstRingStyle()` helpers from Phase 73, not hardcoded hex, so any future theme colour changes automatically propagate to the legend. The threshold note interpolates from the BURST_MARGIN_DB constant at ReplayPage.jsx:47 rather than hardcoding "6.0" — this is enforced by the existing contract test `tests/dashboard/test_replay_burst_thresholds.py` which validates that BURST_MARGIN_DB in `core/pipeline/features.py` and the constant used in ReplayPage.jsx stay in sync.

**Test counts.** 1424 passing (973 pytest + 451 Vitest), 0 failures. Vitest +12 (11 initial tests + 1 review-fix regression test). Pytest unchanged at 973.

**Review fixes.** Frontend-reviewer caught a real bug where `fullMin`/`fullMax` would remain `Infinity`/`-Infinity` if all chunks had non-finite `burst_excess_db`, causing `Infinity.toFixed()` to either crash or render literal "Infinity" text. Fixed by returning `null` and adding a `hasAnyFiniteBurst` flag. Plus 1 regression test (`test_timeline_statistics_handles_all_non_finite_burst_values`). Plan-reviewer verified that `useMemo` import was added, that helper sharing was correct, and that the legend 4 swatches were enumerated as designed.

**Resolved tech debt.** None.

**New tech debt.** Two new desk-fixable rows logged in `AGENTS.md` as TD-74-1 and TD-74-2: (1) Timeline aria-label gap — advisory for future a11y polish. (2) ReplayPage.jsx file-size trend — advisory noting that the file is growing with each phase (171 lines added this phase, 108 lines of CSS).

**Deferred items.** Step 6B live-browser check deferred per TD-73-2 environmental precedent (Flask can't be backgrounded, Vite proxy can't reach backend). The `.replay-burst-badge` rule uses `color-mix(in srgb, var(--neon-amber) 15%, transparent)` — the codebase's first color-mix() use. Feature itself IS verified via manual live-dashboard check this session; only the automated Step 6B reproducibility is deferred.

**RF/Legal notes.** No TX surfaces; all changes are pure frontend styling and state management. No hardware interaction, no new RF capability or legal exposure. Jurisdiction: AU/SA, ACMA, Radiocommunications Act 1992 (Cth).

---

## Phase 75 — Replay stats visual card layout (frontend-only) (2026-08-20)

**Type:** Frontend-only. No backend changes, no hardware changes.

**Goal.** Visual-only follow-up to Phase 74. Remove the timeline strip (visual gap at real capture sizes) and restyle the stats panel from compact single-line text into a 4-column grid of cards.

**What shipped.** Two pure-frontend changes: (1) Timeline strip removal — the `.replay-burst-timeline` JSX block (flex-row of per-chunk buttons) deleted from `ReplayPage.jsx`, CSS rules `.replay-burst-timeline`, `.replay-burst-timeline-seg`, `.replay-burst-timeline-seg:hover` deleted from `ReplayPage.css`, two timeline-specific tests deleted from `ReplayPage.test.jsx`, comments cleaned up (timeline references removed). Rationale: at real capture sizes (332-474+ chunks), the timeline rendered as hundreds of near-invisible slivers directly above the chunk grid, which already provides the same colour-coded view, click-to-select, and chunk numbering. Confirmed via live screenshot comparison. (2) Stats panel card restyle — the four stats (bursts detected, burst excess range, strongest burst, full range) restructured from compact single-line text into a 4-column grid of cards. Each card has a label div (small, dim, uppercase, letter-spaced via `.replay-burst-stat-label`) and a value div (larger body text via `.replay-burst-stat-value`). Full-range card has `replay-burst-stat-card-secondary` modifier class + inline `color: var(--text-dim)` style — visually secondary/muted per Phase 74's design intent. 1 new structural test added to verify the card layout. 1 assertion updated to match the new layout (line 887: `'Full range: —'` → `'—'`).

**Live verification.** No hardware required. Existing ReplayPage tests all pass (except the two timeline tests removed, as expected). Zero backend files touched; no TX-capable code introduced. Manual screenshot comparison confirmed the visual gap rationale (hundreds of near-invisible slivers at real capture sizes).

**Design notes.** The 4-column grid is desktop-only via `@media (max-width: 768px)` break to 2-column, preserving mobile layout. The `burstStats` useMemo block (lines 277-323 of ReplayPage.jsx) is byte-identical to Phase 74 — only the rendering path changed. Phase 73 helpers (`burstIntensity()`, `interpolateBurstColour()`, `burstRingStyle()`) remain present and are used by the chunk grid. OneShotResult is untouched. Full-range secondary styling matches Phase 74's intent (dimmer visual weight because it's a span across all bursts, not a per-burst metric).

**Test counts.** 1423 passing (973 pytest + 450 Vitest), 0 failures. Vitest net -1: 2 timeline tests removed + 1 structural card test added + 1 assertion updated. Pytest unchanged at 973.

**Resolved tech debt.** TD-74-1 (Timeline aria-label gap) is now moot because the timeline strip was removed entirely. Closed as RESOLVED in AGENTS.md.

**Updated tech debt.** TD-74-2 wording updated to reflect that the timeline is now removed (reducing ReplayPage.jsx's growth from ~800 to ~950 lines across Phases 74-75) and that legend and statistics remain in the same file.

**Deferred items.** Step 6B env deferral unchanged from Phase 73/74 — bash scope doesn't allow backgrounding Flask for Vite proxy, so automated Playwright checks cannot run reproducibly in build sessions. Live visual verification is done via manual dashboard checks.

**RF/Legal notes.** No TX surfaces; all changes are pure frontend styling and JSX structure changes. No hardware interaction, no new RF capability or legal exposure. Jurisdiction: AU/SA, ACMA, Radiocommunications Act 1992 (Cth).

---
