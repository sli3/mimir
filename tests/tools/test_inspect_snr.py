"""tests/tools/test_inspect_snr.py
Read-only tests for ``tools/inspect_snr.py`` (Phase 33).

PURPOSE
───────
The SNR inspector prints a read-only report of the ChromaDB vector store —
label counts, SNR histogram with 2 dB buckets, and a preview of records whose
SNR is strictly below ``--max-snr``. It never mutates or deletes any records.

The strict-less-than selection semantics mirror those used by
``tools/delete_low_snr.py``: a record exactly on the cut line (e.g. 5.0 dB)
is kept and only reported as "Would select" but not actually selected. This
prevents accidental deletion of boundary records that sit precisely at the
threshold.

All tests use a temporary ChromaDB path; the production ``data/vectorstore``
directory is never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the repository root is on the path when this file is run in isolation.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.inspect_snr import main as inspect_snr_main


class TestInspectSnr:
    """Tests for the read-only SNR inspection tool.

    Covers rules C1 through C5 from Phase 33:

    - **C1** The script is read-only — ``store.count()`` is unchanged after
      invocation, and the output confirms "NO changes".
    - **C2** The ``--label`` filter restricts the report to records of that label.
    - **C3** The strict-less-than selection excludes boundary records exactly at
      ``--max-snr`` (e.g. a 5.0 dB record when ``--max-snr 5.0`` is set).
    - **C4** The histogram section is printed with 2 dB buckets.
    - **C5** A label matching no records prints a clear message and exits cleanly
      without raising.
    """

    def test_read_only_invariant(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Running inspect_snr.py must not add or remove any records."""
        path, store = seeded_snr_store
        count_before = store.count()
        assert count_before > 0

        monkeypatch.setattr(
            sys,
            "argv",
            ["inspect_snr.py", "--path", str(path), "--max-snr", "5.0"],
        )
        inspect_snr_main()

        captured = capsys.readouterr()
        assert store.count() == count_before
        assert "NO changes" in captured.out or "This script made NO changes" in captured.out

    def test_label_filter(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """``--label`` restricts the report to the chosen label."""
        path, _store = seeded_snr_store

        monkeypatch.setattr(
            sys,
            "argv",
            ["inspect_snr.py", "--path", str(path), "--label", "ADS_B"],
        )
        inspect_snr_main()

        out = capsys.readouterr().out
        assert "=== ADS_B records: 4 ===" in out
        assert "=== FM records:" not in out

    def test_max_snr_strictly_less_than(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """A record exactly on the cut line is kept; only sub-cut rows are previewed."""
        path, _store = seeded_snr_store

        monkeypatch.setattr(
            sys,
            "argv",
            ["inspect_snr.py", "--path", str(path), "--label", "ADS_B", "--max-snr", "5.0"],
        )
        inspect_snr_main()

        out = capsys.readouterr().out
        assert "=== PREVIEW: --max-snr 5.00 (strictly below) ===" in out
        assert "Would select 1" in out
        assert "low_3" in out
        assert "boundary_5" not in out

    def test_histogram_output(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """The histogram section is printed with 2 dB buckets."""
        path, _store = seeded_snr_store

        monkeypatch.setattr(
            sys,
            "argv",
            ["inspect_snr.py", "--path", str(path), "--label", "ADS_B"],
        )
        inspect_snr_main()

        out = capsys.readouterr().out
        assert "SNR histogram" in out
        assert "2 dB buckets" in out

    def test_empty_label_is_reported_cleanly(
        self,
        seeded_snr_store,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """A label matching no records prints a clear message and exits cleanly."""
        path, _store = seeded_snr_store

        monkeypatch.setattr(
            sys,
            "argv",
            ["inspect_snr.py", "--path", str(path), "--label", "NONEXISTENT"],
        )
        inspect_snr_main()  # must not raise

        out = capsys.readouterr().out
        assert "No records found with label 'NONEXISTENT'" in out
