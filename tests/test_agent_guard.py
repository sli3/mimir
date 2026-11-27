"""
test_agent_guard.py — Runs the agent guard's own allow/block cases in the suite.

.claude/hooks/check_agent_guard.py feeds sample tool calls to the PreToolUse
hook (agent_guard.py) and checks each is allowed or blocked as intended. Running
it here means a guard regression fails `uv run pytest`, not just a manual check.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / ".claude" / "hooks" / "check_agent_guard.py"


def test_agent_guard_cases_all_pass() -> None:
    """Every case in check_agent_guard.py behaves as expected."""
    result = subprocess.run(
        [sys.executable, str(CHECKER)], capture_output=True, text=True, timeout=120, check=False
    )
    failures = [line for line in result.stdout.splitlines() if line.startswith("FAIL")]
    assert result.returncode == 0 and not failures, "\n".join(failures) or result.stdout[-2000:]


# --- SDR tools after the rf#87 move (capture, diagnose) -----------------------
# These call the guard's every-session check directly, so each case tests the
# SDR rule itself, not a named agent's allowlist.
import importlib.util
import json
import os

import pytest

GUARD_PATH = REPO_ROOT / ".claude" / "hooks" / "agent_guard.py"
_spec = importlib.util.spec_from_file_location("agent_guard", GUARD_PATH)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

SDR_BLOCKED = [
    # Old script names, blocked wherever they live
    "python tools/calibrate_thresholds.py",
    "python3 tools/compare_decode_rate.py --help",
    "env PYTHONPATH=. .venv-scan/bin/python -s tools/diagnose_pluto_gain.py",
    "python -m tools.diagnose_threshold",
    "python tools/capture/calibrate_thresholds.py",
    # The new packages as files or folders
    "python tools/capture/calibrate.py",
    "python tools/capture",
    "python tools/capture/",
    "python3 ./tools/diagnose/gain.py",
    "python tools/diagnose/__main__.py fingerprints",
    "./tools/capture/__main__.py calibrate",
    "tools/diagnose/gain.py",
    "python tools/vectors/../capture/store.py",
    "python /home/someone/mimir/tools/capture/store.py",
    "python tools/c*/calibrate.py",
    "python tools/diag?ose/gain.py",
    "python capture/calibrate.py",
    # The new packages as modules
    "python -m tools.capture calibrate",
    "python -m tools.capture",
    "python -m tools.capture.store",
    "python -m tools.diagnose.gain",
    "python -mtools.diagnose decode-rate",
    "python -I -m tools.capture calibrate",
    "python -u -X dev -m tools.diagnose threshold",
    "python -m tools",
    "python -m capture calibrate",
    "python capture calibrate",
    # Other interpreters and runners
    "uv run python -m tools.capture calibrate",
    "uv run tools/diagnose/gain.py",
    "uv run --with numpy python -m tools.diagnose",
    "/usr/bin/python3.13 -m tools.capture",
    ".venv/bin/python -m tools.diagnose.gain",
    "ipython tools/capture/calibrate.py",
    "pytest tools/diagnose/fingerprints.py",
    "uv run pytest -p tools.diagnose.fingerprints",
    # Wrappers
    "sudo -n python -m tools.capture calibrate",
    "timeout -k 5 10 python -m tools.diagnose gain",
    "env -i PATH=/usr/bin python3 -m tools.capture store",
    "nohup python -m tools.capture store",
    'bash -c "python -m tools.capture calibrate"',
    "sh -c 'python tools/diagnose/gain.py'",
    "eval python -m tools.capture",
    "cd tools && python -m capture calibrate",
    "echo x | xargs python -m tools.diagnose gain",
    # Code given inline
    "python -c 'import tools.capture'",
    'python -c "from tools import capture"',
    "python -c 'import runpy; runpy.run_module(\"tools.diagnose\")'",
    # The launcher
    "./mimir tool calibrate_thresholds",
    "./mimir scan",
    "echo | ./mimir scan",
    "bash mimir tool diagnose_threshold",
    "./mim* scan",
]

SDR_ALLOWED = [
    # The tools that never open the SDR
    "python tools/vectors/snr.py --path x",
    "python -m tools.vectors snr --label AIS",
    "python -m tools.offline replay",
    "uv run python -m tools.offline demo-cache",
    "python tools/inspect_snr.py --max-snr 3",
    "python tools/replay_capture.py",
    "python3 tools/seed_chromadb.py",
    # Reading, staging and compiling SDR tool files
    "cat tools/capture/calibrate.py",
    "git diff tools/diagnose/gain.py",
    "git add tools/capture/__init__.py",
    "grep -n calibrate tools/capture/calibrate.py",
    "ls tools/capture",
    "graft skeleton tools/diagnose/gain.py",
    "uv run python -m py_compile tools/capture/calibrate.py tools/diagnose/gain.py",
    "git commit -m 'Move calibrate into tools/capture'",
    "cat mimir",
    "git diff mimir",
    # Tests whose names or filters mention the tools
    "uv run pytest tests/test_capture_calibrate.py",
    "uv run pytest -k capture",
    "uv run pytest -m diagnose",
    "uv run python -m pytest tests -k diagnose",
]


@pytest.mark.parametrize("command", SDR_BLOCKED)
def test_sdr_tool_forms_blocked(command: str) -> None:
    """Every way of starting an SDR tool counts as running hardware."""
    assert guard.runs_hardware(command), command


@pytest.mark.parametrize("command", SDR_ALLOWED)
def test_non_sdr_forms_allowed(command: str) -> None:
    """Reads, non-SDR tools and test filters are not hardware runs."""
    assert not guard.runs_hardware(command), command


def run_hook(agent: str, command: str) -> subprocess.CompletedProcess[str]:
    """Feed one Bash call to the hook as Claude Code would."""
    payload = {"agent_type": agent, "tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(GUARD_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(REPO_ROOT)},
    )


@pytest.mark.parametrize("agent", ["", "pm", "code-writer", "deep-bug-hunter"])
@pytest.mark.parametrize("command", ["python -m tools.capture calibrate", "./mimir scan"])
def test_sdr_blocked_for_every_session(agent: str, command: str) -> None:
    """The SDR rule blocks plain sessions and every named agent alike."""
    result = run_hook(agent, command)
    assert result.returncode == 2
    assert "radio-hardware" in result.stderr


def test_pm_may_run_graft_build() -> None:
    """pm may rebuild the graft index, exactly as `graft build`."""
    result = run_hook("pm", "graft build")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("agent", "command"),
    [("pm", "graft build --force"), ("pm", "graft init"), ("pm", "graft upgrade"),
     ("code-writer", "graft build"), ("plan-reviewer", "graft build")],
)
def test_other_graft_writes_blocked(agent: str, command: str) -> None:
    """Only pm, and only the plain `graft build`, may write the index."""
    assert run_hook(agent, command).returncode == 2
