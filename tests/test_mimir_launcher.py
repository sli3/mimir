"""Check the launcher in isolated fake repositories without reaching an SDR."""

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash is not on PATH")
LAUNCHER = Path(__file__).resolve().parents[1] / "mimir"


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Copy the launcher beside inert scripts, packages and command stubs."""
    repo = tmp_path / "fake repo"
    repo.mkdir()
    shutil.copy2(LAUNCHER, repo / "mimir")
    python = repo / ".venv-scan/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\0' \"$@\" > {shlex.quote(str(repo / 'arguments'))}\n"
        f"printf '%s\\n' \"$PWD\" \"$PYTHONPATH\" "
        f"> {shlex.quote(str(repo / 'environment'))}\n"
        "exit 0\n"
    )
    python.chmod(0o755)
    fake_bin = repo / "fake-bin"
    fake_bin.mkdir()
    for name in ("npm", "uv"):
        shutil.copy2(python, fake_bin / name)
    tools = repo / "tools"
    (tools / "archive").mkdir(parents=True)
    for name in (
        "inspect_snr.py", "calibrate_thresholds.py", "__init__.py", "_helper.py",
    ):
        (tools / name).touch()
    (tools / "archive/x.py").touch()
    for name in ("vectors", "_private"):
        (tools / name).mkdir()
        (tools / name / "__main__.py").touch()
    (repo / "data/captures").mkdir(parents=True)
    (repo / "data/demo_cache").mkdir()
    return repo


def run_launcher(
    repo: Path, *args: str, stdin: str = "", launcher: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Capture copied-launcher output as UTF-8 with npm and uv stubbed."""
    assert BASH is not None
    stub_path = f"{repo / 'fake-bin'}:{os.environ.get('PATH', os.defpath)}"
    return subprocess.run(
        [BASH, str(launcher or repo / "mimir"), *args],
        input=stdin,
        text=True,
        encoding="utf-8",
        capture_output=True,
        cwd=repo.parent,
        env={
            **os.environ,
            "PATH": stub_path,
        },
        timeout=10,
        check=False,
    )


def recorded_arguments(repo: Path) -> list[str]:
    """Read the stub's NUL-separated arguments without losing whitespace."""
    return (repo / "arguments").read_bytes().decode().split("\0")[:-1]


def add_capture(
    repo: Path, stem: str, mtime: int, *, complete: bool = True
) -> None:
    """Create a cached fake capture with a chosen cache modification time."""
    (repo / f"data/captures/{stem}.sigmf-meta").touch()
    if complete:
        (repo / f"data/captures/{stem}.sigmf-data").touch()
    cache = repo / f"data/demo_cache/{stem}.json"
    cache.touch()
    os.utime(cache, (mtime, mtime))


@pytest.mark.parametrize("args", [(), ("help",), ("-h",), ("--help",)])
def test_help(fake_repo: Path, args: tuple[str, ...]) -> None:
    """Help succeeds without a confirmation prompt or executed command."""
    result = run_launcher(fake_repo, *args)
    assert result.returncode == 0
    assert "MIMIR launcher (receive-only scanner)" in result.stdout
    assert "Press Enter" not in result.stdout
    assert not (fake_repo / "arguments").exists()


def test_unknown_command(fake_repo: Path) -> None:
    """An unknown subcommand fails and includes usage."""
    result = run_launcher(fake_repo, "unknown")
    assert result.returncode == 1
    assert "Unknown command: unknown" in result.stdout
    assert "MIMIR launcher" in result.stdout


def test_tool_list(fake_repo: Path) -> None:
    """List scripts and runnable packages together, excluding private names."""
    result = run_launcher(fake_repo, "tool")
    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "  calibrate_thresholds (uses the SDR)",
        "  inspect_snr",
        "  vectors",
    ]
    assert "Press Enter" not in result.stdout


@pytest.mark.parametrize(
    "name", [
        "unknown", "archive", "archive/x", "../scan.py", "_helper",
        "_helper.py", "_private",
    ],
)
def test_invalid_tool(fake_repo: Path, name: str) -> None:
    """Reject unknown tools, archives, private packages and paths early."""
    result = run_launcher(fake_repo, "tool", name)
    assert result.returncode == 1
    assert f"No tool called {name}" in result.stdout
    assert "inspect_snr" in result.stdout
    assert "Press Enter" not in result.stdout
    assert not (fake_repo / "arguments").exists()


@pytest.mark.parametrize(
    "args", [("scan",), ("demo",), ("tool", "inspect_snr")]
)
@pytest.mark.parametrize("missing", [True, False])
def test_unavailable_python(
    fake_repo: Path, args: tuple[str, ...], missing: bool
) -> None:
    """A missing or non-executable scanner Python fails before confirmation."""
    python = fake_repo / ".venv-scan/bin/python"
    if missing:
        python.unlink()
    else:
        python.chmod(0o644)
    result = run_launcher(fake_repo, *args)
    assert result.returncode == 1
    assert ".venv-scan is missing. Run ./setup.sh first." in result.stdout
    assert "Press Enter" not in result.stdout


