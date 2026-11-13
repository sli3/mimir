#!/usr/bin/env python3
"""agent_guard.py — PreToolUse hook that applies Mimir's per-agent rules.

Adapted from Ravensight's guard. Claude Code permission rules in settings.json
apply to every agent alike. The PreToolUse hook input, however, carries
`agent_type`: the subagent's name when the hook fires inside a subagent, or the
main-thread agent's name when the session runs as a named agent (the `agent`
setting or `claude --agent`). This script reads that field and blocks the
calls each agent is not permitted to make.

Two rules apply to EVERY session, named agent or not, because Mimir is
receive-only under the Radiocommunications Act 1992 (Cth):
  * no Bash command may run a radio-hardware tool or the live scanner;
  * Codex may run only in pm's three safe `codex exec` forms.

Exit 0 with no output leaves the call to the normal permission rules, so the
global deny and ask rules in settings.json still apply on top of this guard.
Exit 2 blocks the call and shows the stderr message to the agent. Any
unexpected error also exits 2, so a broken guard fails closed.

Codex edits files from its own process, so this guard never sees them. Codex is
held by .codex/config.toml (filesystem), .codex/rules/mimir.rules (commands),
pm's PROTECTED FILE CHECK, and tests/test_no_transmit.py.
"""

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

PM = "pm"
PLAN_REVIEWER = "plan-reviewer"
CODE_WRITER = "code-writer"
DEEP_BUG_HUNTER = "deep-bug-hunter"
TEAM = (PLAN_REVIEWER, CODE_WRITER, DEEP_BUG_HUNTER)
# The Codex plugin's forwarding agent starts Codex with its own sandbox setting,
# which replaces .codex/config.toml, so it is blocked outright.
CODEX_AGENT_NAMES = ("codex:codex-rescue", "codex-rescue")
SPAWNABLE = TEAM

FILE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")

# Per-call model overrides pm may pass, by subagent.
ALLOWED_MODEL_OVERRIDES = {
    CODE_WRITER: ("haiku", "sonnet", "opus"),
}

# pm's write targets. Governance docs: targeted Edit only. Memos: new files only.
ROADMAP = "docs/ROADMAP.md"
TECH_DEBT = "docs/TECH_DEBT.md"
README = "README.md"
PM_EDIT_ONLY = (ROADMAP, TECH_DEBT, README)
MEMO_DIR = ".session-memos/"

# Bash command prefixes each read-only or orchestrating agent may run. A
# command matches a prefix when it equals it or continues with a space.
# Graft (repo context graph) read commands. `graft build` is Prin's: it is on no
# agent's allowlist, and code-writer is blocked from it explicitly.
GRAFT_READ = (
    "graft map",
    "graft ask",
    "graft grep",
    "graft skeleton",
    "graft callers",
    "graft check",
)
GIT_READ = (
    "git status",
    "git --no-pager status",
    "git diff",
    "git --no-pager diff",
    "git log",
    "git --no-pager log",
    "git show",
    "git --no-pager show",
)
BASH_ALLOW = {
    PM: GRAFT_READ + GIT_READ + (
        "uv run pytest",
        "uv run python -m pytest",
        "uv run python -m py_compile",
        "uv run python -c",  # still prompts: "ask" rule in settings.json
        "npm run test --prefix dashboard/frontend",
        "npm run lint --prefix dashboard/frontend",
        "ls -t",
        "ls",
        "head",
        "cat",
        "wc",
        "grep",
        "tail",
        "stat",
        "git add",
        "git reset -q --",  # unstage paths only; "--" makes any later word a path
        "git commit",  # still prompts: "ask" rule in settings.json
        "git switch",
        "git checkout -b",
        "git branch",  # branch -D still prompts: "ask" rule in settings.json
        "mkdir -p .session-memos",
        "date",
    ),
    PLAN_REVIEWER: GRAFT_READ + GIT_READ + ("ls", "grep", "wc"),
    DEEP_BUG_HUNTER: GRAFT_READ + GIT_READ + (
        "ls",
        "grep",
        "wc",
        "uv run python -m py_compile",
        "uv run pytest",
        "uv run python -m pytest",
        "npm run test --prefix dashboard/frontend",
    ),
}

