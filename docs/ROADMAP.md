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
