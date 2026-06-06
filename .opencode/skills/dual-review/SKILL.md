---
name: dual-review
description: >
  Run a parallel dual code review — @review-second and @deep-analyst simultaneously —
  then synthesise findings into a single actionable report. Use this skill whenever Prin asks
  for a code review, wants both reviewers to check something, says "dual review", "run both
  reviewers", "get both reviewers on this", or any variation of wanting more than one
  perspective on code before committing. Always use this skill for review requests — never
  run just a single reviewer when this skill applies. Particularly valuable after completing
  a phase, fixing a bug, or before pushing to main.
---

# Dual Review Skill

Fires `@review-second` (opencode-go/minimax-m2.7, read-only) and `@deep-analyst`
(opencode-go/glm-5.1, read-only) in parallel using the `/multi` command, then
synthesises their findings into a single actionable report.

Two reviewers catch different classes of problems:
- `@review-second` — independent second voice: correctness, regressions, AU legal/TX
  compliance, AGENTS.md adherence
- `@deep-analyst` — deep, thorough: root cause tracing, multi-file dependencies,
  complex logic, architecture

---

## Agents Reference

| Agent | Model | Strengths |
|---|---|---|
| `@review-second` | opencode-go/minimax-m2.7 | Correctness, regressions, TX/AU legal, AGENTS.md conventions |
| `@deep-analyst` | opencode-go/glm-5.1 | Root cause, multi-file tracing, complex logic, architecture |

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
/multi @review-second @deep-analyst

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

Do not synthesise until both `@review-second` and `@deep-analyst` have reported back.
The `/multi` command launches them simultaneously — both will complete before synthesis begins.

### Step 4 — Synthesise findings

Produce this table once both reports are in:

---

**DUAL REVIEW SYNTHESIS**

| | @review-second | @deep-analyst |
|---|---|---|
| Correctness | [finding or ✓ clean] | [finding or ✓ clean] |
| TX safety | [finding or ✓ clean] | [finding or ✓ clean] |
| AU compliance | [finding or ✓ clean] | [finding or ✓ clean] |
| Style | [finding or ✓ clean] | [finding or ✓ clean] |
| Verdict | APPROVE / NOTES / CHANGES | APPROVE / NOTES / CHANGES |

**Unique findings** (caught by only one reviewer):
- @review-second only: [list or "none"]
- @deep-analyst only: [list or "none"]

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
- If `/multi` fails or hangs, run `@review-second` and `@deep-analyst` sequentially
  and still produce the synthesis table — the table is the deliverable regardless
- If the two reviewers directly contradict each other, surface it explicitly in the
  Contradictions row — never silently pick one