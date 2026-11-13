"""
test_no_transmit.py — Static source scan that keeps Mimir receive-only.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

Runtime tests (test_rx_only_lock.py and friends) prove the TX stubs raise
HardwareTransmitError when called. This module proves something different:
that no source file CALLS a transmit function in the first place, that nothing
references the SoapySDR TX direction, and that every TX-named method still
routes to transmit_guard(). It reads the code with the ast module, so comments
and docstrings never trigger it. It runs on every `uv run pytest`, whichever
agent (Claude, Codex or a person) wrote the change.
"""
import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Production code only. Tests deliberately call the blocked stubs to prove
# they raise, so tests/ is excluded.
SOURCE_DIRS = ("core", "modules", "llm", "embeddings", "dashboard", "tools", "mcp")
SOURCE_FILES = ("scan.py",)
SKIP_PARTS = {"node_modules", "static", "__pycache__", ".venv", "frontend"}

# Method and function names that transmit on SoapySDR, HackRF or Pluto, plus
# DeviceBase's own TX surface. Defining one is allowed only as a guarded stub;
# calling one is never allowed.
TX_NAMES = frozenset({
    "writeStream",
    "setupTxStream",
    "activateTxStream",
    "set_tx_gain",
    "set_tx_frequency",
    "transmit",
    "write_samples",
    "hackrf_start_tx",
    "start_tx",
})
TX_DIRECTION_NAMES = frozenset({"SOAPY_SDR_TX"})
# A command line that would make hackrf_transfer transmit (-t file, -c CW).
HACKRF_TX_CLI = re.compile(r"hackrf_transfer\b[^\n]*\s-(?:t|c)\b")


def _source_files() -> list[Path]:
    """Return every production Python file to scan."""
    files = [REPO_ROOT / name for name in SOURCE_FILES if (REPO_ROOT / name).exists()]
    for directory in SOURCE_DIRS:
        root = REPO_ROOT / directory
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if SKIP_PARTS.isdisjoint(path.relative_to(REPO_ROOT).parts):
                files.append(path)
    return sorted(files)


def _parse(path: Path) -> ast.Module:
    """Parse one source file."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _called_name(node: ast.Call) -> str | None:
    """Return the bare name of the function a Call invokes, if it has one."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _is_transmit_guard_call(node: ast.AST) -> bool:
    """Return True if the node is a call to transmit_guard(...)."""
    return isinstance(node, ast.Call) and _called_name(node) == "transmit_guard"


SOURCES = _source_files()
TREES = {path: _parse(path) for path in SOURCES}


def _rel(path: Path) -> str:
    """Return a repo-relative path for messages."""
    return str(path.relative_to(REPO_ROOT))


def test_scan_covers_the_device_layer() -> None:
    """Guard against the scan silently matching no files after a refactor."""
    rel = {_rel(p) for p in SOURCES}
    assert "core/device/hackrf_rx.py" in rel
    assert "core/device/pluto_rx.py" in rel
    assert "core/legal/compliance_guard.py" in rel
    assert len(SOURCES) > 30


def test_no_transmit_calls() -> None:
    """No production code calls a transmit function."""
    offenders = [
        f"{_rel(path)}:{node.lineno} calls {_called_name(node)}()"
        for path, tree in TREES.items()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) in TX_NAMES
    ]
    assert not offenders, "Transmit call found (illegal in AU without a licence):\n" + "\n".join(offenders)


def test_no_tx_direction_reference() -> None:
    """No production code imports or references the SoapySDR TX direction."""
    offenders = []
    for path, node in ((p, n) for p, tree in TREES.items() for n in ast.walk(tree)):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.alias):
            name = node.name
        if name in TX_DIRECTION_NAMES:
            offenders.append(f"{_rel(path)}:{getattr(node, 'lineno', '?')} references {name}")
    assert not offenders, "TX direction referenced:\n" + "\n".join(offenders)


def test_setup_stream_never_uses_direction_zero() -> None:
    """setupStream() is never given the literal TX direction 0."""
    offenders = []
    for path, node in ((p, n) for p, tree in TREES.items() for n in ast.walk(tree)):
        if isinstance(node, ast.Call) and _called_name(node) == "setupStream" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and first.value == 0:
                offenders.append(f"{_rel(path)}:{node.lineno}")
    assert not offenders, "setupStream called with direction 0 (TX):\n" + "\n".join(offenders)


def test_tx_named_methods_are_guarded() -> None:
    """Every function with a TX name exists only to call transmit_guard()."""
    offenders = []
    for path, node in ((p, n) for p, tree in TREES.items() for n in ast.walk(tree)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TX_NAMES:
            if not any(_is_transmit_guard_call(child) for child in ast.walk(node)):
                offenders.append(f"{_rel(path)}:{node.lineno} {node.name}() has no transmit_guard()")
    assert not offenders, "Unguarded TX-named function:\n" + "\n".join(offenders)


def test_no_hackrf_transfer_tx_command() -> None:
    """No string in production code builds a transmitting hackrf_transfer command."""
    offenders = [
        f"{_rel(path)}:{node.lineno}"
        for path, tree in TREES.items()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and HACKRF_TX_CLI.search(node.value)
    ]
    assert not offenders, "hackrf_transfer TX command string found:\n" + "\n".join(offenders)


def test_transmit_guard_always_raises() -> None:
    """transmit_guard() must still end in an unconditional raise."""
    tree = _parse(REPO_ROOT / "core/legal/compliance_guard.py")
    guard = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "transmit_guard"
    )
    body = [s for s in guard.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    assert len(body) == 1 and isinstance(body[0], ast.Raise), "transmit_guard() must be a single raise"
    exc = body[0].exc
    assert isinstance(exc, ast.Call) and _called_name(exc) == "HardwareTransmitError"
