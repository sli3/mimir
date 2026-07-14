"""tests/tools/test_delete_low_snr.py
Safety tests for ``tools/delete_low_snr.py`` (Phase 33).

PURPOSE
───────
The low-SNR deletion tool is the destructive counterpart to
``tools/inspect_snr.py`` — it removes records whose SNR falls below
``--max-snr``. Phase 33 introduced four safety gates to prevent accidental
destruction of valid records and noise pollution in the vector store:

1. **Dry-run default** — without ``--execute``, the tool only previews matches
   and makes no changes. This is the safe default for an operator running a
   destructive command.
2. **Backup before delete** — ``--execute`` creates a timestamped copy of the
   store before any deletion, so a single bad run can be rolled back.
3. **Typed confirmation gate** — the tool reads the expected match count from
   ``input()`` and aborts if the operator's answer does not match. This blocks
   automated or misconfigured invocations.
4. **In-memory backup failure abort** — if the backup step raises an exception
   (e.g. disk full), the tool aborts before deleting anything, leaving the
   store intact.

All tests use a temporary ChromaDB path; the production ``data/vectorstore``
directory is never touched. Backups, confirmation prompts, and backup failures
are all driven through injected I/O so the tests are deterministic.
"""

from __future__ import annotations

import builtins
import sys
from pathlib import Path

import pytest

# Ensure the repository root is on the path when this file is run in isolation.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from embeddings.store import SignalStore
from tools.delete_low_snr import main as delete_low_snr_main


class TestDeleteLowSnr:
    """Tests for the guarded low-SNR deletion tool.

    Covers rules D1 through D6 from Phase 33:

    - **D1** Dry-run default — without ``--execute``, no records are deleted and
      output contains "DRY RUN".
    - **D2** Strict-less-than selection matches the ``inspect_snr.py`` preview —
      a record exactly at ``--max-snr 5.0`` (ID ``boundary_5``) is excluded from
      the matched set.
    - **D3** Backup-before-delete — ``--execute`` creates a timestamped backup
      before any deletion, and the store count reflects only the sub-threshold
      records being removed.
    - **D4** Typed confirmation gate — typing the wrong count aborts with
      SystemExit and leaves the store intact.
    - **D5** Backup failure aborts without deleting anything.
    - **D6** Happy path deletes exactly the selected low-SNR record(s) and
      reports "Deleted N".
    """

    def test_dry_run_is_default(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Without ``--execute`` the tool is a dry run and makes no changes."""
        path, store = seeded_snr_store
        count_before = store.count()

        monkeypatch.setattr(
            sys,
            "argv",
            ["delete_low_snr.py", "--path", str(path), "--label", "ADS_B", "--max-snr", "5.0"],
        )
        delete_low_snr_main()

        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
        assert store.count() == count_before

    def test_max_snr_selection_matches_inspect_snr(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Strict-less-than selection matches the inspect_snr.py preview."""
        path, _store = seeded_snr_store

        monkeypatch.setattr(
            sys,
            "argv",
            ["delete_low_snr.py", "--path", str(path), "--label", "ADS_B", "--max-snr", "5.0"],
        )
        delete_low_snr_main()

        out = capsys.readouterr().out
        assert "Matched 1" in out
        assert "boundary_5" not in out

    def test_backup_created_before_delete(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """``--execute`` creates a timestamped backup before deleting anything."""
        path, _store = seeded_snr_store
        monkeypatch.setattr(builtins, "input", lambda _: "1")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "delete_low_snr.py",
                "--path",
                str(path),
                "--label",
                "ADS_B",
                "--max-snr",
                "5.0",
                "--execute",
            ],
        )
        delete_low_snr_main()

        # Refresh the store from disk to see the post-delete state.
        store_after = SignalStore(str(path))
        assert store_after.count() == 4  # 5 seeded records minus 1 deleted

        backup_dirs = list(path.parent.glob(f"{path.name}.backup-*"))
        assert len(backup_dirs) == 1, "A single timestamped backup should exist."

    def test_typed_confirmation_gate_blocks_deletion(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Typing the wrong count aborts the deletion and leaves the store intact."""
        path, store = seeded_snr_store
        count_before = store.count()

        monkeypatch.setattr(builtins, "input", lambda _: "2")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "delete_low_snr.py",
                "--path",
                str(path),
                "--label",
                "ADS_B",
                "--max-snr",
                "5.0",
                "--execute",
            ],
        )
        with pytest.raises(SystemExit):
            delete_low_snr_main()

        captured = capsys.readouterr()
        assert "Confirmation did not match" in captured.out
        assert store.count() == count_before

    def test_backup_failure_aborts_without_deleting(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """If the backup fails, the tool aborts and deletes nothing."""
        path, store = seeded_snr_store
        count_before = store.count()

        def _failing_backup(_store_path: str) -> Path:
            raise OSError("disk full")

        monkeypatch.setattr(builtins, "input", lambda _: "1")
        monkeypatch.setattr("tools.delete_low_snr._make_backup", _failing_backup)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "delete_low_snr.py",
                "--path",
                str(path),
                "--label",
                "ADS_B",
                "--max-snr",
                "5.0",
                "--execute",
            ],
        )
        with pytest.raises(SystemExit):
            delete_low_snr_main()

        captured = capsys.readouterr()
        assert "BACKUP FAILED" in captured.out
        assert store.count() == count_before

    def test_happy_path_deletes_only_selected_records(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Correct confirmation deletes exactly the selected low-SNR record."""
        path, _store = seeded_snr_store

        monkeypatch.setattr(builtins, "input", lambda _: "1")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "delete_low_snr.py",
                "--path",
                str(path),
                "--label",
                "ADS_B",
                "--max-snr",
                "5.0",
                "--execute",
            ],
        )
        delete_low_snr_main()

        store_after = SignalStore(str(path))
        ids_after = set(store_after.get_all_embeddings()["ids"])
        assert "low_3" not in ids_after, "The sub-threshold record should be deleted."
        assert {"boundary_5", "mid_7", "high_12", "fm_record"}.issubset(ids_after)
        assert store_after.count() == 4

        backup_dirs = list(path.parent.glob(f"{path.name}.backup-*"))
        assert len(backup_dirs) == 1

        captured = capsys.readouterr()
        assert "Deleted 1" in captured.out
