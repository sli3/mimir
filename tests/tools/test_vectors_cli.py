"""Check vector dispatch, compatibility wrappers and hardware-free imports."""

from __future__ import annotations

import ast
import builtins
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

# Support namespace-package imports and subprocesses from the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from embeddings.embedder import EMBEDDING_FEATURES
from embeddings.store import SignalStore
from tools import delete_low_snr, inspect_snr, purge_noise_vectors
from tools.vectors import _store_ops, cli, purge_noise, snr


@pytest.mark.parametrize(("argv", "module", "expected"), [
    (["snr"], snr, ("data/vectorstore", "ADS_B", None, False)),
    (["purge-noise"], purge_noise, ("data/vectorstore", None, False)),
    (
        ["snr", "--path", "custom store", "--label", "AIS",
         "--max-snr", "5", "--execute"],
        snr, ("custom store", "AIS", 5.0, True),
    ),
    (
        ["purge-noise", "--path", "custom store", "--label", "FM",
         "--execute"],
        purge_noise, ("custom store", "FM", True),
    ),
])
def test_subcommand_dispatch(
    argv: list[str], module: ModuleType, expected: tuple,
) -> None:
    """Both subcommands forward parsed flags and preserve run exit codes."""
    with patch.object(module, "run", return_value=7) as run:
        assert cli.main(argv) == 7
    run.assert_called_once_with(*expected)


@pytest.mark.parametrize("argv", [[], ["seed"]])
def test_missing_or_unknown_subcommand(argv: list[str]) -> None:
    """A missing subcommand or the unimplemented seed command is an error."""
    with (
        patch.object(snr, "run") as snr_run,
        patch.object(purge_noise, "run") as purge_run,
        pytest.raises(SystemExit) as exc,
    ):
        cli.main(argv)
    assert exc.value.code == 2
    snr_run.assert_not_called()
    purge_run.assert_not_called()


