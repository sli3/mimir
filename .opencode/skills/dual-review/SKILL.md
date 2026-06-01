---
name: dual-review
description: >
  Run a parallel dual code review — @local-reviewer and @cloud-reviewer simultaneously —
  then synthesise findings into a single actionable report. Use this skill whenever Prin asks
  for a code review, wants both reviewers to check something, says "dual review", "run both
  reviewers", "get both reviewers on this", "local and cloud review", or any variation of
  wanting more than one perspective on code before committing. Always use this skill for
  review requests — never run just a single reviewer when this skill applies. Particularly
  valuable after completing a phase, fixing a bug, or before pushing to main.
---

# Dual Review Skill

Fires `@local-reviewer` (local-llama/Qwen3, read-only) and `@cloud-reviewer`
(opencode/mimo-v2.5-free, read-only) in parallel using the `/multi` command, then
synthesises their findings into a single actionable report.

Two reviewers catch different classes of problems:
- `@local-reviewer` — logic, structure, TX safety, AU legal compliance
- `@cloud-reviewer` — style, edge cases, subtle bugs, Python correctness

This is the pattern that caught the stale docstring in `fingerprint_spectrum()` during
BUG-01 — neither reviewer would have caught it alone.

---

## Agents Reference

| Agent | Model | Strengths |
|---|---|---|
| `@local-reviewer` | local-llama/Qwen3.5-9B(Q4) | Logic, TX safety, AU legal, structure |
| `@cloud-reviewer` | opencode/mimo-v2.5-free | Style, edge cases, subtle bugs |

Both agents are read-only (`edit: deny`, `bash: deny`). Neither modifies files.

---

## Workflow

### Step 1 — Establish scope

Before producing the prompt, confirm:
- Which files changed? (run `git diff --name-only` or `git status` if unsure)
- What type of change? (bug fix / new feature / refactor / calibration tool / config)
- Any specific concerns? (e.g. a tricky algorithm, a new RF frequency, a new dependency)

If Prin hasn't specified, ask: *"Which files or changes should I send to both reviewers?"*

### Step 2 — Produce the /multi prompt

Use this exact structure — the `/multi` command requires `@agent` mentions in the message:

```
/multi @local-reviewer @cloud-reviewer

Review the following changes to the Mimir RF scanner project in parallel.
Each of you must independently assess the code and report your findings.
Do not coordinate — give your own honest assessment.

## What changed
[2–4 sentences: what was changed, why, and what problem it solves]

## Files to review
[List each changed file]

## Specific concerns
[Any known risks, tricky logic, or things to pay particular attention to.
 If none, write "None — general review."]

## Safety checks (mandatory for both reviewers)
1. TX safety — scan for any transmit patterns:
   hackrf_start_tx, SOAPY_SDR_TX, set_tx_gain, set_tx_frequency,
   writeStream, setupTxStream, activateTxStream
2. AU frequency compliance — no 868 MHz (EU LoRa), no 144.390 MHz (US APRS)
   Correct AU values: 915 MHz ISM/LoRa, 145.175 MHz APRS
3. OpenCode format — no CLAUDE.md, no .claude/ paths, no Cursor config

## Each reviewer must report
1. Correctness issues (logic errors, wrong assumptions, off-by-one)
2. Safety issues (TX patterns, AU legal compliance)
3. Style issues (against Mimir python-style skill conventions)
4. Anything the other reviewer might miss
5. Verdict: APPROVE / APPROVE WITH NOTES / REQUEST CHANGES
```

### Step 3 — Wait for both agents

Do not synthesise until both `@local-reviewer` and `@cloud-reviewer` have reported back.
The `/multi` command launches them simultaneously — both will complete before synthesis begins.

### Step 4 — Synthesise findings

Produce this table once both reports are in:

---

**DUAL REVIEW SYNTHESIS**

| | @local-reviewer | @cloud-reviewer |
|---|---|---|
| Correctness | [finding or ✓ clean] | [finding or ✓ clean] |
| TX safety | [finding or ✓ clean] | [finding or ✓ clean] |
| AU compliance | [finding or ✓ clean] | [finding or ✓ clean] |
| Style | [finding or ✓ clean] | [finding or ✓ clean] |
| Verdict | APPROVE / NOTES / CHANGES | APPROVE / NOTES / CHANGES |

**Unique findings** (caught by only one reviewer):
- @local-reviewer only: [list or "none"]
- @cloud-reviewer only: [list or "none"]

**Contradictions** (reviewers disagreed):
- [describe disagreement and which recommendation to follow, or "none"]

**Action items** (must be addressed before committing):
1. [item]

**Overall recommendation:** APPROVE / APPROVE WITH NOTES / REQUEST CHANGES

---

### Step 5 — Handle action items

**If action items exist:**
- Produce an OpenCode prompt to address them
- After fixes, use judgement on re-review:
  - Minor style fixes → no re-review needed
  - Logic or safety fixes → run dual review again

**If both reviewers APPROVE with no action items:**
- Produce the git commit command with an appropriate message

---

## Notes

- Never write or modify files until synthesis is complete and Prin has confirmed direction
  (this mirrors the `/multi` command's own instruction)
- If `/multi` fails or hangs, run `@local-reviewer` and `@cloud-reviewer` sequentially
  and still produce the synthesis table — the table is the deliverable regardless
- If the two reviewers directly contradict each other, surface it explicitly in the
  Contradictions row — never silently pick one
- `@cloud-reviewer` auto-triggers after edits anyway — the value of this skill is the
  *parallel* run with `@local-reviewer` and the structured synthesis, not just the
  cloud review alone
