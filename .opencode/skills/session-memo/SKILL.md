---
name: session-memo
description: Summarise the current session and save a timestamped memo. Triggers ONLY on "memo", "save session", "summarise session", or "memo this was a [Type] session". Never triggers automatically.
---

## Session Memo Protocol

### Steps

1. **Determine session type** — if not stated, ask:
   > "What type was this session? (Explore / Plan / Code / Review / Debug / Mixed)"
   Wait for the answer before writing.

2. **Summarise** — concise session summary containing:
   - Session type
   - What was discussed or decided (2–3 lines max)
   - What was changed or written (list files and functions touched)
   - What was NOT finished (next steps, max 3 bullet points)
   - Any important decisions or rejected approaches
   - Any mistakes made this session with their category
   - Any TX safety incidents or AU legal flags raised

3. **Create memo directory:**
```bash
mkdir -p .session-memos
```

4. **Write memo file:**
```bash
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M")
MEMO_FILE=".session-memos/${TIMESTAMP}.md"
```
   Never overwrite existing memos — always fresh timestamp.

5. **Memo format:**

```markdown
# Session Memo — [YYYY-MM-DD HH:MM]

## Type
[Explore / Plan / Code / Review / Debug / Mixed]

## What We Did
- [2–3 concise bullet points]

## RF/Legal Notes
- TX safety incidents: [None / description]
- AU legal flags: [None / description]

## Files Touched
- `[filename]`: [what changed]
- None *(if read-only session)*

## Decisions Made
- [approach chosen and why]
- [approach rejected and why]

## Mistakes Made
- [exact description] — Category: [Scope Creep / Safety Violation / Logic Error / Process Skip / TX Violation]
- None *(if no mistakes)*

## Not Finished
- [up to 3 clear next steps]

## Next Session Starter
[One specific actionable opening message for the next session]
```

6. **Confirm** — print file path only:
```
Memo saved to .session-memos/[timestamp].md
```

---

### Rules

- Save to `.session-memos/` in project root only
- Never overwrite existing memos
- Keep summary under 300 words
- Always include RF/Legal Notes section — even if empty
- Do NOT print full memo contents — just confirm file path
