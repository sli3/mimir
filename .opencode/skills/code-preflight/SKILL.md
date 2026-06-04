---
name: code-preflight
description: Pre-flight checklist for Code sessions ONLY. Triggers on "run preflight", "preflight check", or when the user explicitly says "Code session". NEVER triggers for Plan, Explore, or Review sessions.
---

## Code Pre-Flight Checklist

### Steps

1. **Read session memo:**
```bash
ls -t .session-memos/*.md | head -1
```
Summarise in one sentence what this Code session is supposed to do.

1b. **If this is a roadmap feature session**, read `docs/MIMIR_ROADMAP.md` before stating scope.

2. **Check previous mistakes** — look for `## Mistakes Made` in memo:
   - Read each mistake aloud
   - State how you will avoid repeating each one
   - If none, state that clearly

3. **TX SAFETY GATE — mandatory, run before anything else:**
   Grep the files in scope for forbidden patterns:
```bash
grep -rn "writeStream\|SOAPY_SDR_TX\|hackrf_start_tx\|set_tx_gain\|set_tx_frequency\|setupTxStream\|activateTxStream" [files-in-scope]
```
   If any match is found:
   ❌ BLOCKED — TX pattern detected. Stop immediately. Report to user. Do not proceed.

   If clean: ✅ TX safety check passed

4. **AU LEGAL CHECK — mandatory:**
   Grep for known illegal frequency values:
```bash
grep -rn "868000000\|868e6\|144390000\|144\.390\|144390" [files-in-scope]
```
   - 868 MHz = EU LoRa band — illegal to use in AU context (AU = 915 MHz)
   - 144.390 MHz = US APRS — illegal to use in AU context (AU = 145.175 MHz)

   If found: ❌ BLOCKED — AU frequency violation. Report and stop.
   If clean: ✅ AU legal check passed

5. **State exact scope:**
   - Which file will be changed
   - Which function or section will be changed
   - What specific change will be made
   - What will NOT be changed

6. **Read only what is needed** — relevant function only, not entire file.

7. **Show the plan** — exact proposed change in a code block with inline comments.
   Do not edit yet.

8. **Wait for OK** — ask:
   > "Does this plan look correct? Shall I proceed?"

   Do not touch any file until user says yes.
   After showing the plan, output exactly this line and nothing else:
   `WAITING FOR OK — do not proceed until user explicitly types "OK"`

9. **Remind user of post-edit sequence:**
   > "After the edit is done: run `@analyst` on the changed function,
   > then `code-sanity-check`, then `git-workflow`."

---

### Checklist Output Format
```
Pre-Flight Check:
✅ Memo read — [one line summary]
✅ Previous mistakes reviewed — [none / list]
✅ TX safety check — [passed / BLOCKED]
✅ AU legal check — [passed / BLOCKED]
✅ Scope confirmed: [file1.py, file2.py]
✅ Plan shown — waiting for your OK
✅ Post-edit sequence noted — @analyst → sanity-check → git-workflow
```

---

### Rules

- Never skip this checklist in a Code session
- Never edit before user says OK
- Never skip the TX safety check or AU legal check — ever
- If TX or legal check fails, stop completely and report back
- Never invoke @analyst yourself — remind the user to do it manually
- Never touch files outside the stated scope