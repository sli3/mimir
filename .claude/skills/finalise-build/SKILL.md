---
name: finalise-build
description: >
  Post-build finalisation for Mimir. Run AFTER a /build has stopped at its
  HARDWARE GATE AND Prin has verified it on real hardware and is done touching
  the code. (A /build that does not hit the gate runs these steps itself.)
  Re-runs both test suites live, records tech debt, the roadmap entry (only
  with CHECKPOINT_MODE: ON) and the README summary lines against the real diff,
  verifies its own prose against disk, writes the session memo, then commits
  the code and the governance records through git-workflow. Never writes
  code, never pushes.
  Usage: /finalise-build "<one-line summary>" (put CHECKPOINT_MODE: ON inside
  the quoted summary to advance the phase tracker).
argument-hint: '"<one-line summary>"'
disable-model-invocation: true
---

This skill runs in the main conversation as `pm` (started with
`claude --agent pm`). If you are not running as `pm`, stop and tell Prin.

Documentation runs only against a frozen, verified tree. Governance prose
written against a moving tree is where this project's fabrication incidents
happened, so this step is deliberately separate from the coding steps of
`/build`. A `/build` that does not hit its HARDWARE GATE runs this workflow
itself once its code is frozen.

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
  the diff and Prin has not said he changed it himself. Never commit it.
- Any COMMIT GATE item fails (Step 6), or `agent_guard.py` refuses a commit.

---

## WORKFLOW

### STEP 0 — CONTEXT

One Hindsight `recall` for this change (MEMORY in your agent definition), and
find the build's card on the board (in `review` after a hardware stop, in
`doing` when `/build` finalises itself).

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
3. `README.md`: always set the `**Total: ...**` line to the Step 1 counts,
   CHECKPOINT or not. Change the `**Current phase: ...**` line only when
   CHECKPOINT is ON. Nothing else in this step: edits that a docs card called
   for were made in `/build` Step 2 and are already in the diff.
4. Test counts anywhere: the three numbers from Step 1, verbatim, nothing
   derived from them.
5. If `AGENTS.md` looks out of date (for example a Key Files row), do not edit
   it: give Prin the exact change in the report.

### STEP 4 — VERIFY YOUR OWN PROSE (mandatory)

1. `git --no-pager diff -- README.md docs/` and read every line added, yours
   and any a docs card made.
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
Then one Hindsight `retain` digest (MEMORY in your agent definition), and a
one-line comment on the card with the verified test total and memo name
(KANZO BOARD 4e).

### STEP 5b — VAULT NOTE

Load the vault-keeper skill and write a session note for this build to
`Projects/Mimir/Sessions/` in the vault. Link to repo files by path; do not
copy memo or AGENTS.md content.

### STEP 6 — COMMIT (through git-workflow)

COMMITS in your agent definition decides this step, and its COMMIT GATE must
hold: both suites green in Step 1 including `tests/test_no_transmit.py`, the
reviewer's approval (or the stated skip), a clean protected-file check, and a
clean TX check on the staged diff.
1. Decide the build's files: the `Scope confirmed:` list from the `/build`
   report if it is in this conversation, otherwise the files the summary names
   and the tests for them. Compare with `git status --porcelain`. Stage only
   files you can tie to this build. Leave every other changed file alone and
   list it in the report. If you cannot tell whether a changed file belongs,
   or a file in the build's list was already modified before the build
   started (`/build` Step 1 notes these), hard stop rather than guess: a
   commit would sweep Prin's own changes in.
2. Code commit first, if this build's code is not committed yet (Step 2 log):
   `git add -- <code and test files>`, then git-workflow Steps 2 to 4 (TX
   check, then commit). Skip it for a docs-only build.
3. Governance commit second, as its own commit with the `docs` prefix: the
   files from Step 3 that changed, plus any docs a docs card edited.
4. `.session-memos/` is never staged. Never push.

### STEP 7 — REPORT (to chat only)

- Verified counts (pytest / Vitest / total), and any mismatch
- Each governance file changed, one line each, plus the diff
- Whether the phase tracker moved, and that CHECKPOINT was ON or OFF
- The memo path
- Memory: retained, declined or failed; Board: card id and column (`done`,
  with the short hash)
- The Step 4 verification result
- Commits: hash and subject of each, any changed file you left out and why,
  and the output of `git log --oneline origin/main..main`
- Any `AGENTS.md` change Prin should make by hand
- Tech debt or follow-ups

End with: "Review the log above, then push by hand:
`git push origin <branch>`."

Never push in this skill.
