---
name: finalise-build
description: >
  Post-build finalisation for Mimir. Run AFTER a /build has finished AND Prin
  has verified it on real hardware and is done touching the code. Re-runs both
  test suites live, records tech debt, the roadmap entry (only with
  CHECKPOINT_MODE: ON) and the README summary lines against the real diff,
  verifies its own prose against disk, writes the session memo, and ends with a
  commit hand-off. Never writes code, never commits.
  Usage: /finalise-build "<one-line summary>" (put CHECKPOINT_MODE: ON inside
  the quoted summary to advance the phase tracker).
argument-hint: '"<one-line summary>"'
disable-model-invocation: true
---

This skill runs in the main conversation as `pm` (started with
`claude --agent pm`). If you are not running as `pm`, stop and tell Prin.

Documentation runs only against a frozen, verified tree. Governance prose
written against a moving tree is where this project's fabrication incidents
happened, so this step is deliberately separate from `/build`.

You write governance records yourself, under the GOVERNANCE RECORDS and
SESSION MEMO rules in your agent definition. No subagent and no Codex run is
needed here. If you find yourself wanting to change code, you are in the wrong
skill: stop and tell Prin.

---

## TASK

$ARGUMENTS

The summary is a POINTER to which files and functions to look at, never the
source of truth: `git diff` is. If it is empty or unintelligible, stop and ask.

CHECKPOINT is ON only if the text above contains `CHECKPOINT_MODE: ON`
(case-insensitive). Otherwise it is OFF. Never infer it from the work.

---

## HARD STOP CONDITIONS

- Either test suite is red (Step 1). Write nothing.
- Any TX or AU-law concern in the diff.
- Governance prose you cannot verify against the diff (Step 4).
- A protected file (`AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/`, `data/`,
  `core/legal/compliance_guard.py`, `tests/test_no_transmit.py`) appears in
  the diff and Prin has not said he changed it himself.

---

## WORKFLOW

### STEP 1 — RE-VERIFY THE HARD TRUTH

Run both suites and read the counts off the real output:
- `uv run pytest`
- `npm run test --prefix dashboard/frontend`

Record pytest passing, Vitest passing and their sum. These are the only test
numbers that may reach any document. Either suite red → hard stop. If the live
total differs from what Prin or the `/build` report expected, the live count
wins; note the difference in the report.

### STEP 2 — GROUND-TRUTH DIFF

Run `git --no-pager status`, `git --no-pager diff --stat`,
`git --no-pager diff`, and `git --no-pager log --oneline -5`. Note the
changed files and the specifics (function names, constants, flags). This is
your reference for every word you write.

### STEP 3 — RECORDS

Following GOVERNANCE RECORDS in your agent definition:
1. `docs/TECH_DEBT.md`: add rows for debt the build surfaced; archive rows the
   diff verifiably fixed (archive first, delete second). Grep every
   identifier before you write it.
2. If CHECKPOINT is ON: add the phase entry to `docs/ROADMAP.md`. Ask Prin
   for the phase number only if the summary does not give one.
3. `README.md`: sync the two Phase Tracker summary lines to the newest
   ROADMAP entry and the Step 1 counts. Nothing else.
4. Test counts anywhere: the three numbers from Step 1, verbatim, nothing
   derived from them.
5. If `AGENTS.md` looks out of date (for example a Key Files row), do not edit
   it: give Prin the exact change in the report.

### STEP 4 — VERIFY YOUR OWN PROSE (mandatory)

1. `git --no-pager diff -- docs/ROADMAP.md docs/TECH_DEBT.md README.md` and
   read every line you added.
2. Cross-check each specific (names, constants, flags, filenames, counts)
   against the Step 2 diff and Step 1 counts. Grep anything not already in
   front of you.
3. Check for: absence claims; rationale Prin did not give as text; derived
   arithmetic; anything not in the diff. Fix your own wording with targeted
   Edits.
4. State the result: "Governance edits verified against disk" or the list of
   anything you could not verify and removed.

### STEP 5 — SESSION MEMO

Write the memo per SESSION MEMO in your agent definition. Confirm the path.

### STEP 6 — REPORT (to chat only)

- Verified counts (pytest / Vitest / total), and any mismatch
- Each governance file changed, one line each, plus the diff
- Whether the phase tracker moved, and that CHECKPOINT was ON or OFF
- The memo path
- The Step 4 verification result
- Any `AGENTS.md` change Prin should make by hand
- Tech debt or follow-ups

End with a **COMMIT HANDOFF** built from this run's facts:
- **Code:** is there already a commit for this build's code (Step 2 log)? If
  not, list the code and test files for a separate `feat:` / `fix:` / `test:`
  commit first.
- **Governance:** the exact files from Step 3 that changed.
- **Never staged:** `.session-memos/` (name this run's memo).
- **Suggested messages:** one per commit, category prefix, British English.
- **Next:** tell Prin to ask you to commit (you will use `git-workflow`, which
  runs the TX grep and waits for his OK), or to commit by hand.

Never commit, push or stage anything in this skill.
