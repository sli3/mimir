"""Check SNR reports and guarded deletion using temporary vector stores."""

from __future__ import annotations

import builtins
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Support isolated execution while tools remains a namespace package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from embeddings.store import SignalStore
from tools.vectors import _store_ops, cli, snr


def test_read_only_invariant(
    seeded_snr_store: tuple[Path, SignalStore],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Previewing a cut preserves every stored record and embedding."""
    path, store = seeded_snr_store
    before = store.get_all_embeddings()
    with (
        patch.object(_store_ops, "make_backup") as backup,
        patch.object(builtins, "input") as confirmation,
    ):
        assert cli.main(["snr", "--path", str(path), "--max-snr", "5"]) == 0
    assert store.get_all_embeddings() == before
    backup.assert_not_called()
    confirmation.assert_not_called()
    assert "NO changes" in capsys.readouterr().out


def test_label_filter(
    seeded_snr_store: tuple[Path, SignalStore],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The chosen label restricts the inspection and deletion preview."""
    path, _ = seeded_snr_store
    assert cli.main([
        "snr", "--path", str(path), "--label", "FM", "--max-snr", "8",
    ]) == 0
    out = capsys.readouterr().out
    assert "=== FM records: 1 ===" in out
    assert "=== ADS_B records:" not in out
    assert "fm_record" in out
    assert "low_3" not in out


def test_max_snr_strictly_less_than(
    seeded_snr_store: tuple[Path, SignalStore],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A cut of 5.0 selects low_3 and keeps the exact boundary record."""
    path, store = seeded_snr_store
    assert cli.main(["snr", "--path", str(path), "--max-snr", "5.0"]) == 0
    out = capsys.readouterr().out
    assert "=== PREVIEW: --max-snr 5.00 (strictly below) ===" in out
    assert "Would select 1 of 4 'ADS_B' record(s)" in out
    assert "low_3" in out
    assert "boundary_5" not in out
    assert "boundary_5" in store.get_all_embeddings()["ids"]


def test_histogram_and_inspection_output(
    seeded_snr_store: tuple[Path, SignalStore],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Inspection retains totals, 2 dB buckets, thresholds and timestamps."""
    path, _ = seeded_snr_store
    assert cli.main(["snr", "--path", str(path)]) == 0
    out = capsys.readouterr().out
    for expected in (
        f"Store: {path}", "Total records in collection: 5",
        "Labels present: ADS_B, FM", "=== ADS_B records: 4 ===",
        "SNR min / median / max: 3.00 / 7.00 / 12.00 dB",
        "SNR histogram (2 dB buckets):", "[  2,   4) dB     1  #",
        "[  4,   6) dB     1  #", "[  6,   8) dB     1  #",
        "[ 12,  14) dB     1  #",
        "Records below their own stored signal_threshold_db: 1 of 4",
        "their SNR range: 3.00 .. 3.00 dB",
        "Timestamp range: 2026-07-14T00:00:00  ..  2026-07-14T00:00:00",
        "Lowest 15 by SNR", "snr_db", "thresh", "peak_db",
    ):
        assert expected in out


def test_empty_label_is_reported_cleanly(
    seeded_snr_store: tuple[Path, SignalStore],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty label reports clearly and never enters deletion gates."""
    path, store = seeded_snr_store
    before = store.get_all_embeddings()
    with (
        patch.object(_store_ops, "make_backup") as backup,
        patch.object(builtins, "input") as confirmation,
    ):
        assert cli.main([
            "snr", "--path", str(path), "--label", "NONEXISTENT",
            "--max-snr", "5", "--execute",
        ]) == 0
    backup.assert_not_called()
    confirmation.assert_not_called()
    assert store.get_all_embeddings() == before
    out = capsys.readouterr().out
    assert "No records found with label 'NONEXISTENT'" in out


def test_dry_run_is_default(
    seeded_snr_store: tuple[Path, SignalStore],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A default dry run preserves records and shows the delete command."""
    path, store = seeded_snr_store
    assert cli.main(["snr", "--path", str(path), "--max-snr", "5"]) == 0
    assert store.count() == 5
    assert list(path.parent.glob(f"{path.name}.backup-*")) == []
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert f"./mimir tool vectors snr --path {path}" in out
    assert "--label ADS_B --max-snr 5.0 --execute" in out


def test_max_snr_selection_matches_preview(
    seeded_snr_store: tuple[Path, SignalStore],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The deletion selection uses the same strict cut as its preview."""
    path, _ = seeded_snr_store
    assert snr.run(str(path), "ADS_B", 5.0, False) == 0
    out = capsys.readouterr().out
    assert "Matched 1 record(s)" in out
    assert "low_3" in out
    assert "boundary_5" not in out


def test_backup_created_before_delete(
    seeded_snr_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The full backup and original records exist when confirmation begins."""
    path, store = seeded_snr_store
    before = store.get_all_embeddings()

    def confirm(prompt: str) -> str:
        """Check the backup and untouched records before confirmation."""
        backups = list(path.parent.glob(f"{path.name}.backup-*"))
        assert len(backups) == 1
        assert (backups[0] / "chroma.sqlite3").is_file()
        assert store.get_all_embeddings() == before
        assert prompt == (
            "Type the number 1 to confirm (anything else aborts): "
        )
        return " 1 "

    monkeypatch.setattr(builtins, "input", confirm)
    assert snr.run(str(path), "ADS_B", 5.0, True) == 0
    assert SignalStore(str(path)).count() == 4


def test_typed_confirmation_gate_blocks_deletion(
    seeded_snr_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An incorrect count preserves records and the untouched backup."""
    path, store = seeded_snr_store
    before = store.get_all_embeddings()
    monkeypatch.setattr(builtins, "input", lambda _: "2")
    assert snr.run(str(path), "ADS_B", 5.0, True) == 1
    assert store.get_all_embeddings() == before
    assert len(list(path.parent.glob(f"{path.name}.backup-*"))) == 1
    out = capsys.readouterr().out
    assert "Confirmation did not match" in out
    assert "backup at" in out and "untouched" in out


@pytest.mark.parametrize("error", [
    OSError("disk full"), FileNotFoundError("missing store"),
    FileExistsError("backup exists"), shutil.Error("copy failed"),
])
def test_backup_failure_aborts_without_deleting(
    seeded_snr_store: tuple[Path, SignalStore],
    capsys: pytest.CaptureFixture[str],
    error: OSError,
) -> None:
    """Filesystem backup failures abort without prompting or deleting."""
    path, store = seeded_snr_store
    before = store.get_all_embeddings()
    with (
        patch.object(_store_ops, "make_backup", side_effect=error),
        patch.object(builtins, "input") as confirmation,
        patch.object(_store_ops, "delete_ids") as deletion,
    ):
        assert snr.run(str(path), "ADS_B", 5.0, True) == 1
    confirmation.assert_not_called()
    deletion.assert_not_called()
    assert store.get_all_embeddings() == before
    assert "BACKUP FAILED" in capsys.readouterr().out


def test_happy_path_deletes_only_selected_records(
    seeded_snr_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Correct confirmation removes low_3 and reports recovery details."""
    path, _ = seeded_snr_store
    monkeypatch.setattr(builtins, "input", lambda _: "1")
    assert cli.main([
        "snr", "--path", str(path), "--max-snr", "5", "--execute",
    ]) == 0
    after = SignalStore(str(path))
    assert set(after.get_all_embeddings()["ids"]) == {
        "boundary_5", "mid_7", "high_12", "fm_record",
    }
    assert after.count() == 4
    backups = list(path.parent.glob(f"{path.name}.backup-*"))
    assert len(backups) == 1
    out = capsys.readouterr().out
    assert "Deleted 1 record(s)" in out
    assert "Collection now holds 4 record(s) (was 5)" in out
    assert str(backups[0]) in out
    assert "To roll back" in out


def test_execute_requires_max_snr_before_opening() -> None:
    """Execution without a deliberate cut is an argparse error before I/O."""
    with (
        patch.object(snr, "SignalStore") as store,
        pytest.raises(SystemExit) as exc,
    ):
        cli.main(["snr", "--execute"])
    assert exc.value.code == 2
    store.assert_not_called()


def test_memory_store_is_refused_before_opening(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Execution refuses an in-memory store before opening or prompting."""
    with (
        patch.object(snr, "SignalStore") as store,
        patch.object(_store_ops, "make_backup") as backup,
        patch.object(builtins, "input") as confirmation,
    ):
        assert cli.main([
            "snr", "--path", ":memory:", "--max-snr", "5", "--execute",
        ]) == 1
    store.assert_not_called()
    backup.assert_not_called()
    confirmation.assert_not_called()
    assert "in-memory store" in capsys.readouterr().out


def test_missing_snr_is_never_selected(
    seeded_snr_store: tuple[Path, SignalStore],
) -> None:
    """Records without SNR cannot enter a cut selection."""
    _, store = seeded_snr_store
    dump = {
        "ids": ["missing_snr", "missing_metadata", "low_3"],
        "metadatas": [
            {"label": "ADS_B"}, None, {"label": "ADS_B", "snr_db": 3},
        ],
    }
    with patch.object(store, "get_all_embeddings", return_value=dump):
        rows = snr._read_rows(store, "ADS_B")
        assert [row["id"] for row in rows] == ["low_3"]


def test_no_matching_cut_skips_backup_and_confirmation(
    seeded_snr_store: tuple[Path, SignalStore],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty strict-cut selection succeeds without deletion gates."""
    path, store = seeded_snr_store
    with (
        patch.object(_store_ops, "make_backup") as backup,
        patch.object(builtins, "input") as confirmation,
    ):
        assert snr.run(str(path), "ADS_B", 3.0, True) == 0
    backup.assert_not_called()
    confirmation.assert_not_called()
    assert store.count() == 5
    assert "Nothing matches the cut" in capsys.readouterr().out


def test_backup_copies_to_sibling_and_refuses_collision(
    tmp_path: Path,
) -> None:
    """Backups copy source files once and preserve an existing target."""
    source = tmp_path / "store"
    source.mkdir()
    (source / "record").write_text("original")
    with patch.object(_store_ops, "datetime") as clock:
        clock.now.return_value.strftime.return_value = "20261127-124947"
        backup = _store_ops.make_backup(str(source))
        assert backup == source.with_name("store.backup-20261127-124947")
        assert (backup / "record").read_text() == "original"
        with pytest.raises(FileExistsError):
            _store_ops.make_backup(str(source))
    assert (backup / "record").read_text() == "original"


def test_backup_refuses_missing_source(tmp_path: Path) -> None:
    """A missing store raises before attempting a directory copy."""
    with (
        patch.object(_store_ops.shutil, "copytree") as copy,
        pytest.raises(FileNotFoundError),
    ):
        _store_ops.make_backup(str(tmp_path / "missing"))
    copy.assert_not_called()
