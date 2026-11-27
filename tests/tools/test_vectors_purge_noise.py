"""Check vectors purge-noise with temporary stores and mocked input."""

from __future__ import annotations

import builtins
import sys
from functools import partial
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Support isolated execution while tools remains a namespace package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from embeddings.embedder import EMBEDDING_FEATURES, SpectrumEmbedder
from embeddings.store import SignalStore
from tools.vectors import _store_ops, cli, purge_noise


@pytest.fixture
def noise_store(tmp_path: Path) -> tuple[Path, SignalStore]:
    """Seed a temporary store with boundaries, signals and noise references."""
    store = SignalStore(str(tmp_path))
    embedder = SpectrumEmbedder()
    records = []
    for rec_id, label, bins, flatness in [
        ("zero_bins", "ADS_B", 0, 0.95),
        ("boundary", "ADS_B", 1, 0.9),
        ("below_flatness", "ADS_B", 1, 0.8999),
        ("two_bins", "ADS_B", 2, 0.95),
        ("tonal", "ADS_B", 1, 0.2),
        ("other_label", "ISM_LoRa", 1, 0.95),
        ("reference_noise", "noise", 0, 0.95),
        ("reference_floor", "NOISE_FLOOR", 1, 0.95),
        ("reference_mixed", "NoIsE", 0, 0.95),
    ]:
        fingerprint = {
            "peak_freq_hz": 0.0, "peak_power_db": -40.0,
            "noise_floor_db": -60.0, "snr_db": 20.0, "bandwidth_hz": 0.0,
            "occupied_bins": bins, "spectral_flatness": flatness,
        }
        records.append({
            "id": rec_id,
            "embedding": np.asarray(
                embedder.embed(fingerprint), dtype=np.float32,
            ).tolist(),
            "metadata": {"label": label, "snr_db": 20.0},
        })
    store.add_batch(records)
    return tmp_path, store


@pytest.mark.parametrize("as_array", [False, True])
def test_selection_decodes_boundaries_from_embeddings(
    noise_store: tuple[Path, SignalStore], as_array: bool,
) -> None:
    """Lists and numpy arrays preserve the one-bin and 0.9 boundaries."""
    _, store = noise_store
    dump = store.get_all_embeddings()
    if as_array:
        dump["embeddings"] = np.asarray(dump["embeddings"], dtype=np.float32)
    with patch.object(store, "get_all_embeddings", return_value=dump):
        rows, excluded = purge_noise._select_rows(store)

    selected = {row["id"]: row for row in rows}
    assert set(selected) == {"zero_bins", "boundary", "other_label"}
    assert selected["boundary"]["occupied_bins"] == 1
    assert selected["boundary"]["spectral_flatness"] == 0.9
    assert selected["zero_bins"]["occupied_bins"] == 0
    assert excluded == 3


def test_label_filter_selects_only_requested_label(
    noise_store: tuple[Path, SignalStore],
) -> None:
    """The optional label filter restricts the decoded noise selection."""
    _, store = noise_store
    rows, excluded = purge_noise._select_rows(store, "ADS_B")
    assert {row["id"] for row in rows} == {"zero_bins", "boundary"}
    assert excluded == 0


@pytest.mark.parametrize("label", ["noise", "NOISE_FLOOR", "NoIsE"])
def test_label_filter_cannot_override_reference_exclusion(
    noise_store: tuple[Path, SignalStore], label: str,
) -> None:
    """Reference labels are protected case-insensitively even with --label."""
    _, store = noise_store
    rows, excluded = purge_noise._select_rows(store, label)
    assert rows == []
    assert excluded == 1


@pytest.mark.parametrize(
    "embedding", [None, [], [0.0] * (len(EMBEDDING_FEATURES) - 1)],
)
def test_missing_or_short_embedding_is_skipped(
    noise_store: tuple[Path, SignalStore], embedding: list[float] | None,
) -> None:
    """Skip incomplete legacy vectors without selecting them or raising."""
    _, store = noise_store
    dump = {
        "ids": ["incomplete"],
        "metadatas": [{"label": "ADS_B"}],
        "embeddings": [embedding],
    }
    with patch.object(store, "get_all_embeddings", return_value=dump):
        assert purge_noise._select_rows(store) == ([], 0)


def test_absent_embedding_array_is_skipped(
    noise_store: tuple[Path, SignalStore],
) -> None:
    """A missing embedding field cannot select a record for deletion."""
    _, store = noise_store
    dump = {"ids": ["missing"], "metadatas": [{"label": "ADS_B"}]}
    with patch.object(store, "get_all_embeddings", return_value=dump):
        assert purge_noise._select_rows(store) == ([], 0)


