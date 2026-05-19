---
name: git-workflow
description: Secure Git workflow with review gates. Triggers on "commit", "git commit", "push", or "save to git". Always run after code-sanity-check passes.
---

## Secure Git Workflow

### Steps

1. **Stage Check**
```bash
git status
```
   Report which files are staged, modified, or untracked.
   If unexpected files are staged, stop and ask the user to review.
   If new files created this session appear as Untracked, stage them too.

2. **TX Safety final check before commit:**
```bash
git diff --cached | grep -E "writeStream|SOAPY_SDR_TX|hackrf_start_tx|set_tx_gain|set_tx_frequency"
```
   If any match: ❌ BLOCKED — TX pattern in staged diff. Do not commit.

3. **Review Gate**
```bash
git diff --cached
```
   Wait for explicit **"OK"** before proceeding.

4. **Commit Format**
   Format: `[category]: [description in past tense]`

   | Category | Use for |
   |----------|---------|
   | `feat` | New feature added |
   | `fix` | Bug corrected |
   | `refactor` | Code restructured, no behaviour change |
   | `docs` | Documentation updated |
   | `chore` | Build, config, or tooling changes |
   | `test` | Tests added or updated |

   Examples:
   ```
   feat: added IQ capture pipeline for FM broadcast
   fix: corrected SoapySDR stream timeout handling
   test: added RX-only lock tests for capture module
   ```

5. **Push Gate**
   Ask explicitly:
   > "Shall I push to `main`? (Yes / No)"
   Never push without an explicit **"Yes"**.

6. **Safety**
   Never use `--force` or `-f` under any circumstance.

---

### Rules

- Never skip the TX safety check on staged diff
- Never skip the diff review gate
- Never push without explicit approval
- Never use `--force` or `-f`
- One logical change per commit