# Bash commands an agent may run only exactly as written.
DEV_SERVER_PROBE = 'curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ --max-time 2'
BASH_EXACT = {
    PM: ("rm -rf .playwright-mcp", DEV_SERVER_PROBE),
}

# Files code-writer must never edit, matched by file name at any depth.
CODE_WRITER_DENY_NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "ROADMAP.md",
    "TECH_DEBT.md",
    "README.md",
    ".mcp.json",
    "compliance_guard.py",
    "test_no_transmit.py",
    "test_agent_guard.py",
}
# Top-level directories code-writer must never edit.
CODE_WRITER_DENY_DIRS = {".claude", ".codex", "data", ".session-memos"}
CODE_WRITER_BASH_DENY = re.compile(
    r"AGENTS\.md|CLAUDE\.md|ROADMAP\.md|TECH_DEBT\.md|README\.md|\.mcp\.json"
    r"|compliance_guard\.py|test_no_transmit\.py|test_agent_guard\.py"
    r"|\.claude/|\.codex/|(?:^|[\s\"'=/])data/"
)

# Radio hardware tools and the live scanner. Blocked for EVERY session when
# they are the command being run (not when merely named, e.g. `git diff scan.py`).
HARDWARE_TOOL = re.compile(r"^(?:hackrf_\w+|iio_\w+|SoapySDRUtil|rx_sdr|tx_sdr)$")
# Wrappers that run another command. Their own flags and numeric arguments are
# skipped too, so `sudo -n tool`, `env -i tool` and `timeout -k 5 10 tool` are seen.
COMMAND_PREFIXES = frozenset({
    "sudo", "doas", "env", "nohup", "exec", "command", "time", "nice", "ionice",
    "stdbuf", "timeout", "xargs", "setsid", "chrt", "taskset", "unbuffer",
})
PYTHON = re.compile(r"^python(?:3(?:\.\d+)?)?$")
# Scripts that open the SDR. Running them is live hardware work, which is Prin's.
SDR_SCRIPTS = frozenset({
    "scan.py",
    "calibrate_thresholds.py",
    "diagnose_threshold.py",
    "capture_to_vectorstore.py",
    "diagnose_pluto_gain.py",
    "diagnose_fingerprints.py",
    "compare_decode_rate.py",
})
SHELL_WRAPPER = re.compile(r"\b(?:ba|z|fi|da)?sh\s+-l?c\b")
# Any agent touching data/ through Bash with a destructive verb.
DATA_PATH = r"(?:\./)?data(?:/|\s|$)"
DATA_DESTRUCTIVE = re.compile(
    r"\b(?:rm|rmdir|mv|cp|rsync|install|ln|truncate|shred|dd|tee|chmod|chown|find)\b[^;&|]*(?:^|[\s=:'\"/])" + DATA_PATH
)
DATA_REDIRECT = re.compile(r">{1,2}\s*" + DATA_PATH)

# Browser rules (Claude in Chrome and Playwright): pm only, local pages only,
# never page code, typing or uploads.
BROWSER_PREFIX = "mcp__claude-in-chrome__"
BROWSER_LOCAL_HOSTS = ("127.0.0.1", "localhost")
BROWSER_PM_ALLOWED = frozenset({
    "tabs_context_mcp",
    "tabs_create_mcp",
    "tabs_close_mcp",
    "navigate",
    "computer",
    "read_page",
    "get_page_text",
    "find",
    "read_console_messages",
    "read_network_requests",
    "resize_window",
    "browser_batch",
})
BROWSER_COMPUTER_ACTIONS = frozenset({
    "screenshot", "zoom", "scroll", "scroll_to", "hover", "wait",
    "left_click", "double_click", "triple_click", "key",
})
BROWSER_BLOCKED_KEYS = re.compile(r"(?i)\b(ctrl|control|cmd|command|meta|alt|win|windows|super)\b|\+|\bf\d{1,2}\b")

