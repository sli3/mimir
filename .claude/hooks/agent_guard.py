#!/usr/bin/env python3
"""agent_guard.py — PreToolUse hook that applies Mimir's per-agent rules.

Adapted from Ravensight's guard. Claude Code permission rules in settings.json
apply to every agent alike. The PreToolUse hook input, however, carries
`agent_type`: the subagent's name when the hook fires inside a subagent, or the
main-thread agent's name when the session runs as a named agent (the `agent`
setting or `claude --agent`). This script reads that field and blocks the
calls each agent is not permitted to make.

These rules apply to EVERY session, named agent or not. The first two hold
because Mimir is receive-only under the Radiocommunications Act 1992 (Cth):
  * no Bash command may run a radio-hardware tool or the live scanner;
  * Codex may run only in pm's three safe `codex exec` forms;
  * no session may run `git push` or define an inline git alias: Prin pushes
    by hand. These checks undo quoting and look through wrappers (env, sudo,
    eval, bash -c...), but a plain session's last line of defence is still
    the permission prompt.

How Bash is checked (2026-11-16 hardening, after Fable's bypass review):
  * Named agents: the guard does not try to model bash. strict_lex() accepts
    only commands whose meaning it can be sure of (no newlines, comments,
    $, backticks, globs, brackets, redirection, or quotes in the middle of a
    word) and blocks everything else.
  * Commands that settings.json allows without a prompt (pytest, npm test,
    git read/add/reset/switch/branch, gh issue, date...) have their
    ARGUMENTS checked too, because options such as --output, --basetemp or
    -R turn a harmless command into a write or a leak. A named agent is
    blocked; a plain session gets a permission prompt instead.
  * The hook runs through run_guard.py, which turns any failure of this file
    (including one that no longer parses) into a block.
  * Second review of 323319a (also Fable): no line breaks at all, no pytest
    @file arguments, an 8000-character cap so every check finishes far inside
    the 10 s hook timeout, quote-aware every-session rules (a commit message
    naming "(scan.py ...)" is prose, not a command), git send-pack counted as a
    push, git read commands and recursive grep kept inside the project and off
    .env, Monitor checked like Bash, and pm's browser keys limited to
    navigation keys.

Known limits, left to the permission prompt: a plain session can still run
code it builds at run time (echo hackrf_info | bash, ${h}_info, python -c);
code-writer writes tests that the suite then runs (review and
tests/test_no_transmit.py are the defence there).

Commits: pm commits on its own at the end of a build, but only with -m
messages, only what it staged by explicit path, and never a guard-rail file
(see COMMIT_GUARD_RAIL_*). Other named agents may not commit. A plain session
(Prin's own `claude`) is handed back to Prin as a permission prompt.

Exit 0 with no output leaves the call to the normal permission rules, so the
global deny and ask rules in settings.json still apply on top of this guard.
Exit 2 blocks the call and shows the stderr message to the agent. Any
unexpected error also exits 2, so a broken guard fails closed.

Codex edits files from its own process, so this guard never sees them. Codex is
held by .codex/config.toml (filesystem), .codex/rules/mimir.rules (commands),
pm's PROTECTED FILE CHECK, and tests/test_no_transmit.py.
"""

import fnmatch
import json
import os
import re
import subprocess
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
# Tools that run a shell command. Monitor streams a command's output; it runs it the same way.
SHELL_TOOLS = ("Bash", "Monitor")

# Per-call model overrides pm may pass, by subagent.
ALLOWED_MODEL_OVERRIDES = {
    CODE_WRITER: ("haiku", "sonnet", "opus"),
}

# pm's write targets. Docs (README.md and docs/**/*.md): targeted Edit on an
# existing file; Write only to create a new file under docs/. Memos: new files only.
README = "README.md"
DOCS_DIR = "docs/"
LEGAL_REFERENCE = "docs/au-legal-reference.md"
MEMO_DIR = ".session-memos/"

