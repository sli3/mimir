"""Share backup, typed confirmation and deletion for local maintenance."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from embeddings.store import SignalStore

MEMORY_STORE = ":memory:"
MEMORY_STORE_REFUSAL = (
    "Refusing to run against an in-memory store: "
    "nothing to back up or persist."
)
DELETE_CHUNK = 500


def make_backup(path: str) -> Path:
    """Copy the store to a timestamped sibling, raising OSError on failure."""
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"Store path does not exist: {src}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = src.with_name(f"{src.name}.backup-{stamp}")
    if dst.exists():
        raise FileExistsError(f"Backup target already exists: {dst}")
    shutil.copytree(src, dst)
    return dst


def confirm_count(n: int) -> bool:
    """Accept only the exact selected count after stripping whitespace."""
    answer = input(f"Type the number {n} to confirm (anything else aborts): ")
    return answer.strip() == str(n)


def delete_ids(
    store: SignalStore, ids: list[str], chunk: int = DELETE_CHUNK,
) -> int:
    """Delete selected ids in bounded chunks and return the deleted count."""
    # Standalone maintenance intentionally accesses the private collection,
    # following SignalStore.delete_by_label's get-then-delete-by-ids pattern.
    collection = store._collection  # noqa: SLF001 - intentional maintenance
    deleted = 0
    for start in range(0, len(ids), chunk):
        batch = ids[start:start + chunk]
        collection.delete(ids=batch)
        deleted += len(batch)
    return deleted