PLAYWRIGHT_PREFIX = "mcp__playwright__"
PLAYWRIGHT_PM_ALLOWED = frozenset({
    "browser_navigate",
    "browser_navigate_back",
    "browser_console_messages",
    "browser_network_requests",
    "browser_snapshot",
    "browser_take_screenshot",
    "browser_find",
    "browser_click",
    "browser_hover",
    "browser_press_key",
    "browser_resize",
    "browser_wait_for",
    "browser_tabs",
    "browser_close",
})
PLAYWRIGHT_FILE_KEYS = ("filename", "path", "outputPath", "output_path")

# Hindsight long-term memory (bank "mimir"). Nobody, in any session, may run a
# destructive memory tool. Named agents: only pm, and only recall and retain.
HINDSIGHT_PREFIX = "mcp__hindsight__"
HINDSIGHT_DESTRUCTIVE = re.compile(r"^(?:delete_|clear_|invalidate_|update_)")
HINDSIGHT_PM_ALLOWED = frozenset({"recall", "retain"})

# Kanzo task board. Named agents: only pm. Nobody deletes cards or projects, and
# next_task is refused because it moves the top todo card to doing by itself.
KANZO_PREFIX = "mcp__kanzo__"
KANZO_BLOCKED = re.compile(r"(?:^|_)(?:delete|archive|remove)(?:_|$)|^next_task$")

# Shell constructs that could write files or run hidden commands.
UNSAFE_SHELL = re.compile(r"[<>`]|\$\(")
HARMLESS_REDIRECTS = re.compile(r"\s2>&1|\s2>/dev/null")
COMMAND_SEPARATORS = re.compile(r"&&|\|\||[;|&\n]")