# Git. Global options that take a separate value, so the subcommand after them
# is still found (`git -C . push`, `git -c x=y push`).
GIT_GLOBAL_OPTS_WITH_ARG = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix",
})
# Staged paths that stop pm's commit: Prin commits these himself.
COMMIT_GUARD_RAIL_DIRS = (".claude/", ".codex/", "data/", MEMO_DIR)
COMMIT_GUARD_RAIL_FILES = frozenset({
    "AGENTS.md",
    "CLAUDE.md",
    ".mcp.json",
    "core/legal/compliance_guard.py",
    "tests/test_no_transmit.py",
    "tests/test_agent_guard.py",
})

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
        "git commit",  # further limited by check_pm_git
        "git switch",
        "git checkout -b",
        "git branch",  # branch -D still prompts: "ask" rule in settings.json
        "gh issue create",
        "gh issue edit",
        "gh issue comment",
        "gh issue close",
        "gh issue reopen",
        "gh issue list",
        "gh issue view",
        "gh label list",
        "gh label create",
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
DEV_SERVER_START = "npm run dev --prefix dashboard/frontend"
# Demo replay only. --demo swaps in DemoDevice and refuses --device. Only the
# capture file names vary; each must be a plain capture_<freq>hz_<date>_<time>
# name under data/captures/, so no flag, separator or path trick can match.
_CAPTURE = r"data/captures/capture_\d+hz_\d{8}_\d{6}\.sigmf-meta"
DEMO_SERVER_START = re.compile(
    r"env PYTHONPATH=\. \.venv-scan/bin/python -s scan\.py --demo "
    rf"--demo-files {_CAPTURE}(?: --demo-files-adsb {_CAPTURE})?"
)
BASH_EXACT = {
    PM: ("rm -rf .playwright-mcp", DEV_SERVER_PROBE, DEV_SERVER_START),
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
CODE_WRITER_DENY_DIRS = {".claude", ".codex", "data", ".session-memos", ".git"}
CODE_WRITER_BASH_DENY = re.compile(
    r"AGENTS\.md|CLAUDE\.md|ROADMAP\.md|TECH_DEBT\.md|README\.md|\.mcp\.json"
    r"|compliance_guard\.py|test_no_transmit\.py|test_agent_guard\.py"
    r"|\.claude/|\.codex/|\.git/|(?:^|[\s\"'=/])data/"
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
# Verbs that delete or replace files. With loose_segments, any argument whose
# first path part is data/ or a glob that matches it (dat?, d*) is refused.
DATA_DESTRUCTIVE_VERBS = frozenset({
    "rm", "rmdir", "mv", "cp", "rsync", "install", "ln", "truncate", "shred", "dd",
    "tee", "chmod", "chown", "find", "unlink", "gzip", "bzip2", "xz", "zstd", "srm",
})
DATA_REDIRECT = re.compile(r">{1,2}\s*" + DATA_PATH)

# Browser rules (Claude in Chrome and Playwright): pm only, local pages only,
# never page code, typing or uploads.
BROWSER_PREFIX = "mcp__claude-in-chrome__"
BROWSER_LOCAL_HOSTS = ("127.0.0.1", "localhost")
# pm checks only the Vite dev server (pm.md BROWSER CHECKS).
PM_BROWSER_PORTS = frozenset({5173})
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
# The only keys pm may press: navigation, never characters (which would type).
BROWSER_ALLOWED_KEYS = frozenset({
    "enter", "return", "escape", "esc", "tab", "pagedown", "pageup", "page_down",
    "page_up", "home", "end", "arrowup", "arrowdown", "arrowleft", "arrowright",
    "up", "down", "left", "right",
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
# --- Strict lexing (named agents) --------------------------------------------
# Characters allowed outside quotes. Everything else (#, $, `, globs, brackets,
# braces, redirection, !, backslash, a lone &) makes the command unparseable.
SAFE_UNQUOTED = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./=:,@%+^~"
)
# A quoted section may start a word, or follow `--opt=` or `+` (date formats).
QUOTE_PREFIX = re.compile(r"(?:[-\w.]*=[\w:]*|\+)?")  # also --pretty=format:"..."
# Characters never allowed inside double quotes (they expand or escape).
DOUBLE_QUOTE_BANNED = frozenset('$`\n\r')
# A backslash in double quotes is literal unless it escapes one of these.
DOUBLE_QUOTE_ESCAPED = frozenset('"$`\\\n')


class Unparseable(Exception):
    """A command whose bash meaning the guard cannot be sure of."""


# Wrappers that run another command. When one appears, every later word is
# treated as a possible command, because their flags and arguments vary.
LOOSE_WRAPPERS = frozenset({
    "sudo", "doas", "env", "nohup", "exec", "command", "builtin", "time", "nice",
    "ionice", "stdbuf", "timeout", "xargs", "setsid", "chrt", "taskset",
    "unbuffer", "eval", "source", ".", "bash", "sh", "zsh", "fish", "dash", "ksh",
    "watch", "flock", "then", "do", "else", "!", "coproc", "npx", "bunx",
    "strace", "ltrace", "script", "valgrind", "gdb", "perf", "unshare", "firejail",
    "systemd-run", "runuser", "su", "pkexec", "busybox", "parallel", "nsenter",
    "chroot", "setarch", "catchsegv", "xdg-open",
})
# find actions that run a command or delete what find matched.
FIND_ACTIONS = frozenset({"-exec", "-execdir", "-ok", "-okdir", "-delete"})
# Every hardware tool name, so a glob such as hackrf_inf? can be matched against them.
HARDWARE_NAMES = (
    "hackrf_info", "hackrf_transfer", "hackrf_sweep", "hackrf_spiflash", "hackrf_cpldjtag",
    "hackrf_debug", "hackrf_clock", "hackrf_operacake", "iio_info", "iio_attr",
    "iio_readdev", "iio_writedev", "iio_reg", "SoapySDRUtil", "rx_sdr", "tx_sdr",
)
# Git subcommands that send commits to a remote.
GIT_PUSH_SUBCOMMANDS = frozenset({"push", "send-pack", "http-push"})
# Longest Bash command any session may send: the guard's checks must finish
# well inside the 10 s hook timeout.
MAX_COMMAND_CHARS = 8000
# Module names that open the SDR when run with python -m.
SDR_MODULES = frozenset({"scan"} | {"tools." + name.removesuffix(".py") for name in SDR_SCRIPTS})
REDIRECT_WORD = re.compile(r"^\d*(?:>>?|<)&?\d*$|^\d*>&\d+$|^&>")

# Git subcommands code-writer may run: reading only.
GIT_READ_SUBCOMMANDS = frozenset({
    "status", "diff", "log", "show", "grep", "ls-files", "blame", "rev-parse",
})
# Long options of git read commands that write a file, read outside the repo
# or run an external program. Git accepts abbreviations, so match prefixes.
GIT_READ_BAD_PREFIXES = ("--ou", "--no-ind", "--ext", "--textc")
GIT_BRANCH_READ_FLAGS = frozenset({
    "--list", "-l", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose",
    "--show-current",
})
BRANCH_NAME = re.compile(r"^[A-Za-z0-9][\w./-]*$")

# pytest options pm and the team may pass. Anything else (--basetemp,
# --junitxml, -o, -c, --rootdir, -p <plugin>...) can write files or load code.
PYTEST_FLAGS = frozenset({
    "-q", "-qq", "--quiet", "-v", "-vv", "--verbose", "-x", "--exitfirst", "-s",
    "-l", "--showlocals", "-ra", "-rA", "-rf", "-rs", "--lf", "--last-failed",
    "--ff", "--failed-first", "--nf", "--co", "--collect-only", "--no-header",
})
PYTEST_FLAGS_WITH_VALUE = frozenset({"-k", "-m", "--tb", "--maxfail", "--durations", "-p", "-W"})
TEST_PATH = re.compile(r"^tests(?:/[\w.-]+)*(?:::[\w\[\].:-]+)*$")

# gh: (needs one issue number, allowed options). Options not listed, including
# -R/--repo, -F/--body-file, --web, --editor, --delete-last and --edit-last,
# are refused, as are URLs in place of a number.
GH_SPEC = {
    ("issue", "create"): ("none", frozenset({"--title", "-t", "--body", "-b", "--label", "-l"})),
    ("issue", "edit"): ("number", frozenset({"--title", "-t", "--body", "-b", "--add-label", "--remove-label"})),
    ("issue", "comment"): ("number", frozenset({"--body", "-b"})),
    ("issue", "close"): ("number", frozenset({"--comment", "-c", "--reason", "-r"})),
    ("issue", "reopen"): ("number", frozenset({"--comment", "-c"})),
    ("issue", "list"): ("none", frozenset({"--state", "-s", "--label", "-l", "--limit", "-L", "--search", "-S", "--json", "--jq", "-q"})),
    ("issue", "view"): ("number", frozenset({"--json", "--jq", "-q", "--comments"})),
    ("label", "list"): ("none", frozenset({"--limit", "-L", "--json", "--jq", "-q"})),
    ("label", "create"): ("name", frozenset({"--color", "-c", "--description", "-d"})),
}
GH_BOOL_FLAGS = frozenset({"--comments"})
LABEL_NAME = re.compile(r"^[\w.:-]+$")

# Commands that read files. Named agents may point them only inside the project.
READ_COMMANDS = frozenset({"cat", "head", "tail", "grep", "stat", "ls", "wc"})

UNSAFE_SHELL = re.compile(r"[<>`]|\$\(")
# [ \t] not \s: \s would also swallow a newline and hide a second command (Fable, 323319a).
HARMLESS_REDIRECTS = re.compile(r"[ \t]2>&1|[ \t]2>/dev/null")
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
    for words in rule_segments(command)[0]:
        for start in command_starts(words):
            if re.search(r"(?:^|/)codex(?:@[\w.-]+)?$", words[start]):
                return True
    return False


def block(reason: str) -> None:
    """Block the tool call and tell the agent why."""
    print(f"agent_guard: {reason}", file=sys.stderr)
    sys.exit(2)


def ask(reason: str) -> None:
    """Hand the call to Prin as a permission prompt, whatever the allow rules say."""
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": f"agent_guard: {reason}",
    }}))
    sys.exit(0)