def test_package_help_subprocess() -> None:
    """The module entry point lists both commands from the repository root."""
    result = subprocess.run(
        [sys.executable, "-m", "tools.vectors", "--help"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "snr" in result.stdout
    assert "purge-noise" in result.stdout


def test_inspect_shim_rejects_execute(
    seeded_snr_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The legacy inspector rejects deletion flags before reaching a store."""
    path, store = seeded_snr_store
    before = store.get_all_embeddings()
    monkeypatch.setattr(sys, "argv", [
        "inspect_snr.py", "--path", str(path), "--max-snr", "5", "--execute",
    ])
    with (
        patch.object(snr, "SignalStore") as opened,
        pytest.raises(SystemExit) as exc,
    ):
        inspect_snr.main()
    assert exc.value.code == 2
    opened.assert_not_called()
    assert store.get_all_embeddings() == before


def test_inspect_shim_cut_is_read_only(
    seeded_snr_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The old preview flag lists low_3 without any backup or deletion."""
    path, store = seeded_snr_store
    before = store.get_all_embeddings()
    monkeypatch.setattr(sys, "argv", [
        "inspect_snr.py", "--path", str(path), "--label", "ADS_B",
        "--max-snr", "5",
    ])
    with (
        patch.object(_store_ops, "make_backup") as backup,
        patch.object(builtins, "input") as confirmation,
        patch.object(_store_ops, "delete_ids") as deletion,
    ):
        assert inspect_snr.main() is None
    backup.assert_not_called()
    confirmation.assert_not_called()
    deletion.assert_not_called()
    assert store.get_all_embeddings() == before
    out = capsys.readouterr().out
    assert "low_3" in out and "boundary_5" not in out
    assert "Would select 1" in out


def test_delete_shim_requires_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    """The old deletion name retains its mandatory --max-snr argument."""
    monkeypatch.setattr(sys, "argv", ["delete_low_snr.py", "--execute"])
    with (
        patch.object(snr, "run") as run,
        pytest.raises(SystemExit) as exc,
    ):
        delete_low_snr.main()
    assert exc.value.code == 2
    run.assert_not_called()


def test_delete_shim_dry_run_default(
    seeded_snr_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The old deletion name defaults to a preview and never prompts."""
    path, store = seeded_snr_store
    before = store.get_all_embeddings()
    monkeypatch.setattr(sys, "argv", [
        "delete_low_snr.py", "--path", str(path), "--max-snr", "5",
    ])
    with (
        patch.object(_store_ops, "make_backup") as backup,
        patch.object(builtins, "input") as confirmation,
    ):
        assert delete_low_snr.main() is None
    backup.assert_not_called()
    confirmation.assert_not_called()
    assert store.get_all_embeddings() == before
    assert "DRY RUN" in capsys.readouterr().out


@pytest.mark.parametrize(("answer", "code", "remaining"), [
    ("2", 1, {"low_3", "boundary_5", "mid_7", "high_12", "fm_record"}),
    ("1", 0, {"boundary_5", "mid_7", "high_12", "fm_record"}),
])
def test_delete_shim_execute_is_gated(
    seeded_snr_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
    answer: str, code: int, remaining: set[str],
) -> None:
    """The old execute flag backs up and requires the correct typed count."""
    path, store = seeded_snr_store
    before = set(store.get_all_embeddings()["ids"])

    def confirm(_prompt: str) -> str:
        """Require a backup and unchanged records at the confirmation gate."""
        backups = list(path.parent.glob(f"{path.name}.backup-*"))
        assert len(backups) == 1
        assert (backups[0] / "chroma.sqlite3").is_file()
        assert set(store.get_all_embeddings()["ids"]) == before
        return answer

    monkeypatch.setattr(builtins, "input", confirm)
    monkeypatch.setattr(sys, "argv", [
        "delete_low_snr.py", "--path", str(path), "--label", "ADS_B",
        "--max-snr", "5", "--execute",
    ])
    if code:
        with pytest.raises(SystemExit) as exc:
            delete_low_snr.main()
        assert exc.value.code == code
    else:
        assert delete_low_snr.main() is None
    assert set(store.get_all_embeddings()["ids"]) == remaining


def test_delete_shim_backup_failure_aborts(
    seeded_snr_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backup failure through the old name prevents prompts and deletion."""
    path, store = seeded_snr_store
    before = store.get_all_embeddings()
    monkeypatch.setattr(sys, "argv", [
        "delete_low_snr.py", "--path", str(path), "--max-snr", "5",
        "--execute",
    ])
    with (
        patch.object(
            _store_ops, "make_backup", side_effect=OSError("disk full"),
        ),
        patch.object(builtins, "input") as confirmation,
        pytest.raises(SystemExit) as exc,
    ):
        delete_low_snr.main()
    assert exc.value.code == 1
    confirmation.assert_not_called()
    assert store.get_all_embeddings() == before


def test_purge_shim_default_is_dry_run(
    seeded_snr_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The legacy noise tool keeps path and label flags and dry-run safety."""
    path, store = seeded_snr_store
    vector = [0.0] * len(EMBEDDING_FEATURES)
    vector[EMBEDDING_FEATURES.index("spectral_flatness")] = 1.0
    store.add({
        "id": "noise_candidate", "embedding": vector,
        "metadata": {"label": "AIS", "snr_db": 3.0},
    })
    before = store.get_all_embeddings()
    monkeypatch.setattr(sys, "argv", [
        "purge_noise_vectors.py", "--path", str(path), "--label", "AIS",
    ])
    with (
        patch.object(_store_ops, "make_backup") as backup,
        patch.object(builtins, "input") as confirmation,
    ):
        assert purge_noise_vectors.main() is None
    backup.assert_not_called()
    confirmation.assert_not_called()
    assert store.get_all_embeddings() == before
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "noise_candidate" in out
    assert "Matched 1 record(s)" in out


@pytest.mark.parametrize(("shim", "module", "argv", "expected", "notice"), [
    (
        inspect_snr, snr,
        ["inspect_snr.py", "--path", "custom", "--label", "AIS",
         "--max-snr", "5"],
        ("custom", "AIS", 5.0), "./mimir tool vectors snr",
    ),
    (
        delete_low_snr, snr,
        ["delete_low_snr.py", "--path", "custom", "--label", "AIS",
         "--max-snr", "5", "--execute"],
        ("custom", "AIS", 5.0, True), "./mimir tool vectors snr",
    ),
    (
        purge_noise_vectors, purge_noise,
        ["purge_noise_vectors.py", "--path", "custom", "--label", "AIS",
         "--execute"],
        ("custom", "AIS", True), "./mimir tool vectors purge-noise",
    ),
])
@pytest.mark.parametrize("code", [0, 1, 2])
def test_shim_flags_notices_and_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    shim: ModuleType, module: ModuleType, argv: list[str],
    expected: tuple, notice: str, code: int,
) -> None:
    """Shims keep flags, print one stderr notice and propagate run failures."""
    monkeypatch.setattr(sys, "argv", argv)
    with patch.object(module, "run", return_value=code) as run:
        if code:
            with pytest.raises(SystemExit) as exc:
                shim.main()
            assert exc.value.code == code
        else:
            assert shim.main() is None
    if shim is inspect_snr:
        run.assert_called_once_with(*expected, execute=False)
    else:
        run.assert_called_once_with(*expected)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert notice in captured.err


def test_vectors_has_no_hardware_tool_imports() -> None:
    """Every vectors module excludes SDR tools, scan and the console helper."""
    forbidden = {
        "capture", "diagnose", "calibrate_thresholds", "diagnose_threshold",
        "capture_to_vectorstore", "diagnose_pluto_gain",
        "diagnose_fingerprints",
        "compare_decode_rate", "scan", "_console",
    }
    sources = sorted((REPO_ROOT / "tools/vectors").glob("*.py"))
    assert sources
    for source in sources:
        tree = ast.parse(source.read_text(), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
                modules.extend(
                    f"{node.module or ''}.{alias.name}" for alias in node.names
                )
            else:
                continue
            for module in modules:
                assert forbidden.isdisjoint(module.split(".")), (
                    f"{source.name}:{node.lineno} imports {module}"
                )
