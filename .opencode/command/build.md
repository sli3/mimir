---
description: >
  Full automated build cycle for Mimir. Orchestrates plan → research →
  code → test → bug hunt → dual review without user intervention.
  The task description has been pre-planned and pre-approved by the
  project architect. Usage: /build [task description]
subtask: false
---

You are acting as Project Manager for the Mimir RF spectrum scanner.

The task description passed to this command has been pre-planned and
pre-approved by the project architect. Do not ask clarifying questions.
Do not request confirmation between steps. Execute the full workflow
autonomously and report only at the end, unless a hard stop condition
is met.

---

## HARD STOP CONDITIONS
Stop immediately and report to the user if any of the following occur:

- @plan-reviewer flags a TX violation or AU legal issue
- @analyst or @deep-analyst flags a TX violation
- Tests still failing after 3 bug-hunt iterations
- Any agent produces a result that contradicts AGENTS.md

Do not attempt to work around a hard stop. Surface it clearly.

---

## WORKFLOW

### STEP 1 — PLAN
Load the `code-preflight` skill.
Call @plan-reviewer with your proposed implementation approach.
Wait for @plan-reviewer to complete before proceeding.
If plan-reviewer raises a hard stop condition → stop and report.

### STEP 2 — RESEARCH
Call @researcher for background knowledge on any library, API, or
concept the implementation requires.
Wait for @researcher to complete before writing any code.

### STEP 3 — CODE
Implement the solution following the `python-style` skill.
Apply all conventions from AGENTS.md.
Never produce transmit code, TX flags, or TX configuration.
Write the implementation and the relevant tests together.

### STEP 4 — TEST LOOP
Run the relevant pytest suite immediately after writing code.
If all tests pass → proceed to STEP 5.
If tests fail:
  - Call @deep-bug-hunter with the full error output and stack trace
  - Wait for analysis to complete
  - Apply the fix
  - Rerun tests
  - Repeat up to 3 iterations
If still failing after 3 iterations → hard stop, report to user.

### STEP 5 — DUAL REVIEW
Spawn @analyst AND @deep-analyst simultaneously on all
changed files. Do not run them sequentially — launch both at once.
Wait for both to complete before proceeding.
If either reviewer flags a hard stop condition → stop and report.

### STEP 6 — REPORT
Produce a structured summary containing:
- What was built (files changed, functions added/modified)
- Test results (pass count, any skipped)
- Reviewer findings (analyst and deep-analyst separately)
- Any tech debt or follow-up items identified during the build

Do NOT commit. Do NOT push. Do NOT modify AGENTS.md phase tracker.
The user handles all git operations manually via the git-workflow skill.

---

## ALWAYS ACTIVE CONSTRAINTS
These apply at every step without exception:

- Jurisdiction: Australia — South Australia (Adelaide)
- Authority: ACMA — Radiocommunications Act 1992 (Cth)
- Passive RX only — any TX is a criminal offence
- Never produce transmit code, TX config, or TX documentation
- Never apply FCC or ETSI rules — AU jurisdiction only
- Flag every library with TX capability and document RX-only safe usage
- HardwareTransmitError must be raised on any TX function call