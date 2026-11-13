---
name: deep-bug-analysis
description: Root-cause analysis before any bug fix, outside /build. Triggers on "deep bug hunt", "rca", "analyse this bug", "root cause", or "why is this failing". Runs the Codex debugger (or @deep-bug-hunter as fallback), gates on Prin's OK, then hands the findings to /build as the fix task. Never edits code itself.
---

## Deep Bug Analysis

Use this when the error is not obvious from the traceback, involves state,
threading or ordering, crosses modules, or a first fix did not work. For a
trivial one-line error (syntax, typo, missing import), go straight to `/build`.

### 1. Gather context

Collect the exact error and stack trace, the entry-point file and function, and
recent changes (latest memo: `ls -t .session-memos/`). If Prin has not given
the error, ask:
> "Please paste the error output (stack trace + last 20 lines of log). Which
> file and function is the entry point? Did it happen on hardware or in tests?"

Hardware-only bugs matter here: mock tests can be more permissive than the
real SDR. If the bug only shows on hardware, say so in the brief.

### 2. Run the analysis

If you are `pm`: run the Codex debugger in Diagnosis mode, effort `xhigh`,
with the REVIEW CHECK around it, exactly as your agent definition describes.
Put the error and test output in a HAND-OFF FILE. Fall back to
`@deep-bug-hunter` Mode 2 if Codex fails, has no clear root cause, or its
answer contradicts the code.

If you are not `pm`: use `@deep-bug-hunter` Mode 2 (Agent tool,
`subagent_type: deep-bug-hunter`, no `model` override) with a brief holding
the error, entry point, files to investigate and context.

### 3. Present and gate

Show the full analysis, then ask:
> "Root cause analysis complete.
> **Confidence:** [High / Medium / Low]
> **Hypothesis:** [one line]
> **Needs hardware to confirm:** [yes/no]
> Does this look right? Shall I turn it into a /build task? (Yes / No / Revise)"

- **Yes** → step 4
- **No / Revise** → re-run with Prin's corrections, at most 2 more times
- Low confidence after that → stop and say so plainly

### 4. Hand off to /build

Write the `/build` task for Prin to run (as `pm`):

```
/build "Fix <one-line bug>. Root cause: <hypothesis>. Fix strategy: <strategy>.
Only modify: <affected paths>. Do not touch: <what not to touch>.
RCA confidence: <level>."
```

### Rules

- Never edit a file in this skill; fixes go through `/build` and its plan
  review
- If the analysis surfaces anything that could transmit, that is a TX hard
  stop: report it before anything else
- British English throughout
