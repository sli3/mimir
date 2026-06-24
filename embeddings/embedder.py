"""
embedder.py — Spectrum fingerprint vector embedding for the Mimir RF Scanner

Converts spectral fingerprints (from fingerprint_spectrum) into fixed-length
numerical vectors suitable for similarity search in ChromaDB.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import hashlib
import logging

logger = logging.getLogger(__name__)

# The 7 features extracted from a fingerprint for embedding.
# center_freq_hz is excluded — it is capture metadata, not a fingerprint feature.
EMBEDDING_FEATURES = [
    "peak_freq_hz",
    "peak_power_db",
    "noise_floor_db",
    "snr_db",
    "bandwidth_hz",
    "occupied_bins",
    "spectral_flatness",
]

# Normalisation ranges for each feature [min, max].
# These are practical bounds for RF spectrum analysis.
NORMALISATION_RANGES = {
    "peak_freq_hz": [0.0, 6_000_000_000.0],       # 0 – 6 GHz (HackRF range)
    "peak_power_db": [-100.0, 0.0],                # dBFS range
    "noise_floor_db": [-100.0, 0.0],               # dBFS range
    "snr_db": [0.0, 100.0],                        # 0 – 100 dB
    "bandwidth_hz": [0.0, 20_000_000.0],             # 0 – 20 MHz (max HackRF BW)
    "occupied_bins": [0.0, 2048.0],                  # 0 – DEFAULT_NFFT
    "spectral_flatness": [0.0, 1.0],                 # 0 – 1 (Wiener entropy)
}

VECTOR_DIM = len(EMBEDDING_FEATURES)


class SpectrumEmbedder:
    """Converts spectral fingerprints into normalised embedding vectors."""

    def __init__(self) -> None:
        self.feature_names = list(EMBEDDING_FEATURES)
        self.ranges = dict(NORMALISATION_RANGES)
        self.dim = VECTOR_DIM

    def embed(self, fingerprint: dict) -> list[float]:
        """
        Convert a fingerprint dict into a normalised embedding vector.

        Each feature is min-max normalised to [0, 1] using the predefined
        ranges in NORMALISATION_RANGES. Values outside the range are clamped.

        Args:
            fingerprint: Dict from fingerprint_spectrum() containing at least
                         the 7 keys listed in EMBEDDING_FEATURES.

        Returns:
            List of 7 floats, each in [0, 1].
        """
        vector = []
        for feature in self.feature_names:
            value = float(fingerprint[feature])
            lo, hi = self.ranges[feature]
            normalised = max(0.0, min(1.0, (value - lo) / (hi - lo)))
            vector.append(normalised)
        return vector

    def make_id(self, fingerprint: dict, metadata: dict | None = None) -> str:
        """
        Generate a deterministic record ID from fingerprint + metadata.

        Uses SHA-256 of the normalised vector plus optional metadata fields
        to create a unique, reproducible identifier.

        Args:
            fingerprint: Dict from fingerprint_spectrum().
            metadata: Optional capture metadata (e.g., timestamp, source).

        Returns:
            Hex string suitable as a ChromaDB document ID.
        """
        vector = self.embed(fingerprint)
        content = f"{vector}"
        if metadata:
            content += f"|{sorted(metadata.items())}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def embed_fingerprint(
        self,
        fingerprint: dict,
        metadata: dict | None = None,
    ) -> dict:
        """
        Build a ChromaDB-compatible record from a fingerprint.

        Args:
            fingerprint: Dict from fingerprint_spectrum().
            metadata: Optional capture metadata to store alongside the embedding.

        Returns:
            Dict with keys: id, embedding, metadata.
        """
        vector = self.embed(fingerprint)
        record_id = self.make_id(fingerprint, metadata)
        return {
            "id": record_id,
            "embedding": vector,
            "metadata": metadata or {},
        }
