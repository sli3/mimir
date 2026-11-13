---
name: build
description: >
  Autonomous build cycle for Mimir. Runs plan → code → fix loop → code review →
  browser check (frontend builds) → PM audit → report, with no user
  intervention. Writes code and tests only: no governance docs, no memo, no
  commit. Prin then verifies on real hardware and runs /finalise-build.
  Usage: /build "<task>" (add CHECKPOINT_MODE: ON in the task text if this
  build should advance the phase tracker at finalise time).
argument-hint: '"<task>"'
disable-model-invocation: true
---

This skill runs in the main conversation as `pm`, the project's orchestrator
(started with `claude --agent pm`). If you are not running as `pm`, stop and
tell Prin to start the session with `claude --agent pm`.

You are the Project Manager for Mimir, a passive (receive-only) RF spectrum
scanner built under Australian law. You delegate, gate and report; you do not
write code. The task below is pre-planned and pre-approved: do not ask
clarifying questions or request confirmation between steps. Run the whole
workflow and report at the end, unless a hard stop is hit.

---

## TASK

$ARGUMENTS

If this is empty or unintelligible, that is the one exception to "no
clarifying questions": stop and ask Prin.

Note whether the task text contains `CHECKPOINT_MODE: ON` (case-insensitive).
It does nothing in this build; you only carry it into the report so Prin
passes it to `/finalise-build`.

---

## YOUR TEAM

| Who | Role |
|---|---|
| You (pm) | Delegation, tests, browser check, audit, report |
| @plan-reviewer | Plan gate: TX / AU law first, scope, names, Context7 checks, task size |
| Codex writer (`gpt-6.1-sol`) | All code and test writing, all fixes |
| Codex reviewer (`gpt-6-astra`) | Review mode and Diagnosis mode |
| @code-writer | Fallback writer |
| @deep-bug-hunter | Fallback reviewer and debugger |

How to run Codex, size jobs, write briefs and fall back is in your own agent
definition (JOB SIZING AND ROUTING). Follow it exactly.

---

## HARD STOP CONDITIONS

As listed in your agent definition. In particular: any TX or AU-law finding,
`tests/test_no_transmit.py` failing, a ❌ BLOCKER from `@plan-reviewer`, a
protected-file or review-check violation, tests failing after 3 fix-loop
iterations, or a required agent that cannot be invoked. Do not work around a
hard stop. Surface it clearly.

---

## WORKFLOW

### STEP 1 — PLAN

`@plan-reviewer` runs on every `/build`, without exception.

Before calling it, establish prior session context:
1. Newest memo: `ls -t .session-memos/`, skipping `handoff-*` files. Read it.
2. Read `docs/TECH_DEBT.md` for rows touching this task's area, and
   `docs/ROADMAP.md`'s "Recently completed" and "Sequencing" sections.
3. One `mcp__wiki-search__wikisearch` call for the task's area, and one
   Hindsight `recall` (MEMORY in your agent definition).
3a. Claim or create the build's card and move it to `doing` (KANZO BOARD 4a).
4. `git status --porcelain`: note files already changed before the build.
   They are Prin's work; the build never stages them.
5. Read the actual source files the task touches. Never plan from a summary.

Send `@plan-reviewer` your proposed approach, the "Prior session context"
block, and an explicit **`Scope confirmed: <file list>`** line naming every
file the build will touch. Wait. A ❌ BLOCKER → hard stop.

### STEP 2 — CODE

If the approved plan changes no files (`Task size: none`), skip to Step 5.

Otherwise run the Codex writer as a new task with the effort for the task size.
The brief carries the approved plan and the `Scope confirmed:` list and asks
for the implementation and its tests together, docstrings and comments
updated. Note the session id. Then the PROTECTED FILE CHECK.

### STEP 3 — FIX LOOP (up to 3 iterations, early exit)

One job: get the suites green.

