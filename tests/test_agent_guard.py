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
