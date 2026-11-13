---
name: git-workflow
description: Secure Git commit workflow for Mimir with a TX safety check on the staged diff and an explicit OK gate. Use only when Prin asks to commit ("commit", "git commit", "save to git"). Never pushes.
---

## Secure Git Workflow

Prin asked for this commit. You still show the staged diff and wait for his
"OK" before committing: Mimir's code goes onto real radio hardware.

### Steps

1. **Stage**
   Stage only the files Prin named, or the files the `/finalise-build`
   COMMIT HANDOFF listed for this commit, with `git add -- <files>`. Code and
   governance are separate commits. Never stage `.session-memos/`, `data/`,
   `opencode.json` or a `.env` file. Then run `git status --short` and
   `git diff --cached --name-only`. Anything unexpected staged → stop and ask.

2. **TX safety check on the staged diff**
   Run `git diff --cached` and read the added lines (`+`) yourself. If any
   added line calls `writeStream`, `setupTxStream`, `activateTxStream`,
   `set_tx_gain`, `set_tx_frequency`, `hackrf_start_tx`, uses
   `SOAPY_SDR_TX`, or removes or weakens a `transmit_guard()` call:
   ❌ BLOCKED — TX pattern in staged diff. Do not commit. Report it.
   (The existing blocking stubs in `core/device/` define these names to raise
   `HardwareTransmitError`; a definition that calls `transmit_guard()` is
   fine, a call is not.) Also confirm `uv run pytest tests/test_no_transmit.py`
   passes.

3. **Review gate**
   Show the staged diff summary and the proposed message, then ask:
   > "Staged diff above. Type OK to commit."
   Wait for an explicit **OK**. Anything else → do not commit.

4. **Commit**
   Format: `<category>: <description in past tense>`, British English.

   | Category | Use for |
   |---|---|
   | `feat` | New feature |
   | `fix` | Bug corrected |
   | `refactor` | Restructure, no behaviour change |
   | `docs` | Documentation and governance records |
   | `chore` | Build, config or tooling |
   | `test` | Tests added or updated |

   Any body goes in a further `-m` argument. Keep messages free of `;`, `&`,
   `|`, `<`, `>`, backticks and `$(`, which `agent_guard.py` rejects.
   `git commit` also prompts Prin once more (an `ask` rule): that is expected.

5. **Push: Prin does it by hand**
   Never push; `git push` is denied. After the commit, show
   `git log -1 --oneline` and give Prin the exact command, naming the branch:
   `git push origin <branch>`.

### Rules

- Never commit without the TX check and Prin's explicit OK
- Never push, never `--force`, never `reset --hard`
- One logical change per commit
