---
name: build
description: >
  Autonomous build cycle for Mimir. Runs plan → code → fix loop → code review →
  browser check (frontend builds) → PM audit, with no user intervention, then
  finalises and commits by itself. Capture, DSP, decoding and device changes
  are committed as hardware-pending ([hw-pending]) for Prin to check on real
  hardware later. Never pushes: Prin reviews the commits and pushes by hand.
  pm starts it when Prin asks for a task or card in plain words, or Prin runs
  it. Usage: /build "<task>" (add CHECKPOINT_MODE: ON in the task text if
  this build should advance the phase tracker when it is finalised).
argument-hint: '"<task>"'
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

Note whether the task text contains `CHECKPOINT_MODE: ON` (case-insensitive),
and apply it when the build finalises (Step 7A or 7B).

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
iterations, a required agent that cannot be invoked, a COMMIT GATE item that
fails, or a commit that `agent_guard.py` refuses. Do not work around a hard
stop. Surface it clearly.

---

## WORKFLOW

### STEP 1 — PLAN

`@plan-reviewer` runs on every `/build`, without exception.

Before calling it, establish prior session context:
1. Newest memo: `ls -t .session-memos/`, skipping `handoff-*` files. Read it.
2. Read `docs/TECH_DEBT.md` for rows touching this task's area, and
   `docs/ROADMAP.md`'s "Recently completed" and "Sequencing" sections.
3. One Hindsight `recall` (MEMORY in your agent definition).
3a. Claim or create the build's card and move it to `doing` (KANZO BOARD 4a).
4. `git status --porcelain`: note files already changed before the build.
   They are Prin's work; the build never stages them. Then
   `git diff --cached --name-only`: if anything is already staged, hard stop
   now, before any work, and tell Prin to commit or unstage it. The build's
   commit would otherwise sweep it in.
5. Orient with graft (GRAFT in your agent definition): freshness check, then
   locate the task's code and trace callers. Then read the actual source at
   the cited spans. Never plan from a summary.

Send `@plan-reviewer` your proposed approach, the "Prior session context"
block, and an explicit **`Scope confirmed: <file list>`** line naming every
file the build will touch. Wait. A ❌ BLOCKER → hard stop.

### STEP 2 — CODE

If the approved plan changes no files (`Task size: none`), skip to Step 5.

If the `Scope confirmed:` list holds only `README.md` and Markdown under
`docs/` (a docs card), run no Codex. Make the edits yourself under GOVERNANCE
RECORDS AND DOCS in your agent definition: targeted Edit calls, Write only for
a new file under `docs/`, never `docs/au-legal-reference.md`, and every
specific checked against the code or `git diff` before you write it. Then
skip to Step 5.

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
- Did Step 1 include graft orientation, or say why it was skipped?
- Frontend build: did 4b run, or is "not run" stated with the reason?
- Were docstrings and comments of changed functions updated?

Clean → Step 6. Flagged → re-enter only the affected step, once. Still
unresolved → hard stop.

### STEP 6 — HARDWARE GATE

Apply HARDWARE GATE (in COMMITS in your agent definition) to the approved plan
and the final diff. A docs-only build never triggers it. Gate hit → Step 7A.
Gate not hit → Step 7B. Say in the report which one applied and why.

### STEP 7A — FINALISE AND COMMIT AS HARDWARE-PENDING (HARDWARE GATE hit)

Do everything Step 7B says, with HARDWARE PENDING on: carry out
`/finalise-build` STEP 0 to STEP 7 with its HARDWARE PENDING rules, so the
commits carry `[hw-pending]`, the records and the memo say the build awaits
Prin's hardware check, the Hindsight retain says it is unverified on hardware,
and the card goes to `review` (KANZO BOARD 4d), not `done`. Then:
1. The report is the same as Step 7B's, with the GOVERNANCE checklist line
   listing the files changed and "hardware-pending".
2. End with HARDWARE CHECK FOR PRIN: name the HARDWARE GATE trigger that
   fired, say exactly what to check on real hardware, then give him the two
   ready-to-paste results:
   `/finalise-build "HARDWARE: PASSED rf#N"` and
   `/finalise-build "HARDWARE: FAILED rf#N <what failed>"`
   (or he can say the same in plain words). Then the commit hashes and
   `git log --oneline origin/main..main`, and: "These commits are marked
   [hw-pending]. Push them by hand after your hardware check:
   `git push origin <branch>`."

### STEP 7B — FINALISE AND COMMIT (HARDWARE GATE not hit)

1. Read `.claude/skills/finalise-build/SKILL.md` and carry out its FINALISE
   mode, STEP 0 to STEP 7, yourself, in this run. Write the one-line summary from the approved
   plan. CHECKPOINT is ON only if the task text carried it. The build's files
   are the `Scope confirmed:` list. Its Step 1 (both suites, live) is the
   final test run, so do not run a separate one first.
2. Its COMMIT step applies the COMMIT GATE (in COMMITS in your agent
   definition). Any item failing is a hard stop: report it, leave the changes
   uncommitted (unstage only what the build staged) and leave the card in
   `doing`.
3. The report is `/finalise-build`'s Step 7 plus what Step 7A lists that it
   does not: what was built, fix-loop summary, models, code-review findings,
   browser check, PM audit, graft and memory lines. The GOVERNANCE checklist
   line lists the files changed instead of "not touched".
4. End with the commit hashes and `git log --oneline origin/main..main`, then:
   "Review the log above, then push by hand: `git push origin <branch>`."
   No hardware check is asked for, because the gate was not hit.

Never push in `/build`.
