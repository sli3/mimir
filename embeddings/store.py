"""
store.py — ChromaDB-backed vector store for the Mimir RF Scanner

Wraps ChromaDB to provide a simple interface for storing and querying
spectrum fingerprint embeddings.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging
import os

import chromadb

logger = logging.getLogger(__name__)

COLLECTION_NAME = "spectrum_signals"


class SignalStore:
    """Persistent or in-memory ChromaDB vector store for spectrum signals."""

    def __init__(self, path: str = "data/vectorstore") -> None:
        """
        Create or load a ChromaDB collection for spectrum embeddings.

        Args:
            path: Filesystem path for persistent storage. Use ":memory:"
                  for ephemeral in-memory storage (e.g., in tests).
        """
        if path == ":memory:":
            self._client = chromadb.Client()
        else:
            os.makedirs(path, exist_ok=True)
            self._client = chromadb.PersistentClient(path=path)

        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Mimir RF spectrum signal embeddings"},
        )
        logger.info("SignalStore initialised at %s (%d records)", path, self.count())

    def add(self, record: dict) -> None:
        """
        Insert one embedding record into the store.

        Args:
            record: Dict with keys 'id', 'embedding', and optionally 'metadata'.
        """
        self._collection.add(
            ids=[record["id"]],
            embeddings=[record["embedding"]],
            metadatas=[record.get("metadata") or None],
        )
        logger.debug("Added record %s to SignalStore", record["id"])

    def add_batch(self, records: list[dict]) -> None:
        """
        Bulk-insert multiple embedding records.

        Args:
            records: List of dicts, each with 'id', 'embedding', 'metadata'.
        """
        if not records:
            return
        ids = [r["id"] for r in records]
        embeddings = [r["embedding"] for r in records]
        metadatas = [r.get("metadata") or None for r in records]
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("Batch-added %d records to SignalStore", len(records))

    def query(self, vector: list[float], n_results: int = 5) -> dict:
        """
        Find the most similar stored embeddings to a query vector.

        Args:
            vector: Normalised embedding vector (same dimension as stored records).
            n_results: Maximum number of results to return.

        Returns:
            ChromaDB query result dict with 'ids', 'distances', 'metadatas'.
        """
        return self._collection.query(
            query_embeddings=[vector],
            n_results=n_results,
        )

    def count(self) -> int:
        """Return the total number of records in the store."""
        return self._collection.count()

    def delete_collection(self) -> None:
        """Delete the entire collection, removing all stored records."""
        self._client.delete_collection(name=COLLECTION_NAME)
        logger.info("SignalStore collection deleted")

    def list_labels(self) -> list[str]:
        """
        Return a sorted list of unique label strings from stored metadata.

        Scans all records and extracts unique values from the 'label' key
        in metadata. Records without a 'label' key are skipped.

        Returns:
            Sorted list of unique label strings.
        """
        all_records = self._collection.get(include=["metadatas"])
        labels = set()
        for meta in (all_records.get("metadatas") or []):
            if meta and "label" in meta:
                labels.add(str(meta["label"]))
        return sorted(labels)

    def get_all_embeddings(self) -> dict:
        """
        Return every stored record with its embedding vector and metadata.

        Uses ``collection.get(include=["embeddings", "metadatas"])`` so the
        returned dict contains the raw 7-dimensional vectors required by the
        vector-space visualisation endpoint.  An empty collection returns a
        dict with empty lists, never an exception.

        Returns:
            Dict with keys ``ids``, ``embeddings``, and ``metadatas``.
        """
        result = self._collection.get(include=["embeddings", "metadatas"])

        ids = result.get("ids")
        embeddings = result.get("embeddings")
        metadatas = result.get("metadatas")

        if embeddings is not None and hasattr(embeddings, "tolist"):
            embeddings = embeddings.tolist()

        return {
            "ids": ids if ids is not None else [],
            "embeddings": embeddings if embeddings is not None else [],
            "metadatas": metadatas if metadatas is not None else [],
        }