def strict_lex(command: str) -> list[list[str]]:
    """Split a command into segments of words, or raise Unparseable.

    Accepts only what has one obvious bash meaning: plain words from
    SAFE_UNQUOTED, whole-word single or double quotes (double quotes without
    $, backticks or backslashes), and the separators ; | && ||. Comments,
    newlines, substitution, globs, brackets, braces, redirection and a quote in
    the middle of a word (hack''rf) are all refused, so the words returned are
    exactly the words bash would run. The harmless 2>&1 and 2>/dev/null are
    removed first.
    """
    if "\n" in command or "\r" in command:
        raise Unparseable("a line break (one command per call)")
    text = HARMLESS_REDIRECTS.sub("", command)
    segments: list[list[str]] = [[]]
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in " \t":
            i += 1
            continue
        if ch in ";|&":
            pair = text[i:i + 2]
            if pair in ("&&", "||"):
                i += 2
            elif ch == "&":
                raise Unparseable("a lone & (background job)")
            else:
                i += 1
            if not segments[-1]:
                raise Unparseable("an empty command between separators")
            segments.append([])
            continue
        # A word: unquoted characters, optionally one quoted section that
        # starts the word or follows `--opt=` or `+`, then the word ends.
        word = []
        while i < n and text[i] not in " \t;|&":
            ch = text[i]
            if ch in "'\"":
                if not QUOTE_PREFIX.fullmatch("".join(word)):
                    raise Unparseable("a quote in the middle of a word")
                end = text.find(ch, i + 1)
                if end == -1:
                    raise Unparseable("an unterminated quote")
                body = text[i + 1:end]
                if ch == '"' and any(
                    body[k] == "\\" and (k + 1 == len(body) or body[k + 1] in DOUBLE_QUOTE_ESCAPED)
                    for k in range(len(body))
                ):
                    raise Unparseable("a backslash escape inside double quotes")
                if "\n" in body or "\r" in body:
                    raise Unparseable("a line break inside quotes")
                if ch == '"' and any(c in DOUBLE_QUOTE_BANNED for c in body):
                    raise Unparseable("$ or a backtick inside double quotes")
                word.append(body)
                i = end + 1
                if i < n and text[i] not in " \t;|&":
                    raise Unparseable("text straight after a closing quote")
                break
            if ch not in SAFE_UNQUOTED:
                raise Unparseable(f"the character {ch!r} outside quotes")
            word.append(ch)
            i += 1
        segments[-1].append("".join(word))
    if not segments[-1]:
        if len(segments) == 1:
            raise Unparseable("an empty command")
        raise Unparseable("a trailing separator")
    return segments


BRACE = re.compile(r"\{([^{}]*,[^{}]*)\}")