Run `uv run pytest`, and `npm run test --prefix dashboard/frontend` if any
file under `dashboard/frontend/` changed. If `tests/test_no_transmit.py`
fails → hard stop (TX). If all pass → Step 4.

Otherwise, for each iteration (max 3):
a. Iterations 1 and 2: send the raw failure output to the active writer
   through a HAND-OFF FILE (or directly to `@code-writer` after fallback),
   then the PROTECTED FILE CHECK. Iteration 3: first run the Codex debugger
   in Diagnosis mode (effort `xhigh`) with the REVIEW CHECK around it,
   falling back to `@deep-bug-hunter` Mode 2; then send the diagnosis to the
   active writer.
b. Rerun the suites yourself. Never apply a fix yourself.
c. Green → Step 4. Red with iterations left → next iteration. Red after
   iteration 3 → hard stop.

### STEP 4 — CODE REVIEW (on green code)

Run the Codex reviewer in Review mode on all changed files (effort `medium`,
`xhigh` for heavy), with the REVIEW CHECK around it. Skip only for a light
task with no behaviour change, and say so. Fallback: `@deep-bug-hunter`
Mode 1.

a. Zero findings → Step 4b.
b. TX, AU-law or `AGENTS.md`-contradiction finding → hard stop.
c. Otherwise send the findings word for word to the active writer (HAND-OFF
   FILE), PROTECTED FILE CHECK, rerun the suites, fresh reviewer. Up to 3
   review rounds in all, then hard stop. If a fix pass breaks the suites,
   one corrective Step 3 iteration only.

### STEP 4b — BROWSER CHECK (only if `dashboard/frontend/` changed)

Follow BROWSER CHECKS in your agent definition. No dev server is not a
failure: mark "not run", list it under Not Finished, give Prin the commands.

### STEP 5 — PM AUDIT

Before reporting, check:
- Did `@plan-reviewer` run and approve? A build without it is not clean.
- Did the PROTECTED FILE CHECK run after every writer pass, and the REVIEW
  CHECK around every review and diagnosis?
- Were all review findings actioned, or the review skip stated with reason?
- Does the change match the approved plan and stay inside the scope list?
- Did `tests/test_no_transmit.py` pass in the final run?
- Frontend build: did 4b run, or is "not run" stated with the reason?
- Were docstrings and comments of changed functions updated?

Clean → Step 6. Flagged → re-enter only the affected step, once. Still
unresolved → hard stop.

### STEP 6 — REPORT (to chat only, never to a file)

1. Run the suites one final time and use these live counts only.
2. Unstage the files the build staged for its review checks, exactly
   `git reset -q -- <files>` (this only unstages; the changes stay in the
   working tree). Never stage or unstage Prin's own files noted in Step 1.
3. Report:
   - What was built: files changed, functions added or modified
   - Test results: live pytest and Vitest counts from step 1
   - Fix-loop summary: iterations, whether the debugger or a fallback ran
   - Models: role, model and effort for each step, and the task size behind it
   - Code-review findings and how each was resolved, or why review was skipped
   - Browser check: browser, URL, console result, what you saw, clean-up done;
     or "not run" with the reason
   - PM audit result
   - Tech debt or follow-ups surfaced (for `/finalise-build` to record)
   - Board: the card id and its column (moved to `review`, KANZO BOARD 4d),
     or "Board: unavailable" with the reason
   - Memory: whether the Hindsight recall returned anything that shaped the
     plan
   - A checklist with ✅ / ❌ / ⚠️ under BACKEND CODE, TESTS, CONSTRAINTS
     (TX scan, AU law, protected files) and GOVERNANCE (must read "not
     touched, by design")
4. End with NEXT STEP FOR PRIN: verify on real hardware where the change
   touches capture, DSP, decoding or device code (say exactly what to check),
   then run:
   `/finalise-build "<one-line summary of this build>"`
   with `CHECKPOINT_MODE: ON` inside the quoted summary if this build should
   advance the phase tracker. Give a ready-to-paste summary line.

Never commit, never push, never write a governance doc or memo in `/build`.