@pytest.mark.parametrize(
    "args",
    [
        ("scan",), ("demo",), ("tool", "inspect_snr"),
        ("tool", "calibrate_thresholds"), ("frontend",), ("test",),
    ],
)
def test_empty_stdin_cancels(fake_repo: Path, args: tuple[str, ...]) -> None:
    """EOF shows a rounded, aligned, plain box and explicit cancellation."""
    add_capture(fake_repo, "saved", 100)
    result = run_launcher(fake_repo, *args)
    assert result.returncode == 1
    assert "Will run:" in result.stdout
    assert "Press Enter to run, or Ctrl+C to cancel." in result.stdout
    prompt = "Press Enter to run, or Ctrl+C to cancel."
    inner_width = len(prompt) + 4
    top = "╭" + "─" * inner_width + "╮"
    middle = "│  " + prompt + "  │"
    bottom = "╰" + "─" * inner_width + "╯"
    lines = result.stdout.splitlines()
    assert lines.count(top) == 1
    assert lines.count(middle) == 1
    assert lines.count(bottom) == 1
    start = lines.index(top)
    assert lines[start:start + 3] == [top, middle, bottom]
    assert len(top) == len(middle) == len(bottom)
    assert "\x1b" not in result.stdout
    assert "Cancelled: no confirmation." in result.stdout
    assert not (fake_repo / "arguments").exists()
    if args == ("frontend",):
        assert "npm run dev --prefix dashboard/frontend" in result.stdout
    if args == ("test",):
        assert "uv run pytest" in result.stdout
        assert "npm run test --prefix dashboard/frontend" in result.stdout
        assert result.stdout.count("Press Enter to run") == 1
    if args == ("tool", "calibrate_thresholds"):
        assert "This tool opens the SDR (receive only)." in result.stdout


def test_scan_arguments_and_location(fake_repo: Path) -> None:
    """Enter preserves metacharacters and runs from the script directory."""
    literal = "two words; $(touch unexpected)"
    result = run_launcher(
        fake_repo, "scan", "--device", "pluto", literal, stdin="\n"
    )
    assert result.returncode == 0
    assert recorded_arguments(fake_repo) == [
        "-s", "scan.py", "--device", "pluto", literal,
    ]
    assert (fake_repo / "environment").read_text().splitlines() == [
        str(fake_repo), ".",
    ]
    assert r"two\ words\;\ \$\(touch\ unexpected\)" in result.stdout
    assert not (fake_repo / "unexpected").exists()


def test_symlink_location(fake_repo: Path) -> None:
    """A symlink resolves the fake repository containing the real script."""
    link = fake_repo.parent / "launcher-link"
    link.symlink_to(fake_repo / "mimir")
    result = run_launcher(fake_repo, "scan", stdin="\n", launcher=link)
    assert result.returncode == 0
    assert recorded_arguments(fake_repo) == ["-s", "scan.py"]
    environment = (fake_repo / "environment").read_text().splitlines()
    assert environment[0] == str(fake_repo)


@pytest.mark.parametrize("name", ["inspect_snr", "inspect_snr.py"])
def test_tool_arguments(fake_repo: Path, name: str) -> None:
    """Accept tool names with either suffix and preserve their arguments."""
    result = run_launcher(
        fake_repo, "tool", name, "--label", "AIS", stdin="\n"
    )
    assert result.returncode == 0
    assert recorded_arguments(fake_repo) == [
        "-s", "tools/inspect_snr.py", "--label", "AIS",
    ]
    assert "This tool opens the SDR" not in result.stdout


def test_package_tool_arguments(fake_repo: Path) -> None:
    """Launch vectors as a module with its arguments and no SDR warning."""
    result = run_launcher(
        fake_repo, "tool", "vectors", "snr", "--label", "AIS", stdin="\n"
    )
    assert result.returncode == 0
    assert recorded_arguments(fake_repo) == [
        "-s", "-m", "tools.vectors", "snr", "--label", "AIS",
    ]
    assert "This tool opens the SDR" not in result.stdout
    assert (fake_repo / "environment").read_text().splitlines() == [
        str(fake_repo), ".",
    ]


def test_demo_auto_pick(fake_repo: Path) -> None:
    """Choose the newest complete cached capture over incomplete ones."""
    add_capture(fake_repo, "older", 100)
    add_capture(fake_repo, "chosen capture", 200)
    add_capture(fake_repo, "incomplete", 300, complete=False)
    orphan = fake_repo / "data/demo_cache/orphan.json"
    orphan.touch()
    os.utime(orphan, (400, 400))
    result = run_launcher(fake_repo, "demo", "--extra", "value", stdin="\n")
    assert result.returncode == 0
    assert (
        "Demo file: chosen capture.sigmf-meta (newest with a cache)"
        in result.stdout
    )
    assert recorded_arguments(fake_repo) == [
        "-s", "scan.py", "--demo", "--demo-files",
        "data/captures/chosen capture.sigmf-meta", "--extra", "value",
    ]


def test_demo_explicit_file(fake_repo: Path) -> None:
    """Use the supplied metadata path without requiring a cache match."""
    path = fake_repo / "explicit capture.sigmf-meta"
    path.touch()
    result = run_launcher(fake_repo, "demo", str(path), "--extra", stdin="\n")
    assert result.returncode == 0
    assert recorded_arguments(fake_repo) == [
        "-s", "scan.py", "--demo", "--demo-files", str(path), "--extra",
    ]
    assert "newest with a cache" not in result.stdout


def test_demo_missing_explicit_file(fake_repo: Path) -> None:
    """A missing explicit file fails without prompting or falling back."""
    add_capture(fake_repo, "fallback", 100)
    result = run_launcher(fake_repo, "demo", "missing.sigmf-meta")
    assert result.returncode == 1
    assert "Demo file does not exist: missing.sigmf-meta" in result.stdout
    assert "Press Enter" not in result.stdout
    assert not (fake_repo / "arguments").exists()


def test_demo_no_candidate(fake_repo: Path) -> None:
    """Explain all required files when no complete cached capture exists."""
    add_capture(fake_repo, "incomplete", 100, complete=False)
    result = run_launcher(fake_repo, "demo")
    assert result.returncode == 1
    assert "A demo needs a .sigmf-meta, its .sigmf-data" in result.stdout
    assert "data/demo_cache/<stem>.json" in result.stdout
    assert "Press Enter" not in result.stdout
    assert not (fake_repo / "arguments").exists()