def expand_braces(word: str, limit: int = 64) -> list[str]:
    """Expand bash brace lists (da{t,}a -> data daa), so built-up names are seen."""
    match = BRACE.search(word)
    if not match or limit <= 0:
        return [word]
    out = []
    for part in match.group(1).split(","):
        out.extend(expand_braces(word[:match.start()] + part + word[match.end():], limit // 2))
    return out[:limit]


def loose_segments(command: str) -> list[list[str]]:
    """Split any command into word lists for the every-session checks.

    Never fails. Quotes and backslashes are removed (so hack''rf_info reads as
    hackrf_info), substitution and brackets become separators, and redirection
    words are dropped (so `git 2>&1 push` reads as git push).
    """
    flat = re.sub(r"[\"'\\]", "", command)
    flat = " ".join(w for token in flat.split(" ") for w in expand_braces(token))
    flat = re.sub(r"\$\(|`|[(){}]|<\(|>\(", ";", flat)
    # Redirections that contain & (2>&1, >&2, &>file) must go before splitting on &.
    flat = re.sub(r"\d*>&\d*|&>>?", " ", flat)
    result = []
    for segment in COMMAND_SEPARATORS.split(flat):
        words = [w for w in segment.split() if not REDIRECT_WORD.match(w)]
        if words:
            result.append(words)
    return result


def rule_segments(command: str) -> tuple[list[list[str]], bool]:
    """Word lists for the every-session rules, and whether the command lexed strictly.

    When strict_lex succeeds, quoted text stays one word, so a commit message
    or a Codex brief that mentions (scan.py ...) or "find ... data/" is prose,
    not a command. A segment that runs a wrapper (bash -c, eval, env...) is
    re-read loosely, because the wrapper's argument is itself a command. When
    strict_lex fails, everything is read loosely.
    """
    try:
        strict = strict_lex(command)
    except Unparseable:
        return loose_segments(command), False
    result = []
    for words in strict:
        starts = command_starts(words)
        if len(starts) > 1 or (starts and starts[0] > 0 and words[starts[0] - 1] in LOOSE_WRAPPERS):
            result.extend(loose_segments(" ".join(words)))
        else:
            result.append(words)
    return result, True


def command_starts(words: list[str]) -> list[int]:
    """Return the indexes of words that may be the command a segment runs.

    VAR=value assignments are skipped. After a wrapper (env, sudo, eval,
    timeout, bash...) every later word counts, because the guard cannot know
    how many arguments the wrapper's own flags take.
    """
    i = 0
    while i < len(words) and re.match(r"^[A-Za-z_]\w*=", words[i]):
        i += 1
    if i >= len(words):
        return []
    head = words[i].rsplit("/", 1)[-1]
    rest = words[i + 1:]
    if (
        head in LOOSE_WRAPPERS
        or (head == "uv" and rest[:1] == ["run"])                       # uv run <anything>
        or (head == "npm" and rest[:1] in (["exec"], ["x"]))            # npm exec <pkg>
        or (head in ("pnpm", "yarn") and rest[:1] in (["dlx"], ["exec"]))
        or (head == "find" and any(w in FIND_ACTIONS for w in rest))    # find -exec <cmd>
    ):
        return list(range(i + 1, len(words)))
    return [i]


def command_heads(words: list[str]) -> list[int]:
    """Like command_starts, but always including the segment's own command (find, uv...)."""
    i = 0
    while i < len(words) and re.match(r"^[A-Za-z_]\w*=", words[i]):
        i += 1
    return sorted({i, *command_starts(words)}) if i < len(words) else []


def git_subcommand(words: list[str]) -> str | None:
    """Return the git subcommand a command's words run (push, commit...), or None if not git."""
    if not words or words[0].rsplit("/", 1)[-1] != "git":
        return None
    i = 1
    while i < len(words):
        word = words[i]
        if word in GIT_GLOBAL_OPTS_WITH_ARG:
            i += 2
        elif word.startswith("-") or REDIRECT_WORD.match(word):
            i += 1
        else:
            return word
    return None


def runs_git(command: str, subcommand: str | frozenset) -> bool:
    """Return True if any segment runs `git <subcommand>`, however it is spelt or wrapped."""
    wanted = {subcommand} if isinstance(subcommand, str) else subcommand
    for words in rule_segments(command)[0]:
        for start in command_starts(words):
            if git_subcommand(words[start:]) in wanted:
                return True
    return False


def points_at_data(arg: str) -> bool:
    """Return True if an argument's first path part is data, or a glob that matches data.

    Absolute and ~ paths into the project count too (~/Repository/mimir/dat*).
    """
    path = os.path.expanduser(arg.split("=", 1)[-1])
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if path.startswith("/"):
        root = root.rstrip("/") + "/"
        if not path.startswith(root):
            # Outside this checkout (another clone, a moved repo): any data folder counts.
            return any(fnmatch.fnmatchcase("data", part) for part in path.split("/") if part)
        path = path[len(root):]
    while path.startswith("./"):
        path = path[2:]
    first = path.split("/", 1)[0]
    return bool(first) and fnmatch.fnmatchcase("data", first)


def searches_project_root(arg: str) -> bool:
    """Return True if a path is the project root itself (., ./, the absolute path)."""
    root = (os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).rstrip("/")
    path = os.path.expanduser(arg).rstrip("/") or "/"
    return path in (".", "", root) or os.path.normpath(path) == "."


def touches_data_destructively(command: str) -> bool:
    """Return True if a command could delete or replace data/: Prin's captures, gitignored.

    Catches a destructive verb aimed at data/ (also through dat? or d*), a
    destructive verb after `cd data`, and git clean -x/-X, which deletes
    ignored files and so all of data/.
    """
    in_data = False
    for words in rule_segments(command)[0]:
        for start in command_heads(words):
            verb = words[start].rsplit("/", 1)[-1]
            args = words[start + 1:]
            if verb in ("cd", "pushd") and args and points_at_data(args[-1]):
                in_data = True
            if verb == "find" and any(a in FIND_ACTIONS for a in args):
                roots = [a for a in args[:next((k for k, a in enumerate(args) if a.startswith("-")), len(args))]]
                if in_data or not roots or any(points_at_data(a) or searches_project_root(a) for a in roots):
                    return True
            if verb in DATA_DESTRUCTIVE_VERBS and verb != "find":
                if in_data or any(points_at_data(a) for a in args):
                    return True
            if verb in ("sed", "perl") and any(a.startswith("-i") for a in args):
                if in_data or any(points_at_data(a) for a in args):
                    return True
            if is_python(words[start]) and "-c" in args:
                code = " ".join(args[args.index("-c") + 1:])
                if re.search(r"rmtree|remove|unlink|rename|replace|truncate", code) and re.search(r"\bdata\b", code):
                    return True
            if git_subcommand(words[start:]) == "stash" and any(a in ("-a", "--all") for a in args):
                return True
            if git_subcommand(words[start:]) == "clean":
                flags = "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))
                if "x" in flags.lower() or any(a.startswith("--") and "ignored" in a for a in args):
                    return True
    return False


def defines_git_alias(command: str) -> bool:
    """Return True if a git command defines an alias inline (git -c alias.p=push p)."""
    for words in rule_segments(command)[0]:
        for start in command_starts(words):
            if git_subcommand(words[start:]) is None:
                continue
            rest = [w.lower() for w in words[start + 1:]]
            if any(w.startswith("alias.") or w.startswith("-calias.") for w in rest):
                return True
    return False


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


def is_pm_doc(rel: str) -> bool:
    """Return True for the docs pm may change: README.md and Markdown under docs/."""
    if rel == LEGAL_REFERENCE:
        return False  # Prin's, by AGENTS.md; settings.json denies it too
    return rel == README or (rel.startswith(DOCS_DIR) and rel.endswith(".md"))


def governance_edit_problem(tool_input: dict, project_dir: Path, rel: str) -> str | None:
    """Return a reason to block a pm doc Edit, or None if it may go ahead.

    pm may change README.md and docs/**/*.md only with targeted Edit calls: a
    non-empty old_string that matches exactly once. Which parts it may touch,
    and when, is governed by pm.md, not by this guard.
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
            block("pm may only write inside .session-memos/, README.md and docs/")
        if rel.startswith(MEMO_DIR) and tool in ("Edit", "Write"):
            if not rel.endswith(".md"):
                block("pm may write only Markdown (.md) files in .session-memos/")
            if tool == "Write" and (project_dir / rel).exists():
                block(f"{rel} already exists; never overwrite a session memo")
            return
        if is_pm_doc(rel):
            if tool == "Write":
                if rel.startswith(DOCS_DIR) and not (project_dir / rel).exists():
                    return  # a new doc
                block(f"pm may change {rel} only with targeted Edit calls; Write only creates new files under docs/")
            if tool != "Edit":
                block(f"pm may change {rel} only with targeted Edit calls")
            reason = governance_edit_problem(tool_input, project_dir, rel)
            if reason:
                block(reason)
            return
        block(f"pm may not edit {rel}; only .session-memos/, README.md and docs/**/*.md")


def names_secret(command: str) -> bool:
    """Return True if a Bash command names a .env file (other than .env.example).

    Quoted prose (a word with spaces: a commit message, a brief) may mention
    .env; a word that is a path, or a glob that could match .env, may not.
    """
    segments, strict = rule_segments(command)
    if not strict:
        flat = re.sub(r"[\"'\\]", "", command)
        return bool(SECRET_FILES.search(flat)) or bool(re.search(r"\.e[\w*?\[\]]*[*?\[]|\.[*?]env", flat))
    for words in segments:
        for word in words:
            if " " in word:
                continue
            if SECRET_FILES.search(word) or re.search(r"\.e[\w*?\[\]]*[*?\[]|\.[*?\[]", word):
                return True
    return False


def is_python(word: str) -> bool:
    """Return True for python, python3, python3.11 and venv paths to them, and uv."""
    name = word.rsplit("/", 1)[-1]
    return bool(PYTHON.match(name)) or name == "uv"


def python_runs_sdr(args: list[str]) -> bool:
    """Return True if a python or uv command's arguments run an SDR script or module.

    Every argument is looked at, because flags such as -W, -X or --with take a
    value and would otherwise hide the script that follows.
    """
    for k, word in enumerate(args):
        if word.rsplit("/", 1)[-1] in SDR_SCRIPTS:
            return True
        module = None
        if word == "-m" and k + 1 < len(args):
            module = args[k + 1]
        elif word.startswith("-m") and len(word) > 2 and not word.startswith("--"):
            module = word[2:]
        if module == "py_compile":
            return False  # compiles the files named after it; runs none of them
        if module in SDR_MODULES:
            return True
        # -c code: loose_segments has removed its quotes, so read all that follows.
        if word == "-c" and re.search(
            r"SoapySDR|hackrf|\bimport scan\b|\bfrom scan\b|pluto|adi\.", " ".join(args[k + 1:]), re.I
        ):
            return True
    return False


def runs_hardware(command: str) -> bool:
    """Return True if any segment runs a radio tool, the scanner or an SDR script.

    Works on loose_segments, so quotes, brackets, substitution, redirection and
    wrappers (env -u X, timeout -k 5 10, eval, bash -c...) do not hide the tool.
    """
    for words in rule_segments(command)[0]:
        # Files named after `-m py_compile` are compiled, not run.
        compiled_from = next(
            (k + 2 for k in range(len(words) - 1) if words[k] == "-m" and words[k + 1] == "py_compile"),
            len(words),
        )
        for start in command_starts(words):
            program = words[start].rsplit("/", 1)[-1]
            if HARDWARE_TOOL.match(program) or (program in SDR_SCRIPTS and start < compiled_from):
                return True
            if any(c in program for c in "*?[") and any(
                fnmatch.fnmatchcase(name, program) for name in (*HARDWARE_NAMES, *SDR_SCRIPTS)
            ):
                return True
            if is_python(words[start]) and python_runs_sdr(words[start + 1:]):
                return True
    return False


def check_every_session_bash(command: str) -> None:
    """Rules that apply to every session, named agent or not."""
    if len(command) > MAX_COMMAND_CHARS:
        block(f"command longer than {MAX_COMMAND_CHARS} characters; split it up")
    flat = re.sub(r"[\"'\\]", "", command)
    strict = rule_segments(command)[1]
    if runs_codex(command) and not CODEX_EXEC.fullmatch(command.strip()):
        block(
            "Codex may run only as: codex exec [resume <session id> | -m gpt-6-astra] "
            '-c model_reasoning_effort=low|medium|high|xhigh "<one-line brief>", with no other '
            "flags, and no double quote, backslash, $, backticks, ; & | < > or line breaks in the brief"
        )
    if runs_hardware(command):
        block(
            "no agent may run radio-hardware tools (hackrf_*, iio_*, SoapySDRUtil) or scan.py. "
            "Mimir is receive-only and live hardware checks are Prin's, by hand"
        )
    # The broad regex nets read quoted prose as commands, so they run only when
    # the command could not be lexed strictly (a strict command has no redirection).
    if not strict:
        # flat, not split_shell's unquoted text: a quoted target ("data/x") is still a target.
        if DATA_DESTRUCTIVE.search(flat) or DATA_REDIRECT.search(flat):
            block("no agent may remove, move, copy over or overwrite anything under data/")
    if touches_data_destructively(command):
        block("no session may remove, move, compress or overwrite anything under data/")
    if runs_git(command, GIT_PUSH_SUBCOMMANDS):
        block("no session may push (git push, send-pack, http-push); Prin pushes by hand")
    if defines_git_alias(command):
        block("no session may define a git alias inline (-c alias.*)")


def is_guard_rail(rel: str) -> bool:
    """Return True for a path pm may never commit: Prin commits these himself."""
    name = rel.rsplit("/", 1)[-1]
    return (
        rel.startswith(COMMIT_GUARD_RAIL_DIRS)
        or rel in COMMIT_GUARD_RAIL_FILES
        or name == ".env"
        or (name.startswith(".env.") and name != ".env.example")
    )


def staged_paths(project_dir: Path) -> list[str]:
    """List every staged path, both sides of a rename. Raises if git fails."""
    result = subprocess.run(
        ["git", "-C", str(project_dir), "diff", "--cached", "--name-only", "--no-renames", "-z"],
        capture_output=True, text=True, timeout=5, check=True,
    )
    return [p for p in result.stdout.split("\0") if p]


def check_commit_args(args: list[str]) -> None:
    """pm commits with -m messages (and -q) only: no -a, --amend, paths or other options."""
    has_message = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-m", "--message") and i + 1 < len(args):
            has_message = True
            i += 2
        elif arg.startswith("--message="):
            has_message = True
            i += 1
        elif arg in ("-q", "--quiet"):
            i += 1
        else:
            block(
                f"pm may commit only with -m messages and -q, not '{arg}' "
                "(no -a, --amend, paths or other options; stage by explicit path first)"
            )
    if not has_message:
        block("pm commits need a -m message")


def inside_project(raw: str, project_dir: Path) -> bool:
    """Return True if a path stays inside the project once resolved (no ~, no escape)."""
    if raw.startswith("~"):
        return False
    return project_relative(raw, project_dir) is not None


def pytest_problem(args: list[str], project_dir: Path) -> str | None:
    """Allow only known pytest flags and test paths under tests/."""
    i = 0
    while i < len(args):
        arg = args[i]
        name, eq, value = arg.partition("=")
        if arg in PYTEST_FLAGS:
            i += 1
            continue
        if arg.startswith("@"):
            return "pytest may not read arguments from a file (@file)"
        if name in PYTEST_FLAGS_WITH_VALUE:
            if not eq:
                if i + 1 >= len(args):
                    return f"pytest {name} needs a value"
                value = args[i + 1]
                i += 1
            if value.startswith("@"):
                return "pytest may not read arguments from a file (@file)"
            if name == "-p" and not value.startswith("no:"):
                return "pytest -p may only disable a plugin (-p no:<name>)"
            i += 1
            continue
        if arg.startswith("-"):
            return f"pytest option {arg} is not allowed (it can write files or load code)"
        path = arg.split("::", 1)[0].rstrip("/") or arg
        if not TEST_PATH.match(arg.rstrip("/")) or ".." in path.split("/") or not inside_project(path, project_dir):
            return f"pytest may only run paths under tests/, not {arg}"
        i += 1
    return None


def git_read_problem(args: list[str], project_dir: Path) -> str | None:
    """git status/diff/log/show: refuse options that write a file or run a program,
    and paths outside the project (git diff then reads them with an implied --no-index)."""
    for arg in args:
        if arg.startswith(GIT_READ_BAD_PREFIXES):
            return f"git option {arg} is not allowed (it writes a file, reads outside the repo or runs a program)"
        if arg.startswith(("/", "~")) or ".." in arg.split("/"):
            if ".." in arg and re.match(r"^[\w./-]*\.\.\.?[\w./-]*$", arg) and not arg.startswith(("/", "~", "../")):
                continue  # a revision range such as origin/main..main
            if not inside_project(arg, project_dir):
                return f"git may only read inside the project, not {arg}"
    return None


def git_add_problem(args: list[str], project_dir: Path) -> str | None:
    """git add: files by explicit path only; no options, globs, pathspec magic or directories."""
    paths = args[1:] if args[:1] == ["--"] else args
    if not paths:
        return "git add needs explicit file paths"
    for path in paths:
        if path.startswith("-"):
            return f"git add option {path} is not allowed; stage files by explicit path"
        if any(c in path for c in "*?[") or path.startswith(":"):
            return f"git add may not use globs or pathspec magic ({path})"
        if os.path.normpath(path) in (".", "") or not inside_project(path, project_dir):
            return f"git add must name files inside the project, not {path}"
        if (project_dir / path).is_dir():
            return f"git add must name files, not a directory ({path})"
    return None


def git_branch_problem(sub: str, args: list[str]) -> str | None:
    """git switch/checkout/branch: list, switch to or create a branch; nothing destructive."""
    if sub == "switch":
        if len(args) == 1 and BRANCH_NAME.match(args[0]):
            return None
        if len(args) == 2 and args[0] in ("-c", "--create") and BRANCH_NAME.match(args[1]):
            return None
        return "git switch may only switch to a branch or create one with -c <name>"
    if sub == "checkout":
        if len(args) == 2 and args[0] == "-b" and BRANCH_NAME.match(args[1]):
            return None
        return "git checkout may only create a branch with -b <name>"
    if all(a in GIT_BRANCH_READ_FLAGS for a in args):
        return None
    if len(args) == 1 and BRANCH_NAME.match(args[0]):
        return None
    return "git branch may only list branches or create one; no delete, move, copy or force"


def gh_problem(words: list[str]) -> str | None:
    """gh issue and gh label on this repo only: known options, inline text, numbers not URLs."""
    spec = GH_SPEC.get(tuple(words[1:3]))
    if spec is None:
        return f"gh {' '.join(words[1:3])} is not allowed"
    positional, allowed = spec
    found = []
    i = 3
    while i < len(words):
        word = words[i]
        if word.startswith("-"):
            name, eq, _ = word.partition("=")
            if name not in allowed:
                return f"gh option {word} is not allowed"
            if name not in GH_BOOL_FLAGS and not eq:
                if i + 1 >= len(words):
                    return f"gh {name} needs a value"
                i += 1
        else:
            found.append(word)
        i += 1
    if positional == "none" and found:
        return f"gh {' '.join(words[1:3])} takes no positional argument, got {found[0]}"
    if positional == "number" and (len(found) != 1 or not found[0].isdigit()):
        return "gh issue commands need exactly one issue number from this repo (no URLs)"
    if positional == "name" and (len(found) != 1 or not LABEL_NAME.match(found[0])):
        return "gh label create needs exactly one plain label name"
    return None


def auto_allowed_problem(words: list[str], project_dir: Path) -> str | None:
    """Check the arguments of a command that settings.json runs without a prompt.

    Returns a reason when the arguments go beyond safe use, or None. Commands
    outside these families are left to the allowlists and permission rules.
    """
    if words[:3] == ["uv", "run", "pytest"]:
        return pytest_problem(words[3:], project_dir)
    if words[:5] == ["uv", "run", "python", "-m", "pytest"]:
        return pytest_problem(words[5:], project_dir)
    if words[:5] == ["uv", "run", "python", "-m", "py_compile"]:
        for path in words[5:]:
            if path.startswith("-") or not path.endswith(".py") or not inside_project(path, project_dir):
                return f"py_compile may only take .py files inside the project, not {path}"
            if (project_relative(path, project_dir) or "").split("/")[0] in CODE_WRITER_DENY_DIRS:
                return f"py_compile may not write under {path.split('/')[0]}/"
        return None
    if words[:2] == ["npm", "run"] and words[3:5] == ["--prefix", "dashboard/frontend"]:
        rest = words[5:]
        if not rest:
            return None
        if words[2] == "test" and rest[0] == "--" and all(not w.startswith("-") for w in rest[1:]):
            return None
        return "npm test and lint take no extra options (only test file names after --)"
    if words[:1] == ["git"]:
        rest = words[1:]
        if rest[:1] == ["--no-pager"]:
            rest = rest[1:]
        sub, args = (rest[0], rest[1:]) if rest else ("", [])
        if sub in ("status", "diff", "log", "show"):
            return git_read_problem(args, project_dir)
        if sub == "add":
            return git_add_problem(args, project_dir)
        if sub == "reset":
            if args[:2] == ["-q", "--"] and len(args) > 2 and all(not a.startswith("-") for a in args[2:]):
                return None
            return "git reset may only unstage paths: git reset -q -- <paths>"
        if sub in ("switch", "checkout", "branch"):
            return git_branch_problem(sub, args)
        return None
    if words[:1] == ["gh"] and words[1:2] in (["issue"], ["label"]):
        return gh_problem(words)
    if words[:1] == ["date"]:
        if all(w.startswith("+") for w in words[1:]):
            return None
        return "date may only print a +FORMAT"
    if words[:3] == ["mkdir", "-p", ".session-memos"] and len(words) > 3:
        return "mkdir -p may only create .session-memos"
    return None


GREP_OPTS_WITH_VALUE = frozenset({"-e", "-f", "-m", "-A", "-B", "-C", "-d", "-D", "--regexp", "--file"})


def grep_problem(words: list[str]) -> str | None:
    """A recursive grep must name a subfolder or file: from the root it would read .env."""
    args = words[1:]
    recursive, pattern_given, paths = False, False, []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            paths.extend(args[i + 1:])
            break
        if arg.startswith("--"):
            name, _, value = arg.partition("=")
            if name in ("--recursive", "--dereference-recursive") or (name == "--directories" and value == "recurse"):
                recursive = True
            if name in ("--regexp", "--file"):
                pattern_given = True
        elif arg.startswith("-") and len(arg) > 1:
            letters = arg[1:]
            if "r" in letters or "R" in letters:
                recursive = True
            if letters[-1] in "efmABCdD" and len(letters) == 1 or arg in GREP_OPTS_WITH_VALUE:
                if arg in ("-e", "-f"):
                    pattern_given = True
                if arg == "-d" and i + 1 < len(args) and args[i + 1] == "recurse":
                    recursive = True
                i += 1
        elif not pattern_given:
            pattern_given = True
        else:
            paths.append(arg)
        i += 1
    if recursive and (not paths or any(searches_project_root(p) for p in paths)):
        return "a recursive grep must name a folder or file, not the project root (it would read .env)"
    return None


def read_path_problem(words: list[str], project_dir: Path) -> str | None:
    """cat, grep, ls and friends: every path-like argument must stay inside the project."""
    if words[0] == "grep":
        problem = grep_problem(words)
        if problem:
            return problem
    for word in words[1:]:
        candidate = word.partition("=")[2] if word.startswith("-") else word
        if not candidate:
            continue
        if candidate.startswith(("/", "~")) or ".." in candidate.split("/"):
            if not inside_project(candidate, project_dir):
                return f"{words[0]} may only read inside the project, not {candidate}"
    return None


def check_pm_git(segments: list[list[str]], project_dir: Path) -> None:
    """pm stages by explicit path and commits on its own, never a guard-rail file."""
    for words in segments:
        if words[:1] == ["gh"] and len(segments) != 1:
            block("pm must run gh in a call of its own")
        if words[:2] == ["git", "add"] and any(w[:2] == ["git", "commit"] for w in segments):
            block("pm must commit in a call of its own, so the staged paths can be checked")
        if words[:2] == ["git", "commit"]:
            if len(segments) != 1:
                block("pm must commit in a call of its own, so the staged paths can be checked")
            check_commit_args(words[2:])
            try:
                staged = staged_paths(project_dir)
            except (OSError, subprocess.SubprocessError):
                block("could not read the staged paths; refusing to commit")
            if not staged:
                block("nothing is staged; stage the build's files by explicit path first")
            rails = [p for p in staged if is_guard_rail(p)]
            if rails:
                block(
                    f"guard-rail paths are staged ({', '.join(rails)}); unstage them with "
                    "git reset -q -- <path> and leave them for Prin"
                )


def check_bash(agent: str, command: str, project_dir: Path) -> None:
    """Apply the per-agent Bash rules."""
    if names_secret(command):
        block(f"{agent} may not reach a .env file in Bash, by name, glob or quoting")
    if agent in CODEX_AGENT_NAMES:
        block("the Codex plugin agent is disabled: it skips Codex's sandbox; pm runs codex exec itself")
    if command.strip() in BASH_EXACT.get(agent, ()):
        return
    if agent == PM and DEMO_SERVER_START.fullmatch(command.strip()):
        return
    try:
        segments = strict_lex(command)
    except Unparseable as err:
        block(
            f"{agent} sent a command the guard cannot parse safely ({err}). Use one plain "
            "command per call: no comments, line breaks, $, backticks, globs, brackets or "
            "redirection, and quotes only around a whole word"
        )
    if runs_codex(command):
        if agent != PM:
            block(f"{agent} may not run Codex; only pm may, with codex exec")
        return  # form already checked by check_every_session_bash

    for words in segments:
        problem = auto_allowed_problem(words, project_dir)
        if problem:
            block(f"{agent}: {problem}")
        if words[0] in READ_COMMANDS:
            problem = read_path_problem(words, project_dir)
            if problem:
                block(f"{agent}: {problem}")

    if agent == CODE_WRITER:
        if CODE_WRITER_BASH_DENY.search(command):
            block("code-writer may not name protected files or data/ in Bash; use Read to read them")
        for words in segments:
            program = words[0].rsplit("/", 1)[-1]
            if re.match(r"^[A-Za-z_]\w*=", words[0]) and words[0] != "PYTHONPATH=.":
                block("code-writer may not set variables in front of a command (PYTHONPATH=. is fine)")
            if words[0] == "PYTHONPATH=.":
                words = words[1:] or [""]
                program = words[0].rsplit("/", 1)[-1]
            if program == "find" and any(w in FIND_ACTIONS for w in words):
                block("code-writer may not use find -exec, -ok or -delete; use Read, Edit and plain commands")
            if program in LOOSE_WRAPPERS:
                block("code-writer may not run commands through env, sudo, eval or a shell; run them directly")
            if program in ("cd", "pushd", "popd"):
                block("code-writer may not change directory; use paths from the project root")
            if program == "gh":
                block("code-writer may not use gh; pm keeps the issues")
            sub = git_subcommand(words)
            if program == "git" and sub not in GIT_READ_SUBCOMMANDS:
                block(f"code-writer may only read with git ({', '.join(sorted(GIT_READ_SUBCOMMANDS))}), not git {sub}")
            if words[:2] == ["graft", "build"] or words[:2] in (["graft", "init"], ["graft", "upgrade"]):
                block("code-writer may not run graft build, init or upgrade; Prin runs them")
        return

    allowed = BASH_ALLOW.get(agent)
    if allowed is None:
        return
    for words in segments:
        segment = " ".join(words)
        if not any(segment == p or segment.startswith(p + " ") for p in allowed):
            block(f"{agent} may not run '{segment}' (not on its Bash allowlist)")
    if agent == PM:
        check_pm_git(segments, project_dir)


AUTO_ALLOWED_WORD = re.compile(r"\b(?:git|gh|pytest|npm|uv|date|mkdir)\b")


def check_plain_session_bash(command: str, project_dir: Path) -> None:
    """Prompt Prin where settings.json alone would run a command unsafely without asking."""
    try:
        segments = strict_lex(command)
    except Unparseable as err:
        if AUTO_ALLOWED_WORD.search(command):
            ask(f"cannot parse this command safely ({err}); check it before it runs")
        return
    for words in segments:
        problem = auto_allowed_problem(words, project_dir)
        if problem:
            ask(problem)
    if runs_git(command, "commit"):
        ask("commits outside pm need Prin's OK")


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


def local_url_problem(url: str, ports: frozenset | None = None) -> str | None:
    """Return a reason to refuse this navigate target, or None if it is allowed.

    ports, when given, limits the page to those localhost ports (pm: 5173 only).
    """
    if url in ("back", "forward"):
        return None
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        return f"navigate needs an explicit http://localhost:<port>/ URL, not '{url}'"
    if parts.username or parts.password:
        return "navigate URLs may not carry credentials"
    if parts.hostname not in BROWSER_LOCAL_HOSTS:
        return f"pm may browse only 127.0.0.1 and localhost, not '{parts.hostname}'"
    if ports is not None and parts.port not in ports:
        return f"pm may browse only port {', '.join(map(str, sorted(ports)))}, not {parts.port}"
    return None


def browser_key_ok(text: str) -> bool:
    """Return True for one navigation key (Enter, Tab, PageDown...): never characters or shortcuts."""
    key = text.strip().lower()
    return key in BROWSER_ALLOWED_KEYS and not BROWSER_BLOCKED_KEYS.search(key)


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
        return local_url_problem(str(tool_input.get("url", "")), PM_BROWSER_PORTS)
    if tool == "computer":
        action = tool_input.get("action", "")
        if action not in BROWSER_COMPUTER_ACTIONS:
            return f"pm may not use the browser action '{action}'"
        if tool_input.get("modifiers"):
            return "pm may not click with modifier keys"
        if action == "key" and not browser_key_ok(str(tool_input.get("text", ""))):
            return "pm may not press shortcut or function keys in the browser"
    return None


def playwright_call_problem(tool: str, tool_input: dict, ports: frozenset | None = None) -> str | None:
    """Return a reason to refuse one pm Playwright call, or None if it is allowed."""
    if tool not in PLAYWRIGHT_PM_ALLOWED:
        return f"pm may not use Playwright tool '{tool}' (allowed: {', '.join(sorted(PLAYWRIGHT_PM_ALLOWED))})"
    for key in ("url", "href"):
        if key in tool_input:
            reason = local_url_problem(str(tool_input.get(key, "")), ports)
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
    if tool == "browser_press_key" and not browser_key_ok(str(tool_input.get("key", ""))):
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
    reason = playwright_call_problem(
        tool.removeprefix(PLAYWRIGHT_PREFIX), tool_input, PM_BROWSER_PORTS if agent == PM else None
    )
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

    if tool in SHELL_TOOLS:
        command = str(tool_input.get("command", ""))
        if not (agent == PM and DEMO_SERVER_START.fullmatch(command.strip())):
            check_every_session_bash(command)
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

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".")
    if agent != PM and agent not in TEAM and agent not in CODEX_AGENT_NAMES:
        # Plain sessions (Prin's own `claude`) keep the normal permission rules,
        # plus the every-session Bash rules above. Where settings.json would
        # run a command with no prompt, but its arguments go beyond safe use,
        # or the command cannot be parsed safely, Prin gets a prompt instead.
        if tool in SHELL_TOOLS:
            check_plain_session_bash(str(tool_input.get("command", "")), project_dir)
        return

    if tool in FILE_TOOLS:
        check_file_tool(agent, tool, tool_input, project_dir)
    elif tool in SHELL_TOOLS:
        check_bash(agent, str(tool_input.get("command", "")), project_dir)
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