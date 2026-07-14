"""Shared helpers for destructive-vector-store tool tests.

Provides the ``seeded_snr_store`` fixture used by
``tests/tools/test_inspect_snr.py`` and
``tests/tools/test_delete_low_snr.py``. The fixture creates a temporary
filesystem-backed ``SignalStore`` with five seeded records across two labels:

- **ADS_B**: four records at SNR 3.0, 5.0, 7.0, and 12.0 dB.
- **FM**: one record at SNR 6.0 dB.

The 3.0 and 5.0 dB ADS-B records exercise the strict-less-than ``--max-snr``
boundary: a record exactly on the cut line (5.0 dB) is kept by both the
inspector and the deleter, while the sub-threshold record (3.0 dB, ID
``low_3``) is selected for preview and deletion. This mirrors the production
tool behaviour and anchors tests that depend on boundary-case semantics.
"""

from __future__ import annotations

import numpy as np
import pytest

from embeddings.store import SignalStore


def _seed_snr_store(path: str, label: str = "ADS_B") -> SignalStore:
    """Seed a temporary SignalStore with known SNR values.

    Creates four records for the requested label at 3.0, 5.0, 7.0, and 12.0 dB
    SNR, plus one record with a different label (``FM``). This set exercises the
    strict-less-than ``--max-snr`` boundary at 5.0 dB.
    """
    store = SignalStore(path=path)

    records = [
        {
            "id": "low_3",
            "embedding": np.zeros(7, dtype=np.float32).tolist(),
            "metadata": {
                "label": label,
                "snr_db": 3.0,
                "signal_threshold_db": 5.0,
                "peak_power_db": -40.0,
                "timestamp": "2026-07-14T00:00:00",
            },
        },
        {
            "id": "boundary_5",
            "embedding": np.zeros(7, dtype=np.float32).tolist(),
            "metadata": {
                "label": label,
                "snr_db": 5.0,
                "signal_threshold_db": 5.0,
                "peak_power_db": -38.0,
                "timestamp": "2026-07-14T00:00:00",
            },
        },
        {
            "id": "mid_7",
            "embedding": np.zeros(7, dtype=np.float32).tolist(),
            "metadata": {
                "label": label,
                "snr_db": 7.0,
                "signal_threshold_db": 5.0,
                "peak_power_db": -36.0,
                "timestamp": "2026-07-14T00:00:00",
            },
        },
        {
            "id": "high_12",
            "embedding": np.zeros(7, dtype=np.float32).tolist(),
            "metadata": {
                "label": label,
                "snr_db": 12.0,
                "signal_threshold_db": 5.0,
                "peak_power_db": -30.0,
                "timestamp": "2026-07-14T00:00:00",
            },
        },
        {
            "id": "fm_record",
            "embedding": np.zeros(7, dtype=np.float32).tolist(),
            "metadata": {
                "label": "FM",
                "snr_db": 6.0,
                "signal_threshold_db": 21.0,
                "peak_power_db": -40.0,
                "timestamp": "2026-07-14T00:00:00",
            },
        },
    ]
    store.add_batch(records)
    return store


@pytest.fixture
def seeded_snr_store(tmp_path):
    """Yield a seeded store and its filesystem path."""
    store = _seed_snr_store(str(tmp_path))
    return tmp_path, store