def test_dry_run_preserves_store_and_prints_selection(
    noise_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """The package default prints decoded fields and preserves every record."""
    path, store = noise_store
    before = store.get_all_embeddings()
    monkeypatch.setattr(sys, "argv", [
        "vectors", "purge-noise", "--path", str(path),
    ])
    with (
        patch.object(_store_ops, "make_backup") as backup,
        patch.object(builtins, "input") as confirmation,
    ):
        assert cli.main() == 0
    assert store.get_all_embeddings() == before
    backup.assert_not_called()
    confirmation.assert_not_called()
    assert list(path.parent.glob(f"{path.name}.backup-*")) == []
    output = capsys.readouterr().out
    assert "DRY RUN" in output
    assert "Matched 3 record(s)" in output
    assert "Excluded 3 record(s) as reference labels" in output
    for value in (
        "boundary", "ADS_B", "bins", "flatness", "snr_db", "0.900000",
    ):
        assert value in output


def test_execute_backs_up_before_confirming_and_deletes_selected_chunks(
    noise_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """Matching confirmation deletes selected ids through shared chunking."""
    path, store = noise_store
    before_ids = set(store.get_all_embeddings()["ids"])

    def confirm(_prompt: str) -> str:
        """Verify the backup and original records exist at confirmation."""
        backups = list(path.parent.glob(f"{path.name}.backup-*"))
        assert len(backups) == 1
        assert (backups[0] / "chroma.sqlite3").is_file()
        assert set(store.get_all_embeddings()["ids"]) == before_ids
        return "3"

    monkeypatch.setattr(builtins, "input", confirm)
    monkeypatch.setattr(sys, "argv", [
        "vectors", "purge-noise", "--path", str(path), "--execute",
    ])
    monkeypatch.setattr(
        _store_ops, "delete_ids", partial(_store_ops.delete_ids, chunk=1),
    )
    collection = MagicMock(wraps=store._collection)
    store._collection = collection
    with patch.object(purge_noise, "SignalStore", return_value=store):
        assert cli.main() == 0

    assert set(store.get_all_embeddings()["ids"]) == (
        before_ids - {"zero_bins", "boundary", "other_label"}
    )
    assert collection.delete.call_count == 3
    assert all(
        len(call.kwargs["ids"]) == 1
        for call in collection.delete.call_args_list
    )
    assert len(list(path.parent.glob(f"{path.name}.backup-*"))) == 1
    assert "Deleted 3 record(s)" in capsys.readouterr().out


def test_wrong_confirmation_preserves_every_record(
    noise_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """A mismatched count returns failure with records and backup preserved."""
    path, store = noise_store
    before = store.get_all_embeddings()
    monkeypatch.setattr(builtins, "input", lambda _prompt: "2")
    monkeypatch.setattr(sys, "argv", [
        "vectors", "purge-noise", "--path", str(path), "--execute",
    ])
    assert cli.main() == 1
    assert store.get_all_embeddings() == before
    assert len(list(path.parent.glob(f"{path.name}.backup-*"))) == 1
    assert "Confirmation did not match" in capsys.readouterr().out


def test_backup_failure_aborts_before_confirmation_or_deletion(
    noise_store: tuple[Path, SignalStore],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """A filesystem backup failure returns before prompting or deleting."""
    path, store = noise_store
    before = store.get_all_embeddings()
    monkeypatch.setattr(sys, "argv", [
        "vectors", "purge-noise", "--path", str(path), "--execute",
    ])
    with (
        patch.object(
            _store_ops, "make_backup",
            side_effect=OSError("disk full"),
        ),
        patch.object(builtins, "input") as confirmation,
    ):
        assert cli.main() == 1
    confirmation.assert_not_called()
    assert store.get_all_embeddings() == before
    assert "BACKUP FAILED" in capsys.readouterr().out


def test_memory_store_is_refused_before_opening(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    """Execution rejects in-memory paths before constructing a store."""
    monkeypatch.setattr(sys, "argv", [
        "vectors", "purge-noise", "--path", ":memory:", "--execute",
    ])
    with (
        patch.object(purge_noise, "SignalStore") as store,
    ):
        assert cli.main() == 1
    store.assert_not_called()
    assert "in-memory store" in capsys.readouterr().out
