---
name: code-sanity-check
description: Logic and syntax verification for Python code. Run when user says "sanity check", "check this", or "verify this file". Always run before committing.
---

## Sanity Check Protocol

### Steps

1. **Syntax**
   Run `ruff check` on the file:
```bash
ruff check [file.py] || python -m py_compile [file.py]
```
   If syntax fails — stop immediately. Do NOT continue.

2. **TX SAFETY — mandatory, non-negotiable:**
```bash
grep -n "writeStream\|SOAPY_SDR_TX\|hackrf_start_tx\|set_tx_gain\|set_tx_frequency\|setupTxStream\|activateTxStream\|setupTxStream" [file.py]
```
   Any match = ❌ TX VIOLATION — stop, report, do not proceed to git-workflow.
   Also verify: any SoapySDR direction argument must be `1` (RX), never `0` (TX).

3. **AU Legal check:**
```bash
grep -n "868000000\|868e6\|144390000\|144\.390" [file.py]
```
   Any match = ❌ AU LEGAL VIOLATION — wrong frequency for Australian jurisdiction.

4. **HardwareTransmitError guard:**
   Verify that any function touching TX-adjacent APIs calls `transmit_guard()` at the top.
   If a TX-adjacent function exists without this guard: ❌ BLOCKER

5. **Logic checks:**
   - Bare `except:` clauses — must catch specific exceptions
   - Missing type hints on function signatures
   - `print()` used instead of `logging`
   - Hardcoded IPs, credentials, or paths that should come from config
   - `os.path` used instead of `pathlib.Path`
   - RF-specific: sample rate outside HackRF One supported range (1–20 MHz)
   - RF-specific: gain values outside HackRF One range (LNA 0–40 dB, VGA 0–62 dB)

6. **Error handling:**
   - SoapySDR calls have try/except
   - `sr.ret < 0` checked after `readStream()`
   - File I/O handles missing files gracefully

7. **Second-pass review:**
   Invoke `@local-reviewer` on the changed function:
   > "@local-reviewer review the change to [file.py]"
   Wait for reviewer output before continuing.

8. **Approval gate:**
   > "Sanity check and local review complete — OK to proceed to git-workflow? (Yes / No)"
   Do not trigger git-workflow until user says Yes.

---

### Report Format
```
Sanity Check Report — [filename]
──────────────────────────────────
Syntax:         [Passed / Failed — reason]
TX Safety:      [Passed / ❌ VIOLATION — description]
AU Legal:       [Passed / ❌ VIOLATION — description]
TX Guard:       [Present / ❌ Missing on [function]]
Logic:          [Passed / Warnings — list]
Error Handling: [Passed / Concerns — list]
Local Reviewer Output:
──────────────────────────────────
[bullet points from @local-reviewer]
Result: ✅ Ready for git-workflow / ⚠️ Issues found / ❌ Blocked
```

---

### Rules

- Never modify the file during a sanity check — report only
- Never skip TX safety or AU legal check
- Never proceed to git-workflow without explicit Yes from the user
- If syntax fails, stop at step 1
