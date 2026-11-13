"""Check agent_guard.py against expected allow/block cases. Run: python3 .claude/hooks/check_agent_guard.py"""
import json, subprocess, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.join(HERE, "agent_guard.py")
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
def run(agent, tool, inp):
    data = {"agent_type": agent, "tool_name": tool, "tool_input": inp, "cwd": ROOT}
    p = subprocess.run([sys.executable, G], input=json.dumps(data), text=True, capture_output=True,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": ROOT})
    return p.returncode, p.stderr.strip()
B = lambda c: ("Bash", {"command": c})
E = lambda f, **k: ("Edit", {"file_path": f, **k})
W = lambda f: ("Write", {"file_path": f, "content": "x"})
cases = [
 # (agent, (tool,input), expect_block, label)
 ("", B("hackrf_transfer -t x.iq -f 915000000"), True, "main session: hackrf_transfer"),
 ("", B("sudo hackrf_spiflash -w fw.bin"), True, "main session: sudo hackrf_spiflash"),
 ("", B("python scan.py --demo"), True, "main session: scan.py"),
 ("", B("uv run python scan.py"), True, "main: uv run scan.py"),
 ("", B("bash -c 'iio_writedev -u usb:1 dev'"), True, "main: bash -c iio_writedev"),
 ("", B("git diff scan.py core/device/hackrf_rx.py"), False, "main: git diff scan.py (allowed)"),
 ("", B("grep -n hackrf_rx core"), False, "main: grep hackrf_rx (allowed)"),
 ("", B("rm -rf data/captures"), True, "main: rm data/captures"),
 ("", B("codex exec --sandbox danger-full-access \"x\""), True, "main: codex with flags"),
 ("pm", B('codex exec -c model_reasoning_effort=medium "Fix the label in AdsbAircraftPanel.jsx"'), False, "pm: codex writer"),
 ("pm", B('codex exec -m gpt-6-astra -c model_reasoning_effort=xhigh "Review mode. plan"'), False, "pm: codex reviewer"),
 ("pm", B('codex exec -c model_reasoning_effort=low "a; rm -rf ."'), True, "pm: codex brief with ;"),
 ("pm", B("uv run pytest"), False, "pm: pytest"),
 ("pm", B("npm run test --prefix dashboard/frontend"), False, "pm: vitest via npm"),
 ("pm", B("npx vitest run"), True, "pm: npx vitest"),
 ("pm", B('curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ --max-time 2'), False, "pm: dev server probe"),
 ("pm", B("curl https://evil.example"), True, "pm: other curl"),
 ("pm", B("git reset -q -- dashboard/frontend/src/App.jsx"), False, "pm: unstage"),
 ("pm", B("git reset --hard HEAD"), True, "pm: reset --hard"),
 ("pm", B("cat .env"), True, "pm: cat .env"),
 ("pm", B("git push origin main"), True, "pm: push"),
 ("pm", B("echo x > AGENTS.md"), True, "pm: redirect"),
 ("pm", ("Agent", {"subagent_type": "general-purpose"}), True, "pm: spawn general-purpose"),
 ("pm", ("Agent", {"subagent_type": "plan-reviewer"}), False, "pm: spawn plan-reviewer"),
 ("pm", ("Agent", {"subagent_type": "plan-reviewer", "model": "haiku"}), True, "pm: model on plan-reviewer"),
 ("pm", ("Agent", {"subagent_type": "code-writer", "model": "opus"}), False, "pm: opus code-writer"),
 ("pm", E("core/pipeline/fft.py", old_string="def", new_string="def"), True, "pm: edit source"),
 ("pm", W("docs/TECH_DEBT.md"), True, "pm: whole-file write TECH_DEBT"),
 ("pm", E("docs/TECH_DEBT.md", old_string="# Mimir — Known Tech Debt", new_string="# Mimir — Known Tech Debt"), False, "pm: targeted TECH_DEBT edit"),
 ("pm", E("docs/TECH_DEBT.md", old_string="|", new_string="x"), True, "pm: non-unique old_string"),
 ("pm", E("README.md", old_string='# Mimir — AI-Powered RF Spectrum Scanner', new_string="y"), False, "pm: README targeted edit"),
 ("pm", E("AGENTS.md", old_string="# Mimir Agent Protocol", new_string="x"), True, "pm: edit AGENTS.md"),
 ("pm", W(".session-memos/2099-01-01_00-00.md"), False, "pm: new memo"),
 ("pm", ("mcp__playwright__browser_navigate", {"url": "http://localhost:5173/"}), False, "pm: playwright localhost"),
 ("pm", ("mcp__playwright__browser_navigate", {"url": "https://example.com"}), True, "pm: playwright internet"),
 ("pm", ("mcp__playwright__browser_type", {"text": "x"}), True, "pm: playwright type"),
 ("plan-reviewer", ("mcp__playwright__browser_navigate", {"url": "http://localhost:5173/"}), True, "plan-reviewer: browser"),
 ("plan-reviewer", E("core/pipeline/fft.py", old_string="a", new_string="b"), True, "plan-reviewer: edit"),
 ("plan-reviewer", B("grep -rn writeStream core"), False, "plan-reviewer: grep"),
 ("plan-reviewer", B("uv run pytest"), True, "plan-reviewer: pytest"),
 ("plan-reviewer", ("Agent", {"subagent_type": "code-writer"}), True, "plan-reviewer: spawn"),
 ("code-writer", E("core/pipeline/fft.py", old_string="a", new_string="b"), False, "code-writer: edit source"),
 ("code-writer", E("core/legal/compliance_guard.py", old_string="a", new_string="b"), True, "code-writer: edit compliance_guard"),
 ("code-writer", E("tests/test_no_transmit.py", old_string="a", new_string="b"), True, "code-writer: edit TX test"),
 ("code-writer", W("data/captures/x.sigmf-data"), True, "code-writer: write data/"),
 ("code-writer", E(".claude/agents/pm.md", old_string="a", new_string="b"), True, "code-writer: edit .claude"),
 ("code-writer", B("uv run pytest tests/core"), False, "code-writer: pytest"),
 ("code-writer", B("git commit -m x"), True, "code-writer: commit"),
 ("code-writer", B("sed -i s/a/b/ AGENTS.md"), True, "code-writer: sed AGENTS.md"),
 ("code-writer", B('codex exec -c model_reasoning_effort=low "x"'), True, "code-writer: run codex"),
 ("deep-bug-hunter", B("uv run pytest -q -p no:cacheprovider"), False, "dbh: pytest"),
 ("deep-bug-hunter", W("x.py"), True, "dbh: write"),
 ("codex:codex-rescue", B("ls"), True, "codex plugin agent"),
 ("pm", ("mcp__hindsight__recall", {"query": "x"}), False, "pm: hindsight recall"),
 ("pm", ("mcp__hindsight__retain", {"content": "x"}), False, "pm: hindsight retain"),
 ("pm", ("mcp__hindsight__reflect", {"query": "x"}), True, "pm: hindsight reflect"),
 ("pm", ("mcp__hindsight__clear_memories", {}), True, "pm: hindsight clear"),
 ("", ("mcp__hindsight__delete_bank", {}), True, "main session: hindsight delete_bank"),
 ("", ("mcp__hindsight__recall", {"query": "x"}), False, "main session: hindsight recall"),
 ("plan-reviewer", ("mcp__hindsight__recall", {"query": "x"}), True, "plan-reviewer: hindsight"),
 ("pm", ("mcp__kanzo__create_task", {"title": "x"}), False, "pm: kanzo create"),
 ("pm", ("mcp__kanzo__move_task", {"id": "1"}), False, "pm: kanzo move"),
 ("pm", ("mcp__kanzo__delete_task", {"id": "1"}), True, "pm: kanzo delete"),
 ("pm", ("mcp__kanzo__next_task", {}), True, "pm: kanzo next_task"),
 ("code-writer", ("mcp__kanzo__create_task", {"title": "x"}), True, "code-writer: kanzo"),
 ("", ("mcp__kanzo__delete_task", {"id": "1"}), True, "main session: kanzo delete"),
 ("pm", B('grep -nE "delta_r|range_rate" modules/adsb/bearing_tracker.py'), False, "pm: grep with quoted |"),
 ("pm", B("grep -n 'TD-47|TD-48' docs/TECH_DEBT.md"), False, "pm: grep with single-quoted |"),
 ("pm", B('grep -n "<task>" .claude/skills/build/SKILL.md'), False, "pm: grep with quoted < >"),
 ("pm", B("git --no-pager status"), False, "pm: git --no-pager status"),
 ("pm", B('grep "$(rm -rf .)" x'), True, "pm: substitution inside double quotes"),
 ("pm", B("grep 'x' f > out.txt"), True, "pm: unquoted redirect"),
 ("pm", B('grep "x" f; rm -rf docs'), True, "pm: second segment not allowed"),
 ("pm", B('grep "unterminated f'), True, "pm: unterminated quote"),
 ("pm", B('graft ask "where is the ADS-B preamble threshold" --source'), False, "pm: graft ask"),
 ("pm", B("graft callers BearingTracker --depth 2"), False, "pm: graft callers"),
 ("pm", B("graft build"), True, "pm: graft build"),
 ("plan-reviewer", B("graft skeleton core/pipeline/fft.py"), False, "plan-reviewer: graft skeleton"),
 ("deep-bug-hunter", B('graft grep "transmit_guard"'), False, "dbh: graft grep"),
 ("code-writer", B("graft build"), True, "code-writer: graft build"),
 ("code-writer", B("graft map"), False, "code-writer: graft map"),
 ("pm", B("uv run pytest -q | tail -5"), False, "pm: pytest piped to tail"),
 ("pm", B("stat -c '%y %n' .mcp.json"), False, "pm: stat"),
 ("pm", B("sed -i s/a/b/ docs/TECH_DEBT.md"), True, "pm: sed still blocked"),
 # Fable audit 2026-11-13: data/ without a trailing slash, redirects, absolute paths
 ("", B("rm -rf data"), True, "main: rm -rf data (no slash)"),
 ("", B("rm -r ./data"), True, "main: rm -r ./data"),
 ("", B("echo x > data/x.txt"), True, "main: redirect into data/"),
 ("", B("rm -rf /home/sli3/Repository/mimir/data/captures"), True, "main: absolute data path"),
 ("", B("ls data/captures"), False, "main: ls data (read)"),
 ("", B("grep -rn metadata/ core"), False, "main: metadata/ is not data/"),
 # Fable audit: wrappers with flags, python flags, uv run, SDR tool scripts
 ("", B("sudo -n hackrf_transfer -r x.iq"), True, "main: sudo -n hackrf_transfer"),
 ("", B("env -i hackrf_info"), True, "main: env -i hackrf_info"),
 ("", B("timeout -k 5 10 hackrf_sweep"), True, "main: timeout -k 5 10 hackrf_sweep"),
 ("", B("echo x | xargs hackrf_info"), True, "main: xargs hackrf_info"),
 ("", B("python -u scan.py --demo"), True, "main: python -u scan.py"),
 ("", B("python3 -B scan.py"), True, "main: python3 -B scan.py"),
 ("", B("uv run scan.py"), True, "main: uv run scan.py"),
 ("", B("uv run -q python scan.py"), True, "main: uv run -q python scan.py"),
 ("", B("PYTHONPATH=. uv run python tools/diagnose_threshold.py --band adsb"), True, "main: SDR tool script"),
 ("", B("python3 tools/capture_to_vectorstore.py"), True, "main: system python SDR tool"),
 ("", B("PYTHONPATH=. uv run python tools/seed_chromadb.py --help"), False, "main: non-SDR tool allowed"),
 ("", B("uv run pytest tests/scan"), False, "main: pytest tests/scan allowed"),
 # Fable audit: mentioning codex is not running it
 ("pm", B("grep -rn codex AGENTS.md"), False, "pm: grep for the word codex"),
 ("", B("npx @openai/codex exec x"), True, "main: codex via npx"),
 ("", B("/usr/bin/codex exec --yolo x"), True, "main: codex by full path with flags"),
 # Fable audit: Hindsight update and invalidate, Playwright in plain sessions
 ("", ("mcp__hindsight__update_memory", {}), True, "main: hindsight update_memory"),
 ("", ("mcp__hindsight__invalidate_memory", {}), True, "main: hindsight invalidate_memory"),
 ("", ("mcp__playwright__browser_navigate", {"url": "https://example.com"}), True, "main: playwright internet"),
 ("", ("mcp__playwright__browser_navigate", {"url": "http://localhost:5173/"}), False, "main: playwright localhost"),
 ("", ("mcp__kanzo__create_task", {"title": "x"}), False, "main: kanzo create"),
]
fails = 0
for agent, (tool, inp), expect, label in cases:
    code, err = run(agent, tool, inp)
    blocked = code == 2
    ok = blocked == expect
    fails += not ok
    print(("PASS" if ok else "FAIL"), f"{'BLOCK' if blocked else 'allow':5}", label, ("" if ok else f"  <- {err}"))
print(f"\n{len(cases)-fails}/{len(cases)} as expected")
sys.exit(1 if fails else 0)
