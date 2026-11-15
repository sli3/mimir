---
name: git-workflow
description: Git commit workflow for Mimir, run by pm. Stages by explicit path, checks the staged diff for TX patterns, then commits with no OK gate. Used at the end of a build and when Prin asks to commit ("commit", "git commit", "save to git"). Never pushes.
---

## Secure Git Workflow

pm commits on its own. Prin reviews the commits before he pushes, so the checks
below are what stand between a build and the history: never skip or soften one.
Mimir's code goes onto real radio hardware.

### Steps

1. **Stage**
   Stage only the files the build's list names (from `/build` or
   `/finalise-build`) or the files Prin named, by explicit path, in a call of
   its own: `git add -- <files>`. Never `-A`, `--all`, `-u`, `.`, a glob or
   `-f`: `agent_guard.py` rejects them. Code and governance are separate
   commits. Never stage `.session-memos/`, `data/`, a `.env` file, or a
   guard-rail file (`.claude/`, `.codex/`, `AGENTS.md`, `CLAUDE.md`,
   `.mcp.json`, `core/legal/compliance_guard.py`,
   `tests/test_no_transmit.py`, `tests/test_agent_guard.py`): Prin commits
   those himself. Then run `git status --short` and
   `git diff --cached --name-only`. The staged set must be exactly the files
   you meant to stage. Anything else staged, or anything Prin staged himself
   → hard stop: do not commit, do not unstage what you did not stage, report.

2. **TX safety check on the staged diff**
   Run `git diff --cached` and read the added lines (`+`) yourself. If any
   added line calls `writeStream`, `setupTxStream`, `activateTxStream`,
   `set_tx_gain`, `set_tx_frequency`, `hackrf_start_tx`, uses
   `SOAPY_SDR_TX`, or removes or weakens a `transmit_guard()` call:
   ❌ BLOCKED — TX pattern in staged diff. Do not commit. Hard stop: report it.
   (The existing blocking stubs in `core/device/` define these names to raise
   `HardwareTransmitError`; a definition that calls `transmit_guard()` is
   fine, a call is not.) Also confirm `uv run pytest tests/test_no_transmit.py`
   passes.

3. **Gate**
   Inside a build, the COMMIT GATE in pm's agent definition must hold. When
   Prin asked for the commit directly, his request is the approval for the
   files he named. Either way there is no "type OK" step: do not ask for one.

4. **Commit**
   Run `git commit -m "<subject>"` in a call of its own, nothing chained to
   it. Format: `<category>: <description in past tense>`, British English.

   | Category | Use for |
   |---|---|
   | `feat` | New feature |
   | `fix` | Bug corrected |
   | `refactor` | Restructure, no behaviour change |
   | `docs` | Documentation and governance records |
   | `chore` | Build, config or tooling |
   | `test` | Tests added or updated |

   End the subject with the build's Kanzo card id in brackets when there is
   one, exactly as the board shows it, for example `(rf#12)`. Any body goes in
   a further `-m` argument. Add nothing else to the command: no `-a`,
   `--amend`, `-F`, paths or other options, and no `git -C`; `agent_guard.py`
   rejects them and checks the staged paths at the moment you commit. No
   trailer. Keep the message on one line per `-m`, free of `;`, `&`, `|`, `<`,
   `>`, backticks and `$(`.
   No permission prompt appears. If the guard blocks the commit, that is a
   hard stop: report the exact message and do not work around it.

5. **Push: Prin does it by hand**
   Never push; `git push` is blocked for every session. After the commit, show
   `git log -1 --oneline`. At the end of a build also show
   `git log --oneline origin/<branch>..<branch>`, so Prin sees everything he
   would push, and give him the exact command naming the branch:
   `git push origin <branch>`.

6. **Board (pm only)**
   If the commit belongs to a build with a Kanzo card, move the card to
   `done` with a one-line comment giving the short hash (KANZO BOARD 4f in
   pm's agent definition). A Kanzo failure never undoes the commit.

### Rules

- Never commit without the TX check
- Only pm commits; `agent_guard.py` blocks every other named agent, and a
  plain session's commit asks Prin
- Never push, never `--force`, never `reset --hard`
- One logical change per commit
