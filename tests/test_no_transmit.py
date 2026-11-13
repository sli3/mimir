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


def _rx_direction_name(node: ast.AST) -> str | None:
    """Return the name if the node is a Name or Attribute ending in RX_DIRECTION."""
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
    return name if name and name.endswith("RX_DIRECTION") else None


def _assigned_names(node: ast.AST) -> list[tuple[str, ast.AST]]:
    """Return (name, value) for each Name/Attribute target of an assignment node."""
    pairs = []
    if isinstance(node, ast.Assign):
        for target in node.targets:
            name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else None
            if name:
                pairs.append((name, node.value))
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        target = node.target
        name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else None
        if name:
            pairs.append((name, node.value))
    return pairs


def _is_soapy_rx(node: ast.AST) -> bool:
    """Return True for SoapySDR's own receive constant, SOAPY_SDR_RX."""
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
    return name == "SOAPY_SDR_RX"


def test_setup_stream_direction_is_rx() -> None:
    """setupStream() is only ever given an RX direction.

    Accepted: the literal 1, SOAPY_SDR_RX, a *RX_DIRECTION constant, or a
    variable (such as Pluto's self._rx) that every assignment in the same file
    sets to SOAPY_SDR_RX (or None while closed). Anything else, including a variable that is ever set
    to something else, fails.
    """
    offenders = []
    for path, tree in TREES.items():
        values: dict[str, list[ast.AST]] = {}
        for node in ast.walk(tree):
            for name, value in _assigned_names(node):
                values.setdefault(name, []).append(value)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _called_name(node) == "setupStream" and node.args):
                continue
            first = node.args[0]
            name = first.id if isinstance(first, ast.Name) else first.attr if isinstance(first, ast.Attribute) else None
            ok = (
                (isinstance(first, ast.Constant) and first.value == 1)
                or _is_soapy_rx(first)
                or bool(_rx_direction_name(first))
                or (
                    name in values
                    and any(_is_soapy_rx(v) for v in values[name])
                    and all(_is_soapy_rx(v) or (isinstance(v, ast.Constant) and v.value is None) for v in values[name])
                )
            )
            if not ok:
                offenders.append(f"{_rel(path)}:{node.lineno}")
    assert not offenders, "setupStream direction is not provably RX:\n" + "\n".join(offenders)


def test_rx_direction_constants_are_one() -> None:
    """Every *RX_DIRECTION constant is assigned exactly 1 (SoapySDR RX); 0 would be TX."""
    found, offenders = [], []
    for path, node in ((p, n) for p, tree in TREES.items() for n in ast.walk(tree)):
        targets = []
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        for target in targets:
            if _rx_direction_name(target):
                found.append(_rel(path))
                if not (isinstance(value, ast.Constant) and value.value == 1):
                    offenders.append(f"{_rel(path)}:{node.lineno}")
    assert "core/device/hackrf_rx.py" in found, "expected HackRF's _SOAPY_RX_DIRECTION constant"
    assert not offenders, "RX direction constant not set to 1:\n" + "\n".join(offenders)


def _is_guard_import(node: ast.stmt) -> bool:
    """Return True for `from core.legal.compliance_guard import transmit_guard`."""
    return (
        isinstance(node, ast.ImportFrom)
        and node.module == "core.legal.compliance_guard"
        and all(alias.name == "transmit_guard" for alias in node.names)
    )


def test_tx_named_methods_are_guarded() -> None:
    """Every TX-named function does nothing except call transmit_guard().

    Allowed body: a docstring, an import of transmit_guard, and one call to it.
    Any other statement (even one placed before the guard) fails, so a stub can
    never do real work before raising.
    """
    offenders = []
    for path, node in ((p, n) for p, tree in TREES.items() for n in ast.walk(tree)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TX_NAMES:
            body = [
                s for s in node.body
                if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                and not _is_guard_import(s)
            ]
            guarded = (
                len(body) == 1
                and isinstance(body[0], (ast.Expr, ast.Return))
                and body[0].value is not None
                and _is_transmit_guard_call(body[0].value)
            )
            if not guarded:
                offenders.append(f"{_rel(path)}:{node.lineno} {node.name}() is not a pure transmit_guard() stub")
    assert not offenders, "TX-named function does more than call transmit_guard():\n" + "\n".join(offenders)


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
