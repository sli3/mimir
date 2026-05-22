"""
embeddings — Vector embedding and similarity search for the Mimir RF Scanner

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

from embeddings.embedder import SpectrumEmbedder
from embeddings.store import SignalStore

__all__ = ["SpectrumEmbedder", "SignalStore"]