def split_shell(command: str) -> tuple[list[str], str]:
    """Split a command on UNQUOTED ; | & && || and newlines.

    Returns the segments, plus the command text with quoted contents removed,
    for spotting redirection. Text inside quotes is an argument (for example a
    grep pattern "a|b"), not shell syntax, so it must not split a segment or
    count as a redirect. Command substitution is still dangerous inside double
    quotes, so callers check for `$(` and backticks on the raw command too.
    """
    segments, current, unquoted = [], [], []
    quote = None
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            current.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(command):
                current.append(command[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            current.append(ch)
        elif ch == "\\" and i + 1 < len(command):
            current.append(ch + command[i + 1])
            unquoted.append(" ")
            i += 2
            continue
        elif ch in ";|&\n":
            segments.append("".join(current))
            current = []
            unquoted.append(" ")
            if command[i:i + 2] in ("&&", "||"):
                i += 1
        else:
            current.append(ch)
            unquoted.append(ch)
        i += 1
    segments.append("".join(current))
    if quote:
        segments.append("\x00unterminated-quote")
    return segments, "".join(unquoted)


SUBSTITUTION = re.compile(r"`|\$\(")
# Files holding secrets. No guarded agent may name them in Bash.
SECRET_FILES = re.compile(r"(?:^|[\s/\"'=])\.env\b(?!\.example)")
# The only Codex commands pm may run.
CODEX_EXEC = re.compile(
    r'codex exec (?:resume [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12} '
    r'|-m gpt-6-astra )?-c model_reasoning_effort=(?:low|medium|high|xhigh) '
    r'"[^"\\$`;&|<>\n\r]+"'
)


def command_words(segment: str) -> list[str]:
    """Return a segment's words from the command it actually runs.

    Drops VAR=value assignments and wrapper commands (sudo, env, timeout, xargs
    and so on) together with their flags and numeric arguments.
    """
    words = segment.split()
    while words:
        head = words[0]
        if "=" in head or head.rsplit("/", 1)[-1] in COMMAND_PREFIXES:
            words = words[1:]
            while words and (words[0].startswith("-") or re.fullmatch(r"[\d.]+[smhd]?", words[0])):
                words = words[1:]
            continue
        break
    return words


def runs_codex(command: str) -> bool:
    """Return True if any segment runs the codex CLI (not merely mentions it)."""
    if "codex-companion" in command:
        return True
    segments, _ = split_shell(command)
    for segment in segments:
        words = command_words(re.sub(r"[\"']", " ", segment))
        if words and words[0].rsplit("/", 1)[-1] == "codex":
            return True
        if words and words[0] in ("npx", "bunx", "pnpm", "yarn") and any(
            re.search(r"(?:^|/)codex(?:@[\w.-]+)?$", w) for w in words[1:4]
        ):
            return True
    return False


def block(reason: str) -> None:
    """Block the tool call and tell the agent why."""
    print(f"agent_guard: {reason}", file=sys.stderr)
    sys.exit(2)


def project_relative(raw_path: str, project_dir: Path) -> str | None:
    """Return the path relative to the project root, or None if outside it."""
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_dir / path
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError:
        return None


def code_writer_may_edit(rel: str) -> bool:
    """Return True if code-writer may edit this project-relative path."""
    parts = rel.split("/")
    name = parts[-1]
    if parts[0] in CODE_WRITER_DENY_DIRS or name in CODE_WRITER_DENY_NAMES:
        return False
    return not (name == ".env" or (name.startswith(".env.") and name != ".env.example"))


def governance_edit_problem(tool_input: dict, project_dir: Path, rel: str) -> str | None:
    """Return a reason to block a pm governance-doc Edit, or None if it may go ahead.

    pm may change ROADMAP.md, TECH_DEBT.md and README.md only with targeted
    Edit calls: a non-empty old_string that matches exactly once. Which parts it
    may touch, and when, is governed by pm.md, not by this guard.
    """
    old = tool_input.get("old_string", "")
    if not old:
        return f"{rel} edits need a non-empty old_string"
    if tool_input.get("replace_all"):
        return f"{rel} edits may not use replace_all"
    text = (project_dir / rel).read_text(encoding="utf-8")
    if text.count(old) != 1:
        return f"old_string must match exactly one place in {rel}; widen it"
    return None


def check_file_tool(agent: str, tool: str, tool_input: dict, project_dir: Path) -> None:
    """Apply the per-agent edit rules to Edit, Write, MultiEdit and NotebookEdit."""
    raw = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    rel = project_relative(raw, project_dir)

    if agent in (PLAN_REVIEWER, DEEP_BUG_HUNTER) or agent in CODEX_AGENT_NAMES:
        block(f"{agent} is read-only and may not use {tool}")

    if agent == CODE_WRITER:
        if rel is None:
            block("code-writer may only edit files inside the project")
        if not code_writer_may_edit(rel):
            block(f"code-writer may not edit {rel} (protected file; flag it to Prin)")
        return

    if agent == PM:
        if rel is None:
            block("pm may only write inside .session-memos/ and the governance docs")
        if rel.startswith(MEMO_DIR) and tool in ("Edit", "Write"):
            if tool == "Write" and (project_dir / rel).exists():
                block(f"{rel} already exists; never overwrite a session memo")
            return
        if rel in PM_EDIT_ONLY:
            if tool != "Edit":
                block(f"pm may change {rel} only with targeted Edit calls, never a whole-file write")
            reason = governance_edit_problem(tool_input, project_dir, rel)
            if reason:
                block(reason)
            return
        block(f"pm may not edit {rel}; only .session-memos/, {', '.join(PM_EDIT_ONLY)}")


def names_secret(command: str) -> bool:
    """Return True if a Bash command names a .env file (other than .env.example)."""
    flat = re.sub(r"[\"'\\]", "", command)
    return bool(SECRET_FILES.search(flat)) or bool(re.search(r"\.env\*|\.e\*|\.\*env", flat))


def runs_hardware(command: str) -> bool:
    """Return True if any segment runs a radio tool, the scanner or an SDR script."""
    flat = re.sub(r"[\"'\\]", " ", command)
    for segment in COMMAND_SEPARATORS.split(flat):
        words = command_words(segment)
        if not words:
            continue
        program = words[0].rsplit("/", 1)[-1]
        if HARDWARE_TOOL.match(program) or program in SDR_SCRIPTS:
            return True
        # Interpreters: python [flags] script.py, uv run [flags] [python [flags]] script.py
        if PYTHON.match(program) or program == "uv":
            for word in words[1:]:
                if word.startswith("-") or word == "run" or PYTHON.match(word):
                    continue
                if word.rsplit("/", 1)[-1] in SDR_SCRIPTS:
                    return True
                break
    # `bash -c "<script>"`: be strict and look at every word of the script.
    if SHELL_WRAPPER.search(flat):
        return any(
            HARDWARE_TOOL.match(w.rsplit("/", 1)[-1]) or w.rsplit("/", 1)[-1] in SDR_SCRIPTS
            for w in flat.split()
        )
    return False


def check_every_session_bash(command: str) -> None:
    """Rules that apply to every session, named agent or not."""
    flat = re.sub(r"[\"'\\]", "", command)
    if runs_hardware(command):
        block(
            "no agent may run radio-hardware tools (hackrf_*, iio_*, SoapySDRUtil) or scan.py. "
            "Mimir is receive-only and live hardware checks are Prin's, by hand"
        )
    _, unquoted = split_shell(command)
    if DATA_DESTRUCTIVE.search(flat) or DATA_REDIRECT.search(unquoted):
        block("no agent may remove, move, copy over or overwrite anything under data/")
    if runs_codex(command) and not CODEX_EXEC.fullmatch(command.strip()):
        block(
            "Codex may run only as: codex exec [resume <session id> | -m gpt-6-astra] "
            '-c model_reasoning_effort=low|medium|high|xhigh "<one-line brief>", with no other '
            "flags, and no double quote, backslash, $, backticks, ; & | < > or line breaks in the brief"
        )


def check_bash(agent: str, command: str) -> None:
    """Apply the per-agent Bash rules."""
    if names_secret(command):
        block(f"{agent} may not reach a .env file in Bash, by name, glob or quoting")
    if agent in CODEX_AGENT_NAMES:
        block("the Codex plugin agent is disabled: it skips Codex's sandbox; pm runs codex exec itself")
    if runs_codex(command):
        if agent != PM:
            block(f"{agent} may not run Codex; only pm may, with codex exec")
        return  # form already checked by check_every_session_bash
    if agent == CODE_WRITER:
        if CODE_WRITER_BASH_DENY.search(command):
            block("code-writer may not name protected files or data/ in Bash; use Read to read them")
        for segment in COMMAND_SEPARATORS.split(command):
            if segment.strip().startswith(("git commit", "git push", "git reset", "git checkout", "git switch")):
                block("code-writer may not run git commands that change history or branches")
            if segment.strip().startswith(("graft build", "graft init", "graft upgrade")):
                block("code-writer may not run graft build, init or upgrade; Prin runs them")
        return

    allowed = BASH_ALLOW.get(agent)
    if allowed is None:
        return
    if command.strip() in BASH_EXACT.get(agent, ()):
        return
    cleaned = HARMLESS_REDIRECTS.sub("", command)
    # $( and backticks run commands even inside double quotes; single quotes
    # are literal, so drop single-quoted text before looking.
    if SUBSTITUTION.search(re.sub(r"'[^']*'", "''", cleaned)):
        block(f"{agent} may not use command substitution in Bash")
    segments, unquoted = split_shell(cleaned)
    if re.search(r"[<>]", unquoted):
        block(f"{agent} may not use redirection in Bash")
    for segment in segments:
        if segment.startswith("\x00"):
            block(f"{agent} sent a command with an unterminated quote")
        segment = " ".join(segment.split())
        if not segment:
            continue
        if not any(segment == p or segment.startswith(p + " ") for p in allowed):
            block(f"{agent} may not run '{segment}' (not on its Bash allowlist)")


def check_agent(agent: str, tool_input: dict) -> None:
    """Restrict which subagents can be spawned, and with which model."""
    if agent in TEAM or agent in CODEX_AGENT_NAMES:
        block(f"{agent} may not spawn subagents")
    if agent == PM:
        subagent = tool_input.get("subagent_type", "")
        if subagent not in SPAWNABLE:
            block(
                f"pm may spawn only {', '.join(SPAWNABLE)}, not '{subagent or 'default'}'; "
                "never substitute a built-in agent such as general-purpose"
            )
        model = tool_input.get("model")
        allowed = ALLOWED_MODEL_OVERRIDES.get(subagent, ())
        if model and model not in allowed:
            block(
                f"model '{model}' is not allowed on {subagent}; allowed: "
                f"{', '.join(allowed) or 'none (omit the model parameter)'}"
            )


def local_url_problem(url: str) -> str | None:
    """Return a reason to refuse this navigate target, or None if it is allowed."""
    if url in ("back", "forward"):
        return None
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        return f"navigate needs an explicit http://localhost:<port>/ URL, not '{url}'"
    if parts.username or parts.password:
        return "navigate URLs may not carry credentials"
    if parts.hostname not in BROWSER_LOCAL_HOSTS:
        return f"pm may browse only 127.0.0.1 and localhost, not '{parts.hostname}'"
    return None


def browser_call_problem(tool: str, tool_input: dict) -> str | None:
    """Return a reason to refuse one pm Chrome call, or None if it is allowed."""
    if tool == "browser_batch":
        actions = tool_input.get("actions")
        if not isinstance(actions, list):
            return "browser_batch needs an actions list"
        for item in actions:
            if not isinstance(item, dict):
                return "browser_batch item is not an object"
            name = str(item.get("name", "")).removeprefix(BROWSER_PREFIX)
            if name == "browser_batch":
                return "browser_batch cannot be nested"
            reason = browser_call_problem(name, item.get("input") or {})
            if reason:
                return reason
        return None
    if tool not in BROWSER_PM_ALLOWED:
        return f"pm may not use browser tool '{tool}' (allowed: {', '.join(sorted(BROWSER_PM_ALLOWED))})"
    if tool == "navigate":
        return local_url_problem(str(tool_input.get("url", "")))
    if tool == "computer":
        action = tool_input.get("action", "")
        if action not in BROWSER_COMPUTER_ACTIONS:
            return f"pm may not use the browser action '{action}'"
        if tool_input.get("modifiers"):
            return "pm may not click with modifier keys"
        if action == "key" and BROWSER_BLOCKED_KEYS.search(str(tool_input.get("text", ""))):
            return "pm may not press shortcut or function keys in the browser"
    return None


def playwright_call_problem(tool: str, tool_input: dict) -> str | None:
    """Return a reason to refuse one pm Playwright call, or None if it is allowed."""
    if tool not in PLAYWRIGHT_PM_ALLOWED:
        return f"pm may not use Playwright tool '{tool}' (allowed: {', '.join(sorted(PLAYWRIGHT_PM_ALLOWED))})"
    for key in ("url", "href"):
        if key in tool_input:
            reason = local_url_problem(str(tool_input.get(key, "")))
            if reason:
                return reason
    if tool == "browser_navigate" and "url" not in tool_input:
        return "browser_navigate needs an explicit http://localhost:<port>/ URL"
    for key in PLAYWRIGHT_FILE_KEYS:
        if tool_input.get(key):
            return (
                f"pm may not choose where Playwright saves a file ('{key}'); omit it so "
                "output goes to .playwright-mcp/, which is deleted after the check"
            )
    if tool == "browser_press_key" and BROWSER_BLOCKED_KEYS.search(str(tool_input.get("key", ""))):
        return "pm may not press shortcut or function keys in the browser"
    return None


def check_browser(agent: str, tool: str, tool_input: dict) -> None:
    """Chrome: pm only, local pages only."""
    if agent != PM:
        block(f"{agent or 'this session'} may not use the browser; only pm may, and only on local pages")
    reason = browser_call_problem(tool.removeprefix(BROWSER_PREFIX), tool_input)
    if reason:
        block(reason)


def check_playwright(agent: str, tool: str, tool_input: dict) -> None:
    """Playwright: local pages only for every session; of the named agents only pm."""
    if agent and agent != PM:
        block(f"{agent or 'this session'} may not use the browser; only pm may, and only on local pages")
    reason = playwright_call_problem(tool.removeprefix(PLAYWRIGHT_PREFIX), tool_input)
    if reason:
        block(reason)


def check_hindsight(agent: str, tool: str) -> None:
    """Hindsight: no destructive tools for anyone; named agents get pm's two tools only."""
    short = tool.removeprefix(HINDSIGHT_PREFIX)
    if HINDSIGHT_DESTRUCTIVE.match(short):
        block(f"no session may run the destructive Hindsight tool '{short}'; Prin manages the bank by hand")
    if agent in TEAM or agent in CODEX_AGENT_NAMES:
        block(f"{agent} may not use Hindsight; pm passes recalled context in the task prompt")
    if agent == PM and short not in HINDSIGHT_PM_ALLOWED:
        block(f"pm may use only Hindsight recall and retain, not '{short}'")


def check_kanzo(agent: str, tool: str) -> None:
    """Kanzo board: no session deletes, archives or auto-advances; of the named agents only pm."""
    short = tool.removeprefix(KANZO_PREFIX)
    if KANZO_BLOCKED.search(short):
        block(f"no session may run Kanzo '{short}' (no deleting, archiving or next_task); Prin does that in the board")
    if agent in TEAM or agent in CODEX_AGENT_NAMES:
        block(f"{agent} may not use the Kanzo board; only pm may")


def main() -> None:
    """Read the hook input from stdin and apply the rules for its agent."""
    data = json.load(sys.stdin)
    agent = data.get("agent_type") or ""
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}

    if tool == "Bash":
        check_every_session_bash(str(tool_input.get("command", "")))
    if tool.startswith(HINDSIGHT_PREFIX):
        check_hindsight(agent, tool)
        return
    if tool.startswith(KANZO_PREFIX):
        check_kanzo(agent, tool)
        return
    if tool.startswith(PLAYWRIGHT_PREFIX):
        # Playwright exists here only for checking the local dashboard.
        check_playwright(agent, tool, tool_input)
        return

    if agent != PM and agent not in TEAM and agent not in CODEX_AGENT_NAMES:
        # Plain sessions (Prin's own `claude`) keep the normal permission rules,
        # plus the every-session Bash rules above.
        return
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".")

    if tool in FILE_TOOLS:
        check_file_tool(agent, tool, tool_input, project_dir)
    elif tool == "Bash":
        check_bash(agent, str(tool_input.get("command", "")))
    elif tool == "Agent":
        check_agent(agent, tool_input)
    elif tool.startswith(BROWSER_PREFIX):
        check_browser(agent, tool, tool_input)
    elif tool.startswith(PLAYWRIGHT_PREFIX):
        check_playwright(agent, tool, tool_input)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    # Fail closed: a broken guard must not let calls through.
    except Exception as err:  # noqa: BLE001
        block(f"guard error, call blocked: {err!r}")
