---
name: session-memo
description: Summarise the current session and save a timestamped memo to .session-memos/. Triggers ONLY on "memo", "save session", "summarise session", or "memo this was a [Type] session". Never triggers automatically. (/finalise-build writes its own memo.)
---

## Session Memo Protocol

1. **Session type.** If Prin has not said, ask:
   > "What type was this session? (Explore / Plan / Code / Review / Debug / Mixed)"
   Wait for the answer.

2. **Timestamp.** Run `date +"%Y-%m-%d_%H-%M"`. The file is
   `.session-memos/<timestamp>.md`. Run `mkdir -p .session-memos` if needed.
   Never overwrite an existing memo: if the name exists, wait a minute and take
   a fresh timestamp.

3. **Write it with the Write tool** (not a shell redirect or heredoc), in
   exactly this format, under 300 words. Square brackets mark text to replace;
   do not keep the brackets:

```markdown
# Session Memo — YYYY-MM-DD HH:MM

## Type
[Explore / Plan / Code / Review / Debug / Mixed]

## What We Did
- [2–3 concise bullet points]

## RF/Legal Notes
- TX safety incidents: [None / description]
- AU legal flags: [None / description]

## Files Touched
- `[filename]`: [what changed, from git diff]
- None *(if read-only session)*

## Decisions Made
- [what Prin decided, in his words; otherwise "None recorded"]

## Mistakes Made
- [exact description] — Category: [Scope Creep / Safety Violation / Logic Error / Process Skip / TX Violation]
- None *(if no mistakes)*

## Not Finished
- [up to 3 clear next steps]

## Next Session Starter
[One specific actionable opening message for the next session]
```

4. **Confirm** with the path only:
   `Memo saved to .session-memos/<timestamp>.md`

### Rules

- `.session-memos/` is gitignored and local only: never stage it
- Files Touched comes from `git diff`, not memory
- No absence claims, no invented rationale, no derived test arithmetic
- Always include RF/Legal Notes, even when both are "None"
- Do not print the memo contents
